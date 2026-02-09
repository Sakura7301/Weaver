"""
OpenClaw 风格记忆系统
模块化版本，保持原有功能不变
"""

from .core import MemorySystem
from .tools import create_memory_tools

__all__ = ['MemorySystem', 'create_memory_tools']
__version__ = '1.0.0'