"""
搜索功能模块
"""

import json

class SearchEngine:
    """搜索引擎"""
    
    def __init__(self, embedding_manager, db_manager):
        self.embedding_manager = embedding_manager
        self.db_manager = db_manager
    
    def _bm25_score(self, query, text):
        """简化版 BM25 评分"""
        query_terms = set(query.lower().split())
        text_lower = text.lower()
        
        score = 0
        for term in query_terms:
            if term in text_lower:
                tf = text_lower.count(term)
                score += tf / (tf + 1.0)  # 简化的 TF 计算
        
        return score
    
    def search(self, query, top_k=5, min_score=0.3):
        """
        混合搜索记忆（向量 + BM25）
        
        Args:
            query: 搜索查询
            top_k: 返回结果数量
            min_score: 最低分数阈值
        
        Returns:
            [{"text": "...", "path": "...", "score": 0.85}, ...]
        """
        print(f"🧠 搜索记忆: {query}")
        
        # 查询向量化
        query_embedding = self.embedding_manager.get_embedding(query)
        if not query_embedding:
            return []
        
        # 从数据库获取所有记忆块
        rows = self.db_manager.get_all_chunks()
        
        if not rows:
            print("💭 记忆为空")
            return []
        
        # 混合评分
        results = []
        for chunk_id, path, text, embedding_json in rows:
            embedding = json.loads(embedding_json)
            
            # 向量相似度（70%）
            vector_score = self.embedding_manager.cosine_similarity(query_embedding, embedding)
            
            # BM25 分数（30%）
            bm25 = self._bm25_score(query, text)
            
            # 混合分数
            final_score = 0.7 * vector_score + 0.3 * min(bm25, 1.0)
            
            if final_score >= min_score:
                results.append({
                    "id": chunk_id,
                    "text": text,
                    "path": path,
                    "score": final_score
                })
        
        # 排序并返回
        results.sort(key=lambda x: x['score'], reverse=True)
        
        print(f"✅ 找到 {len(results[:top_k])} 条相关记忆")
        return results[:top_k]