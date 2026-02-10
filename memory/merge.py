"""
合并整理功能模块
"""

from log import logger
from datetime import datetime, timedelta
from config import MEMORY_FILE, LAST_MERGE_FILE

class MergeManager:
    """合并管理器"""
    
    def __init__(self, client, db_manager, embedding_manager, merge_threshold=0.6, merge_interval_days=7):
        self.client = client
        self.db_manager = db_manager
        self.embedding_manager = embedding_manager
        self.merge_threshold = merge_threshold
        self.merge_interval_days = merge_interval_days
    
    def should_merge(self):
        """检查是否需要定期整理"""
        if not LAST_MERGE_FILE.exists():
            return True  # 从未整理过
        
        last_merge_time = datetime.fromtimestamp(LAST_MERGE_FILE.stat().st_mtime)
        days_since_merge = (datetime.now() - last_merge_time).days
        
        return days_since_merge >= self.merge_interval_days
    
    def _update_merge_timestamp(self):
        """更新整理时间戳"""
        LAST_MERGE_FILE.write_text(datetime.now().isoformat(), encoding='utf-8')
    
    def smart_merge(self, text, similar_chunks):
        """
        智能合并新信息与相似记忆
        
        Args:
            text: 新信息
            similar_chunks: 相似记忆列表
        
        Returns:
            合并后的文本
        """
        try:
            # 1. 收集旧记忆
            old_texts = "\n".join([f"- {s['text']}" for s in similar_chunks])
            
            # 2. 用 AI 合并
            merge_prompt = f"""你是记忆管理助手。请将新信息与已有记忆智能合并。

【已有记忆】
{old_texts}

【新信息】
- {text}

**任务**：输出一条简洁的综合记忆（不要时间戳，不要解释）

**规则**：
1. 如果新信息是补充细节，合并为一条
2. 如果新信息是更新/修正，替换旧内容
3. 如果完全重复，保持原样
4. 保留所有关键信息，避免丢失细节

**输出格式示例**：
用户xxx是开发者，热爱电子游戏（最爱黑暗之魂，艾尔登法环500+小时）
"""

            response = self.client.chat.completions.create(
                model="glm-4-plus",
                messages=[{"role": "user", "content": merge_prompt}],
                temperature=0.3
            )
            
            merged_text = response.choices[0].message.content.strip()
            # 清理可能的markdown格式
            merged_text = merged_text.replace('**', '').replace('- ', '').strip()
            
            return merged_text
            
        except Exception as e:
            logger.error(f"合并失败: {e}")
            return text
    
    def deep_merge_all(self):
        """深度整理所有长期记忆（定期任务）"""
        logger.debug("🔄 开始深度整理长期记忆...")
        
        # 读取所有长期记忆
        content = MEMORY_FILE.read_text(encoding='utf-8')
        lines = [l.strip() for l in content.split('\n') if l.strip() and l.startswith('- ')]
        
        if len(lines) <= 1:
            logger.debug("记忆内容很精简，无需整理")
            self._update_merge_timestamp()
            return
        
        logger.debug(f"📊 当前有 {len(lines)} 条记忆，准备整理...")
        
        try:
            # 用 AI 深度分析并重组
            merge_prompt = f"""你是专业的记忆管理助手。下面是用户的长期记忆碎片，请进行深度整理。

【当前记忆】
{chr(10).join(lines)}

**任务**：
1. 合并重复和相似的内容
2. 按主题分类（用户信息、偏好、技能、经历等）
3. 保留所有关键细节
4. 输出精简但完整的记忆

**输出格式**：
## 用户信息
- 条目1
- 条目2

## 重要偏好
- 条目1
- 条目2

## 关键决策
- 条目1
- 条目2

**要求**：
- 不要丢失任何重要信息
- 每个类别最多5条（合并相似的）
- 不要添加时间戳
- 保持简洁清晰
"""

            response = self.client.chat.completions.create(
                model="glm-4-plus",
                messages=[{"role": "user", "content": merge_prompt}],
                temperature=0.3,
                max_tokens=2000
            )
            
            merged_content = response.choices[0].message.content.strip()
            
            # 重写文件
            new_content = f"""# 长期记忆

{merged_content}

---
*最后整理时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
*原始条目数: {len(lines)} → 整理后见上*
"""
            
            MEMORY_FILE.write_text(new_content, encoding='utf-8')
            
            # 清空向量数据库中的长期记忆
            self.db_manager.delete_chunks_by_path("MEMORY.md")
            
            logger.info(f"深度整理完成！{len(lines)} 条记忆已优化")
            logger.debug(f"📅 下次整理时间: {(datetime.now() + timedelta(days=self.merge_interval_days)).strftime('%Y-%m-%d')}")
            
            # 更新整理时间戳
            self._update_merge_timestamp()
            
        except Exception as e:
            logger.error(f"整理失败: {e}")