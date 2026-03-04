"""
用户管理模块 - 支持登录、注册、权限管理
"""
import os
import re
import sqlite3
import hashlib
import secrets
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv
from log import logger

load_dotenv()

# 用户数据库路径
USER_DB_PATH = "users.db"

# 密码最小长度
MIN_PASSWORD_LENGTH = 8

# 用户名正则：只允许字母、数字、下划线
USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]+$')


class UserManager:
    """用户管理器"""
    
    def __init__(self):
        self._init_db()
        self._ensure_admin_exists()
    
    def _get_conn(self):
        """获取数据库连接"""
        conn = sqlite3.connect(USER_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """初始化用户数据库"""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()
        logger.info("用户数据库初始化完成")
    
    def _ensure_admin_exists(self):
        """确保管理员用户存在"""
        admin_password = os.getenv("ADMIN_PASSWORD", "")
        
        if not admin_password:
            logger.warning("未在.env中配置ADMIN_PASSWORD，管理员用户将使用默认密码")
            admin_password = "admin12345678"  # 默认密码，建议在.env中配置
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 检查root用户是否存在
        cursor.execute("SELECT id FROM users WHERE username = ?", ("root",))
        if cursor.fetchone() is None:
            # 创建root用户
            salt, password_hash = self._hash_password(admin_password)
            cursor.execute(
                "INSERT INTO users (username, password_hash, salt, is_admin) VALUES (?, ?, ?, 1)",
                ("root", password_hash, salt)
            )
            conn.commit()
            logger.info("已创建管理员用户 'root'")
        
        conn.close()
    
    def _hash_password(self, password: str) -> Tuple[str, str]:
        """生成密码哈希"""
        salt = secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return salt, password_hash
    
    def _verify_password(self, password: str, salt: str, password_hash: str) -> bool:
        """验证密码"""
        computed_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        ).hex()
        return computed_hash == password_hash
    
    def _validate_username(self, username: str) -> Tuple[bool, str]:
        """验证用户名"""
        if not username:
            return False, "用户名不能为空"
        
        if len(username) < 3:
            return False, "用户名至少需要3个字符"
        
        if len(username) > 20:
            return False, "用户名最多20个字符"
        
        if not USERNAME_PATTERN.match(username):
            return False, "用户名只能包含字母、数字和下划线"
        
        return True, ""
    
    def _validate_password(self, password: str) -> Tuple[bool, str]:
        """验证密码"""
        if not password:
            return False, "密码不能为空"
        
        if len(password) < MIN_PASSWORD_LENGTH:
            return False, f"密码至少需要{MIN_PASSWORD_LENGTH}个字符"
        
        return True, ""
    
    def register(self, username: str, password: str) -> Tuple[bool, str]:
        """
        用户注册
        
        Returns:
            (success, message): 成功状态和消息
        """
        # 验证用户名
        valid, msg = self._validate_username(username)
        if not valid:
            return False, msg
        
        # 验证密码
        valid, msg = self._validate_password(password)
        if not valid:
            return False, msg
        
        # 检查用户名是否已存在
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone() is not None:
            conn.close()
            return False, "用户名已存在"
        
        # 创建用户
        salt, password_hash = self._hash_password(password)
        try:
            cursor.execute(
                "INSERT INTO users (username, password_hash, salt, is_admin) VALUES (?, ?, ?, 0)",
                (username, password_hash, salt)
            )
            conn.commit()
            conn.close()
            logger.info(f"新用户注册成功: {username}")
            return True, "注册成功"
        except Exception as e:
            logger.error(f"注册失败: {e}")
            conn.close()
            return False, "注册失败，请稍后重试"
    
    def login(self, username: str, password: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        用户登录
        
        Returns:
            (success, message, user_info): 成功状态、消息和用户信息
        """
        if not username or not password:
            return False, "用户名和密码不能为空", None
        
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, password_hash, salt, is_admin FROM users WHERE username = ?",
            (username,)
        )
        row = cursor.fetchone()
        
        if row is None:
            conn.close()
            return False, "用户名或密码错误", None
        
        # 验证密码
        if not self._verify_password(password, row['salt'], row['password_hash']):
            conn.close()
            return False, "用户名或密码错误", None
        
        # 更新最后登录时间
        cursor.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (datetime.now().isoformat(), row['id'])
        )
        conn.commit()
        conn.close()
        
        user_info = {
            "id": row['id'],
            "username": row['username'],
            "is_admin": bool(row['is_admin'])
        }
        
        logger.info(f"用户登录成功: {username}")
        return True, "登录成功", user_info
    
    def change_password(self, username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        修改密码
        """
        # 验证旧密码
        success, msg, _ = self.login(username, old_password)
        if not success:
            return False, "原密码错误"
        
        # 验证新密码
        valid, msg = self._validate_password(new_password)
        if not valid:
            return False, msg
        
        # 更新密码
        salt, password_hash = self._hash_password(new_password)
        conn = self._get_conn()
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
            (password_hash, salt, username)
        )
        conn.commit()
        conn.close()
        
        logger.info(f"用户修改密码成功: {username}")
        return True, "密码修改成功"
    
    def admin_change_password(self, admin_username: str, target_username: str, new_password: str) -> Tuple[bool, str]:
        """
        管理员修改用户密码
        """
        # 验证是否是管理员
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE username = ?", (admin_username,))
        admin_row = cursor.fetchone()
        
        if admin_row is None or not admin_row['is_admin']:
            conn.close()
            return False, "权限不足"
        
        # 验证新密码
        valid, msg = self._validate_password(new_password)
        if not valid:
            conn.close()
            return False, msg
        
        # 检查目标用户是否存在
        cursor.execute("SELECT id FROM users WHERE username = ?", (target_username,))
        if cursor.fetchone() is None:
            conn.close()
            return False, "用户不存在"
        
        # 更新密码
        salt, password_hash = self._hash_password(new_password)
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ? WHERE username = ?",
            (password_hash, salt, target_username)
        )
        conn.commit()
        conn.close()
        
        logger.info(f"管理员 {admin_username} 修改了用户 {target_username} 的密码")
        return True, "密码修改成功"
    
    def get_all_users(self, admin_username: str) -> Tuple[bool, List[Dict]]:
        """
        获取所有用户列表（仅管理员）
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 验证是否是管理员
        cursor.execute("SELECT is_admin FROM users WHERE username = ?", (admin_username,))
        admin_row = cursor.fetchone()
        
        if admin_row is None or not admin_row['is_admin']:
            conn.close()
            return False, []
        
        # 获取所有用户
        cursor.execute(
            "SELECT id, username, is_admin, created_at, last_login FROM users ORDER BY id"
        )
        users = []
        for row in cursor.fetchall():
            users.append({
                "id": row['id'],
                "username": row['username'],
                "is_admin": bool(row['is_admin']),
                "created_at": row['created_at'],
                "last_login": row['last_login']
            })
        
        conn.close()
        return True, users
    
    def get_user_password(self, admin_username: str, target_username: str) -> Tuple[bool, str]:
        """
        获取用户密码（仅管理员，返回的是实际密码或提示不可用）
        注意：由于密码是哈希存储，这里只返回提示信息
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 验证是否是管理员
        cursor.execute("SELECT is_admin FROM users WHERE username = ?", (admin_username,))
        admin_row = cursor.fetchone()
        
        if admin_row is None or not admin_row['is_admin']:
            conn.close()
            return False, "权限不足"
        
        # 检查目标用户
        cursor.execute("SELECT username, is_admin FROM users WHERE username = ?", (target_username,))
        user_row = cursor.fetchone()
        
        if user_row is None:
            conn.close()
            return False, "用户不存在"
        
        conn.close()
        
        # 由于密码是哈希存储，无法返回原始密码
        # 这里返回一个提示，告诉管理员可以重置密码
        if user_row['is_admin']:
            return True, "管理员账户密码不可查看，可通过.env配置ADMIN_PASSWORD来重置"
        else:
            return True, "密码已加密存储，无法查看原始密码，可使用重置密码功能"
    
    def delete_user(self, admin_username: str, target_username: str) -> Tuple[bool, str]:
        """
        删除用户（仅管理员，不能删除root）
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 验证是否是管理员
        cursor.execute("SELECT is_admin FROM users WHERE username = ?", (admin_username,))
        admin_row = cursor.fetchone()
        
        if admin_row is None or not admin_row['is_admin']:
            conn.close()
            return False, "权限不足"
        
        # 不能删除root用户
        if target_username == "root":
            conn.close()
            return False, "不能删除管理员账户 root"
        
        # 检查目标用户是否存在
        cursor.execute("SELECT id FROM users WHERE username = ?", (target_username,))
        if cursor.fetchone() is None:
            conn.close()
            return False, "用户不存在"
        
        # 删除用户
        conn.execute("DELETE FROM users WHERE username = ?", (target_username,))
        conn.commit()
        conn.close()
        
        logger.info(f"管理员 {admin_username} 删除了用户 {target_username}")
        return True, "用户已删除"
    
    def create_user_by_admin(self, admin_username: str, username: str, password: str) -> Tuple[bool, str]:
        """
        管理员创建用户
        """
        # 验证是否是管理员
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE username = ?", (admin_username,))
        admin_row = cursor.fetchone()
        
        if admin_row is None or not admin_row['is_admin']:
            conn.close()
            return False, "权限不足"
        
        conn.close()
        
        # 使用普通注册逻辑
        return self.register(username, password)
    
    def is_admin(self, username: str) -> bool:
        """检查用户是否是管理员"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        conn.close()
        
        return row is not None and bool(row['is_admin'])


# 全局用户管理器实例
user_manager = UserManager()
