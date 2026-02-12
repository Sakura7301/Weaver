"""
日志模块
"""
import logging
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


class ColoredFormatter(logging.Formatter):
    """带颜色的终端日志格式化器"""
    
    COLORS = {
        'DEBUG': '\033[90m',
        'INFO': '\033[92m',
        'WARNING': '\033[93m',
        'ERROR': '\033[91m',
    }
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    def format(self, record):
        log_time = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d-%H-%M-%S')
        level_name = record.levelname
        log_msg = record.getMessage()
        
        color = self.COLORS.get(level_name, '')
        colored_level = f"{color}{self.BOLD}[{level_name}]{self.RESET}"
        return f"[{log_time}] {colored_level} {log_msg}"


class PlainFormatter(logging.Formatter):
    """纯文本日志格式化器"""
    
    def format(self, record):
        log_time = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        return f"[{log_time}] [{record.levelname}] {record.getMessage()}"


log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
log_mode = os.getenv("LOG_MODE", "console").lower()

level_map = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR
}
log_level = level_map.get(log_level_str, logging.INFO)

logger = logging.getLogger("demo")
logger.setLevel(log_level)

if log_mode == "file":
    log_filename = datetime.now().strftime('%Y-%m-%d-%H-%M-%S.log')
    log_file = os.path.join(LOG_DIR, log_filename)
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(PlainFormatter())
    logger.addHandler(file_handler)
else:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)