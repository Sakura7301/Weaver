"""
数据库操作模块
"""

import sqlite3
import json
from datetime import datetime
from config import MEMORY_DB

class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path=MEMORY_DB):
        self.db_path = db_path
        self._init_tables()
    
    def _init_tables(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 文本块表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                path TEXT,
                text TEXT,
                embedding TEXT,
                timestamp TEXT
            )
        """)
        
        # 嵌入缓存表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                text_hash TEXT PRIMARY KEY,
                embedding TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def save_chunk(self, chunk_id, path, text, embedding, timestamp=None):
        """保存文本块到数据库"""
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO chunks (id, path, text, embedding, timestamp) VALUES (?, ?, ?, ?, ?)",
            (chunk_id, path, text, json.dumps(embedding), timestamp)
        )
        conn.commit()
        conn.close()
    
    def delete_chunk(self, chunk_id):
        """删除文本块"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chunks WHERE id = ?", (chunk_id,))
        conn.commit()
        conn.close()
    
    def delete_chunks_by_path(self, path):
        """删除指定路径的所有文本块"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chunks WHERE path = ?", (path,))
        conn.commit()
        conn.close()
    
    def get_all_chunks(self):
        """获取所有文本块"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, path, text, embedding FROM chunks")
        rows = cursor.fetchall()
        conn.close()
        return rows
    
    def get_chunk_count_by_path(self, path):
        """获取指定路径的文本块数量"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE path = ?", (path,))
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def save_embedding_cache(self, text_hash, embedding):
        """保存嵌入缓存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO embedding_cache (text_hash, embedding) VALUES (?, ?)",
            (text_hash, json.dumps(embedding))
        )
        conn.commit()
        conn.close()
    
    def get_embedding_cache(self, text_hash):
        """获取嵌入缓存"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT embedding FROM embedding_cache WHERE text_hash = ?", (text_hash,))
        row = cursor.fetchone()
        conn.close()
        return json.loads(row[0]) if row else None