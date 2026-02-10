"""
配置验证脚本
"""
import json
from log import logger
from pathlib import Path

def validate_config():
    """验证配置文件结构和必需字段"""
    config_path = Path(__file__).parent / "config.json"
    
    if not config_path.exists():
        logger.error(f"配置文件不存在: {config_path}")
        return False
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"JSON格式无效: {e}")
        return False
    
    # 必需字段检查
    required_sections = ["paths", "api", "models", "features", "memory"]
    for section in required_sections:
        if section not in config:
            logger.error(f"缺少必需配置节: {section}")
            return False
    
    # 必需路径字段
    required_paths = ["memory_dir", "memory_db", "memory_file", "daily_memory_dir", "last_merge_file"]
    for path_key in required_paths:
        if path_key not in config["paths"]:
            logger.error(f"缺少必需路径配置: paths.{path_key}")
            return False
    
    logger.info("配置验证通过!")
    return True

if __name__ == "__main__":
    validate_config()