"""
记忆系统 V2 - 参考OpenClaw设计的三层记忆架构

架构说明:
1. 工作记忆(Working Memory): 当前对话的即时上下文，保持在LLM上下文窗口内
2. 会话记忆(Session Memory): 近期对话历史，按日期分割存储
3. 长期记忆(Long-term Memory): 重要信息持久化，向量索引 + Markdown双存储

作者: AI Assistant
版本: 2.0
"""

import os
import re
import json
import hashlib
import sqlite3
import threading
import math
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from pathlib import Path
from contextlib import contextmanager
import logging

import numpy as np
from openai import OpenAI

logger = logging.getLogger(__name__)


# ============ 配置类 ============

@dataclass
class MemoryConfig:
    """记忆系统配置"""
    # API配置
    api_key: str
    base_url: str
    embedding_model: str = "embedding-3"
    chat_model: str = "glm-4-plus"
    
    # 存储路径
    memory_dir: str = "./memory_data"
    
    # 检索配置
    similarity_threshold: float = 0.75
    max_memory_results: int = 5
    min_similarity_score: float = 0.3
    
    # 时间衰减配置
    time_decay_enabled: bool = True
    time_decay_half_life: int = 30  # 半衰期（天）
    
    # 记忆容量配置
    max_working_memory_turns: int = 10
    max_session_memory_days: int = 30
    max_long_term_memories: int = 1000
    
    # 记忆处理配置
    memory_process_interval: int = 100  # 每100轮对话处理一次
    auto_forget_enabled: bool = True
    forget_threshold_days: int = 90


# ============ 数据库管理类 ============

class DatabaseManager:
    """数据库连接管理器 - 解决连接泄漏问题"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()
    
    @contextmanager
    def get_connection(self):
        """上下文管理器方式获取连接，确保正确关闭"""
        conn = None
        try:
            if not hasattr(self._local, 'conn') or self._local.conn is None:
                self._local.conn = sqlite3.connect(
                    self.db_path, 
                    check_same_thread=False,
                    timeout=30.0
                )
                self._local.conn.row_factory = sqlite3.Row
            conn = self._local.conn
            yield conn
        except Exception as e:
            logger.error(f"数据库操作错误: {e}")
            raise
    
    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 长期记忆表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS long_term_memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                embedding BLOB,
                importance REAL DEFAULT 0.5,
                access_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_access TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 会话记忆表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                date TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                processed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 记忆处理日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory_process_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                process_type TEXT NOT NULL,
                processed_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ltm_category ON long_term_memories(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ltm_importance ON long_term_memories(importance)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sm_session ON session_memories(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sm_date ON session_memories(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sm_processed ON session_memories(processed)")
        
        conn.commit()
        conn.close()
    
    def close_all(self):
        """关闭所有连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# ============ 向量存储类 ============

