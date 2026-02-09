"""
工具函数接口
"""

def create_memory_tools():
    """创建记忆相关的 Function Calling 工具定义"""
    return [
        {
            "type": "function",
            "function": {
                "name": "memory_search",
                "description": "搜索历史记忆，查找相关的对话历史、用户信息、过往决策等。适用于：用户问'我之前说过什么'、'我的偏好是什么'等需要回忆的问题。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索查询，例如：'用户喜好'、'上周讨论的项目'、'Python相关笔记'"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回结果数量，默认5",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "memory_save",
                "description": "保存重要信息到记忆系统。当用户提供个人信息、偏好、重要决策时应调用此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "要保存的内容"
                        },
                        "memory_type": {
                            "type": "string",
                            "enum": ["long", "short"],
                            "description": "long=长期记忆(用户偏好等), short=短期记忆(临时笔记)",
                            "default": "short"
                        }
                    },
                    "required": ["text"]
                }
            }
        }
    ]