"""
对话历史管理
"""
import json
import os
from datetime import datetime
from log import logger

HISTORY_DIR = "history"
os.makedirs(HISTORY_DIR, exist_ok=True)


class ChatHistory:
    def __init__(self):
        self.sessions = {}
        self.load_all()
    
    def load_all(self):
        """加载所有历史记录"""
        logger.debug("加载历史记录")
        for filename in os.listdir(HISTORY_DIR):
            if filename.endswith('.json'):
                session_id = filename[:-5]
                try:
                    with open(os.path.join(HISTORY_DIR, filename), 'r', encoding='utf-8') as f:
                        self.sessions[session_id] = json.load(f)
                except Exception as e:
                    logger.error(f"加载历史失败: {filename} - {e}")
    
    def create_session(self):
        """创建新对话"""
        session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.sessions[session_id] = {
            "title": "新对话",
            "messages": []
        }
        logger.info(f"创建新对话: {session_id}")
        return session_id
    
    def get_session(self, session_id: str):
        """获取对话"""
        return self.sessions.get(session_id, {"title": "新对话", "messages": []})
    
    def add_message(self, session_id: str, role: str, content: str, duration: float = None):
        """添加消息"""
        if session_id not in self.sessions:
            self.sessions[session_id] = {"title": "新对话", "messages": []}
        
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        if duration is not None:
            msg["duration"] = duration
        
        self.sessions[session_id]["messages"].append(msg)
        
        # 自动生成标题
        if len(self.sessions[session_id]["messages"]) == 1 and role == "user":
            title = content[:30] + ("..." if len(content) > 30 else "")
            self.sessions[session_id]["title"] = title
        
        self.save_session(session_id)
    
    def save_session(self, session_id: str):
        """保存对话"""
        filename = os.path.join(HISTORY_DIR, f"{session_id}.json")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.sessions[session_id], f, ensure_ascii=False, indent=2)
        logger.debug(f"保存对话: {session_id}")
    
    def get_all_sessions(self):
        """获取所有对话列表"""
        return [
            {"id": sid, "title": data["title"]}
            for sid, data in sorted(self.sessions.items(), reverse=True)
        ]
    
    def delete_session(self, session_id: str):
        """删除对话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            filename = os.path.join(HISTORY_DIR, f"{session_id}.json")
            if os.path.exists(filename):
                os.remove(filename)
            logger.info(f"删除对话: {session_id}")
    
    def rename_session(self, session_id: str, new_title: str):
        """重命名对话"""
        if session_id in self.sessions:
            self.sessions[session_id]["title"] = new_title
            self.save_session(session_id)
            logger.info(f"重命名对话: {session_id} -> {new_title}")

    def clear_all_sessions(self):
        """清空所有对话"""
        # 删除所有文件
        for session_id in list(self.sessions.keys()):
            filename = os.path.join(HISTORY_DIR, f"{session_id}.json")
            if os.path.exists(filename):
                os.remove(filename)
        
        self.sessions.clear()
        logger.info("清空所有对话历史")