class VectorStore:
    """向量存储 - 支持高效的向量检索"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._embedding_cache: Dict[str, List[float]] = {}
        self._cache_lock = threading.Lock()
        self._cache_max_size = 1000
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        return hashlib.md5(text.encode()).hexdigest()
    
    def add_embedding(self, memory_id: str, content: str, embedding: List[float], table: str = "long_term"):
        """添加向量和内容"""
        emb_bytes = np.array(embedding, dtype=np.float32).tobytes()
        
        with self.db.get_connection() as conn:
            if table == "long_term":
                conn.execute(
                    "UPDATE long_term_memories SET embedding = ? WHERE id = ?",
                    (emb_bytes, memory_id)
                )
            else:
                conn.execute(
                    "UPDATE session_memories SET embedding = ? WHERE id = ?",
                    (emb_bytes, memory_id)
                )
            conn.commit()
    
    def search(
        self, 
        query_embedding: List[float], 
        top_k: int = 5,
        min_score: float = 0.3,
        table: str = "long_term",
        category: Optional[str] = None,
        time_decay: bool = False,
        half_life_days: int = 30
    ) -> List[Dict]:
        """
        向量搜索 - 支持时间衰减
        
        Args:
            query_embedding: 查询向量
            top_k: 返回结果数量
            min_score: 最低相似度阈值
            table: 搜索的表
            category: 分类过滤
            time_decay: 是否启用时间衰减
            half_life_days: 时间衰减半衰期
        """
        results = []
        query_vec = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        
        if query_norm == 0:
            return results
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            if table == "long_term":
                if category:
                    cursor.execute(
                        "SELECT id, content, embedding, importance, access_count, created_at, last_access "
                        "FROM long_term_memories WHERE category = ? AND embedding IS NOT NULL",
                        (category,)
                    )
                else:
                    cursor.execute(
                        "SELECT id, content, embedding, importance, access_count, created_at, last_access "
                        "FROM long_term_memories WHERE embedding IS NOT NULL"
                    )
            else:
                cursor.execute(
                    "SELECT id, content, embedding, created_at "
                    "FROM session_memories WHERE embedding IS NOT NULL AND processed = 0"
                )
            
            now = datetime.now()
            
            for row in cursor:
                mem_id = row['id']
                content = row['content']
                emb_bytes = row['embedding']
                
                if emb_bytes is None:
                    continue
                
                mem_vec = np.frombuffer(emb_bytes, dtype=np.float32)
                mem_norm = np.linalg.norm(mem_vec)
                
                if mem_norm == 0:
                    continue
                
                # 余弦相似度
                similarity = np.dot(query_vec, mem_vec) / (query_norm * mem_norm)
                
                if similarity < min_score:
                    continue
                
                # 计算综合得分
                score = float(similarity)
                
                if time_decay and table == "long_term":
                    # 时间衰减因子
                    created_at = datetime.fromisoformat(row['created_at']) if row['created_at'] else now
                    days_old = (now - created_at).days
                    decay_factor = math.exp(-days_old * math.log(2) / half_life_days)
                    
                    # 访问频率因子
                    access_count = row['access_count'] or 0
                    access_factor = 1 + math.log1p(access_count) * 0.1
                    
                    # 重要性因子
                    importance = row['importance'] or 0.5
                    
                    # 综合得分
                    score = similarity * decay_factor * access_factor * (0.5 + importance * 0.5)
                
                results.append({
                    "id": mem_id,
                    "content": content,
                    "score": score,
                    "raw_similarity": float(similarity)
                })
        
        # 按综合得分排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]
    
    def update_access(self, memory_id: str):
        """更新记忆的访问计数"""
        with self.db.get_connection() as conn:
            conn.execute(
                """UPDATE long_term_memories 
                   SET access_count = access_count + 1, 
                       last_access = ? 
                   WHERE id = ?""",
                (datetime.now().isoformat(), memory_id)
            )
            conn.commit()
    
    def cache_embedding(self, text: str, embedding: List[float]):
        """缓存向量"""
        with self._cache_lock:
            key = self._get_cache_key(text)
            if len(self._embedding_cache) >= self._cache_max_size:
                # 清理一半缓存
                keys = list(self._embedding_cache.keys())
                for k in keys[:len(keys)//2]:
                    del self._embedding_cache[k]
            self._embedding_cache[key] = embedding
    
    def get_cached_embedding(self, text: str) -> Optional[List[float]]:
        """获取缓存的向量"""
        with self._cache_lock:
            key = self._get_cache_key(text)
            return self._embedding_cache.get(key)


# ============ 记忆分类器 ============

class MemoryClassifier:
    """记忆分类器 - 判断记忆重要性和分类"""
    
    INVALID_PATTERNS = [
        "无内容", "暂无内容", "没有内容", "无", "没有", "暂无", "未知", "空",
        "无可奉告", "未提供", "未提及", "无信息", "用户未", "没有提供",
        "未说明", "未告知", "null", "none", "empty", "n/a", "na"
    ]
    
    CATEGORY_KEYWORDS = {
        "identity": ["我叫", "我的名字", "我是", "我是一名", "职业", "工作", "年龄", "岁", "住在", "地址"],
        "preference": ["喜欢", "爱好", "偏好", "讨厌", "厌恶", "不喜欢", "最爱", "最讨厌"],
        "schedule": ["明天", "下周", "计划", "约定", "会议", "安排", "日程", "提醒我"],
        "important": ["记住", "别忘了", "重要", "记住这", "帮我记", "一定要"],
        "project": ["项目", "正在做", "开发", "研究", "学习", "写", "创作"]
    }
    
    @classmethod
    def is_valid_content(cls, content: str) -> bool:
        """检查内容是否有效"""
        if not content or len(content.strip()) < 3:
            return False
        
        content_lower = content.strip().lower()
        
        for pattern in cls.INVALID_PATTERNS:
            if content_lower == pattern.lower():
                return False
        
        # 必须包含至少一个中文字符或英文单词
        if not re.search(r'[\u4e00-\u9fa5]|[a-zA-Z]{2,}', content):
            return False
        
        return True
    
    @classmethod
    def classify(cls, content: str) -> Tuple[str, float]:
        """
        分类记忆内容并评估重要性
        
        Returns:
            (category, importance): 分类和重要性分数(0-1)
        """
        content_lower = content.lower()
        category = "general"
        importance = 0.3
        
        # 匹配分类关键词
        for cat, keywords in cls.CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in content_lower:
                    category = cat
                    importance = max(importance, 0.6)
                    break
        
        # 重要关键词提升重要性
        important_markers = ["重要", "必须", "一定", "记住", "千万别"]
        for marker in important_markers:
            if marker in content:
                importance = min(1.0, importance + 0.3)
                break
        
        return category, importance


# ============ 三层记忆系统 ============

class MemorySystem:
    """
    三层记忆系统
    
    1. 工作记忆(Working Memory): 当前对话上下文
    2. 会话记忆(Session Memory): 近期对话历史
    3. 长期记忆(Long-term Memory): 重要信息持久化
    """
    
    def __init__(self, config: MemoryConfig):
        self.config = config
        
        # 初始化OpenAI客户端
        self.client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        
        # 确保目录存在
        Path(config.memory_dir).mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库和向量存储
        db_path = os.path.join(config.memory_dir, "memory.db")
        self.db = DatabaseManager(db_path)
        self.vector_store = VectorStore(self.db)
        
        # 长期记忆Markdown文件路径
        self.memory_md_path = os.path.join(config.memory_dir, "MEMORY.md")
        
        # 工作记忆（内存中）
        self._working_memory: List[Dict] = []
        self._working_memory_lock = threading.Lock()
        
        # 初始化MEMORY.md
        self._init_memory_md()
        
        logger.info("记忆系统初始化完成（三层架构：工作记忆 + 会话记忆 + 长期记忆）")
    
    def _init_memory_md(self):
        """初始化MEMORY.md文件"""
        if not os.path.exists(self.memory_md_path):
            default_content = """# 长期记忆存储

