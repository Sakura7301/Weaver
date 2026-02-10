"""
主程序 - AI智能助手入口
"""
from datetime import datetime, timedelta
from typing import Dict, Callable

from log import logger
from config import (
    API_KEY, BASE_URL, SEARXNG_URL, MAX_FETCH, 
    MAX_HISTORY, AUTO_MERGE_ON_STARTUP, MERGE_INTERVAL_DAYS,
    MERGE_SIMILARITY_THRESHOLD, LAST_MERGE_FILE, create_tools
)
from memory.core import MemorySystem
from ai_chat import AIChat


# 命令常量定义
COMMANDS = {
    'quit': '退出程序',
    'memory': '查看所有记忆',
    'save': '手动保存到长期记忆 (!save <内容>)',
    'merge': '立即深度整理',
    'config': '查看整理配置',
    'clear': '清空对话历史',
    'history': '查看对话历史',
}


def print_commands() -> None:
    """打印命令列表"""
    logger.info("可用命令:")
    for cmd, desc in COMMANDS.items():
        logger.debug(f" !{cmd:<10} - {desc}")


def print_config(memory_system: MemorySystem) -> None:
    """打印配置信息"""
    logger.info("记忆系统配置:")
    logger.debug(f"整理间隔: 每 {MERGE_INTERVAL_DAYS} 天")
    logger.debug(f"相似度阈值: {MERGE_SIMILARITY_THRESHOLD}")
    logger.debug(f"启动时自动整理: {'是' if AUTO_MERGE_ON_STARTUP else '否'}")
    
    if LAST_MERGE_FILE.exists():
        last = datetime.fromtimestamp(LAST_MERGE_FILE.stat().st_mtime)
        next_merge = last + timedelta(days=MERGE_INTERVAL_DAYS)
        logger.debug(f"上次整理: {last.strftime('%Y-%m-%d %H:%M')}")
        logger.debug(f"下次整理: {next_merge.strftime('%Y-%m-%d %H:%M')}")
    else:
        logger.debug("上次整理: 从未整理")


def handle_save_command(memory: MemorySystem, text: str) -> None:
    """处理保存命令"""
    memory.save_memory(text, memory_type='long')
    logger.info(f"已保存到长期记忆: {text[:50]}...")


def handle_history_command(ai_chat: AIChat) -> None:
    """处理历史记录命令"""
    history = ai_chat.get_history()
    if history:
        logger.info("\n📜 对话历史:")
        for i, msg in enumerate(history, 1):
            role = "用户" if msg["role"] == "user" else "助手"
            logger.debug(f"{i}. [{role}] {msg['content'][:100]}...")
    else:
        logger.info("📜 对话历史为空")


def setup_command_handlers(
    memory: MemorySystem, 
    ai_chat: AIChat
) -> Dict[str, Callable[[str], bool]]:
    """设置命令处理器映射"""
    return {
        'quit': lambda _: False,  # 返回False退出循环
        'q': lambda _: False,
        'exit': lambda _: False,
        'merge': lambda _: (memory.deep_merge_all(), True)[1],
        'config': lambda _: (print_config(memory), True)[1],
        'clear': lambda _: (ai_chat.clear_history(), logger.info("对话历史已清空"), True)[2],
        'history': lambda _: (handle_history_command(ai_chat), True)[1],
        'memory': lambda _: (logger.debug("\n" + "="*20), logger.debug(memory.get_long_term_memory()), 
                            logger.debug("="*20), True)[3],
    }


def main() -> None:
    """主函数"""
    # 初始化记忆系统
    memory = MemorySystem(
        api_key=API_KEY, 
        base_url=BASE_URL,
        embedding_model="embedding-3",
        merge_threshold=MERGE_SIMILARITY_THRESHOLD,
        merge_interval_days=MERGE_INTERVAL_DAYS
    )
    
    # 初始化AI聊天处理器
    ai_chat = AIChat(memory, SEARXNG_URL, MAX_FETCH)
    
    # 创建工具列表
    tools = create_tools(memory)
    
    # 自动索引
    memory.auto_index()
    
    # 启动时检查是否需要定期整理
    if AUTO_MERGE_ON_STARTUP:
        memory.check_and_auto_merge()
    
    print_commands()
    
    # 设置命令处理器
    handlers = setup_command_handlers(memory, ai_chat)
    
    # 交互循环
    while True:
        try:
            q = input("问题: ").strip()
            
            if not q:
                continue
            
            # 处理命令
            if q.startswith('!'):
                cmd = q[1:].split(maxsplit=1)
                cmd_name = cmd[0]
                cmd_args = cmd[1] if len(cmd) > 1 else ""
                
                # 处理保存命令（带参数）
                if cmd_name == 'save':
                    if cmd_args:
                        handle_save_command(memory, cmd_args)
                    continue
                
                # 处理其他命令
                if cmd_name in handlers:
                    should_continue = handlers[cmd_name](cmd_args)
                    if not should_continue:
                        logger.info("\n👋 再见！")
                        break
                    continue
                
                logger.warning(f"未知命令: {cmd_name}")
                continue
            
            # 正常对话
            current_history = ai_chat.get_history()
            answer = ai_chat.ask(q, history=current_history, tools=tools)
            logger.info(f"回答：\n{answer}")
            ai_chat.update_history(q, answer, MAX_HISTORY)
            
        except KeyboardInterrupt:
            logger.warning("检测到中断信号，正在退出...")
            break
        except Exception as e:
            logger.error(f"发生错误: {e}")
            continue

# 快速排序算法实现
def quick_sort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]
    return quick_sort(left) + middle + quick_sort(right)


if __name__ == "__main__":
    main()