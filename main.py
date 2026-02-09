"""
主程序 - AI智能助手入口
"""
from datetime import timedelta
from config import (
    MEMORY_DIR, API_KEY, BASE_URL, SEARXNG_URL, MAX_FETCH, 
    MAX_HISTORY, AUTO_MERGE_ON_STARTUP, MERGE_INTERVAL_DAYS,
    MERGE_SIMILARITY_THRESHOLD, LAST_MERGE_FILE
)
from memory.core import MemorySystem
from ai_chat import AIChat
from config import create_tools
from datetime import datetime

def print_banner():
    """打印程序横幅"""
    print("\n🚀 AI智能助手已启动（联网搜索 + 智能记忆）")
    print("="*80)

def print_commands():
    """打印命令列表"""
    print("\n💡 命令列表:")
    print("   quit          - 退出程序")
    print("   !memory       - 查看所有记忆")
    print("   !save <内容>  - 手动保存到长期记忆")
    print("   !merge        - 立即深度整理")
    print("   !config       - 查看整理配置")
    print("   !clear        - 清空对话历史")
    print("   !history      - 查看对话历史")
    print("="*80 + "\n")

def print_config(memory_system):
    """打印配置信息"""
    print("\n" + "="*80)
    print("⚙️  记忆系统配置:")
    print(f"   整理间隔: 每 {MERGE_INTERVAL_DAYS} 天")
    print(f"   相似度阈值: {MERGE_SIMILARITY_THRESHOLD}")
    print(f"   启动时自动整理: {'是' if AUTO_MERGE_ON_STARTUP else '否'}")
    
    if LAST_MERGE_FILE.exists():
        last = datetime.fromtimestamp(LAST_MERGE_FILE.stat().st_mtime)
        next_merge = last + timedelta(days=MERGE_INTERVAL_DAYS)
        print(f"   上次整理: {last.strftime('%Y-%m-%d %H:%M')}")
        print(f"   下次整理: {next_merge.strftime('%Y-%m-%d %H:%M')}")
    else:
        print(f"   上次整理: 从未整理")
    
    print(f"   记忆路径: {MEMORY_DIR}")
    print("="*80)

def main():
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
    
    print_banner()
    
    # 自动索引
    memory.auto_index()
    
    # 启动时检查是否需要定期整理
    if AUTO_MERGE_ON_STARTUP:
        memory.check_and_auto_merge()
    
    print_commands()
    
    # 交互循环
    while True:
        try:
            q = input("\n问题: ").strip()
            
            if q.lower() in ['quit', 'q', 'exit']:
                print("\n👋 再见！")
                break
            
            # 立即整理
            if q == '!merge':
                memory.deep_merge_all()
                continue
            
            # 查看配置
            if q == '!config':
                print_config(memory)
                continue
            
            # 清空对话历史
            if q == '!clear':
                ai_chat.clear_history()
                print("✅ 对话历史已清空")
                continue
            
            # 查看对话历史
            if q == '!history':
                history = ai_chat.get_history()
                if history:
                    print("\n📜 对话历史:")
                    for i, msg in enumerate(history, 1):
                        role = "用户" if msg["role"] == "user" else "助手"
                        print(f"{i}. [{role}] {msg['content'][:100]}...")
                else:
                    print("📜 对话历史为空")
                continue
            
            # 查看记忆
            if q == '!memory':
                print("\n" + "="*80)
                print(memory.get_long_term_memory())
                print("="*80)
                continue
            
            # 手动保存
            if q.startswith('!save '):
                text = q[6:]
                memory.save_memory(text, memory_type='long')
                print(f"✅ 已保存到长期记忆: {text[:50]}...")
                continue
            
            # 正常对话
            if not q:
                continue
            
            print("\n" + "=" * 80)
            
            # 获取当前对话历史
            current_history = ai_chat.get_history()
            
            # 处理问题
            answer = ai_chat.ask(q, history=current_history, tools=tools)
            
            print(f"\n💡 回答：\n{answer}\n")
            print("=" * 80)
            
            # 更新对话历史
            ai_chat.update_history(q, answer, MAX_HISTORY)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  检测到中断信号，正在退出...")
            break
        except Exception as e:
            print(f"\n❌ 发生错误: {e}")
            continue

if __name__ == "__main__":
    main()