此文件由AI智能体自动维护，存储重要的用户信息。

## 用户画像 (User Profile)

<!-- 用户身份信息 -->

## 偏好设置 (Preferences)

<!-- 用户偏好和习惯 -->

## 重要事件 (Important Events)

<!-- 重要约定和事件 -->

## 项目信息 (Projects)

<!-- 进行中的项目 -->
"""
            with open(self.memory_md_path, 'w', encoding='utf-8') as f:
                f.write(default_content)
    
    # ============ 向量获取 ============
    
    def _get_embedding(self, text: str) -> List[float]:
        """获取文本向量（带缓存）"""
        # 先检查缓存
        cached = self.vector_store.get_cached_embedding(text)
        if cached:
            return cached
        
        try:
            response = self.client.embeddings.create(
                model=self.config.embedding_model,
                input=text[:8000]
            )
            embedding = response.data[0].embedding
            
            # 缓存结果
            self.vector_store.cache_embedding(text, embedding)
            
            return embedding
        except Exception as e:
            logger.error(f"获取向量失败: {e}")
            return []
    
    # ============ 工作记忆 ============
    
    def add_to_working_memory(self, role: str, content: str):
        """添加到工作记忆"""
        with self._working_memory_lock:
            self._working_memory.append({
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat()
            })
            
            # 限制工作记忆大小
            max_turns = self.config.max_working_memory_turns
            if len(self._working_memory) > max_turns * 2:
                # 保留最近的消息
                self._working_memory = self._working_memory[-max_turns * 2:]
    
    def get_working_memory(self) -> List[Dict]:
        """获取工作记忆"""
        with self._working_memory_lock:
            return list(self._working_memory)
    
    def clear_working_memory(self):
        """清空工作记忆"""
        with self._working_memory_lock:
            self._working_memory = []
    
    # ============ 会话记忆 ============
    
    def add_to_session_memory(self, session_id: str, role: str, content: str) -> str:
        """
        添加到会话记忆
        
        Returns:
            memory_id: 记忆ID
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO session_memories 
                   (session_id, date, role, content, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, date_str, role, content, datetime.now().isoformat())
            )
            memory_id = cursor.lastrowid
            conn.commit()
        
        # 异步获取向量
        try:
            embedding = self._get_embedding(content)
            if embedding:
                self.vector_store.add_embedding(str(memory_id), content, embedding, table="session")
        except Exception as e:
            logger.warning(f"获取会话记忆向量失败: {e}")
        
        return str(memory_id)
    
    def get_recent_session_memories(self, days: int = 7, limit: int = 100) -> List[Dict]:
        """获取最近的会话记忆"""
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, session_id, date, role, content, created_at
                   FROM session_memories 
                   WHERE date >= ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (cutoff_date, limit)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    # ============ 长期记忆 ============
    
    def save_long_term_memory(
        self, 
        content: str, 
        category: Optional[str] = None,
        importance: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        保存长期记忆
        
        Args:
            content: 记忆内容
            category: 分类（可选，自动检测）
            importance: 重要性（可选，自动评估）
        
        Returns:
            (success, message): 保存结果
        """
        # 验证内容
        if not MemoryClassifier.is_valid_content(content):
            return False, "内容无效，拒绝保存"
        
        content = content.strip()
        
        # 自动分类和评估重要性
        if category is None or importance is None:
            auto_category, auto_importance = MemoryClassifier.classify(content)
            category = category or auto_category
            importance = importance or auto_importance
        
        # 获取向量
        embedding = self._get_embedding(content)
        if not embedding:
            return False, "获取向量失败"
        
        # 检查相似记忆
        similar = self.vector_store.search(
            embedding,
            top_k=3,
            min_score=self.config.similarity_threshold,
            time_decay=False
        )
        
        with self.db.get_connection() as conn:
            # 处理相似记忆
            if similar:
                # 检查是否是完全重复
                for s in similar:
                    if s["raw_similarity"] > 0.95:
                        return True, "记忆已存在（高度相似）"
                
                # 合并相似记忆
                if len(similar) >= 1 and similar[0]["raw_similarity"] > 0.8:
                    merged = self._merge_memories(content, [s["content"] for s in similar])
                    if merged and merged != content:
                        content = merged
                        # 删除旧记忆
                        for s in similar:
                            conn.execute("DELETE FROM long_term_memories WHERE id = ?", (s["id"],))
            
            # 生成ID
            memory_id = hashlib.md5(f"{content}{datetime.now()}".encode()).hexdigest()
            
            # 保存到数据库
            emb_bytes = np.array(embedding, dtype=np.float32).tobytes()
            conn.execute(
                """INSERT OR REPLACE INTO long_term_memories 
                   (id, content, category, embedding, importance, created_at, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (memory_id, content, category, emb_bytes, importance, 
                 datetime.now().isoformat(), datetime.now().isoformat())
            )
            conn.commit()
        
        # 更新MEMORY.md
        self._update_memory_md(content, category)
        
        logger.info(f"保存长期记忆: {content[:60]}...")
        return True, memory_id
    
    def _merge_memories(self, new_content: str, old_contents: List[str]) -> Optional[str]:
        """合并记忆"""
        try:
            prompt = f"""请将以下记忆信息合并为一条准确、完整的记忆，去除冗余描述。

已有记忆:
{chr(10).join(f"- {c}" for c in old_contents)}

新信息:
- {new_content}

要求:
1. 去除重复和冗余描述
2. 保留所有关键事实
3. 直接输出合并后的陈述，不要添加解释
4. 控制在100字以内

合并结果:"""

            response = self.client.chat.completions.create(
                model=self.config.chat_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200
            )
            
            merged = response.choices[0].message.content.strip()
            merged = merged.lstrip("- •").strip()
            
            if len(merged) > 200:
                merged = merged[:200]
            
            return merged if MemoryClassifier.is_valid_content(merged) else None
            
        except Exception as e:
            logger.error(f"合并记忆失败: {e}")
            return None
    
    def _update_memory_md(self, content: str, category: str):
        """更新MEMORY.md文件"""
        section_map = {
            "identity": "## 用户画像 (User Profile)",
            "preference": "## 偏好设置 (Preferences)",
            "schedule": "## 重要事件 (Important Events)",
            "important": "## 重要事件 (Important Events)",
            "project": "## 项目信息 (Projects)",
            "general": "## 其他信息 (Other)"
        }
        
        target_section = section_map.get(category, "## 其他信息 (Other)")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        try:
            with open(self.memory_md_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # 在对应章节添加内容
            if target_section in file_content:
                lines = file_content.split('\n')
                new_lines = []
                inserted = False
                
                for i, line in enumerate(lines):
                    new_lines.append(line)
                    if line.strip() == target_section and not inserted:
                        # 检查下一节的位置
                        for j in range(i + 1, len(lines)):
                            if lines[j].startswith('## ') and lines[j] != target_section:
                                new_lines.append(f"- {content} (记录于 {timestamp})")
                                inserted = True
                                break
                            elif j == len(lines) - 1:
                                new_lines.append(f"- {content} (记录于 {timestamp})")
                                inserted = True
                                break
                
                if inserted:
                    with open(self.memory_md_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(new_lines))
                        
        except Exception as e:
            logger.error(f"更新MEMORY.md失败: {e}")
    
    def search_long_term_memory(
        self, 
        query: str, 
        top_k: int = None,
        category: Optional[str] = None
    ) -> List[Dict]:
        """
        搜索长期记忆
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            category: 分类过滤
        """
        top_k = top_k or self.config.max_memory_results
        
        embedding = self._get_embedding(query)
        if not embedding:
            return []
        
        results = self.vector_store.search(
            embedding,
            top_k=top_k,
            min_score=self.config.min_similarity_score,
            category=category,
            time_decay=self.config.time_decay_enabled,
            half_life_days=self.config.time_decay_half_life
        )
        
        # 更新访问计数
        for r in results:
            self.vector_store.update_access(r["id"])
        
        return results
    
    # ============ 记忆处理 ============
    
    def process_session_to_long_term(self, force: bool = False) -> int:
        """
        将未处理的会话记忆转为长期记忆
        
        Args:
            force: 是否强制处理（忽略处理间隔）
        
        Returns:
            提取的长期记忆数量
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # 检查处理间隔
            if not force:
                cursor.execute(
                    "SELECT COUNT(*) FROM session_memories WHERE processed = 0"
                )
                unprocessed_count = cursor.fetchone()[0]
                if unprocessed_count < self.config.memory_process_interval:
                    return 0
            
            # 获取未处理的用户消息
            cursor.execute(
                """SELECT id, content FROM session_memories 
                   WHERE role = 'user' AND processed = 0
                   ORDER BY created_at DESC
                   LIMIT 100"""
            )
            messages = cursor.fetchall()
        
        if not messages:
            return 0
        
        logger.info(f"开始处理 {len(messages)} 条会话记忆...")
        
        # 批量提取重要信息
        important_facts = self._extract_important_facts([m['content'] for m in messages])
        
        saved_count = 0
        for fact in important_facts:
            if MemoryClassifier.is_valid_content(fact):
                success, _ = self.save_long_term_memory(fact)
                if success:
                    saved_count += 1
        
        # 标记为已处理
        with self.db.get_connection() as conn:
            message_ids = [m['id'] for m in messages]
            conn.execute(
                f"UPDATE session_memories SET processed = 1 WHERE id IN ({','.join('?' * len(message_ids))})",
                message_ids
            )
            
            # 记录处理日志
            conn.execute(
                "INSERT INTO memory_process_log (process_type, processed_count) VALUES (?, ?)",
                ("session_to_long_term", len(messages))
            )
            conn.commit()
        
        logger.info(f"从会话记忆提取了 {saved_count} 条长期记忆")
        return saved_count
    
    def _extract_important_facts(self, messages: List[str]) -> List[str]:
        """从消息中提取重要事实"""
        if not messages:
            return []
        
        # 批量处理
        batch_size = 10
        all_facts = []
        
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i+batch_size]
            
            prompt = f"""分析以下对话内容，提取应该被长期记住的重要信息。

对话内容:
{chr(10).join(f"- {m[:300]}" for m in batch if m.strip())}

重要信息标准（仅提取符合标准的信息）:
1. 用户身份信息（姓名、职业、年龄、所在地）
2. 用户明确要求记住的内容
3. 用户的偏好和习惯（喜好、厌恶）
4. 重要的约定、计划或承诺
5. 对理解用户背景至关重要的个人信息

输出要求:
- 每行一条独立事实，直接陈述
- 例如："用户是软件工程师"、"用户喜欢吃辣"
- 无重要信息时留空，不要输出提示词

提取结果:"""

            try:
                response = self.client.chat.completions.create(
                    model=self.config.chat_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=500
                )
                
                result = response.choices[0].message.content.strip()
                
                if result:
                    for line in result.split('\n'):
                        line = line.strip().lstrip("- •").strip()
                        if line and len(line) > 5:
                            all_facts.append(line)
                            
            except Exception as e:
                logger.error(f"提取重要事实失败: {e}")
                continue
        
        # 去重
        unique_facts = []
        seen = set()
        for fact in all_facts:
            fact_hash = hashlib.md5(fact.encode()).hexdigest()
            if fact_hash not in seen:
                seen.add(fact_hash)
                unique_facts.append(fact)
        
        return unique_facts
    
    # ============ 记忆遗忘 ============
    
    def forget_old_memories(self, days: int = None) -> int:
        """
        清理过期记忆
        
        Args:
            days: 过期天数
        
        Returns:
            删除的记忆数量
        """
        days = days or self.config.forget_threshold_days
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        deleted = 0
        
        with self.db.get_connection() as conn:
            # 删除过期的会话记忆
            cursor = conn.execute(
                "DELETE FROM session_memories WHERE date < ? AND processed = 1",
                (cutoff,)
            )
            deleted += cursor.rowcount
            
            # 删除低重要性且长期未访问的长期记忆
            cursor = conn.execute(
                """DELETE FROM long_term_memories 
                   WHERE importance < 0.3 
                   AND last_access < ?
                   AND access_count = 0""",
                (cutoff,)
            )
            deleted += cursor.rowcount
            
            conn.commit()
        
        if deleted > 0:
            logger.info(f"清理了 {deleted} 条过期记忆")
        
        return deleted
    
    # ============ 统计和导出 ============
    
    def get_stats(self) -> Dict[str, Any]:
        """获取记忆系统统计"""
        stats = {
            "working_memory_turns": len(self._working_memory),
            "session_memories": 0,
            "long_term_memories": 0,
            "categories": {},
            "oldest_memory": None,
            "newest_memory": None
        }
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # 会话记忆统计
            cursor.execute("SELECT COUNT(*) FROM session_memories")
            stats["session_memories"] = cursor.fetchone()[0]
            
            # 长期记忆统计
            cursor.execute("SELECT COUNT(*) FROM long_term_memories")
            stats["long_term_memories"] = cursor.fetchone()[0]
            
            # 分类统计
            cursor.execute(
                "SELECT category, COUNT(*) FROM long_term_memories GROUP BY category"
            )
            stats["categories"] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 时间范围
            cursor.execute(
                "SELECT MIN(created_at), MAX(created_at) FROM long_term_memories"
            )
            row = cursor.fetchone()
            if row and row[0]:
                stats["oldest_memory"] = row[0]
                stats["newest_memory"] = row[1]
        
        return stats
    
    def export_long_term_memories(self) -> List[Dict]:
        """导出所有长期记忆"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, content, category, importance, access_count, 
                          created_at, last_access
                   FROM long_term_memories 
                   ORDER BY importance DESC, created_at DESC"""
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_memory(self, memory_id: str) -> bool:
        """删除指定记忆"""
        try:
            with self.db.get_connection() as conn:
                conn.execute("DELETE FROM long_term_memories WHERE id = ?", (memory_id,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            return False
    
    def close(self):
        """关闭记忆系统"""
        self.db.close_all()
        logger.info("记忆系统已关闭")


# ============ 单例管理 ============

_memory_instance: Optional[MemorySystem] = None
_memory_lock = threading.Lock()


def get_memory_system(config: Optional[MemoryConfig] = None) -> Optional[MemorySystem]:
    """获取记忆系统单例"""
    global _memory_instance
    if _memory_instance is None and config is not None:
        with _memory_lock:
            if _memory_instance is None:
                _memory_instance = MemorySystem(config)
    return _memory_instance


def reset_memory_system():
    """重置记忆系统单例"""
    global _memory_instance
    if _memory_instance:
        _memory_instance.close()
        _memory_instance = None
