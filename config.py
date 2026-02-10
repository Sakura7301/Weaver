"""
配置管理模块 - 从JSON加载配置并处理动态功能
"""
import json
import warnings
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# 加载JSON配置
CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config() -> Dict[str, Any]:
    """加载JSON配置文件"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 将相对路径转换为绝对路径
    base_dir = Path(__file__).parent
    paths = config["paths"]
    
    for key, path_str in paths.items():
        if key.endswith("_dir") or key.endswith("_file") or key.endswith("_db"):
            paths[key] = str(base_dir / path_str)
    
    return config

# 加载配置
CONFIG = load_config()

# ==================== 路径配置 ====================
MEMORY_DIR = Path(CONFIG["paths"]["memory_dir"])
MEMORY_DB = Path(CONFIG["paths"]["memory_db"])
MEMORY_FILE = Path(CONFIG["paths"]["memory_file"])
DAILY_MEMORY_DIR = Path(CONFIG["paths"]["daily_memory_dir"])
LAST_MERGE_FILE = Path(CONFIG["paths"]["last_merge_file"])
LOG_DIR = Path(CONFIG["paths"]["log_dir"])

# ==================== API配置 ====================
SEARXNG_URL = CONFIG["api"]["searxng_url"]
API_KEY = CONFIG["api"]["api_key"]
BASE_URL = CONFIG["api"]["base_url"]

# ==================== 模型配置 ====================
JUDGE_MODEL = CONFIG["models"]["judge_model"]
ANSWER_MODEL = CONFIG["models"]["answer_model"]
EMBEDDING_MODEL = CONFIG["models"]["embedding_model"]

# ==================== 功能配置 ====================
MAX_FETCH = CONFIG["features"]["max_fetch"]
TIMEZONE = CONFIG["features"]["timezone"]
MAX_HISTORY = CONFIG["features"]["max_history"]

# ==================== 记忆系统配置 ====================
MERGE_INTERVAL_DAYS = CONFIG["memory"]["merge_interval_days"]
AUTO_MERGE_ON_STARTUP = CONFIG["memory"]["auto_merge_on_startup"]
MERGE_SIMILARITY_THRESHOLD = CONFIG["memory"]["merge_similarity_threshold"]

# ==================== 工具定义 ====================
def create_tools(memory_system):
    """创建可用的工具列表"""
    from memory import create_memory_tools

    tools = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "搜索互联网获取实时信息。适用于：最新新闻、实时价格、天气、最新版本、近期事件等需要实时数据的问题。注意：当前日期时间已经在系统提示中提供，无需为此搜索。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词，应包含具体时间信息（如'2026年2月'）以获取最新结果，例如：'2026年2月比特币价格'、'Python 3.13最新版本'"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        *create_memory_tools()
    ]
    return tools

# ==================== 文件系统初始化 ====================
def init_filesystem():
    """初始化记忆文件系统"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    
    # 创建长期记忆文件
    if not MEMORY_FILE.exists():
        MEMORY_FILE.write_text(
            "# 长期记忆\n\n"
            "## 用户信息\n\n"
            "## 重要偏好\n\n"
            "## 关键决策\n\n",
            encoding='utf-8'
        )
    
    return {
        "memory_dir": MEMORY_DIR,
        "memory_db": MEMORY_DB,
        "memory_file": MEMORY_FILE,
        "daily_dir": DAILY_MEMORY_DIR,
        "last_merge_file": LAST_MERGE_FILE
    }

# ==================== 配置管理函数 ====================
def update_config(key_path: str, value: Any):
    """
    更新配置并保存到JSON文件
    
    Args:
        key_path: 点分隔的键路径，如 "api.base_url"
        value: 新值
    """
    global CONFIG  # 声明为全局变量
    
    keys = key_path.split('.')
    config_ref = CONFIG
    
    # 导航到目标位置
    for key in keys[:-1]:
        config_ref = config_ref[key]
    
    # 更新值
    config_ref[keys[-1]] = value
    
    # 保存到JSON文件
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(CONFIG, f, indent=2, ensure_ascii=False)
    
    # 重新加载配置
    CONFIG = load_config()

def get_config(key_path: str = None, default: Any = None) -> Any:
    """
    获取配置值
    
    Args:
        key_path: 点分隔的键路径，如 "api.base_url"
        default: 如果键不存在时的默认值
    
    Returns:
        配置值或整个配置字典
    """
    if key_path is None:
        return CONFIG
    
    keys = key_path.split('.')
    config_ref = CONFIG
    
    try:
        for key in keys:
            config_ref = config_ref[key]
        return config_ref
    except (KeyError, TypeError):
        return default