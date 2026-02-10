import hashlib
from log import logger
from datetime import datetime, timedelta 
from openai import OpenAI

from config import (
    init_filesystem,
    MEMORY_FILE,
    DAILY_MEMORY_DIR,
    EMBEDDING_MODEL,
    MERGE_SIMILARITY_THRESHOLD,
    MERGE_INTERVAL_DAYS,
    LAST_MERGE_FILE
)
from .database import DatabaseManager
from .embedding import EmbeddingManager
from .search import SearchEngine
from .merge import MergeManager


class MemorySystem:
    def __init__(self, api_key, base_url, embedding_model=None, merge_threshold=None, merge_interval_days=None, memory_dir=None):
        """
        初始化记忆系统
        
        Args:
            api_key: API密钥
            base_url: API地址
            embedding_model: 嵌入模型名称
            merge_threshold: 相似度阈值（0.5-0.8）
            merge_interval_days: 定期整理间隔（天）
            memory_dir: 记忆存储路径（默认 ~/.ai_memory）
        """
        self.api_key = api_key
        self.base_url = base_url
        self.embedding_model = embedding_model or EMBEDDING_MODEL
        self.merge_threshold = merge_threshold or MERGE_SIMILARITY_THRESHOLD
        self.merge_interval_days = merge_interval_days or MERGE_INTERVAL_DAYS
        
        # 初始化 OpenAI 客户端
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        
        # 初始化文件系统
        self.paths = init_filesystem()
        
        # 初始化各模块
        self.db_manager = DatabaseManager(self.paths["memory_db"])
        self.embedding_manager = EmbeddingManager(self.client, self.embedding_model, self.db_manager)
        self.search_engine = SearchEngine(self.embedding_manager, self.db_manager)
        self.merge_manager = MergeManager(
            self.client, self.db_manager, self.embedding_manager,
            self.merge_threshold, self.merge_interval_days
        )
    
    def save_memory(self, text, memory_type="short"):
        """
        智能保存记忆
        
        Args:
            text: 要保存的文本
            memory_type: "long" (MEMORY.md + 数据库) 或 "short" (仅 daily/日期.md)
        """
        if memory_type == "long":
            # === 长期记忆：实时去重 + 向量化 ===
            similar = self.search_engine.search(text, top_k=3, min_score=self.merge_threshold)
            
            if similar:
                logger.debug(f"检测到 {len(similar)} 条相似记忆，智能合并中...")
                
                try:
                    # 1. 智能合并
                    merged_text = self.merge_manager.smart_merge(text, similar)
                    
                    # 2. 删除旧记忆（文件）
                    content = MEMORY_FILE.read_text(encoding='utf-8')
                    lines = content.split('\n')
                    new_lines = []
                    
                    for line in lines:
                        # 检查是否包含要删除的旧记忆
                        should_keep = True
                        for s in similar:
                            if s['text'] in line:
                                should_keep = False
                                break
                        if should_keep:
                            new_lines.append(line)
                    
                    content = '\n'.join(new_lines)
                    MEMORY_FILE.write_text(content, encoding='utf-8')
                    
                    # 3. 写入合并后的新记忆
                    with open(MEMORY_FILE, 'a', encoding='utf-8') as f:
                        f.write(f"{merged_text} (更新于 {datetime.now().strftime('%Y-%m-%d %H:%M')})")
                    
                    # 4. 删除旧向量
                    for s in similar:
                        self.db_manager.delete_chunk(s['id'])
                    
                    logger.info(f"已合并更新: {merged_text[:60]}...")
                    text = merged_text
                    
                except Exception as e:
                    logger.warning(f"合并失败，降级为追加模式: {e}")
                    with open(MEMORY_FILE, 'a', encoding='utf-8') as f:
                        f.write(f"{text} (记录于 {datetime.now().strftime('%Y-%m-%d %H:%M')})")
            else:
                # 没有相似内容，直接追加
                with open(MEMORY_FILE, 'a', encoding='utf-8') as f:
                    f.write(f"{text} (记录于 {datetime.now().strftime('%Y-%m-%d %H:%M')})")
            
            # === 向量化并存入数据库（只有长期记忆） ===
            embedding = self.embedding_manager.get_embedding(text)
            if embedding:
                chunk_id = hashlib.md5(f"{text}{datetime.now()}".encode()).hexdigest()
                self.db_manager.save_chunk(chunk_id, "MEMORY.md", text, embedding)
            
            logger.info(f"已保存长期记忆（已向量化）")
                
        else:
            # === 短期记忆：只存文件，不向量化 ===
            today = datetime.now().strftime("%Y-%m-%d")
            daily_file = DAILY_MEMORY_DIR / f"{today}.md"
            
            if not daily_file.exists():
                daily_file.write_text(f"# {today} 记忆日志\n\n", encoding='utf-8')
            
            with open(daily_file, 'a', encoding='utf-8') as f:
                f.write(f"{text}\n")  # 保持完整上下文格式
            
            logger.debug(f"已保存短期记忆（仅文件，未向量化）{daily_file}")
    
    def search_memory(self, query, top_k=5, min_score=0.3):
        """
        搜索记忆
        
        Args:
            query: 搜索查询
            top_k: 返回结果数量
            min_score: 最低分数阈值
        
        Returns:
            [{"text": "...", "path": "...", "score": 0.85}, ...]
        """
        return self.search_engine.search(query, top_k, min_score)
    
    def should_merge(self):
        """检查是否需要定期整理"""
        return self.merge_manager.should_merge()
    
    def deep_merge_all(self):
        """深度整理所有长期记忆（定期任务）"""
        self.merge_manager.deep_merge_all()
    
    def check_and_auto_merge(self):
        """启动时检查并自动整理"""
        if self.should_merge():
            days = 999 if not LAST_MERGE_FILE.exists() else (datetime.now() - datetime.fromtimestamp(LAST_MERGE_FILE.stat().st_mtime)).days
            
            logger.debug(f"距离上次整理已过 {days} 天，触发自动整理...")
            self.deep_merge_all()
        else:
            last_merge = datetime.fromtimestamp(LAST_MERGE_FILE.stat().st_mtime)
            next_merge = last_merge + timedelta(days=self.merge_interval_days)  # 修复这里
            days_left = (next_merge - datetime.now()).days
            logger.debug(f"记忆状态良好，下次整理: {next_merge.strftime('%Y-%m-%d')} ({days_left}天后)")
    
    def get_long_term_memory(self):
        """读取完整长期记忆（用于注入上下文）"""
        if MEMORY_FILE.exists():
            return MEMORY_FILE.read_text(encoding='utf-8')
        return ""
    
    def get_stats(self):
        """获取记忆统计信息"""
        # 长期记忆数（数据库中的）
        long_term = self.db_manager.get_chunk_count_by_path("MEMORY.md")
        
        # 短期记忆文件数
        daily_files = len(list(DAILY_MEMORY_DIR.glob("*.md")))
        
        # 长期记忆文件行数
        if MEMORY_FILE.exists():
            content = MEMORY_FILE.read_text(encoding='utf-8')
            long_term_lines = len([l for l in content.split('\n') if l.strip().startswith('- ')])
        else:
            long_term_lines = 0
        
        return {
            "long_term_indexed": long_term,  # 数据库中的长期记忆
            "long_term_total": long_term_lines,  # 文件中的长期记忆
            "daily_files": daily_files  # 短期记忆天数
        }
    
    def auto_index(self):
        """自动索引长期记忆文件（短期记忆不索引）"""
        logger.debug("索引长期记忆...")
        
        if not MEMORY_FILE.exists():
            logger.warning("长期记忆文件不存在")
            return
        
        content = MEMORY_FILE.read_text(encoding='utf-8')
        
        # 按段落分块
        paragraphs = [p.strip() for p in content.split('\n') if p.strip() and p.startswith('- ')]
        
        for para in paragraphs:
            # 去除前缀 "- "
            para_clean = para.lstrip('- ').strip()
            
            # 检查是否已存在
            para_hash = hashlib.md5(para_clean.encode()).hexdigest()
            
            # 检查是否已存在（简化检查）
            chunks = self.db_manager.get_all_chunks()
            exists = any(chunk_id == para_hash for chunk_id, _, _, _ in chunks)
            
            if not exists:
                embedding = self.embedding_manager.get_embedding(para_clean)
                if embedding:
                    self.db_manager.save_chunk(para_hash, "MEMORY.md", para_clean, embedding)
        
        logger.debug(f"已索引 {len(paragraphs)} 条长期记忆")