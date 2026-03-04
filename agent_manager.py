"""
Agent 管理器 - 三级记忆架构版本（支持用户隔离）- 修复版
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
    """工作记忆 - 维护当前对话任务上下文"""
    
    def __init__(self, capacity: int = 10):
        self.capacity = capacity
        self.items: Dict[str, WorkingMemoryItem] = {}
        self._lock = threading.Lock()
    
    def add(self, key: str, value: str, priority: int = 0, source: str = "extracted") -> bool:
        """添加工作记忆项"""
        with self._lock:
            if key in self.items:
                self.items[key].value = value
                self.items[key].priority = max(self.items[key].priority, priority)
                self.items[key].last_access = datetime.now()
                self.items[key].access_count += 1
                return True
            
            if len(self.items) >= self.capacity:
                self._evict()
            
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
        """获取工作记忆上下文文本"""
        with self._lock:
            if not self.items:
                return ""
            
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
        """淘汰策略"""
        if not self.items:
            return
        
        min_priority = min(item.priority for item in self.items.values())
        candidates = [
            (key, item) for key, item in self.items.items()
            if item.priority == min_priority
        ]
        
        evict_key = min(candidates, key=lambda x: x[1].last_access)[0]
        del self.items[evict_key]
        logger.debug(f"工作记忆淘汰: {evict_key}")


class VectorStore:
    """长期记忆向量存储"""
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
        """向量搜索"""
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
        
        for r in results[:top_k]:
            conn.execute(
                "UPDATE long_term_memories SET access_count = access_count + 1, last_access = ? WHERE id = ?",
                (datetime.now().isoformat(), r["id"])
            )
        conn.commit()
        
        return results[:top_k]
    
    def get_all(self) -> List[Dict]:
        """获取所有长期记忆"""
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
        """批量删除"""
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
    """短期记忆记录器"""
    def __init__(self, log_path: str):
        self.log_path = log_path
    
    def log_turn(self, user_msg: str, assistant_msg: str):
        """记录一轮对话"""
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
        """获取最近的对话记录"""
        if not os.path.exists(self.log_path):
            return ""
        
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                content = f.read()
            
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
    """记忆系统主类"""
    
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
        
        db_path = os.path.join(config.memory_dir, "long_term.db")
        self.vector_store = VectorStore(db_path)
        
        session_path = os.path.join(config.memory_dir, config.session_log_file)
        self.session_logger = SessionLogger(session_path)
        
        self.working_memory = WorkingMemory(capacity=config.working_memory_capacity)
        
        self._embedding_cache = {}
        self._cache_lock = threading.Lock()
        
        logger.info(f"记忆系统初始化完成（用户目录: {config.memory_dir}）")
    
    def _is_valid_content(self, content: str) -> bool:
        """检查内容是否有效"""
        if not content:
            return False
        
        content_stripped = content.strip()
        content_lower = content_stripped.lower()
        
        for invalid in self.INVALID_CONTENT_PATTERNS:
            if content_lower == invalid.lower():
                return False
        
        analysis_prefixes = [
            "这是", "属于", "符合", "不符合", "分析", "结论", 
            "从对话中", "用户表示", "用户提供", "用户说",
        ]
        for prefix in analysis_prefixes:
            if content_stripped.startswith(prefix):
                return False
        
        if len(content_stripped) < 3:
            return False
        
        if not re.search(r'[\u4e00-\u9fa5a-zA-Z]', content_stripped):
            return False
            
        return True
    
    def log_session_turn(self, user_msg: str, assistant_msg: str):
        """记录对话"""
        self.session_logger.log_turn(user_msg, assistant_msg)
    
    def _get_embedding(self, text: str) -> List[float]:
        """获取向量"""
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
    
    def save_long_term(self, content: str) -> bool:
        """保存长期记忆"""
        try:
            content = content.strip()
            
            if not self._is_valid_content(content):
                return False
            
            embedding = self._get_embedding(content)
            if not embedding:
                return False
            
            similar = self.vector_store.search(
                embedding, 
                top_k=5,
                min_score=self.config.similarity_threshold
            )
            
            if similar:
                for s in similar:
                    existing = s["content"]
                    if content in existing or existing in content:
                        return True
            
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
            
            session_count = 0
            session_file = os.path.join(self.config.memory_dir, self.config.session_log_file)
            if os.path.exists(session_file):
                with open(session_file, "r", encoding="utf-8") as f:
                    session_count = f.read().count("## ")
            
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


# ============ Agent 管理器 ============

class AgentManager:
    def __init__(self, username: str = "default"):
        self.username = username
        self.agent = None
        self.current_model = None
        self.api_key = None
        self.base_url = None
        self.memory_system = None
        self._assistant_response_buffer = ""
        self._thinking_content = ""
        self._stop_requested = False
        self.reload_config()
    
    def _get_user_memory_dir(self) -> str:
        """获取用户专属的记忆目录"""
        base_dir = os.getenv("MEMORY_DIR", "./memory_data")
        user_dir = os.path.join(base_dir, self.username)
        return user_dir
    
    def reload_config(self):
        """重新加载配置"""
        load_dotenv(override=True)
        
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL")
        
        if not self.api_key:
            raise ValueError("未设置 OPENAI_API_KEY")
        
        if not self.current_model:
            models = self.fetch_models()
            if models:
                self.current_model = models[0]['id']
            else:
                raise ValueError("无法获取模型列表")
        
        # 初始化用户专属记忆系统
        try:
            memory_model = os.getenv("MEMORY_MODEL", "") or self.current_model
            user_memory_dir = self._get_user_memory_dir()
            
            mem_config = MemoryConfig(
                api_key=self.api_key,
                base_url=self.base_url,
                embedding_model=os.getenv("EMBEDDING_MODEL", "embedding-3"),
                chat_model=memory_model,
                memory_dir=user_memory_dir,
                similarity_threshold=float(os.getenv("MEMORY_SIMILARITY_THRESHOLD", "0.75")),
                max_memory_results=int(os.getenv("MEMORY_MAX_RESULTS", "5")),
                min_similarity_score=float(os.getenv("MEMORY_MIN_SCORE", "0.3")),
                session_log_file="session_log.md",
                working_memory_capacity=int(os.getenv("WORKING_MEMORY_CAPACITY", "10"))
            )
            
            self.memory_system = MemorySystem(mem_config)
            self._init_agent()
            
            logger.info(f"用户 {self.username} 的Agent初始化完成")
            
        except Exception as e:
            logger.error(f"初始化记忆系统失败: {e}")
            self.memory_system = None
            self._init_agent_without_memory()
    
    def _init_agent(self):
        """初始化带记忆功能的Agent"""
        try:
            model = OpenAIChatModel(
                model_name=self.current_model,
                provider=OpenAIProvider(
                    api_key=self.api_key,
                    base_url=self.base_url
                )
            )
            
            # 创建工具
            self._create_memory_tools()
            
            self.agent = Agent(
                model,
                system_prompt=CORE_MEMORY_INSTRUCTIONS,
                tools=[self.search_memory_tool, self.save_memory_tool]
            )
            
            logger.info(f"Agent初始化成功（模型: {self.current_model}，用户: {self.username}）")
            
        except Exception as e:
            logger.error(f"Agent初始化失败: {e}")
            self._init_agent_without_memory()
    
    def _init_agent_without_memory(self):
        """初始化不带记忆功能的Agent"""
        try:
            model = OpenAIChatModel(
                model_name=self.current_model,
                provider=OpenAIProvider(
                    api_key=self.api_key,
                    base_url=self.base_url
                )
            )
            
            self.agent = Agent(model, system_prompt="你是一个智能助手，回答要简洁准确。")
            logger.info(f"Agent初始化成功（无记忆功能，模型: {self.current_model}）")
            
        except Exception as e:
            logger.error(f"Agent初始化失败: {e}")
            raise
    
    def _create_memory_tools(self):
        """创建记忆工具"""
        from pydantic_ai import Tool
        
        @Tool
        def search_memory_tool(query: str) -> str:
            """搜索长期记忆中的相关信息。"""
            if not self.memory_system:
                return "记忆系统未启用"
            
            results = self.memory_system.search_long_term(query, top_k=5)
            
            if not results:
                return "未找到相关记忆"
            
            memories = [f"- {r['content']} (相关度: {r['score']:.2f})" for r in results]
            return "找到相关记忆:\n" + "\n".join(memories)
        
        @Tool
        def save_memory_tool(content: str) -> str:
            """保存重要信息到长期记忆。"""
            if not self.memory_system:
                return "记忆系统未启用"
            
            success = self.memory_system.save_long_term(content)
            return "已保存记忆" if success else "保存失败"
        
        self.search_memory_tool = search_memory_tool
        self.save_memory_tool = save_memory_tool
    
    def fetch_models(self) -> List[Dict]:
        """获取可用模型列表"""
        if not self.api_key:
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            base_url = self.base_url or "https://api.openai.com/v1"
            if base_url.endswith('/'):
                base_url = base_url[:-1]
            
            response = requests.get(f"{base_url}/models", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                models = []
                raw_models = data.get('data', data.get('models', []))
                
                for m in raw_models:
                    if isinstance(m, dict):
                        model_id = m.get('id', m.get('name', ''))
                        if model_id:
                            models.append({
                                "id": model_id,
                                "name": m.get('name', model_id),
                                "features": {
                                    "vision": 'vision' in model_id.lower() or 'gpt-4' in model_id.lower(),
                                    "tools": True,
                                    "reasoning": 'reasoning' in model_id.lower() or 'o1' in model_id.lower(),
                                    "fast": 'fast' in model_id.lower() or 'lite' in model_id.lower() or 'mini' in model_id.lower()
                                }
                            })
                    elif isinstance(m, str):
                        models.append({
                            "id": m,
                            "name": m,
                            "features": {
                                "vision": 'vision' in m.lower() or 'gpt-4' in m.lower(),
                                "tools": True,
                                "reasoning": 'reasoning' in m.lower() or 'o1' in m.lower(),
                                "fast": 'fast' in m.lower() or 'lite' in m.lower() or 'mini' in m.lower()
                            }
                        })
                
                models.sort(key=lambda x: x['id'])
                return models
            
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
        
        return []
    
    def switch_model(self, model_id: str):
        """切换模型"""
        self.current_model = model_id
        self._init_agent() if self.memory_system else self._init_agent_without_memory()
        logger.info(f"切换模型: {model_id}")
    
    def stop_generation(self):
        """停止生成"""
        self._stop_requested = True
    
    def chat_stream(self, message: str, history: List[Dict] = None):
        """流式聊天 - 修复版"""
        logger.info(f"用户输入: {message[:50]}... (用户: {self.username})")
        self._assistant_response_buffer = ""
        self._thinking_content = ""
        self._stop_requested = False
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # ===== 自动搜索相关记忆并注入上下文 =====
            final_message = message
            if self.memory_system:
                search_results = self.memory_system.search_long_term(message, top_k=3, min_score=0.3)
                working_context = self.memory_system.working_memory.get_context_text(max_items=5)
                
                memory_parts = []
                
                if search_results:
                    memory_text = "\n".join([f"{i+1}. {r['content']}" for i, r in enumerate(search_results)])
                    memory_parts.append(f"【长期记忆引用】\n{memory_text}\n【长期记忆结束】")
                
                if working_context:
                    memory_parts.append(working_context)
                
                if memory_parts:
                    final_message = f"""{chr(10).join(memory_parts)}

