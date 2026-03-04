"""
Flask Web 应用 - 支持三级记忆架构和用户管理
"""
import os
import re
import time
import sqlite3
import requests
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv, set_key
from agent_manager import AgentManager
from chat_history import ChatHistory
from datetime import datetime
from log import logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from user_manager import user_manager

# 保存提示词到文件
PROMPT_FILE = "system_prompt.txt"
DEFAULT_PROMPT = """你是一个智能助手，回答要简洁准确，使用中文。

你有记忆能力。在回答用户问题前，你应该先调用 search_memory 工具查找相关记忆。
如果找到相关记忆，请基于记忆内容回答；如果没有找到，再基于通用知识回答。

当用户告诉你重要信息（如姓名、喜好、重要约定）时，请使用 save_memory 工具保存到长期记忆。"""

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 用户专属的Agent管理器和聊天历史
user_agents = {}  # {username: AgentManager}
chat_history = ChatHistory()

current_session = {}  # {username: session_id}

# 初始化定时任务
scheduler = BackgroundScheduler()
scheduler.start()

def get_interval_seconds():
    """从配置计算间隔秒数"""
    value = int(os.getenv("MEMORY_INTERVAL_VALUE", "30"))
    unit = os.getenv("MEMORY_INTERVAL_UNIT", "minutes")
    
    multipliers = {
        "minutes": 60,
        "hours": 3600,
        "days": 86400
    }
    return value * multipliers.get(unit, 60)

def schedule_memory_merge():
    """设置记忆合并定时任务"""
    # 移除已有的记忆合并任务
    for job in scheduler.get_jobs():
        if job.id == 'memory_merge':
            job.remove()
    
    seconds = get_interval_seconds()
    scheduler.add_job(
        func=merge_memories_task,
        trigger=IntervalTrigger(seconds=seconds),
        id='memory_merge',
        name='合并相似长期记忆',
        replace_existing=True
    )
    logger.info(f"已设置记忆合并任务，间隔: {seconds}秒")

def merge_memories_task():
    """执行记忆合并的后台任务"""
    try:
        # 对所有在线用户的记忆系统执行合并
        for username, agent_manager in user_agents.items():
            if agent_manager.memory_system:
                logger.info(f"执行用户 {username} 的定期记忆处理...")
                # 第1步：将短期记忆中的重要信息转为长期记忆
                agent_manager.memory_system.process_short_term_to_long_term()
                # 第2步：合并相似的长期记忆
                agent_manager.memory_system.merge_similar_memories()
    except Exception as e:
        logger.error(f"记忆处理任务失败: {e}")

# 启动时设置定时任务
schedule_memory_merge()

def get_current_user():
    """获取当前登录用户"""
    return session.get('username')

def get_user_agent(username: str) -> AgentManager:
    """获取用户的Agent管理器"""
    if username not in user_agents:
        user_agents[username] = AgentManager(username)
    return user_agents[username]

