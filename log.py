
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from enum import Enum
from config import LOG_DIR


class LogMode(Enum):
    """日志输出模式"""
    CONSOLE = 0  # 仅输出到终端
    FILE = 1     # 仅输出到文件
    BOTH = 2     # 同时输出到文件和终端


class LogLevel(Enum):
    """日志级别"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class Logger:
    """全局日志类，可直接导入使用"""
    
    # 控制台颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m'        # 重置
    }
    
    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化日志器（只初始化一次）"""
        if self._initialized:
            return
        
        self._initialized = True
        self.level = LogLevel.DEBUG
        self.colored = True
        self.mode = LogMode.BOTH  # 默认 BOTH 模式
        self.log_dir = LOG_DIR
        
        # 创建logger
        self.logger = logging.getLogger('Weaver')
        self.logger.setLevel(self.level.value)
        self.logger.handlers.clear()
        
        # 默认添加控制台和文件处理器（BOTH模式）
        self._add_console_handler()
        self._add_file_handler()
    
    def _add_console_handler(self):
        """添加控制台处理器"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.level.value)
        if self.colored:
            formatter = ColoredFormatter(
                '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        else:
            formatter = logging.Formatter(
                '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
    
    def _add_file_handler(self):
        """添加文件处理器"""
        # 生成日志文件名：年-月-日-时-分.log
        now = datetime.now()
        log_filename = now.strftime('%Y-%m-%d-%H-%M.log')
        log_path = self.log_dir / log_filename
        
        # 确保日志目录存在
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setLevel(self.level.value)
        formatter = logging.Formatter(
            '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
    
    def _clear_handlers(self):
        """清除所有处理器"""
        self.logger.handlers.clear()
    
    def setup(
        self,
        mode: LogMode = LogMode.CONSOLE,
        log_dir: Optional[str] = None,
        level: LogLevel = LogLevel.INFO,
        colored: bool = True
    ):
        """
        配置日志器
        
        Args:
            mode: 输出模式 (LogMode.CONSOLE, LogMode.FILE, LogMode.BOTH)
            log_dir: 日志文件存放目录，None表示使用当前目录
            level: 日志级别 (LogLevel.DEBUG, LogLevel.INFO, 等)
            colored: 控制台输出是否使用颜色
        """
        self.mode = mode
        self.colored = colored
        self.level = level
        
        # 设置日志目录
        if log_dir:
            self.log_dir = Path(log_dir).expanduser()
        else:
            self.log_dir = Path.cwd()
        
        # 清除现有处理器
        self._clear_handlers()
        
        # 设置日志级别
        self.logger.setLevel(self.level.value)
        
        # 根据模式添加处理器
        if mode == LogMode.CONSOLE:
            self._add_console_handler()
        elif mode == LogMode.FILE:
            self._add_file_handler()
        elif mode == LogMode.BOTH:
            self._add_console_handler()
            self._add_file_handler()
        
        return self
    
    def set_name(self, name: str):
        """设置日志名称"""
        self.logger.name = name
        return self
    
    def set_level(self, level: LogLevel):
        """设置日志级别"""
        self.level = level
        self.logger.setLevel(level.value)
        for handler in self.logger.handlers:
            handler.setLevel(level.value)
        return self
    
    def debug(self, message: str):
        """输出DEBUG级别日志"""
        self.logger.debug(message)
    
    def info(self, message: str):
        """输出INFO级别日志"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """输出WARNING级别日志"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """输出ERROR级别日志"""
        self.logger.error(message)
    
    def critical(self, message: str):
        """输出CRITICAL级别日志"""
        self.logger.critical(message)
    
    def exception(self, message: str):
        """输出异常信息（ERROR级别，包含堆栈跟踪）"""
        self.logger.exception(message)


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""
    
    def format(self, record):
        # 保存原始levelname
        levelname = record.levelname
        
        # 添加颜色
        if levelname in Logger.COLORS:
            record.levelname = (
                f"{Logger.COLORS[levelname]}{levelname}{Logger.COLORS['RESET']}"
            )
        
        # 格式化输出
        result = super().format(record)
        
        # 恢复原始levelname
        record.levelname = levelname
        
        return result


# 创建全局日志对象
logger = Logger()
