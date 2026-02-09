"""
AI智能助手包
"""

from .config import *
from .time_utils import get_current_time_info
from .web_search import web_search, fetch_webpage
from .ai_chat import AIChat
from .main import main

__version__ = "1.0.0"
__all__ = [
    'get_current_time_info',
    'web_search',
    'fetch_webpage',
    'AIChat',
    'main',
    'create_tools'
]