def require_login(f):
    """登录验证装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        username = get_current_user()
        if not username:
            return jsonify({"success": False, "error": "请先登录"}), 401
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    return render_template('index.html')


# ============ 用户认证 API ============

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """获取当前登录状态"""
    username = get_current_user()
    if username:
        is_admin = user_manager.is_admin(username)
        return jsonify({
            "logged_in": True,
            "username": username,
            "is_admin": is_admin
        })
    return jsonify({"logged_in": False})


@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    success, message, user_info = user_manager.login(username, password)
    
    if success:
        session['username'] = user_info['username']
        session['is_admin'] = user_info['is_admin']
        
        # 初始化用户的Agent管理器
        get_user_agent(user_info['username'])
        
        return jsonify({
            "success": True,
            "message": message,
            "user": user_info
        })
    
    return jsonify({"success": False, "message": message})


@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    success, message = user_manager.register(username, password)
    return jsonify({"success": success, "message": message})


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """用户登出"""
    username = get_current_user()
    if username and username in user_agents:
        # 清理用户的Agent管理器
        del user_agents[username]
    
    session.clear()
    return jsonify({"success": True, "message": "已退出登录"})


@app.route('/api/auth/change-password', methods=['POST'])
@require_login
def change_password():
    """修改密码"""
    data = request.json
    old_password = data.get('old_password', '')
    new_password = data.get('new_password', '')
    
    username = get_current_user()
    success, message = user_manager.change_password(username, old_password, new_password)
    return jsonify({"success": success, "message": message})


# ============ 管理员 API ============

@app.route('/api/admin/users', methods=['GET'])
@require_login
def get_users():
    """获取用户列表（仅管理员）"""
    username = get_current_user()
    success, users = user_manager.get_all_users(username)
    
    if not success:
        return jsonify({"success": False, "error": "权限不足"}), 403
    
    return jsonify({"success": True, "users": users})


@app.route('/api/admin/users/<target_username>/password', methods=['GET'])
@require_login
def get_user_password(target_username):
    """获取用户密码信息（仅管理员）"""
    username = get_current_user()
    success, message = user_manager.get_user_password(username, target_username)
    
    if not success:
        return jsonify({"success": False, "error": message}), 403
    
    return jsonify({"success": True, "message": message})


@app.route('/api/admin/users/<target_username>/password', methods=['POST'])
@require_login
def admin_change_user_password(target_username):
    """管理员修改用户密码"""
    username = get_current_user()
    data = request.json
    new_password = data.get('new_password', '')
    
    success, message = user_manager.admin_change_password(username, target_username, new_password)
    return jsonify({"success": success, "message": message})


@app.route('/api/admin/users', methods=['POST'])
@require_login
def admin_create_user():
    """管理员创建用户"""
    username = get_current_user()
    data = request.json
    new_username = data.get('username', '').strip()
    new_password = data.get('password', '')
    
    success, message = user_manager.create_user_by_admin(username, new_username, new_password)
    return jsonify({"success": success, "message": message})


@app.route('/api/admin/users/<target_username>', methods=['DELETE'])
@require_login
def admin_delete_user(target_username):
    """管理员删除用户"""
    username = get_current_user()
    success, message = user_manager.delete_user(username, target_username)
    return jsonify({"success": success, "message": message})


# ============ 模型和配置 API ============

@app.route('/api/models', methods=['GET'])
@require_login
def get_models():
    """获取模型列表（包含特性信息）"""
    username = get_current_user()
    agent_manager = get_user_agent(username)
    return jsonify(agent_manager.fetch_models())


@app.route('/api/config', methods=['GET'])
@require_login
def get_config():
    """获取配置"""
    username = get_current_user()
    is_admin = user_manager.is_admin(username)
    agent_manager = get_user_agent(username)
    
    config = {
        "MEMORY_ENABLED": str(agent_manager.memory_system is not None),
        "CURRENT_MODEL": agent_manager.current_model,
        "MEMORY_MODEL": os.getenv("MEMORY_MODEL", "glm-4-plus"),
        "MEMORY_INTERVAL_VALUE": os.getenv("MEMORY_INTERVAL_VALUE", "30"),
        "MEMORY_INTERVAL_UNIT": os.getenv("MEMORY_INTERVAL_UNIT", "minutes"),
        "WORKING_MEMORY_CAPACITY": os.getenv("WORKING_MEMORY_CAPACITY", "10"),
        "IS_ADMIN": is_admin
    }
    
    # 仅管理员可见API配置
    if is_admin:
        config["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")
        config["OPENAI_BASE_URL"] = os.getenv("OPENAI_BASE_URL", "")
    
    return jsonify(config)


@app.route('/api/config', methods=['POST'])
@require_login
def save_config():
    """保存配置"""
    username = get_current_user()
    is_admin = user_manager.is_admin(username)
    
    if not is_admin:
        return jsonify({"success": False, "error": "权限不足，只有管理员可以修改配置"}), 403
    
    config = request.json
    
    # 保存到 .env 文件
    env_file = ".env"
    for key, value in config.items():
        if key.startswith("OPENAI_"):
            set_key(env_file, key, value)
        elif key in ["MEMORY_INTERVAL_VALUE", "MEMORY_INTERVAL_UNIT", "MEMORY_MODEL", "WORKING_MEMORY_CAPACITY"]:
            set_key(env_file, key, str(value))
    
    # 重新加载配置并更新定时任务
    load_dotenv(override=True)
    schedule_memory_merge()
    
    # 重新初始化所有用户的Agent
    for uname in user_agents:
        user_agents[uname].reload_config()
    
    return jsonify({"success": True})


@app.route('/api/validate-api', methods=['POST'])
@require_login
def validate_api():
    """校验 API Key 和 Base URL，返回可用模型列表"""
    username = get_current_user()
    is_admin = user_manager.is_admin(username)
    
    data = request.json
    
    # 非管理员只能验证当前配置
    if not is_admin:
        agent_manager = get_user_agent(username)
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", "")
    else:
        api_key = data.get('api_key', '').strip()
        base_url = data.get('base_url', '').strip() or 'https://api.openai.com/v1'
    
    if not api_key:
        return jsonify({"success": False, "error": "API Key 不能为空"})
    
    # 移除末尾的斜杠
    if base_url.endswith('/'):
        base_url = base_url[:-1]
    
    logger.info(f"校验 API: {base_url}")
    
    # 尝试获取模型列表
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 尝试 OpenAI 兼容的 models 端点
    models_url = f"{base_url}/models"
    
    try:
        response = requests.get(models_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            models_data = response.json()
            
            # 解析模型列表
            models = []
            raw_models = models_data.get('data', models_data.get('models', []))
            
            for m in raw_models:
                if isinstance(m, dict):
                    model_id = m.get('id', m.get('name', ''))
                    if model_id:
                        models.append({
                            "id": model_id,
                            "name": m.get('name', model_id),
                            "features": {
                                "vision": 'vision' in model_id.lower() or 'gpt-4' in model_id.lower(),
                                "tools": True,
                                "reasoning": 'reasoning' in model_id.lower() or 'o1' in model_id.lower(),
                                "fast": 'fast' in model_id.lower() or 'lite' in model_id.lower() or 'mini' in model_id.lower()
                            }
                        })
                elif isinstance(m, str):
                    models.append({
                        "id": m,
                        "name": m,
                        "features": {
                            "vision": 'vision' in m.lower() or 'gpt-4' in m.lower(),
                            "tools": True,
                            "reasoning": 'reasoning' in m.lower() or 'o1' in m.lower(),
                            "fast": 'fast' in m.lower() or 'lite' in m.lower() or 'mini' in m.lower()
                        }
                    })
            
            # 按名称排序
            models.sort(key=lambda x: x['id'])
            
            logger.info(f"API 校验成功，获取到 {len(models)} 个模型")
            return jsonify({
                "success": True,
                "models": models,
                "message": f"校验成功，获取到 {len(models)} 个可用模型"
            })
        else:
            error_msg = f"API 返回错误: HTTP {response.status_code}"
            try:
                error_data = response.json()
                if 'error' in error_data:
                    error_msg = error_data['error'].get('message', error_msg)
            except:
                pass
            
            logger.error(f"API 校验失败: {error_msg}")
            return jsonify({"success": False, "error": error_msg})
            
    except requests.exceptions.Timeout:
        logger.error("API 校验超时")
        return jsonify({"success": False, "error": "请求超时，请检查网络连接"})
    except requests.exceptions.ConnectionError:
        logger.error("API 连接失败")
        return jsonify({"success": False, "error": "无法连接到 API 服务器，请检查 Base URL"})
    except Exception as e:
        logger.error(f"API 校验失败: {e}")
        return jsonify({"success": False, "error": str(e)})


# ============ 会话管理 API ============

@app.route('/api/sessions', methods=['GET'])
@require_login
def get_sessions():
    """获取对话列表"""
    username = get_current_user()
    return jsonify(chat_history.get_all_sessions(username))


@app.route('/api/sessions', methods=['POST'])
@require_login
def create_session():
    """创建新对话"""
    username = get_current_user()
    session_id = chat_history.create_session(username)
    current_session[username] = session_id
    return jsonify({"session_id": session_id})


@app.route('/api/sessions/<session_id>', methods=['GET'])
@require_login
def get_session(session_id):
    """获取对话内容"""
    username = get_current_user()
    return jsonify(chat_history.get_session(username, session_id))


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
@require_login
def delete_session(session_id):
    """删除对话"""
    username = get_current_user()
    chat_history.delete_session(username, session_id)
    return jsonify({"success": True})


@app.route('/api/sessions/<session_id>/rename', methods=['POST'])
@require_login
def rename_session(session_id):
    """重命名对话"""
    username = get_current_user()
    try:
        data = request.json
        new_title = data.get('title', '新对话')
        chat_history.rename_session(username, session_id, new_title)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"重命名失败: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/sessions/all', methods=['DELETE'])
@require_login
def clear_all_sessions():
    """清空所有对话"""
    username = get_current_user()
    try:
        chat_history.clear_all_sessions(username)
        if username in current_session:
            current_session[username] = None
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"清空失败: {e}")
        return jsonify({"success": False, "error": str(e)})


# ============ 记忆管理 API ============

@app.route('/api/memory/all', methods=['GET'])
@require_login
def get_all_memories():
    """获取所有记忆（支持三种类型）"""
    username = get_current_user()
    agent_manager = get_user_agent(username)
    
    try:
        memory_type = request.args.get('type', 'long')
        
        if memory_type == 'long':
            if agent_manager.memory_system:
                try:
                    memories = agent_manager.export_long_term_memories()
                    formatted_memories = []
                    for m in memories:
                        if isinstance(m, dict) and 'id' in m and 'content' in m:
                            formatted_memories.append({
                                "id": m['id'],
                                "content": m['content'],
                                "created_at": m.get('created_at', datetime.now().isoformat()),
                                "score": m.get('score', 1.0)
                            })
                    return jsonify({"memories": formatted_memories})
                except Exception as inner_e:
                    logger.error(f"获取长期记忆详情失败: {inner_e}")
                    return jsonify({"memories": []})
        
        elif memory_type == 'working':
            if agent_manager.memory_system:
                working_memories = agent_manager.export_working_memories()
                formatted_memories = []
                for m in working_memories:
                    formatted_memories.append({
                        "id": m.get('key', ''),
                        "content": f"{m.get('key', '')}: {m.get('value', '')}",
                        "created_at": m.get('created_at', datetime.now().isoformat()),
                        "priority": m.get('priority', 0),
                        "access_count": m.get('access_count', 0),
                        "source": m.get('source', 'extracted')
                    })
                return jsonify({"memories": formatted_memories})
        
        else:
            memories = []
            if agent_manager.memory_system:
                session_file = os.path.join(
                    agent_manager.memory_system.config.memory_dir,
                    agent_manager.memory_system.config.session_log_file
                )
                if os.path.exists(session_file):
                    with open(session_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    turns = content.split('---')
                    for i, turn in enumerate(turns):
                        turn = turn.strip()
                        if not turn:
                            continue
                        
                        lines = turn.split('\n')
                        timestamp = ''
                        if lines and lines[0].startswith('## '):
                            timestamp = lines[0][3:].strip()
                        
                        user_match = re.search(r'\*\*User\*\*:\s*(.*?)(?=\*\*Assistant\*\*|$)', turn, re.DOTALL)
                        if user_match:
                            user_content = user_match.group(1).strip()[:200]
                            if len(user_match.group(1).strip()) > 200:
                                user_content += "..."
                            if user_content:
                                memories.append({
                                    "id": f"short_user_{i}",
                                    "content": f"👤 用户: {user_content}",
                                    "created_at": timestamp or datetime.now().isoformat(),
                                    "role": "user"
                                })
                        
                        assistant_match = re.search(r'\*\*Assistant\*\*:\s*(.*?)$', turn, re.DOTALL)
                        if assistant_match:
                            ai_content = assistant_match.group(1).strip()[:200]
                            if len(assistant_match.group(1).strip()) > 200:
                                ai_content += "..."
                            if ai_content:
                                memories.append({
                                    "id": f"short_ai_{i}",
                                    "content": f"🤖 AI: {ai_content}",
                                    "created_at": timestamp or datetime.now().isoformat(),
                                    "role": "assistant"
                                })
            
            return jsonify({"memories": memories})
            
        return jsonify({"memories": []})
    except Exception as e:
        logger.error(f"获取记忆列表失败: {e}")
        return jsonify({"memories": []})


@app.route('/api/memory/stats', methods=['GET'])
@require_login
def get_memory_stats():
    """获取记忆统计"""
    username = get_current_user()
    agent_manager = get_user_agent(username)
    
    try:
        stats = agent_manager.get_memory_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"获取记忆统计失败: {e}")
        return jsonify({"long_term": 0, "short_term": 0, "working": 0, "total": 0})


@app.route('/api/memory/save', methods=['POST'])
@require_login
def save_memory():
    """手动保存记忆"""
    username = get_current_user()
    agent_manager = get_user_agent(username)
    
    try:
        data = request.json
        content = data.get('content', '')
        memory_type = data.get('type', 'long')
        
        if not content.strip():
            return jsonify({"success": False, "error": "内容不能为空"})
        
        if agent_manager.memory_system:
            if memory_type == 'long':
                success = agent_manager.memory_system.save_long_term(content)
            elif memory_type == 'working':
                key = data.get('key', '用户输入')
                success = agent_manager.add_working_memory(key, content, priority=1)['success']
            else:
                success = agent_manager.memory_system.save(content, 'short')
            return jsonify({"success": success})
        return jsonify({"success": False, "error": "记忆系统未启用"})
    except Exception as e:
        logger.error(f"保存记忆失败: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/memory/<memory_id>', methods=['DELETE'])
@require_login
def delete_memory(memory_id):
    """删除单条记忆"""
    username = get_current_user()
    agent_manager = get_user_agent(username)
    
    try:
        memory_type = request.args.get('type', 'long')
        
        if agent_manager.memory_system:
            if memory_type == 'long':
                success = agent_manager.memory_system.vector_store.delete(memory_id)
            elif memory_type == 'working':
                success = agent_manager.memory_system.working_memory.remove(memory_id)
            else:
                success = False
            return jsonify({"success": success})
        return jsonify({"success": False, "error": "记忆系统未启用"})
    except Exception as e:
        logger.error(f"删除记忆失败: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/memory/batch-delete', methods=['POST'])
@require_login
def batch_delete_memories():
    """批量删除记忆"""
    username = get_current_user()
    agent_manager = get_user_agent(username)
    
    try:
        data = request.json
        memory_type = data.get('type', 'long')
        memory_ids = data.get('ids', [])
        
        if not memory_ids:
            return jsonify({"success": False, "error": "未指定要删除的记忆"})
        
        result = agent_manager.delete_memories(memory_type, memory_ids)
        return jsonify(result)
    except Exception as e:
        logger.error(f"批量删除记忆失败: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/memory/clear', methods=['POST'])
@require_login
def clear_memory():
    """清空指定类型的所有记忆"""
    username = get_current_user()
    agent_manager = get_user_agent(username)
    
    try:
        data = request.json
        memory_type = data.get('type', 'long')
        
        result = agent_manager.clear_memory(memory_type)
        return jsonify(result)
    except Exception as e:
        logger.error(f"清空记忆失败: {e}")
        return jsonify({"success": False, "error": str(e)})


# ============ 提示词 API ============

@app.route('/api/prompt', methods=['GET'])
@require_login
def get_prompt():
    """获取当前提示词"""
    try:
        if os.path.exists(PROMPT_FILE):
            with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
                prompt = f.read()
        else:
            prompt = DEFAULT_PROMPT
        
        return jsonify({
            "prompt": prompt,
            "default_prompt": DEFAULT_PROMPT
        })
    except Exception as e:
        logger.error(f"获取提示词失败: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/prompt', methods=['POST'])
@require_login
def save_prompt():
    """保存提示词"""
    try:
        data = request.json
        prompt = data.get('prompt', '')
        
        with open(PROMPT_FILE, 'w', encoding='utf-8') as f:
            f.write(prompt)
        
        # 重新初始化所有用户的Agent
        for username in user_agents:
            user_agents[username].reload_config()
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"保存提示词失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ============ Socket.IO 事件处理 ============

@socketio.on('connect')
def handle_connect():
    """连接时检查登录状态"""
    # Socket.IO 无法直接访问 Flask session
    # 客户端需要在连接后发送认证信息
    pass


@socketio.on('auth')
def handle_socket_auth(data):
    """Socket.IO 认证"""
    username = data.get('username')
    if username and username in user_agents:
        # 认证成功
        emit('auth_success', {"username": username})
    else:
        emit('auth_failed', {"message": "请先登录"})


@socketio.on('chat')
def handle_chat(data):
    """处理聊天消息"""
    username = data.get('username')
    if not username or username not in user_agents:
        emit('error', {"message": "请先登录"})
        return
    
    agent_manager = get_user_agent(username)
    message = data.get('message', '')
    session_id = data.get('session_id') or current_session.get(username)
    
    if not message.strip():
        emit('error', {"message": "消息不能为空"})
        return
    
    if not session_id:
        session_id = chat_history.create_session(username)
        current_session[username] = session_id
        emit('session_created', {"session_id": session_id})
    
    # 保存用户消息
    chat_history.add_message(username, session_id, 'user', message)
    
    try:
        # 获取历史消息
        session_data = chat_history.get_session(username, session_id)
        messages = session_data['messages']
        
        logger.info(f"处理消息: {message[:50]}... (用户: {username}, 会话ID: {session_id})")
        
        # 流式响应
        start_time = time.time()
        full_response = ""
        thinking_content = ""
        
        # 调用真正的流式聊天
        for chunk in agent_manager.chat_stream(message, messages):
            chunk_type = chunk.get('type')
            content = chunk.get('content', '')
            
            if chunk_type == 'stopped':
                emit('stopped', {"message": chunk.get('message', '已停止')})
                break
            
            if chunk_type == 'thinking':
                thinking_content += content
                emit('thinking', {"content": content, "append": True})
            elif chunk_type == 'content':
                full_response += content
                emit('stream', {"content": content})
            elif chunk_type == 'tool_call':
                emit('tool_call', {"name": chunk.get('name'), "args": chunk.get('args')})
            elif chunk_type == 'tool_result':
                emit('tool_result', {"name": chunk.get('name'), "result": chunk.get('result')})
            
            socketio.sleep(0.01)
        
        duration = time.time() - start_time
        logger.info(f"流式完成，耗时: {duration:.2f}s")
        
        # 保存 AI 回复
        response_with_thinking = full_response
        if thinking_content:
            response_with_thinking = f"<thinking>{thinking_content}</thinking>\n{full_response}"
        
        chat_history.add_message(username, session_id, 'assistant', response_with_thinking, duration)
        
        emit('stream_end', {"duration": round(duration, 2), "thinking": thinking_content})
        
    except Exception as e:
        logger.error(f"处理消息失败: {e}", exc_info=True)
        emit('error', {"message": str(e)})


@socketio.on('regenerate')
def handle_regenerate(data):
    """重新生成回复"""
    username = data.get('username')
    if not username or username not in user_agents:
        emit('error', {"message": "请先登录"})
        return
    
    agent_manager = get_user_agent(username)
    session_id = data.get('session_id')
    user_msg_index = data.get('user_msg_index', -1)
    
    if not session_id:
        emit('error', {"message": "无效的会话"})
        return
    
    try:
        session = chat_history.get_session(username, session_id)
        messages = session['messages']
        
        logger.info(f"重新生成回复 (用户: {username}, 会话ID: {session_id}, 用户消息索引: {user_msg_index})")
        
        target_user_msg = None
        target_user_idx = -1
        
        if user_msg_index >= 0:
            for i in range(user_msg_index, -1, -1):
                if i < len(messages) and messages[i]['role'] == 'user':
                    target_user_msg = messages[i]['content']
                    target_user_idx = i
                    break
        else:
            for i in range(len(messages) - 1, -1, -1):
                if messages[i]['role'] == 'user':
                    target_user_msg = messages[i]['content']
                    target_user_idx = i
                    break
        
        if not target_user_msg:
            emit('error', {"message": "找不到用户消息"})
            return
        
        history = messages[:target_user_idx]
        
        messages_to_keep = []
        for i, msg in enumerate(messages):
            if i <= target_user_idx:
                messages_to_keep.append(msg)
        
        session['messages'] = messages_to_keep
        
        start_time = time.time()
        full_response = ""
        thinking_content = ""
        
        for chunk in agent_manager.chat_stream(target_user_msg, history):
            chunk_type = chunk.get('type')
            content = chunk.get('content', '')
            
            if chunk_type == 'stopped':
                emit('stopped', {"message": chunk.get('message', '已停止')})
                break
            
            if chunk_type == 'thinking':
                thinking_content += content
                emit('thinking', {"content": content, "append": True})
            elif chunk_type == 'content':
                full_response += content
                emit('stream', {"content": content})
            elif chunk_type == 'tool_call':
                emit('tool_call', {"name": chunk.get('name'), "args": chunk.get('args')})
            elif chunk_type == 'tool_result':
                emit('tool_result', {"name": chunk.get('name'), "result": chunk.get('result')})
            
            socketio.sleep(0.01)
        
        duration = time.time() - start_time
        logger.info(f"重新生成完成，耗时: {duration:.2f}s")
        
        response_with_thinking = full_response
        if thinking_content:
            response_with_thinking = f"<thinking>{thinking_content}</thinking>\n{full_response}"
        
        chat_history.add_message(username, session_id, 'assistant', response_with_thinking, duration)
        
        emit('stream_end', {"duration": round(duration, 2), "thinking": thinking_content})
        
    except Exception as e:
        logger.error(f"重新生成失败: {e}", exc_info=True)
        emit('error', {"message": str(e)})


@socketio.on('switch_model')
def handle_switch_model(data):
    """切换模型"""
    username = data.get('username')
    if not username or username not in user_agents:
        emit('error', {"message": "请先登录"})
        return
    
    agent_manager = get_user_agent(username)
    
    try:
        model_id = data.get('model_id')
        if not model_id:
            emit('error', {"message": "模型ID不能为空"})
            return
        
        logger.info(f"切换模型: {model_id} (用户: {username})")
        agent_manager.switch_model(model_id)
        emit('model_switched', {"model_id": model_id})
    except Exception as e:
        logger.error(f"切换模型失败: {e}")
        emit('error', {"message": str(e)})


@socketio.on('stop_generation')
def handle_stop_generation():
    """停止生成"""
    username = session.get('username') if hasattr(session, 'get') else None
    if username and username in user_agents:
        try:
            logger.info(f"收到停止生成请求 (用户: {username})")
            user_agents[username].stop_generation()
        except Exception as e:
            logger.error(f"停止生成失败: {e}")
            emit('error', {"message": str(e)})


if __name__ == '__main__':
    host = os.getenv('WEB_HOST', '0.0.0.0')
    port = int(os.getenv('WEB_PORT', 5000))
    
    logger.info("=" * 50)
    logger.info("Weaver - 智能对话助手启动中")
    logger.info(f"访问地址: http://{host}:{port}")
    logger.info("=" * 50)
    
    socketio.run(app, host=host, port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)


@app.route('/api/memory/process', methods=['POST'])
@require_login
def process_memories_manual():
    """手动触发短期记忆处理"""
    username = get_current_user()
    agent_manager = get_user_agent(username)
    
    try:
        if agent_manager.memory_system:
            agent_manager.memory_system.process_short_term_to_long_term()
            agent_manager.memory_system.merge_similar_memories()
            return jsonify({"success": True, "message": "记忆处理完成"})
        return jsonify({"success": False, "error": "记忆系统未启用"})
    except Exception as e:
        logger.error(f"手动处理记忆失败: {e}")
        return jsonify({"success": False, "error": str(e)})
