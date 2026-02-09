"""
AI对话核心逻辑
"""
import json
from openai import OpenAI
from memory.core import MemorySystem
from memory.tools import create_memory_tools
from config import API_KEY, BASE_URL, JUDGE_MODEL, ANSWER_MODEL, TIMEZONE
from time_utils import get_current_time_info
from web_search import web_search

class AIChat:
    """AI对话处理器"""
    
    def __init__(self, memory_system, searxng_url, max_fetch=2):
        """
        初始化AI对话处理器
        
        Args:
            memory_system: 记忆系统实例
            searxng_url: SearXNG服务器地址
            max_fetch: 最大爬取网页数量
        """
        self.memory = memory_system
        self.searxng_url = searxng_url
        self.max_fetch = max_fetch
        self.client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
        self.conversation_history = []
        
    def _build_system_prompt(self, time_text, long_term_memory):
        """构建系统提示"""
        return f"""你是一个智能助手，拥有记忆和联网能力。\n{time_text}\n【长期记忆】\n{long_term_memory}\n【工作流程】\n1. 如果用户问当前日期/时间，直接用上述信息回答，无需搜索\n2. 如果用户询问历史信息、偏好、过往对话，调用 memory_search 搜索记忆\n3. 如果用户提供重要信息（个人信息、偏好、决策），调用 memory_save 保存\n4. 如果需要实时信息（新闻、价格、天气），调用 web_search\n5. 如果是通用知识问题，直接回答\n【重要】保持上下文连贯性。回答时要引用来源。"""
    
    def _extract_important_info(self, question, answer):
        """自动提取重要信息到长期记忆"""
        try:
            extract_prompt = f"""分析对话，提取值得长期记忆的重要信息。\n【用户问题】\n{question}\n【AI回答】\n{answer}\n**判断规则**：\n需要记忆的信息类型：\n1. 用户自我介绍（姓名、身份、职业、角色设定）\n2. 用户偏好（喜好、厌恶、习惯、兴趣爱好）\n3. 重要关系（师徒关系、家人朋友、宠物角色等）\n4. 关键事实（决策、计划、重要信息）\n无需记忆的信息类型：\n- 普通问候、闲聊\n- 一次性问题\n- 临时指令\n**输出格式**：\n如果有重要信息，输出一句话概括（不包含时间戳）！"""

            extraction_response = self.client.chat.completions.create(
                model=JUDGE_MODEL,
                messages=[{"role": "user", "content": extract_prompt}],
                temperature=0.3,
                max_tokens=200
            )
            
            extracted = extraction_response.choices[0].message.content.strip()
            
            # 清理可能的格式
            extracted = extracted.replace("**", "").replace("- ", "").replace("`", "").strip()
            
            # 如果提取到重要信息，保存到长期记忆
            if extracted and extracted.upper() != "NONE" and len(extracted) > 5:
                print(f"📌 检测到重要信息，自动保存到长期记忆...")
                self.memory.save_memory(extracted, memory_type="long")
        
        except Exception as e:
            print(f"⚠️  自动提取失败: {e}")
    
    def ask(self, question, history=None, tools=None):
        """
        处理用户问题
        
        Args:
            question: 用户问题
            history: 对话历史 [{"role": "user", "content": "..."}, ...]
            tools: 可用工具列表
        
        Returns:
            str: AI回答
        """
        if history is None:
            history = []
        if tools is None:
            tools = []
        
        # 获取当前时间
        time_info, time_text = get_current_time_info(TIMEZONE)
        
        print(f"\n⏰ 系统时间：{time_info['date']} {time_info['weekday']} {time_info['time']}\n")

        # 获取长期记忆
        long_term_memory = self.memory.get_long_term_memory()

        # 构建系统提示
        system_prompt = self._build_system_prompt(time_text, long_term_memory)

        # 构建完整消息列表（加入历史）
        messages = [{"role": "system", "content": system_prompt}]

        # 添加对话历史
        messages.extend(history)

        # 添加当前问题
        messages.append({"role": "user", "content": question})
        
        print(f"🤖 阶段1: 用 {JUDGE_MODEL} 判断是否需要搜索...\n")
        
        try:
            # 第一阶段：用快速模型判断是否需要搜索
            response = self.client.chat.completions.create(
                model=JUDGE_MODEL,  # 用快速模型
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls
            
            # 如果AI决定不搜索，直接用快速模型回答
            if not tool_calls:
                print(f"💡 {JUDGE_MODEL} 判断：无需搜索")
                print(f"🤖 用 {ANSWER_MODEL} 回答...\n")
                
                # 用强力模型重新生成回答（带历史上下文）
                final_response = self.client.chat.completions.create(
                    model=ANSWER_MODEL,
                    messages=messages  # 包含历史的完整上下文
                )
                
                answer = final_response.choices[0].message.content
                
            else:
                # AI决定要搜索
                print(f"💡 {JUDGE_MODEL} 判断：需要搜索网络")
                
                # 显示所有工具调用
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    if function_name == "web_search":
                        print(f"📝 搜索关键词: {args.get('query')}\n")
                    elif function_name == "memory_search":
                        print(f"🧠 搜索记忆: {args.get('query')}\n")
                    elif function_name == "memory_save":
                        print(f"💾 保存记忆: {args.get('text')[:50]}...\n")

                # 执行工具调用
                messages.append(response_message)

                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    # 处理网络搜索
                    if function_name == "web_search":
                        search_result = web_search(
                            function_args.get("query"), 
                            self.searxng_url, 
                            self.max_fetch
                        )
                        
                        if search_result["success"]:
                            formatted_result = "搜索结果：\n\n"
                            for i, r in enumerate(search_result["results"], 1):
                                formatted_result += f"【结果{i}】\n"
                                formatted_result += f"标题：{r['title']}\n"
                                formatted_result += f"链接：{r['url']}\n"
                                formatted_result += f"摘要：{r['snippet']}\n"
                                if r['content']:
                                    formatted_result += f"正文内容：\n{r['content']}\n"
                                formatted_result += "\n" + "="*60 + "\n\n"
                        else:
                            formatted_result = f"搜索失败：{search_result.get('message', search_result.get('error'))}"
                        
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": formatted_result
                        })
                    
                    # 处理记忆搜索
                    elif function_name == "memory_search":
                        query = function_args.get("query")
                        top_k = function_args.get("top_k", 5)
                        
                        results = self.memory.search_memory(query, top_k=top_k)
                        
                        if results:
                            formatted_result = f"找到 {len(results)} 条相关记忆：\n\n"
                            for i, r in enumerate(results, 1):
                                formatted_result += f"【记忆{i}】(相关度: {r['score']:.2f})\n"
                                formatted_result += f"内容：{r['text']}\n"
                                formatted_result += f"来源：{r['path']}\n\n"
                        else:
                            formatted_result = "未找到相关记忆"
                        
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": formatted_result
                        })
                    
                    # 处理记忆保存
                    elif function_name == "memory_save":
                        text = function_args.get("text")
                        memory_type = function_args.get("memory_type", "short")
                        
                        self.memory.save_memory(text, memory_type=memory_type)
                        
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": "✅ 记忆已保存"
                        })
                
                # 第二阶段：用强力模型整合搜索结果并回答
                print(f"🤖 阶段2: 用 {ANSWER_MODEL} 整合结果并回答...\n")
                
                final_response = self.client.chat.completions.create(
                    model=ANSWER_MODEL,  # 用强力模型
                    messages=messages
                )
                
                answer = final_response.choices[0].message.content
            
            # 自动提取重要信息
            self._extract_important_info(question, answer)
            
            # 保存短期记忆（完整对话）
            conversation_log = f"""---
            ## [{time_info['time']}] 对话记录

            **用户问**：{question}

            **AI答**：{answer}
            """

            self.memory.save_memory(conversation_log, memory_type="short")
            
            return answer
            
        except Exception as e:
            return f"❌ AI调用失败: {e}"
    
    def update_history(self, question, answer, max_history=10):
        """更新对话历史
        
        Args:
            question: 用户问题
            answer: AI回答
            max_history: 最大历史记录数
        """
        self.conversation_history.append({"role": "user", "content": question})
        self.conversation_history.append({"role": "assistant", "content": answer})
        
        if len(self.conversation_history) > max_history * 2:
            self.conversation_history = self.conversation_history[-(max_history * 2):]
    
    def clear_history(self):
        """清空对话历史"""
        self.conversation_history.clear()
    
    def get_history(self):
        """获取对话历史"""
        return self.conversation_history.copy()