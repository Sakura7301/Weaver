"""
Agent 管理器 - 三级记忆架构版本
- 短期记忆：对话历史（session_log.md）- 不含思考过程
- 工作记忆：当前任务上下文（内存）
- 长期记忆：重要信息（SQLite + 向量）
"""
import os
import re
import requests
import asyncio
import hashlib
import sqlite3
import threading
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv, set_key
from openai import OpenAI

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, UserPromptPart, TextPart
from pydantic_ai import (
    ThinkingPartDelta,
    TextPartDelta,
    PartDeltaEvent,
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
)

from log import logger
import tools


CORE_MEMORY_INSTRUCTIONS = """【核心能力：三级记忆系统】
你拥有三级记忆能力，可以智能管理对话信息。

【重要：回答前必须先搜索记忆】
每次用户提问时，你必须：
1. 首先调用 `search_memory` 工具搜索与用户问题相关的长期记忆
2. 如果找到相关记忆，基于记忆内容回答
3. 如果没有找到相关记忆，再基于通用知识回答

【何时保存长期记忆】
只有当信息满足以下条件时，才调用 `save_memory` 工具保存：
1. 用户明确说"记住"、"请记住"、"帮我记着"
2. 用户身份信息（姓名、职业、年龄、所在地）
3. 用户的重要偏好（喜好、厌恶、习惯、兴趣）
4. 重要的约定、计划、承诺
5. 对理解用户背景至关重要的信息

【何时不保存】
- 普通闲聊、问候、寒暄
- 一般性知识问答（历史、科学、技术等）
- 临时性、一次性请求
- 用户没有暗示需要记住的信息

【操作要求】
- 使用工具时保持自然，不要让用户察觉你在"保存记忆"
- 保存内容应准确、完整、无冗余，聚焦事实本身
- 不要保存时间戳，系统会自动记录"""


# ============ 记忆系统配置 ============

@dataclass
class MemoryConfig:
    """记忆系统配置"""
    api_key: str
    base_url: str
    embedding_model: str = "embedding-3"
    chat_model: str = "glm-4-plus"  # 记忆处理专用模型
    memory_dir: str = "./memory_data"
    similarity_threshold: float = 0.75
    max_memory_results: int = 5
    min_similarity_score: float = 0.3
    session_log_file: str = "session_log.md"  # 短期记忆（会话记录）
    working_memory_capacity: int = 10  # 工作记忆容量


# ============ 工作记忆 ============

@dataclass
class WorkingMemoryItem:
    """工作记忆项"""
    key: str           # 键（如"用户提到的项目名"）
    value: str         # 值（如"AI助手项目"）
    priority: int = 0  # 优先级（越高越重要）
    created_at: datetime = field(default_factory=datetime.now)
    last_access: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    source: str = "extracted"  # 来源: extracted(提取), user_input(用户输入), tool_result(工具结果)


class WorkingMemory:
    """
    工作记忆 - 维护当前对话任务上下文
    
    特点：
    1. 存储在内存中，不持久化
    2. 容量有限，采用优先级+LRU淘汰策略
    3. 自动从对话中提取关键实体
    4. 支持手动添加/更新/删除
    """
    
    def __init__(self, capacity: int = 10):
        self.capacity = capacity
        self.items: Dict[str, WorkingMemoryItem] = {}  # key -> item
        self._lock = threading.Lock()
    
    def add(self, key: str, value: str, priority: int = 0, source: str = "extracted") -> bool:
        """添加工作记忆项"""
        with self._lock:
            # 如果已存在，更新值和访问时间
            if key in self.items:
                self.items[key].value = value
                self.items[key].priority = max(self.items[key].priority, priority)
                self.items[key].last_access = datetime.now()
                self.items[key].access_count += 1
                return True
            
            # 检查容量，必要时淘汰
            if len(self.items) >= self.capacity:
                self._evict()
            
            # 添加新项
            self.items[key] = WorkingMemoryItem(
                key=key,
                value=value,
                priority=priority,
                source=source
            )
            return True
    
    def get(self, key: str) -> Optional[str]:
        """获取工作记忆项"""
        with self._lock:
            if key in self.items:
                self.items[key].last_access = datetime.now()
                self.items[key].access_count += 1
                return self.items[key].value
            return None
    
    def remove(self, key: str) -> bool:
        """删除工作记忆项"""
        with self._lock:
            if key in self.items:
                del self.items[key]
                return True
            return False
    
    def clear(self):
        """清空工作记忆"""
        with self._lock:
            self.items.clear()
    
    def get_all(self) -> List[Dict]:
        """获取所有工作记忆项"""
        with self._lock:
            return [
                {
                    "key": item.key,
                    "value": item.value,
                    "priority": item.priority,
                    "created_at": item.created_at.isoformat(),
                    "last_access": item.last_access.isoformat(),
                    "access_count": item.access_count,
                    "source": item.source
                }
                for item in sorted(self.items.values(), key=lambda x: (-x.priority, -x.access_count))
            ]
    
    def get_context_text(self, max_items: int = 5) -> str:
        """获取工作记忆上下文文本（用于注入到提示词）"""
        with self._lock:
            if not self.items:
                return ""
            
            # 按优先级和访问次数排序
            sorted_items = sorted(
                self.items.values(),
                key=lambda x: (-x.priority, -x.access_count)
            )[:max_items]
            
            if not sorted_items:
                return ""
            
            lines = ["【工作记忆 - 当前任务上下文】"]
            for item in sorted_items:
                lines.append(f"- {item.key}: {item.value}")
            
            return "\n".join(lines)
    
    def _evict(self):
        """淘汰策略：优先级最低 + 最久未访问"""
        if not self.items:
            return
        
        # 找到优先级最低且最久未访问的项
        min_priority = min(item.priority for item in self.items.values())
        candidates = [
            (key, item) for key, item in self.items.items()
            if item.priority == min_priority
        ]
        
        # 在最低优先级中，选择最久未访问的
        evict_key = min(candidates, key=lambda x: x[1].last_access)[0]
        del self.items[evict_key]
        logger.debug(f"工作记忆淘汰: {evict_key}")
    
    def decay(self, threshold_hours: int = 1):
        """衰减机制：降低旧项目的优先级"""
        with self._lock:
            now = datetime.now()
            for item in self.items.values():
                age_hours = (now - item.last_access).total_seconds() / 3600
                if age_hours > threshold_hours:
                    item.priority = max(0, item.priority - 1)


