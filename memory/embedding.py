"""
向量嵌入相关功能
"""

import hashlib
from log import logger

class EmbeddingManager:
    """嵌入管理器"""
    
    def __init__(self, client, model="embedding-3", db_manager=None):
        self.client = client
        self.model = model
        self.db_manager = db_manager
    
    def get_embedding(self, text, use_cache=True):
        """获取文本向量（带缓存）"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # 检查缓存
        if use_cache and self.db_manager:
            cached = self.db_manager.get_embedding_cache(text_hash)
            if cached:
                return cached
        
        # 调用 API
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text[:8000]  # 限制长度
            )
            embedding = response.data[0].embedding
            
            # 保存到缓存
            if self.db_manager:
                self.db_manager.save_embedding_cache(text_hash, embedding)
            
            return embedding
        except Exception as e:
            logger.error(f"向量化失败: {e}")
            return None
    
    @staticmethod
    def cosine_similarity(vec1, vec2):
        """计算余弦相似度"""
        import math
        dot = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = math.sqrt(sum(a * a for a in vec1))
        mag2 = math.sqrt(sum(b * b for b in vec2))
        if mag1 == 0 or mag2 == 0:
            return 0
        return dot / (mag1 * mag2)