用户问题：{message}"""
                    logger.info(f"已注入 {len(search_results)} 条长期记忆")
            
            msg_history = self._convert_history(history) if history else []
            
            async def stream_async():
                """异步流式生成"""
                async for event in self.agent.run_stream_events(
                    final_message,
                    message_history=msg_history
                ):
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
                        
                        if self.memory_system and self._assistant_response_buffer:
                            try:
                                self.memory_system.log_session_turn(message, self._assistant_response_buffer)
                                logger.debug("已保存会话到短期记忆")
                            except Exception as e:
                                logger.error(f"保存短期记忆失败: {e}")
            
            async_gen = stream_async()
            while True:
                try:
                    if self._stop_requested:
                        yield {"type": "stopped", "message": "用户已停止生成"}
                        break
                    
                    item = loop.run_until_complete(async_gen.__anext__())
                    yield item
                except StopAsyncIteration:
                    break
                    
        except Exception as e:
            logger.error(f"流式响应错误: {e}", exc_info=True)
            yield {"type": "error", "content": f"错误: {str(e)}"}
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
                # 清理思考过程
                if '<thinking>' in content and '</thinking>' in content:
                    content = re.sub(r'<thinking>[\s\S]*?</thinking>', '', content).strip()
                messages.append(ModelResponse(parts=[TextPart(content=content)]))
        return messages
    
    def get_memory_stats(self) -> Dict:
        """获取记忆统计"""
        if self.memory_system:
            return self.memory_system.get_stats()
        return {"long_term": 0, "short_term": 0, "working": 0, "total": 0}
    
    def export_long_term_memories(self) -> List[Dict]:
        """导出长期记忆"""
        if self.memory_system:
            return self.memory_system.vector_store.get_all()
        return []
    
    def export_working_memories(self) -> List[Dict]:
        """导出工作记忆"""
        if self.memory_system:
            return self.memory_system.working_memory.get_all()
        return []
    
    def add_working_memory(self, key: str, value: str, priority: int = 0) -> Dict:
        """添加工作记忆"""
        if self.memory_system:
            success = self.memory_system.working_memory.add(key, value, priority)
            return {"success": success}
        return {"success": False, "error": "记忆系统未启用"}
    
    def delete_memories(self, memory_type: str, memory_ids: List[str]) -> Dict:
        """批量删除记忆"""
        if not self.memory_system:
            return {"success": False, "error": "记忆系统未启用"}
        
        if memory_type == 'long':
            count = self.memory_system.vector_store.delete_many(memory_ids)
            return {"success": True, "deleted_count": count}
        elif memory_type == 'working':
            count = 0
            for mid in memory_ids:
                if self.memory_system.working_memory.remove(mid):
                    count += 1
            return {"success": True, "deleted_count": count}
        
        return {"success": False, "error": "未知的记忆类型"}
    
    def clear_memory(self, memory_type: str) -> Dict:
        """清空记忆"""
        if not self.memory_system:
            return {"success": False, "error": "记忆系统未启用"}
        
        if memory_type == 'long':
            count = self.memory_system.vector_store.clear_all()
            return {"success": True, "deleted_count": count}
        elif memory_type == 'working':
            self.memory_system.working_memory.clear()
            return {"success": True}
        elif memory_type == 'short':
            self.memory_system.session_logger.clear()
            return {"success": True}
        
        return {"success": False, "error": "未知的记忆类型"}