class VectorStore:
    """长期记忆向量存储（仅用于重要记忆）"""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
    
    def _get_conn(self):
        """线程安全的连接获取"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._local.conn
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS long_term_memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                embedding BLOB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                last_access TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_access ON long_term_memories(last_access)")
        conn.commit()
        conn.close()
    
    def add(self, memory_id: str, content: str, embedding: List[float]):
        """添加长期记忆"""
        conn = self._get_conn()
        emb_bytes = np.array(embedding, dtype=np.float32).tobytes()
        conn.execute(
            "INSERT OR REPLACE INTO long_term_memories VALUES (?, ?, ?, ?, 0, ?)",
            (memory_id, content, emb_bytes, datetime.now().isoformat(), datetime.now().isoformat())
        )
        conn.commit()
    
    def search(self, query_embedding: List[float], top_k: int = 5, 
               min_score: float = 0.3) -> List[Dict]:
        """向量搜索长期记忆"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, embedding FROM long_term_memories")
        
        results = []
        query_vec = np.array(query_embedding, dtype=np.float32)
        
        for row in cursor:
            mem_id, content, emb_bytes = row
            mem_vec = np.frombuffer(emb_bytes, dtype=np.float32)
            
            norm_product = np.linalg.norm(query_vec) * np.linalg.norm(mem_vec)
            if norm_product == 0:
                continue
            similarity = np.dot(query_vec, mem_vec) / norm_product
            
            if similarity >= min_score:
                results.append({
                    "id": mem_id,
                    "content": content,
                    "score": float(similarity)
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        
        # 更新访问次数
        for r in results[:top_k]:
            conn.execute(
                "UPDATE long_term_memories SET access_count = access_count + 1, last_access = ? WHERE id = ?",
                (datetime.now().isoformat(), r["id"])
            )
        conn.commit()
        
        return results[:top_k]
    
    def get_all(self) -> List[Dict]:
        """获取所有长期记忆（用于导出）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, content, created_at FROM long_term_memories ORDER BY created_at DESC")
        results = [{"id": row[0], "content": row[1], "created_at": row[2]} for row in cursor.fetchall()]
        conn.close()
        return results
    
    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM long_term_memories WHERE id=?", (memory_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            return False
    
    def delete_many(self, memory_ids: List[str]) -> int:
        """批量删除记忆"""
        try:
            conn = sqlite3.connect(self.db_path)
            placeholders = ','.join('?' * len(memory_ids))
            cursor = conn.execute(
                f"DELETE FROM long_term_memories WHERE id IN ({placeholders})",
                memory_ids
            )
            conn.commit()
            deleted_count = cursor.rowcount
            conn.close()
            return deleted_count
        except Exception as e:
            logger.error(f"批量删除记忆失败: {e}")
            return 0
    
    def clear_all(self) -> int:
        """清空所有长期记忆"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT COUNT(*) FROM long_term_memories")
            count = cursor.fetchone()[0]
            conn.execute("DELETE FROM long_term_memories")
            conn.commit()
            conn.close()
            return count
        except Exception as e:
            logger.error(f"清空长期记忆失败: {e}")
            return 0


class SessionLogger:
    """短期记忆记录器（自动记录会话到 Markdown）"""
    def __init__(self, log_path: str):
        self.log_path = log_path
    
    def log_turn(self, user_msg: str, assistant_msg: str):
        """记录一轮对话（assistant_msg 应该是纯内容，不含思考过程）"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"""## {timestamp}

**User**: {user_msg}

**Assistant**: {assistant_msg}

---

"""
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.error(f"写入短期记忆失败: {e}")
    
    def get_recent(self, n_turns: int = 10) -> str:
        """获取最近的对话记录（用于快速回顾）"""
        if not os.path.exists(self.log_path):
            return ""
        
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 简单的按 "---" 分割，获取最后 n 轮
            turns = [t.strip() for t in content.split("---") if t.strip()]
            recent_turns = turns[-n_turns:] if len(turns) > n_turns else turns
            return "\n\n---\n\n".join(recent_turns)
        except Exception as e:
            logger.error(f"读取短期记忆失败: {e}")
            return ""
    
    def clear(self):
        """清空短期记忆文件"""
        try:
            if os.path.exists(self.log_path):
                with open(self.log_path, "w", encoding="utf-8") as f:
                    f.write("")
                logger.info("短期记忆已清空")
        except Exception as e:
            logger.error(f"清空短期记忆失败: {e}")


class MemorySystem:
    """记忆系统主类 - 三级记忆架构"""
    
    # 无效内容黑名单 - 这些字符串不应该被保存为记忆
    INVALID_CONTENT_PATTERNS = [
        "(无内容)", "无内容", "暂无内容", "没有内容", 
        "无", "没有", "暂无", "未知", "空", 
        "无可奉告", "未提供", "未提及", "无信息",
        "用户未", "没有提供", "未说明", "未告知",
        "null", "none", "empty", "n/a", "na", 
    ]
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        
        Path(config.memory_dir).mkdir(parents=True, exist_ok=True)
        
        # 长期记忆：向量数据库
        db_path = os.path.join(config.memory_dir, "long_term.db")
        self.vector_store = VectorStore(db_path)
        
        # 短期记忆：Markdown 会话日志
        session_path = os.path.join(config.memory_dir, config.session_log_file)
        self.session_logger = SessionLogger(session_path)
        
        # 工作记忆：内存存储
        self.working_memory = WorkingMemory(capacity=config.working_memory_capacity)
        
        self._embedding_cache = {}
        self._cache_lock = threading.Lock()
        
        logger.info(f"记忆系统初始化完成（短期:Markdown | 工作:内存 | 长期:VectorDB）容量:{config.working_memory_capacity}")
    
    def _is_valid_content(self, content: str) -> bool:
        """检查内容是否有效（不是无意义的填充词）"""
        if not content:
            return False
        
        content_stripped = content.strip()
        
        # 检查是否在黑名单中（不区分大小写）
        content_lower = content_stripped.lower()
        for invalid in self.INVALID_CONTENT_PATTERNS:
            if content_lower == invalid.lower():
                logger.warning(f"过滤掉无效内容: {content_stripped}")
                return False
        
        # 检查是否包含分析性前缀（这些通常是无效内容）
        analysis_prefixes = [
            "这是", "属于", "符合", "不符合", "分析", "结论", 
            "从对话中", "用户表示", "用户提供", "用户说",
        ]
        for prefix in analysis_prefixes:
            if content_stripped.startswith(prefix):
                logger.warning(f"过滤掉分析性内容: {content_stripped[:50]}...")
                return False
        
        # 检查长度（太短或太长都不行）
        if len(content_stripped) < 3:
            return False
        
        # 必须包含至少一个中文字符或英文字母（确保是有效文本）
        if not re.search(r'[\u4e00-\u9fa5a-zA-Z]', content_stripped):
            return False
            
        return True
    
    def log_session_turn(self, user_msg: str, assistant_msg: str):
        """自动记录短期记忆（不含思考过程）"""
        self.session_logger.log_turn(user_msg, assistant_msg)
        
        # 同时提取关键信息到工作记忆
        self._extract_to_working_memory(user_msg, assistant_msg)
    
    def _extract_to_working_memory(self, user_msg: str, assistant_msg: str):
        """
        从对话中提取关键信息到工作记忆
        
        工作记忆的作用：维护当前对话的上下文，帮助 AI 理解当前话题
        提取策略：
        1. 从用户消息中提取明确的实体（姓名、职业、偏好等）
        2. 记录当前话题（用户消息摘要）
        3. 提取时间、日期等关键信息
        """
        extracted_count = 0
        
        # ========== 1. 实体提取规则 ==========
        patterns = [
            # 个人信息
            (r'我叫([^\s，。！？,]{2,10})', '用户名'),
            (r'我是(\w+(?:工程师|设计师|经理|学生|老师|医生|程序员|开发者|分析师|架构师|专家|顾问))', '用户身份'),
            (r'我在(\w+(?:公司|学校|医院|团队|部门|集团))', '用户所在'),
            (r'我(的)?(名字|姓名)是([^\s，。！？,]{2,10})', '用户名'),
            
            # 项目/产品名称
            (r'项目[叫名叫是「『"]([^」』"\s，。]{2,20})[」』"]?', '项目名'),
            (r'产品[叫名叫是「『"]([^」』"\s，。]{2,20})[」』"]?', '产品名'),
            (r'(?:在做|开发|写|做)(?:一个|个)?([^\s，。！？]{2,15})(?:项目|系统|应用|网站)', '当前项目'),
            
            # 技术相关
            (r'用(\w+(?:\+\+|\.js|\.py|\.java|\.go|\.rs)?)', '使用语言'),
            (r'使用(\w+(?:框架|库|工具)?)', '使用工具'),
            (r'(?:在用|正在学|学习)(\w+)', '学习内容'),
            
            # 偏好
            (r'我喜欢(\w+)', '用户喜好'),
            (r'我讨厌(\w+)', '用户厌恶'),
            (r'我希望(\w+)', '用户期望'),
            (r'我想要(\w+)', '用户需求'),
            
            # 时间
            (r'(\d{1,2}月\d{1,2}[日号])', '日期'),
            (r'(明天|后天|下周|下周[一二三四五六日天])', '日期'),
            (r'(\d{1,2}:\d{2})', '时间'),
            (r'(上午|下午|晚上|今晚|明早)', '时段'),
            
            # 其他
            (r'记住[，:]?\s*([^\s，。！？]{2,30})', '需记住'),
            (r'别忘了[，:]?\s*([^\s，。！？]{2,30})', '需记住'),
        ]
        
        for pattern, key in patterns:
            try:
                matches = re.findall(pattern, user_msg)
                for match in matches:
                    # 处理可能的元组结果
                    if isinstance(match, tuple):
                        value = match[-1] if match[-1] else match[0]
                    else:
                        value = match
                    
                    if value and len(str(value).strip()) >= 2 and len(str(value)) < 50:
                        value = str(value).strip()
                        self.working_memory.add(key, value, priority=2, source="extracted")
                        extracted_count += 1
                        logger.debug(f"工作记忆提取: {key} = {value}")
            except Exception as e:
                logger.debug(f"正则匹配失败 {pattern}: {e}")
        
        # ========== 2. 记录当前话题（始终保存，确保工作记忆非空） ==========
        # 使用时间戳作为唯一 key，避免覆盖
        import time
        timestamp_key = f"话题_{int(time.time() * 1000) % 100000}"  # 使用毫秒时间戳后5位
        topic = user_msg.strip()[:60]  # 限制长度
        if len(topic) >= 3:
            self.working_memory.add(timestamp_key, topic, priority=3, source="context")
            extracted_count += 1
            logger.debug(f"工作记忆话题: {topic[:30]}...")
        
        # ========== 3. 关键词提取 ==========
        # 提取可能的关键词（简单实现：提取引号内容）
        quoted = re.findall(r'["「『]([^"」』]{2,20})["」』]', user_msg)
        for i, q in enumerate(quoted[:3]):  # 最多3个
            if q and len(q) >= 2:
                self.working_memory.add(f"关键词_{i}", q, priority=1, source="keyword")
                extracted_count += 1
        
        if extracted_count > 0:
            logger.info(f"工作记忆: 新增 {extracted_count} 条（当前共 {len(self.working_memory.items)} 条）")
    
    def _get_embedding(self, text: str) -> List[float]:
        """获取向量（带缓存）"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        with self._cache_lock:
            if text_hash in self._embedding_cache:
                return self._embedding_cache[text_hash]
        
        try:
            response = self.client.embeddings.create(
                model=self.config.embedding_model,
                input=text[:8000]
            )
            embedding = response.data[0].embedding
            
            with self._cache_lock:
                self._embedding_cache[text_hash] = embedding
            
            return embedding
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            return []
    
    def _smart_merge(self, new_content: str, old_contents: List[str]) -> str:
        """使用LLM智能合并记忆，确保结果准确无冗余"""
        try:
            prompt = f"""请将以下信息合并为一条准确、完整的记忆，去除冗余描述。

待合并内容:
{chr(10).join(f"- {c}" for c in old_contents)}
- {new_content}

要求:
1. 去除重复和冗余描述，保留关键事实细节
2. 确保信息准确完整，不要遗漏重要细节
3. 直接输出合并后的陈述，不要添加解释或分析
4. 聚焦"这对服务客户有什么帮助"，保留有助于理解用户的细节

合并结果:"""

            response = self.client.chat.completions.create(
                model=self.config.chat_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=500
            )
            
            merged = response.choices[0].message.content.strip()
            # 去除可能的列表符号
            merged = merged.lstrip("- •").strip()
            return merged
            
        except Exception as e:
            logger.error(f"Merge failed: {e}")
            # 如果合并失败，返回包含最多信息的那个
            return max(old_contents + [new_content], key=len)
    
    def _is_subset_or_redundant(self, new_content: str, existing_content: str) -> bool:
        """
        检查新内容是否被已有内容包含（语义层面）
        不只是字符串包含，还要考虑语义包含
        """
        new_lower = new_content.lower()
        existing_lower = existing_content.lower()
        
        # 直接字符串包含
        if new_content in existing_content:
            return True
        
        # 语义包含检查：如果已有记忆包含了新记忆的所有关键信息
        # 简单实现：如果新内容的每个关键词都在已有内容中，且已有内容明显更长
        new_words = set(new_lower.split())
        existing_words = set(existing_lower.split())
        
        # 如果新内容的所有词都在已有内容中，且已有内容比新内容长20%以上
        if new_words.issubset(existing_words) and len(existing_content) > len(new_content) * 1.2:
            return True
        
        return False
    
    def save_long_term(self, content: str) -> bool:
        """
        保存长期记忆（供 AI 自主调用）
        仅当 AI 判断信息重要时才应调用此方法
        包含子集检测：如果新内容被已有记忆包含，则不保存
        """
        try:
            content = content.strip()
            
            # 严格的内容有效性检查
            if not self._is_valid_content(content):
                logger.warning(f"拒绝保存无效内容: '{content}'")
                return False
            
            embedding = self._get_embedding(content)
            if not embedding:
                return False
            
            # 查找相似记忆进行合并
            similar = self.vector_store.search(
                embedding, 
                top_k=5,
                min_score=self.config.similarity_threshold
            )
            
            if similar:
                # 检查是否被包含或冗余
                for s in similar:
                    existing = s["content"]
                    if self._is_subset_or_redundant(content, existing):
                        logger.info(f"跳过保存（已有记忆的子集）: {content[:60]}...")
                        return True  # 视为成功，因为信息已存在
                
                # 反向检查：如果已有记忆被新内容完全包含，删除旧的
                contents_to_merge = [content]
                ids_to_delete = []
                
                for s in similar:
                    existing = s["content"]
                    # 如果已有记忆被新内容包含（新内容更完整）
                    if self._is_subset_or_redundant(existing, content):
                        ids_to_delete.append(s["id"])
                        logger.debug(f"删除被包含的旧记忆: {existing[:60]}...")
                    else:
                        contents_to_merge.append(existing)
                        ids_to_delete.append(s["id"])
                
                # 执行删除
                for mem_id in ids_to_delete:
                    self.vector_store.delete(mem_id)
                
                # 合并所有内容
                if len(contents_to_merge) > 1:
                    content = self._smart_merge(contents_to_merge[0], contents_to_merge[1:])
                else:
                    content = contents_to_merge[0]
                
                # 合并后再次检查有效性
                if not self._is_valid_content(content):
                    logger.warning(f"合并后的内容无效，跳过保存: '{content}'")
                    return False
            
            mem_id = hashlib.md5(content.encode()).hexdigest()
            self.vector_store.add(mem_id, content, embedding)
            
            logger.info(f"✓ 保存长期记忆: {content[:60]}...")
            return True
            
        except Exception as e:
            logger.error(f"保存长期记忆失败: {e}")
            return False
    
    def search_long_term(self, query: str, top_k: int = None, min_score: float = None) -> List[Dict]:
        """搜索长期记忆"""
        top_k = top_k or self.config.max_memory_results
        min_score = min_score or self.config.min_similarity_score
        
        embedding = self._get_embedding(query)
        if not embedding:
            return []
        
        return self.vector_store.search(embedding, top_k, min_score)
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        try:
            conn = sqlite3.connect(os.path.join(self.config.memory_dir, "long_term.db"))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM long_term_memories")
            long_term_count = cursor.fetchone()[0]
            conn.close()
            
            # 统计短期记忆文件行数（粗略估计对话轮数）
            session_count = 0
            session_file = os.path.join(self.config.memory_dir, self.config.session_log_file)
            if os.path.exists(session_file):
                with open(session_file, "r", encoding="utf-8") as f:
                    session_count = f.read().count("## ")
            
            # 工作记忆数量
            working_count = len(self.working_memory.items)
            
            return {
                "long_term": long_term_count,
                "short_term": session_count,
                "working": working_count,
                "total": long_term_count + session_count + working_count
            }
        except Exception as e:
            logger.error(f"获取统计失败: {e}")
            return {"long_term": 0, "short_term": 0, "working": 0, "total": 0}
        
    def merge_similar_memories(self):
        """定期合并相似的长期记忆"""
        try:
            conn = sqlite3.connect(os.path.join(self.config.memory_dir, "long_term.db"))
            cursor = conn.cursor()
            
            # 获取所有长期记忆
            cursor.execute("SELECT id, content FROM long_term_memories")
            memories = cursor.fetchall()
            
            merged_count = 0
            processed_ids = set()
            
            for i, (id1, content1) in enumerate(memories):
                if id1 in processed_ids:
                    continue
                    
                # 查找相似的记忆
                embedding = self._get_embedding(content1)
                similar = self.vector_store.search(embedding, top_k=10, min_score=0.85)
                
                similar_contents = [s["content"] for s in similar if s["id"] != id1 and s["id"] not in processed_ids]
                
                if similar_contents:
                    # 合并记忆
                    merged_content = self._smart_merge(content1, similar_contents)
                    
                    # 删除旧记忆
                    for s in similar:
                        if s["id"] != id1:
                            self.vector_store.delete(s["id"])
                            processed_ids.add(s["id"])
                            merged_count += 1
                    
                    # 更新当前记忆
                    self.vector_store.delete(id1)
                    new_id = hashlib.md5(merged_content.encode()).hexdigest()
                    self.vector_store.add(new_id, merged_content, self._get_embedding(merged_content))
                    processed_ids.add(id1)
            
            conn.close()
            if merged_count > 0:
                logger.info(f"记忆合并完成，合并了 {merged_count} 条相似记忆")
            
        except Exception as e:
            logger.error(f"记忆合并失败: {e}")

    def process_short_term_to_long_term(self):
        """
        将短期记忆（对话历史）中的重要信息提取并保存为长期记忆
        关键改动：使用 try-finally 确保无论处理成功与否，短期记忆都会被清空
        避免重复处理已处理过的内容
        """
        log_content = ""
        try:
            # 读取短期记忆文件
            log_content = self.session_logger.get_recent(n_turns=9999)  # 读取全部
            
            if not log_content or not log_content.strip():
                return
            
            # 解析出独立的对话轮次
            turns = self._parse_session_log(log_content)
            if not turns:
                return
            
            logger.info(f"开始处理 {len(turns)} 条短期记忆...")
            extracted_count = 0
            
            # 使用LLM分析对话，提取对服务客户有价值的信息
            important_facts = self._extract_important_facts(turns)
            
            for fact in important_facts:
                fact = fact.strip()
                
                # 使用统一的验证方法检查内容有效性
                if not self._is_valid_content(fact):
                    logger.debug(f"跳过无效事实: '{fact}'")
                    continue
                
                # 检查是否与已有长期记忆过于相似
                embedding = self._get_embedding(fact)
                if not embedding:
                    continue
                
                similar = self.vector_store.search(
                    embedding, 
                    top_k=1, 
                    min_score=0.90
                )
                
                if similar:
                    logger.debug(f"跳过已存在的记忆: {fact[:50]}...")
                    continue
                
                # 保存到长期记忆（内部会再次检查有效性）
                success = self.save_long_term(fact)
                if success:
                    extracted_count += 1
                    logger.info(f"提取长期记忆: {fact[:60]}...")
            
            if extracted_count > 0:
                logger.info(f"从短期记忆提取了 {extracted_count} 条重要信息转为长期记忆")
            
        except Exception as e:
            logger.error(f"处理短期记忆失败: {e}")
        finally:
            # 关键：无论处理成功与否，都清空短期记忆
            # 这样可以确保已经处理过的内容不会被重复处理
            self.session_logger.clear()
            if log_content:
                logger.debug(f"已清空已处理的短期记忆（{len(log_content)} 字符）")
    
    def _parse_session_log(self, log_content: str) -> list:
        """解析会话日志，返回对话轮次列表"""
        raw_turns = log_content.split("## ")
        turns = []
        
        for turn in raw_turns:
            turn = turn.strip()
            if not turn:
                continue
            
            # 提取用户消息（**User**: 后面的内容）
            user_match = re.search(r'\*\*User\*\*:\s*(.*?)(?=\*\*Assistant\*\*|$)', turn, re.DOTALL)
            if user_match:
                user_msg = user_match.group(1).strip()
                if user_msg:
                    turns.append(user_msg)
        
        return turns
    
    def _extract_important_facts(self, turns: list) -> list:
        """
        使用LLM从对话中提取对服务客户有价值的重要事实
        重点：根据上下文判断信息价值，而非机械提取
        """
        if not turns:
            return []
        
        # 批量处理，每次处理最近10轮
        batch_size = 10
        all_facts = []
        
        # 新的系统提示：强调客户价值和服务相关性，并明确禁止无效输出
        system_prompt = """你是专业的客户信息分析师。从对话中提取对长期服务客户有价值的信息。

判断标准（仅当信息符合以下标准时提取）：
1. 有助于提供个性化服务（用户偏好、习惯、禁忌）
2. 有助于理解用户背景（职业、expertise、生活状况）
3. 用户明确要求记住的重要信息
4. 对未来交互有长期参考价值（约定、计划、承诺）

【重要：人称转换规则】
用户说话时用第一人称（"我是"、"我的"），但提取记忆时必须转换为第三人称：
- "我是你师父" → "用户是AI的师父"
- "我叫张三" → "用户名叫张三"
- "我的爱好是编程" → "用户的爱好是编程"
- "我是程序员" → "用户是程序员"
确保主语始终是"用户"，而不是"我"或容易产生歧义的代词。

绝对禁止输出：
- "无内容"、"暂无"、"没有"等无信息提示
- 分析、解释、编号、列表符号
- 临时性、一次性的信息

输出要求：
- 每行一条独立事实，直接陈述
- 例如："用户是软件工程师"、"用户对坚果过敏"
- 无有效信息时直接留空，不要输出任何提示词"""

        for i in range(0, len(turns), batch_size):
            batch = turns[i:i+batch_size]
            
            user_prompt = f"""分析以下对话，提取对长期服务该客户有价值的重要信息：

对话记录：
{chr(10).join(f"用户: {t[:400]}" for t in batch if t.strip())}

提取指南：
- 关注用户的显性需求和隐性需求（抱怨、偏好、困扰）
- 提取职业、expertise、生活限制（过敏、素食、作息）
- 提取强烈情绪表达（喜欢/讨厌）以调整交互方式
- 判断信息是否会在未来3个月以上仍有价值

仅输出有价值的事实，每行一条，必须是事实陈述句，无则留空："""

            try:
                response = self.client.chat.completions.create(
                    model=self.config.chat_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2,
                    max_tokens=400
                )
                
                result = response.choices[0].message.content.strip()
                
                if result:
                    lines = [line.strip() for line in result.split('\n') if line.strip()]
                    for line in lines:
                        # 基础清理：去除列表符号
                        cleaned = line.lstrip("- •").strip()
                        if cleaned:
                            all_facts.append(cleaned)
                    
            except Exception as e:
                logger.error(f"LLM提取重要事实失败: {e}")
                continue
        
        # 去重
        unique_facts = []
        seen_hashes = set()
        for fact in all_facts:
            fact_hash = hashlib.md5(fact.encode()).hexdigest()
            if fact_hash not in seen_hashes:
                seen_hashes.add(fact_hash)
                unique_facts.append(fact)
        
        return unique_facts


# ============ Agent 管理器 ============

class AgentManager:
    def __init__(self):
        self.agent = None
        self.current_model = None
        self.api_key = None
        self.base_url = None
        self.memory_system = None
        self._assistant_response_buffer = ""  # 用于收集完整回复以保存短期记忆
        self._thinking_content = ""  # 用于收集思考过程（不保存到短期记忆）
        self._stop_requested = False  # 停止生成标志
        self.reload_config()
    
    def reload_config(self):
        """重新加载配置"""
        load_dotenv(override=True)
        
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL")
        
        if not self.api_key:
            raise ValueError("未设置 OPENAI_API_KEY")
        
        # 获取默认模型
        if not self.current_model:
            models = self.fetch_models()
            if models:
                self.current_model = models[0]['id']
            else:
                raise ValueError("无法获取模型列表")
        
        # 初始化记忆系统
        try:
            # 记忆处理使用专用模型（可配置），默认使用当前模型
            memory_model = os.getenv("MEMORY_MODEL", "") or self.current_model
            mem_config = MemoryConfig(
                api_key=self.api_key,
                base_url=self.base_url,
                embedding_model=os.getenv("EMBEDDING_MODEL", "embedding-3"),
                chat_model=memory_model,  # 使用记忆专用模型
                memory_dir=os.getenv("MEMORY_DIR", "./memory_data"),
                similarity_threshold=float(os.getenv("MEMORY_THRESHOLD", "0.75")),
                working_memory_capacity=int(os.getenv("WORKING_MEMORY_CAPACITY", "10"))
            )
            self.memory_system = MemorySystem(mem_config)
            logger.info(f"记忆系统初始化成功，记忆处理模型: {memory_model}")
        except Exception as e:
            logger.error(f"记忆系统初始化失败: {e}")
            self.memory_system = None
        
        logger.info(f"重新加载配置，当前模型: {self.current_model}")
        self._create_agent()

    def _load_user_system_prompt(self):
        """加载用户自定义的系统提示词（文件中的内容）"""
        prompt_file = "system_prompt.txt"
        default_prompt = """你是一个智能助手，回答要简洁准确，使用中文。简要回答，不要过度解释。"""
        
        try:
            if os.path.exists(prompt_file):
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        return content
        except Exception as e:
            logger.error(f"加载用户提示词失败: {e}")
        
        return default_prompt

    def _create_agent(self):
        """创建 Agent - 合并用户提示词与核心记忆指令"""
        model = OpenAIChatModel(
            self.current_model,
            provider=OpenAIProvider(
                api_key=self.api_key,
                base_url=self.base_url
            )
        )
        
        # 构建工具列表
        tool_list = [
            tools.get_current_time,
            tools.calculate,
            self.save_memory_tool,      # 仅保存长期记忆
            self.search_memory_tool     # 仅搜索长期记忆
        ]
        
        # 添加网络搜索（如果配置了SEARXNG）
        if os.getenv("SEARXNG_URL"):
            tool_list.insert(0, tools.web_search)
            logger.info("已启用网络搜索工具")
        
        # 组合提示词：用户角色设定 + 核心记忆能力（记忆指令在后，确保覆盖）
        user_prompt = self._load_user_system_prompt()
        full_system_prompt = f"{user_prompt}\n\n{CORE_MEMORY_INSTRUCTIONS}"
        
        self.agent = Agent(
            model=model,
            system_prompt=full_system_prompt,
            tools=tool_list
        )
        
        logger.info(f"Agent 初始化完成，工具数: {len(tool_list)}")
    
    def save_memory_tool(self, content: str) -> str:
        """
        保存长期记忆工具 - 由模型自主调用
        
        Args:
            content: 要保存的重要信息（应简洁明了，去除时间戳等冗余信息）
        """
        if not self.memory_system:
            return "记忆系统未启用"
        
        success = self.memory_system.save_long_term(content)
        if success:
            return "已保存长期记忆"
        return "保存失败"
    
    def search_memory_tool(self, query: str, top_k: int = 3) -> str:
        """
        搜索长期记忆工具 - 由模型自主调用
        
        Args:
            query: 搜索关键词，如"用户身份"、"用户喜好"、"之前的约定"
            top_k: 返回结果数量
        """
        if not self.memory_system:
            return "记忆系统未启用"
        
        results = self.memory_system.search_long_term(query, top_k=top_k)
        if not results:
            return "未找到相关长期记忆"
        
        output = "相关记忆：\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. {r['content']} (相关度: {r['score']:.2f})\n"
        
        return output
    
    def fetch_models(self):
        """从 API 获取模型列表，并分析模型特性"""
        try:
            logger.debug("获取模型列表")
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = requests.get(
                f"{self.base_url}/models",
                headers=headers,
                timeout=10
            )
            
            if resp.status_code == 200:
                data = resp.json()
                models = []
                for m in data.get("data", []):
                    model_id = m["id"]
                    # 分析模型特性
                    features = self._analyze_model_features(model_id)
                    models.append({
                        "id": model_id,
                        "name": m.get("id", model_id),
                        "features": features
                    })
                logger.debug(f"获取到 {len(models)} 个模型")
                return models
            else:
                logger.error(f"获取模型列表失败: {resp.status_code}")
                return []
        except Exception as e:
            logger.error(f"获取模型列表异常: {e}")
            return []
    
    def _analyze_model_features(self, model_id: str) -> Dict:
        """分析模型特性"""
        model_lower = model_id.lower()
        features = {
            "vision": False,      # 视觉能力
            "tools": False,       # 工具调用
            "reasoning": False,   # 推理能力
            "fast": False,        # 快速响应
            "chat": True          # 默认支持对话
        }
        
        # 视觉模型检测
        vision_keywords = ["vision", "gpt-4o", "gpt-4-turbo", "gpt-4-vision", 
                          "claude-3", "gemini", "qwen-vl", "glm-4v", "dall-e"]
        if any(kw in model_lower for kw in vision_keywords):
            features["vision"] = True
        
        # 工具调用检测
        tools_keywords = ["gpt-4", "gpt-3.5-turbo", "claude", "glm-4", "qwen", 
                         "deepseek", "doubao", "abab"]
        if any(kw in model_lower for kw in tools_keywords):
            # 排除一些已知不支持工具的模型
            if "instruct" not in model_lower and "base" not in model_lower:
                features["tools"] = True
        
        # 推理模型检测
        reasoning_keywords = ["o1", "o3", "reasoning", "think", "r1", "deepseek-reasoner"]
        if any(kw in model_lower for kw in reasoning_keywords):
            features["reasoning"] = True
        
        # 快速模型检测
        fast_keywords = ["turbo", "flash", "lite", "mini", "fast", "instant", "haiku", "7b"]
        if any(kw in model_lower for kw in fast_keywords):
            features["fast"] = True
        
        return features
    
    def switch_model(self, model_id: str):
        """切换模型"""
        logger.info(f"切换模型: {model_id}")
        self.current_model = model_id
        
        # 更新记忆系统的chat_model配置
        if self.memory_system:
            self.memory_system.config.chat_model = model_id
        
        self._create_agent()
    
    def get_config(self):
        """获取当前配置"""
        return {
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
            "OPENAI_BASE_URL": os.getenv("OPENAI_BASE_URL", ""),
            "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
            "LOG_MODE": os.getenv("LOG_MODE", "console"),
            "MEMORY_ENABLED": str(self.memory_system is not None),
            "CURRENT_MODEL": self.current_model
        }
    
    def save_config(self, config: dict):
        """保存配置到 .env"""
        env_file = ".env"
        for key, value in config.items():
            if key.startswith("OPENAI_") or key in ["LOG_LEVEL", "LOG_MODE"]:
                set_key(env_file, key, value)
        logger.info("配置已保存")
        self.reload_config()
    
    def stop_generation(self):
        """请求停止生成"""
        self._stop_requested = True
        logger.info("用户请求停止生成")
    
    def chat_stream(self, message: str, history: list):
        """
        流式聊天 - 强制先搜索记忆再回答
        短期记忆只保存对话内容，不保存思考过程
        """
        logger.info(f"用户输入: {message[:50]}...")
        self._assistant_response_buffer = ""
        self._thinking_content = ""  # 重置思考内容缓冲
        self._stop_requested = False  # 重置停止标志
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # ===== 自动搜索相关记忆并注入上下文 =====
            final_message = message
            if self.memory_system:
                # 1. 搜索长期记忆
                search_results = self.memory_system.search_long_term(message, top_k=3, min_score=0.3)
                
                # 2. 获取工作记忆上下文
                working_context = self.memory_system.working_memory.get_context_text(max_items=5)
                
                # 构建增强消息
                memory_parts = []
                
                if search_results:
                    memory_text = "\n".join([f"{i+1}. {r['content']}" for i, r in enumerate(search_results)])
                    memory_parts.append(f"【长期记忆引用】\n{memory_text}\n【长期记忆结束】")
                
                if working_context:
                    memory_parts.append(working_context)
                
                if memory_parts:
                    final_message = f"""{chr(10).join(memory_parts)}

用户问题：{message}"""
                    logger.info(f"已注入 {len(search_results)} 条长期记忆 + {len(self.memory_system.working_memory.items)} 条工作记忆")
            # =======================================
            
            msg_history = self._convert_history(history)
            
            async def stream_async():
                async for event in self.agent.run_stream_events(
                    final_message,  # 使用增强后的消息
                    message_history=msg_history
                ):
                    # 检查是否请求停止
                    if self._stop_requested:
                        yield {"type": "stopped", "message": "用户已停止生成"}
                        return
                    
                    if isinstance(event, PartDeltaEvent):
                        if isinstance(event.delta, ThinkingPartDelta):
                            self._thinking_content += event.delta.content_delta
                            yield {"type": "thinking", "content": event.delta.content_delta}
                        elif isinstance(event.delta, TextPartDelta):
                            content = event.delta.content_delta
                            self._assistant_response_buffer += content
                            yield {"type": "content", "content": content}
                    
                    elif isinstance(event, FunctionToolCallEvent):
                        yield {
                            "type": "tool_call", 
                            "name": event.part.tool_name,
                            "args": str(event.part.args)
                        }
                    
                    elif isinstance(event, FunctionToolResultEvent):
                        result_content = str(event.result.content) if hasattr(event.result, 'content') else str(event.result)
                        yield {
                            "type": "tool_result",
                            "name": event.tool_call_id,
                            "result": result_content
                        }
                        
                        if "save_memory" in str(event.tool_call_id) and "已保存" in result_content:
                            logger.info("AI 自主保存了长期记忆")
                    
                    elif isinstance(event, FinalResultEvent):
                        logger.debug("流式生成完成")
                        
                        # 自动保存短期记忆（会话记录）- 只保存对话内容，不含思考过程
                        if self.memory_system:
                            try:
                                # 获取最终回复内容：优先使用 buffer，如果为空则从 event 获取
                                final_content = self._assistant_response_buffer
                                
                                # 如果 buffer 为空，尝试从 FinalResultEvent 获取
                                if not final_content:
                                    # PydanticAI 的 FinalResultEvent 包含 data 属性
                                    if hasattr(event, 'data') and event.data:
                                        if hasattr(event.data, 'content'):
                                            final_content = event.data.content
                                        elif isinstance(event.data, str):
                                            final_content = event.data
                                        else:
                                            final_content = str(event.data)
                                
                                if final_content:
                                    # 只保存实际的对话内容，不包含思考过程
                                    self.memory_system.log_session_turn(
                                        message,  # 保存原始消息
                                        final_content  # 只保存实际回复，不含思考
                                    )
                                    logger.debug(f"已自动保存会话到短期记忆（回复长度: {len(final_content)}）")
                                else:
                                    logger.warning("无法获取AI回复内容，跳过保存短期记忆")
                                    
                            except Exception as e:
                                logger.error(f"自动保存短期记忆失败: {e}")
            
            async_gen = stream_async()
            while True:
                try:
                    # 检查是否请求停止
                    if self._stop_requested:
                        yield {"type": "stopped", "message": "用户已停止生成"}
                        break
                    
                    item = loop.run_until_complete(async_gen.__anext__())
                    yield item
                except StopAsyncIteration:
                    break
                    
        except Exception as e:
            logger.error(f"流式响应错误: {e}", exc_info=True)
            yield {"type": "content", "content": f"错误: {str(e)}"}
        finally:
            loop.close()

    def _convert_history(self, history: list):
        """将历史消息转换为 PydanticAI 格式"""
        messages = []
        for msg in history:
            if msg['role'] == 'user':
                messages.append(ModelRequest(parts=[UserPromptPart(content=msg['content'])]))
            elif msg['role'] == 'assistant':
                content = msg['content']
                # 清理可能的 think 标签内容
                if '<thinking>' in content and '</thinking>' in content:
                    content = content.split('</thinking>')[-1].strip()
                messages.append(ModelResponse(parts=[TextPart(content=content)]))
        return messages
    
    def get_memory_stats(self):
        """获取记忆统计（供前端调用）"""
        if self.memory_system:
            return self.memory_system.get_stats()
        return {"long_term": 0, "short_term": 0, "working": 0, "total": 0}
    
    def export_long_term_memories(self):
        """导出所有长期记忆（供前端调用）"""
        if self.memory_system:
            return self.memory_system.vector_store.get_all()
        return []
    
    def export_working_memories(self):
        """导出所有工作记忆（供前端调用）"""
        if self.memory_system:
            return self.memory_system.working_memory.get_all()
        return []
    
    def get_all_memories(self, memory_type=None):
        """兼容旧API的别名方法"""
        if memory_type == 'long' or memory_type is None:
            return self.export_long_term_memories()
        return []
    
    def clear_memory(self, memory_type: str) -> Dict:
        """清空指定类型的记忆"""
        if not self.memory_system:
            return {"success": False, "error": "记忆系统未启用"}
        
        try:
            if memory_type == "long":
                count = self.memory_system.vector_store.clear_all()
                return {"success": True, "deleted_count": count}
            elif memory_type == "short":
                self.memory_system.session_logger.clear()
                return {"success": True, "deleted_count": 1}
            elif memory_type == "working":
                count = len(self.memory_system.working_memory.items)
                self.memory_system.working_memory.clear()
                return {"success": True, "deleted_count": count}
            else:
                return {"success": False, "error": "未知的记忆类型"}
        except Exception as e:
            logger.error(f"清空记忆失败: {e}")
            return {"success": False, "error": str(e)}
    
    def delete_memories(self, memory_type: str, memory_ids: List[str]) -> Dict:
        """批量删除记忆"""
        if not self.memory_system:
            return {"success": False, "error": "记忆系统未启用"}
        
        try:
            if memory_type == "long":
                count = self.memory_system.vector_store.delete_many(memory_ids)
                return {"success": True, "deleted_count": count}
            elif memory_type == "working":
                count = 0
                for key in memory_ids:
                    if self.memory_system.working_memory.remove(key):
                        count += 1
                return {"success": True, "deleted_count": count}
            else:
                return {"success": False, "error": "不支持批量删除该类型记忆"}
        except Exception as e:
            logger.error(f"批量删除记忆失败: {e}")
            return {"success": False, "error": str(e)}
    
    def add_working_memory(self, key: str, value: str, priority: int = 0) -> Dict:
        """手动添加工作记忆"""
        if not self.memory_system:
            return {"success": False, "error": "记忆系统未启用"}
        
        try:
            self.memory_system.working_memory.add(key, value, priority, source="user_input")
            return {"success": True}
        except Exception as e:
            logger.error(f"添加工作记忆失败: {e}")
            return {"success": False, "error": str(e)}
