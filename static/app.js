const socket = io();
let currentSession = null;
let currentMessageDiv = null;
let currentThinkingDiv = null;
let isStreaming = false;
let currentThinkingContent = "";
let currentFullText = "";
let messageCounter = 0;
let currentMemoryTab = 'long';
let selectedMemoryIds = new Set();
let modelsData = [];
let validatedModels = [];

// 用户状态
let currentUser = null;
let isLoggedIn = false;
let isAdmin = false;

// ============ 初始化 ============

document.addEventListener('DOMContentLoaded', () => {
    checkLoginStatus();
});

// 检查登录状态
async function checkLoginStatus() {
    try {
        const res = await fetch('/api/auth/status');
        const data = await res.json();
        
        if (data.logged_in) {
            currentUser = data.username;
            isLoggedIn = true;
            isAdmin = data.is_admin;
            
            // Socket认证
            socket.emit('auth', { username: currentUser });
            
            // 加载数据
            loadModels();
            loadSessions();
            updateMemoryStats();
            setInterval(updateMemoryStats, 10000);
            
            // 显示欢迎消息
            showWelcomeMessage();
            
            // 更新UI
            updateUserButton();
            updateUIForLoginState();
        } else {
            // 显示登录框
            showLoginModal();
        }
    } catch (e) {
        console.error('检查登录状态失败:', e);
        showLoginModal();
    }
}

// ============ 登录相关 ============

function showLoginModal() {
    document.getElementById('loginModal').classList.remove('hidden');
    document.getElementById('mainContent').style.pointerEvents = 'none';
    document.getElementById('mainContent').style.opacity = '0.5';
}

function hideLoginModal() {
    document.getElementById('loginModal').classList.add('hidden');
    document.getElementById('mainContent').style.pointerEvents = 'auto';
    document.getElementById('mainContent').style.opacity = '1';
}

function switchLoginTab(tab) {
    const loginTab = document.getElementById('loginTab');
    const registerTab = document.getElementById('registerTab');
    const confirmPassword = document.getElementById('loginConfirmPassword');
    const submitBtn = document.getElementById('loginSubmitBtn');
    const errorDiv = document.getElementById('loginError');
    
    errorDiv.classList.add('hidden');
    
    if (tab === 'login') {
        loginTab.classList.add('active');
        registerTab.classList.remove('active');
        confirmPassword.classList.add('hidden');
        submitBtn.textContent = '登录';
        submitBtn.onclick = handleLogin;
    } else {
        loginTab.classList.remove('active');
        registerTab.classList.add('active');
        confirmPassword.classList.remove('hidden');
        submitBtn.textContent = '注册';
        submitBtn.onclick = handleRegister;
    }
}

async function handleLoginSubmit() {
    const loginTab = document.getElementById('loginTab');
    if (loginTab.classList.contains('active')) {
        await handleLogin();
    } else {
        await handleRegister();
    }
}

async function handleLogin() {
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    const errorDiv = document.getElementById('loginError');
    const submitBtn = document.getElementById('loginSubmitBtn');
    
    if (!username || !password) {
        showLoginError('请输入用户名和密码');
        return;
    }
    
    submitBtn.disabled = true;
    submitBtn.textContent = '登录中...';
    
    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        const data = await res.json();
        
        if (data.success) {
            currentUser = data.user.username;
            isLoggedIn = true;
            isAdmin = data.user.is_admin;
            
            hideLoginModal();
            
            // Socket认证
            socket.emit('auth', { username: currentUser });
            
            // 加载数据
            loadModels();
            loadSessions();
            updateMemoryStats();
            setInterval(updateMemoryStats, 10000);
            
            showWelcomeMessage();
            updateUserButton();
            updateUIForLoginState();
            
            showToast(`欢迎回来，${currentUser}！`, 'success');
        } else {
            showLoginError(data.message);
        }
    } catch (e) {
        showLoginError('登录失败，请稍后重试');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '登录';
    }
}

async function handleRegister() {
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    const confirmPassword = document.getElementById('loginConfirmPassword').value;
    const errorDiv = document.getElementById('loginError');
    const submitBtn = document.getElementById('loginSubmitBtn');
    
    if (!username || !password) {
        showLoginError('请输入用户名和密码');
        return;
    }
    
    if (password !== confirmPassword) {
        showLoginError('两次输入的密码不一致');
        return;
    }
    
    submitBtn.disabled = true;
    submitBtn.textContent = '注册中...';
    
    try {
        const res = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('注册成功，请登录', 'success');
            switchLoginTab('login');
            document.getElementById('loginPassword').value = '';
            document.getElementById('loginConfirmPassword').value = '';
        } else {
            showLoginError(data.message);
        }
    } catch (e) {
        showLoginError('注册失败，请稍后重试');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = '注册';
    }
}

function showLoginError(message) {
    const errorDiv = document.getElementById('loginError');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}

// 用户菜单
function showUserMenu(event) {
    event.stopPropagation();
    
    const existingMenu = document.querySelector('.user-dropdown');
    if (existingMenu) existingMenu.remove();
    
    const btn = event.currentTarget;
    const rect = btn.getBoundingClientRect();
    
    const menu = document.createElement('div');
    menu.className = 'user-dropdown';
    
    if (isLoggedIn) {
        menu.innerHTML = `
            <div class="user-dropdown-header">
                <div class="username">${escapeHtml(currentUser)}</div>
                <div class="role">${isAdmin ? '管理员' : '普通用户'}</div>
            </div>
            ${isAdmin ? `
            <div class="menu-item" onclick="openUserManagement()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                    <circle cx="9" cy="7" r="4"></circle>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                    <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                </svg>
                <span>用户管理</span>
            </div>
            ` : ''}
            <div class="menu-item" onclick="showChangePasswordModal()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                </svg>
                <span>修改密码</span>
            </div>
            <div class="menu-item" onclick="switchAccount()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                    <circle cx="8.5" cy="7" r="4"></circle>
                    <line x1="20" y1="8" x2="20" y2="14"></line>
                    <line x1="23" y1="11" x2="17" y2="11"></line>
                </svg>
                <span>切换账号</span>
            </div>
            <div class="menu-item delete" onclick="logout()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                    <polyline points="16 17 21 12 16 7"></polyline>
                    <line x1="21" y1="12" x2="9" y2="12"></line>
                </svg>
                <span>退出登录</span>
            </div>
        `;
    } else {
        menu.innerHTML = `
            <div class="menu-item" onclick="showLoginModal()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path>
                    <polyline points="10 17 15 12 10 7"></polyline>
                    <line x1="15" y1="12" x2="3" y2="12"></line>
                </svg>
                <span>登录 / 注册</span>
            </div>
        `;
    }
    
    menu.style.position = 'fixed';
    menu.style.right = (window.innerWidth - rect.left - 10) + 'px';
    menu.style.top = (rect.bottom + 8) + 'px';
    
    document.body.appendChild(menu);
    
    setTimeout(() => {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        });
    }, 0);
}

function updateUserButton() {
    const btn = document.getElementById('userBtn');
    if (isLoggedIn && currentUser) {
        btn.textContent = currentUser.charAt(0).toUpperCase();
    } else {
        btn.textContent = '?';
    }
}

function updateUIForLoginState() {
    const newChatBtn = document.getElementById('newChatBtn');
    const clearAllBtn = document.getElementById('clearAllBtn');
    const memoryStatsArea = document.getElementById('memoryStatsArea');
    
    if (isLoggedIn) {
        newChatBtn.disabled = false;
        clearAllBtn.disabled = false;
        memoryStatsArea.style.pointerEvents = 'auto';
        memoryStatsArea.style.opacity = '1';
    } else {
        newChatBtn.disabled = true;
        clearAllBtn.disabled = true;
        memoryStatsArea.style.pointerEvents = 'none';
        memoryStatsArea.style.opacity = '0.5';
    }
}

async function logout() {
    try {
        const res = await fetch('/api/auth/logout', { method: 'POST' });
        const data = await res.json();
        
        if (data.success) {
            currentUser = null;
            isLoggedIn = false;
            isAdmin = false;
            
            updateUserButton();
            showLoginModal();
            showToast('已退出登录', 'success');
        }
    } catch (e) {
        showToast('退出失败', 'error');
    }
}

function switchAccount() {
    logout();
}

// 修改密码
function showChangePasswordModal() {
    const existingMenu = document.querySelector('.user-dropdown');
    if (existingMenu) existingMenu.remove();
    
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.id = 'changePasswordModal';
    modal.innerHTML = `
        <div class="modal" style="max-width: 400px;">
            <div class="modal-header">
                <h2>修改密码</h2>
                <button class="modal-close" onclick="closeChangePasswordModal()">×</button>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label>原密码</label>
                    <input type="password" id="oldPassword" placeholder="请输入原密码">
                </div>
                <div class="form-group">
                    <label>新密码</label>
                    <input type="password" id="newPassword" placeholder="请输入新密码（至少8位）">
                </div>
                <div class="form-group">
                    <label>确认新密码</label>
                    <input type="password" id="confirmNewPassword" placeholder="请再次输入新密码">
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-cancel" onclick="closeChangePasswordModal()">取消</button>
                <button class="btn-save" onclick="submitChangePassword()">确定</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

function closeChangePasswordModal() {
    const modal = document.getElementById('changePasswordModal');
    if (modal) modal.remove();
}

async function submitChangePassword() {
    const oldPassword = document.getElementById('oldPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmNewPassword = document.getElementById('confirmNewPassword').value;
    
    if (!oldPassword || !newPassword || !confirmNewPassword) {
        showToast('请填写所有字段', 'error');
        return;
    }
    
    if (newPassword !== confirmNewPassword) {
        showToast('两次输入的新密码不一致', 'error');
        return;
    }
    
    if (newPassword.length < 8) {
        showToast('新密码至少需要8位', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/auth/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('密码修改成功', 'success');
            closeChangePasswordModal();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('修改失败', 'error');
    }
}

// 欢迎消息
function showWelcomeMessage() {
    const chatBox = document.getElementById('chatBox');
    chatBox.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-icon">👋</div>
            <div class="welcome-title">你好，${escapeHtml(currentUser)}！</div>
            <div class="welcome-subtitle">我今天能帮你什么？</div>
        </div>
    `;
}

// ============ 管理员用户管理 ============

async function openUserManagement() {
    const existingMenu = document.querySelector('.user-dropdown');
    if (existingMenu) existingMenu.remove();
    
    if (!isAdmin) {
        showToast('权限不足', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/admin/users');
        const data = await res.json();
        
        if (data.success) {
            renderUserTable(data.users);
            document.getElementById('userManagementModal').classList.remove('hidden');
        } else {
            showToast(data.error || '获取用户列表失败', 'error');
        }
    } catch (e) {
        showToast('获取用户列表失败', 'error');
    }
}

function renderUserTable(users) {
    const tbody = document.getElementById('userTableBody');
    tbody.innerHTML = users.map(user => `
        <tr>
            <td>
                ${escapeHtml(user.username)}
                ${user.is_admin ? '<span class="admin-badge">管理员</span>' : ''}
            </td>
            <td>${user.is_admin ? '管理员' : '普通用户'}</td>
            <td>${user.created_at ? new Date(user.created_at).toLocaleString() : '-'}</td>
            <td>${user.last_login ? new Date(user.last_login).toLocaleString() : '-'}</td>
            <td class="user-actions-cell">
                ${!user.is_admin ? `
                <button class="user-action-btn btn-cancel" onclick="showUserPassword('${user.username}')">查看密码</button>
                <button class="user-action-btn btn-cancel" onclick="resetUserPassword('${user.username}')">重置密码</button>
                <button class="user-action-btn btn-danger" onclick="deleteUser('${user.username}')">删除</button>
                ` : '<span style="color: #9ca3af; font-size: 12px;">管理员不可操作</span>'}
            </td>
        </tr>
    `).join('');
}

function closeUserManagement() {
    document.getElementById('userManagementModal').classList.add('hidden');
}

function showCreateUserForm() {
    document.getElementById('userFormTitle').textContent = '创建用户';
    document.getElementById('formUsername').value = '';
    document.getElementById('formPassword').value = '';
    document.getElementById('formUsername').disabled = false;
    document.getElementById('userFormModal').classList.remove('hidden');
    
    window.currentFormAction = 'create';
}

function closeUserForm() {
    document.getElementById('userFormModal').classList.add('hidden');
}

async function submitUserForm() {
    const username = document.getElementById('formUsername').value.trim();
    const password = document.getElementById('formPassword').value;
    
    if (!username || !password) {
        showToast('请填写用户名和密码', 'error');
        return;
    }
    
    if (password.length < 8) {
        showToast('密码至少需要8位', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/admin/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('用户创建成功', 'success');
            closeUserForm();
            openUserManagement();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('创建失败', 'error');
    }
}

async function showUserPassword(username) {
    try {
        const res = await fetch(`/api/admin/users/${username}/password`);
        const data = await res.json();
        
        if (data.success) {
            showToast(data.message, 'info');
        } else {
            showToast(data.error || '获取失败', 'error');
        }
    } catch (e) {
        showToast('获取失败', 'error');
    }
}

async function resetUserPassword(username) {
    const newPassword = prompt(`请输入 ${username} 的新密码（至少8位）:`);
    if (!newPassword) return;
    
    if (newPassword.length < 8) {
        showToast('密码至少需要8位', 'error');
        return;
    }
    
    try {
        const res = await fetch(`/api/admin/users/${username}/password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_password: newPassword })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('密码重置成功', 'success');
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('重置失败', 'error');
    }
}

async function deleteUser(username) {
    if (!confirm(`确定要删除用户 ${username} 吗？`)) return;
    
    try {
        const res = await fetch(`/api/admin/users/${username}`, { method: 'DELETE' });
        const data = await res.json();
        
        if (data.success) {
            showToast('用户已删除', 'success');
            openUserManagement();
        } else {
            showToast(data.message, 'error');
        }
    } catch (e) {
        showToast('删除失败', 'error');
    }
}

// ============ 输入框自适应高度 ============

function autoResize(textarea) {
    // 重置高度
    textarea.style.height = 'auto';
    
    // 计算行高
    const lineHeight = parseInt(getComputedStyle(textarea).lineHeight);
    const padding = parseInt(getComputedStyle(textarea).paddingTop) + parseInt(getComputedStyle(textarea).paddingBottom);
    
    // 最小1行，最大10行
    const minHeight = lineHeight + padding;
    const maxHeight = lineHeight * 10 + padding;
    
    // 设置新高度
    const newHeight = Math.min(Math.max(textarea.scrollHeight, minHeight), maxHeight);
    textarea.style.height = newHeight + 'px';
}

// ============ 模型和会话管理 ============

const MODEL_FEATURE_ICONS = {
    vision: { icon: '👁️', title: '支持视觉/图片' },
    tools: { icon: '🔧', title: '支持工具调用' },
    reasoning: { icon: '🧠', title: '推理增强' },
    fast: { icon: '⚡', title: '快速响应' }
};

async function loadModels() {
    try {
        const res = await fetch('/api/models');
        modelsData = await res.json();
        
        const select = document.getElementById('modelSelect');
        select.innerHTML = '';
        
        modelsData.forEach(m => {
            const option = document.createElement('option');
            option.value = m.id;
            
            let displayText = m.name || m.id;
            const features = m.features || {};
            const featureIcons = [];
            
            if (features.vision) featureIcons.push(MODEL_FEATURE_ICONS.vision.icon);
            if (features.tools) featureIcons.push(MODEL_FEATURE_ICONS.tools.icon);
            if (features.reasoning) featureIcons.push(MODEL_FEATURE_ICONS.reasoning.icon);
            if (features.fast) featureIcons.push(MODEL_FEATURE_ICONS.fast.icon);
            
            if (featureIcons.length > 0) {
                displayText += ' ' + featureIcons.join('');
            }
            
            option.textContent = displayText;
            option.title = getModelFeatureTooltip(features);
            select.appendChild(option);
        });
    } catch (e) {
        console.error('加载模型失败:', e);
    }
}

function getModelFeatureTooltip(features) {
    if (!features) return '';
    const tips = [];
    if (features.vision) tips.push(MODEL_FEATURE_ICONS.vision.title);
    if (features.tools) tips.push(MODEL_FEATURE_ICONS.tools.title);
    if (features.reasoning) tips.push(MODEL_FEATURE_ICONS.reasoning.title);
    if (features.fast) tips.push(MODEL_FEATURE_ICONS.fast.title);
    return tips.join(' | ');
}

async function loadSession(sessionId) {
    currentSession = sessionId;
    
    const chatBox = document.getElementById('chatBox');
    chatBox.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; 
                    height: 100%; color: #9ca3af; animation: fadeIn 0.3s ease;">
            <div class="loading-spinner" style="width: 40px; height: 40px; border-width: 3px; margin-bottom: 16px;"></div>
            <div style="font-size: 14px;">加载对话中...</div>
        </div>
    `;
    
    try {
        const res = await fetch(`/api/sessions/${sessionId}`);
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        
        const data = await res.json();
        
        let userMsgIndex = -1;
        
        chatBox.innerHTML = data.messages.map((m, index) => {
            const msgId = `msg-${sessionId}-${index}`;
            
            if (m.role === 'user') {
                userMsgIndex = index;
                return `
                    <div class="flex justify-end message-wrapper" data-msg-id="${msgId}" data-msg-index="${index}">
                        <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px; max-width: 70%; width: fit-content; margin-left: auto;">
                            <div class="message-user">${escapeHtml(m.content)}</div>
                            <div class="user-actions">
                                <button class="action-btn small" onclick="copyUserMessage(this)" title="复制">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                const correspondingUserIndex = userMsgIndex;
                let content = m.content;
                let thinking = "";
                
                if (content.includes('<thinking>') && content.includes('</thinking>')) {
                    const match = content.match(/<thinking>([\s\S]*?)<\/thinking>/);
                    if (match) {
                        thinking = match[1];
                        content = content.replace(/<thinking>[\s\S]*?<\/thinking>/, '').trim();
                    }
                }
                
                const thinkingHtml = thinking ? createThinkingHTML(thinking, msgId) : '';
                
                return `
                    <div class="flex flex-col items-start gap-2 message-wrapper" data-msg-id="${msgId}" data-msg-index="${index}" data-user-msg-index="${correspondingUserIndex}">
                        <div class="flex items-start gap-2 w-full">
                            <div class="flex-1">
                                ${thinkingHtml}
                                <div class="message-assistant" data-raw-text="${escapeHtml(content)}">${renderMarkdown(content)}</div>
                            </div>
                        </div>
                        ${createMessageActions(m.duration, content, correspondingUserIndex)}
                    </div>
                `;
            }
        }).join('');
        
        chatBox.scrollTop = chatBox.scrollHeight;
        loadSessions();
        
    } catch (e) {
        console.error('加载会话失败:', e);
        chatBox.innerHTML = `
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; 
                        height: 100%; color: #9ca3af; text-align: center; padding: 40px;">
                <div style="font-size: 16px; margin-bottom: 8px; color: #6b7280;">加载失败</div>
                <button onclick="loadSession('${sessionId}')" 
                        style="padding: 8px 20px; background: #f3f4f6; border: 1px solid #e5e7eb; border-radius: 6px; 
                               cursor: pointer; font-size: 13px; color: #374151;">
                    重新加载
                </button>
            </div>
        `;
    }
}

async function loadSessions() {
    try {
        const res = await fetch('/api/sessions');
        const sessions = await res.json();
        
        const list = document.getElementById('sessionList');
        if (sessions.length === 0) {
            list.innerHTML = '<div style="text-align: center; color: #9ca3af; padding: 20px; font-size: 14px;">暂无历史记录</div>';
            return;
        }
        
        list.innerHTML = sessions.map(s => `
            <div class="session-item ${s.id === currentSession ? 'active' : ''}" data-session-id="${s.id}">
                <div class="session-content" onclick="loadSession('${s.id}')">
                    <div style="font-weight: 500; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                        ${escapeHtml(s.title)}
                    </div>
                </div>
                <div class="session-menu-btn" onclick="event.stopPropagation(); showSessionMenu(event, '${s.id}', '${escapeHtml(s.title)}')">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                        <circle cx="8" cy="4" r="1.5"/>
                        <circle cx="8" cy="8" r="1.5"/>
                        <circle cx="8" cy="12" r="1.5"/>
                    </svg>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('加载会话列表失败:', e);
    }
}

function showSessionMenu(event, sessionId, title) {
    event.stopPropagation();
    
    const existingMenu = document.querySelector('.session-menu-dropdown');
    if (existingMenu) existingMenu.remove();
    
    const btn = event.currentTarget;
    const rect = btn.getBoundingClientRect();
    
    const menu = document.createElement('div');
    menu.className = 'session-menu-dropdown';
    menu.innerHTML = `
        <div class="menu-item" onclick="renameSession('${sessionId}', '${title}'); event.stopPropagation();">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
            </svg>
            <span>重命名</span>
        </div>
        <div class="menu-item delete" onclick="deleteSession('${sessionId}'); event.stopPropagation();">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
            <span>删除</span>
        </div>
    `;
    
    menu.style.position = 'fixed';
    menu.style.visibility = 'hidden';
    menu.style.zIndex = '10000';
    
    document.body.appendChild(menu);
    
    const menuRect = menu.getBoundingClientRect();
    let leftPos = rect.left - menuRect.width + rect.width / 2 + 40;
    if (leftPos < 8) leftPos = 8;
    if (leftPos + menuRect.width > window.innerWidth - 8) leftPos = window.innerWidth - menuRect.width - 8;
    
    let topPos = rect.bottom + 4;
    if (topPos + menuRect.height > window.innerHeight - 8) topPos = rect.top - menuRect.height - 4;
    
    menu.style.left = leftPos + 'px';
    menu.style.top = topPos + 'px';
    menu.style.visibility = 'visible';
    
    setTimeout(() => {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        });
    }, 0);
}

function renameSession(sessionId, currentTitle) {
    const menu = document.querySelector('.session-menu-dropdown');
    if (menu) menu.remove();
    
    const newTitle = prompt('请输入新标题:', currentTitle);
    if (newTitle && newTitle.trim()) {
        saveRename(sessionId, newTitle.trim());
    }
}

async function saveRename(sessionId, newTitle) {
    try {
        const res = await fetch(`/api/sessions/${sessionId}/rename`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle })
        });
        
        if (res.ok) loadSessions();
        else { showToast('重命名失败', 'error'); loadSessions(); }
    } catch (e) {
        console.error('重命名失败:', e);
        loadSessions();
    }
}

function deleteSession(sessionId) {
    const menu = document.querySelector('.session-menu-dropdown');
    if (menu) menu.remove();
    
    showConfirmDialog('确定要删除这个对话吗？', async () => {
        try {
            const res = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
            if (res.ok) {
                if (currentSession === sessionId) {
                    currentSession = null;
                    showWelcomeMessage();
                }
                loadSessions();
                showToast('已删除对话', 'success');
            } else showToast('删除失败', 'error');
        } catch (e) {
            console.error('删除失败:', e);
            showToast('删除失败', 'error');
        }
    });
}

function clearAllSessions() {
    showConfirmDialog('确定要清空所有历史记录吗？此操作不可恢复。', async () => {
        try {
            const res = await fetch('/api/sessions/all', { method: 'DELETE' });
            if (res.ok) {
                currentSession = null;
                showWelcomeMessage();
                loadSessions();
                showToast('已清空所有历史', 'success');
            } else showToast('清空失败', 'error');
        } catch (e) {
            console.error('清空失败:', e);
            showToast('清空失败', 'error');
        }
    });
}

async function createNewChat() {
    if (!isLoggedIn) {
        showToast('请先登录', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/sessions', { method: 'POST' });
        const data = await res.json();
        currentSession = data.session_id;
        showWelcomeMessage();
        loadSessions();
    } catch (e) {
        console.error('创建会话失败:', e);
    }
}

// ============ 发送/停止按钮 ============

function handleSendStopClick() {
    if (isStreaming) {
        stopGeneration();
    } else {
        sendMessage();
    }
}

function updateSendButton(streaming) {
    const btn = document.getElementById('sendBtn');
    const btnText = document.getElementById('sendBtnText');
    const btnIcon = document.getElementById('sendIcon');
    
    if (streaming) {
        btn.className = 'stop-btn';
        btnText.textContent = '停止';
        btnIcon.innerHTML = `<rect x="6" y="6" width="12" height="12" fill="currentColor"></rect>`;
    } else {
        btn.className = 'send-btn';
        btnText.textContent = '发送';
        btnIcon.innerHTML = `
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        `;
    }
}

function stopGeneration() {
    socket.emit('stop_generation');
    showToast('正在停止...', 'warning');
}

// ============ 消息操作 ============

function createThinkingHTML(thinking, uniqueId, isStreaming = false) {
    const wordCount = thinking.length;
    const label = isStreaming ? `思考中... (${wordCount} 字)` : `思考过程 (${wordCount} 字)`;
    
    return `
        <div class="thinking-box mb-2" id="thinking-box-${uniqueId}">
            <div class="thinking-toggle" onclick="toggleThinking('${uniqueId}')">
                <span class="thinking-icon">💭</span>
                <span class="thinking-label">${label}</span>
                <span class="thinking-arrow">▶</span>
            </div>
            <div class="thinking-content hidden" id="thinking-content-${uniqueId}">${escapeHtml(thinking)}</div>
        </div>
    `;
}

function toggleThinking(uniqueId) {
    const content = document.getElementById(`thinking-content-${uniqueId}`);
    const arrow = document.querySelector(`#thinking-box-${uniqueId} .thinking-arrow`);
    
    if (!content || !arrow) return;
    
    if (content.classList.contains('hidden')) {
        content.classList.remove('hidden');
        arrow.textContent = '▼';
    } else {
        content.classList.add('hidden');
        arrow.textContent = '▶';
    }
}

function createMessageActions(duration, content, userMsgIndex = -1) {
    const durationText = duration ? `耗时 ${duration}s` : '';
    
    return `
        <div class="message-actions">
            <div class="action-buttons">
                <button class="action-btn" onclick="copyMessage(this)" title="复制">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                </button>
                <button class="action-btn" onclick="regenerate(${userMsgIndex})" title="重新生成">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                    </svg>
                </button>
            </div>
            <div class="message-duration">${durationText}</div>
        </div>
    `;
}

function copyUserMessage(btn) {
    const wrapper = btn.closest('.message-wrapper');
    const contentDiv = wrapper.querySelector('.message-user');
    const text = contentDiv.textContent;
    
    navigator.clipboard.writeText(text).then(() => {
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
        setTimeout(() => { btn.innerHTML = originalHTML; }, 2000);
    });
}

function copyMessage(btn) {
    const wrapper = btn.closest('.message-wrapper');
    const contentDiv = wrapper.querySelector('.message-assistant');
    const text = contentDiv.getAttribute('data-raw-text') || contentDiv.textContent;
    
    navigator.clipboard.writeText(text).then(() => {
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>';
        setTimeout(() => { btn.innerHTML = originalHTML; }, 2000);
    });
}

// ============ 输入处理 ============

function handleInputKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function showInputMenu(event) {
    event.stopPropagation();
    
    const dropdown = document.getElementById('inputDropdown');
    const btn = event.currentTarget;
    const rect = btn.getBoundingClientRect();
    
    dropdown.classList.remove('hidden');
    dropdown.style.position = 'fixed';
    dropdown.style.right = (window.innerWidth - rect.right) + 'px';
    dropdown.style.bottom = (window.innerHeight - rect.top + 8) + 'px';
    
    setTimeout(() => {
        document.addEventListener('click', function closeDropdown(e) {
            if (!dropdown.contains(e.target) && e.target !== btn) {
                dropdown.classList.add('hidden');
                document.removeEventListener('click', closeDropdown);
            }
        });
    }, 0);
}

// ============ 消息发送和接收 ============

function createAIMessageWrapper(userMsgIndex = -1) {
    messageCounter++;
    const uniqueId = `new-${Date.now()}-${messageCounter}`;
    
    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col items-start gap-2 message-wrapper';
    wrapper.dataset.thinkingId = uniqueId;
    wrapper.dataset.userMsgIndex = userMsgIndex;
    wrapper.innerHTML = `
        <div class="flex items-start gap-2 w-full">
            <div class="flex-1">
                <div class="thinking-box mb-2 hidden" id="thinking-box-${uniqueId}">
                    <div class="thinking-toggle" onclick="toggleThinking('${uniqueId}')">
                        <span class="thinking-icon">💭</span>
                        <span class="thinking-label" id="thinking-label-${uniqueId}">思考中...</span>
                        <span class="thinking-arrow">▶</span>
                    </div>
                    <div class="thinking-content hidden" id="thinking-content-${uniqueId}"></div>
                </div>
                <div class="message-assistant" data-raw-text=""></div>
            </div>
        </div>
        <div class="message-actions" id="actions-${uniqueId}">
            <div class="action-buttons">
                <button class="action-btn" onclick="copyMessage(this)" title="复制">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                </button>
                <button class="action-btn" onclick="regenerate(${userMsgIndex})" title="重新生成">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                    </svg>
                </button>
            </div>
            <div class="message-duration" id="duration-${uniqueId}">
                <span style="color: #9ca3af; display: flex; align-items: center; gap: 6px;">
                    <span class="loading-spinner"></span>
                    处理中...
                </span>
            </div>
        </div>
    `;
    
    return wrapper;
}

function sendMessage() {
    if (!isLoggedIn) {
        showToast('请先登录', 'error');
        return;
    }
    
    if (isStreaming) return;
    
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    const chatBox = document.getElementById('chatBox');
    
    // 清除欢迎消息
    const welcomeMsg = chatBox.querySelector('.welcome-message');
    if (welcomeMsg) welcomeMsg.remove();
    
    const existingMessages = chatBox.querySelectorAll('.message-wrapper');
    const userMsgIndex = existingMessages.length;
    
    const userWrapper = document.createElement('div');
    userWrapper.className = 'flex justify-end message-wrapper';
    userWrapper.dataset.msgIndex = userMsgIndex;
    userWrapper.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px; max-width: 70%; width: fit-content; margin-left: auto;">
            <div class="message-user">${escapeHtml(message)}</div>
            <div class="user-actions">
                <button class="action-btn small" onclick="copyUserMessage(this)" title="复制">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                </button>
            </div>
        </div>
    `;
    chatBox.appendChild(userWrapper);
    
    const aiMessageWrapper = createAIMessageWrapper(userMsgIndex);
    chatBox.appendChild(aiMessageWrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
    
    const uniqueId = aiMessageWrapper.dataset.thinkingId;
    currentMessageDiv = aiMessageWrapper.querySelector('.message-assistant');
    currentThinkingDiv = document.getElementById(`thinking-content-${uniqueId}`);
    
    currentThinkingContent = "";
    currentFullText = "";
    
    input.value = '';
    input.style.height = 'auto';  // 重置输入框高度
    isStreaming = true;
    updateSendButton(true);
    
    socket.emit('chat', {
        message: message,
        session_id: currentSession,
        username: currentUser
    });
}

function regenerate(userMsgIndex = -1) {
    if (isStreaming) return;
    
    const chatBox = document.getElementById('chatBox');
    const messages = chatBox.querySelectorAll('.message-wrapper');
    
    if (userMsgIndex >= 0) {
        for (let i = 0; i < messages.length; i++) {
            const msg = messages[i];
            const msgUserIndex = parseInt(msg.dataset.userMsgIndex || -1);
            if (msgUserIndex === userMsgIndex) {
                msg.remove();
                break;
            }
        }
    } else {
        if (messages.length > 0) messages[messages.length - 1].remove();
    }
    
    const aiMessageWrapper = createAIMessageWrapper(userMsgIndex);
    chatBox.appendChild(aiMessageWrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
    
    const uniqueId = aiMessageWrapper.dataset.thinkingId;
    currentMessageDiv = aiMessageWrapper.querySelector('.message-assistant');
    currentThinkingDiv = document.getElementById(`thinking-content-${uniqueId}`);
    
    currentThinkingContent = "";
    currentFullText = "";
    
    isStreaming = true;
    updateSendButton(true);
    
    socket.emit('regenerate', { 
        session_id: currentSession,
        user_msg_index: userMsgIndex,
        username: currentUser
    });
}

// ============ Socket 事件处理 ============

socket.on('thinking', (data) => {
    if (!currentThinkingDiv) return;
    
    const thinkingBox = document.getElementById(currentThinkingDiv.id.replace('thinking-content', 'thinking-box'));
    if (thinkingBox && thinkingBox.classList.contains('hidden')) {
        thinkingBox.classList.remove('hidden');
    }
    
    if (data.append) {
        currentThinkingContent += data.content;
        currentThinkingDiv.textContent = currentThinkingContent;
    } else {
        currentThinkingContent = data.content;
        currentThinkingDiv.textContent = currentThinkingContent;
    }
    
    const label = thinkingBox.querySelector('.thinking-label');
    if (label) label.textContent = `思考中... (${currentThinkingContent.length} 字)`;
});

socket.on('stream', (data) => {
    if (!currentMessageDiv) return;
    
    if (currentFullText === '' && data.content) currentMessageDiv.innerHTML = '';
    
    currentFullText += data.content;
    currentMessageDiv.setAttribute('data-raw-text', currentFullText);
    currentMessageDiv.innerHTML = renderMarkdown(currentFullText);
    
    const chatBox = document.getElementById('chatBox');
    chatBox.scrollTop = chatBox.scrollHeight;
});

socket.on('stream_end', (data) => {
    isStreaming = false;
    updateSendButton(false);
    
    if (currentMessageDiv) {
        const wrapper = currentMessageDiv.closest('.message-wrapper');
        const uniqueId = wrapper.dataset.thinkingId;
        
        const durationDiv = document.getElementById(`duration-${uniqueId}`);
        if (durationDiv) durationDiv.textContent = `耗时 ${data.duration}s`;
        
        if (currentThinkingContent && data.thinking) {
            const thinkingBox = document.getElementById(`thinking-box-${uniqueId}`);
            if (thinkingBox) {
                const label = thinkingBox.querySelector('.thinking-label');
                if (label) label.textContent = `思考过程 (${currentThinkingContent.length} 字)`;
            }
        }
    }
    
    currentThinkingContent = "";
    currentFullText = "";
    loadSessions();
    updateMemoryStats();
});

socket.on('stopped', (data) => {
    isStreaming = false;
    updateSendButton(false);
    
    if (currentMessageDiv) {
        if (!currentFullText) {
            currentMessageDiv.innerHTML = '<span style="color: #9ca3af;">已停止生成</span>';
        }
    }
    
    showToast('已停止生成', 'warning');
});

socket.on('session_created', (data) => {
    currentSession = data.session_id;
    loadSessions();
});

socket.on('error', (data) => {
    isStreaming = false;
    updateSendButton(false);
    
    if (currentMessageDiv) {
        currentMessageDiv.innerHTML = `<span style="color: red;">错误: ${escapeHtml(data.message)}</span>`;
        
        const wrapper = currentMessageDiv.closest('.message-wrapper');
        const uniqueId = wrapper.dataset.thinkingId;
        const durationDiv = document.getElementById(`duration-${uniqueId}`);
        if (durationDiv) durationDiv.innerHTML = '<span style="color: #ef4444;">生成失败</span>';
    }
});

socket.on('tool_call', (data) => {
    console.log('工具调用:', data.name, data.args);
    if (data.name === 'save_memory_tool') showToast('AI 正在保存记忆...', 'success');
});

socket.on('tool_result', (data) => {
    console.log('工具结果:', data.name, data.result);
    if (data.name === 'save_memory_tool' && data.result && data.result.includes('已保存')) {
        showToast('AI 已保存记忆');
        updateMemoryStats();
    }
});

socket.on('auth_failed', (data) => {
    showToast(data.message || '请重新登录', 'error');
    logout();
});

// ============ 设置 ============

async function openSettings() {
    try {
        const res = await fetch('/api/config');
        const config = await res.json();
        
        // 根据是否管理员显示/隐藏API配置
        const apiKeyGroup = document.getElementById('apiKeyGroup');
        const baseUrlGroup = document.getElementById('baseUrlGroup');
        const saveBtn = document.getElementById('saveSettingsBtn');
        
        if (config.IS_ADMIN) {
            apiKeyGroup.style.display = 'block';
            baseUrlGroup.style.display = 'block';
            document.getElementById('config_OPENAI_API_KEY').value = config.OPENAI_API_KEY || '';
            document.getElementById('config_OPENAI_BASE_URL').value = config.OPENAI_BASE_URL || '';
            saveBtn.style.display = 'block';
        } else {
            apiKeyGroup.style.display = 'none';
            baseUrlGroup.style.display = 'none';
            // 普通用户自动验证API
            validateApiKeyForUser();
        }
        
        document.getElementById('config_memory_interval_value').value = config.MEMORY_INTERVAL_VALUE || '30';
        document.getElementById('config_memory_interval_unit').value = config.MEMORY_INTERVAL_UNIT || 'minutes';
        document.getElementById('config_WORKING_MEMORY_CAPACITY').value = config.WORKING_MEMORY_CAPACITY || '10';
        
        if (config.MEMORY_MODEL) {
            document.getElementById('config_MEMORY_MODEL').value = config.MEMORY_MODEL;
        }
        
        document.getElementById('settingsModal').classList.remove('hidden');
    } catch (e) {
        showToast('加载配置失败', 'error');
    }
}

async function validateApiKeyForUser() {
    try {
        const res = await fetch('/api/validate-api', { method: 'POST' });
        const data = await res.json();
        
        if (data.success) {
            validatedModels = data.models;
            updateMemoryModelSelect();
            showToast('API验证成功', 'success');
        } else {
            showToast('当前API不可用，请联系管理员配置', 'error');
        }
    } catch (e) {
        showToast('API验证失败，请联系管理员', 'error');
    }
}

function closeSettings() {
    document.getElementById('settingsModal').classList.add('hidden');
}

function toggleApiKeyVisibility() {
    const input = document.getElementById('config_OPENAI_API_KEY');
    const btn = event.target;
    
    if (input.type === 'password') {
        input.type = 'text';
        btn.textContent = '🙈 隐藏';
    } else {
        input.type = 'password';
        btn.textContent = '👁️ 显示';
    }
}

async function validateApiKey() {
    const apiKey = document.getElementById('config_OPENAI_API_KEY').value.trim();
    const baseUrl = document.getElementById('config_OPENAI_BASE_URL').value.trim();
    const btn = document.getElementById('validateApiBtn');
    
    if (!apiKey) {
        showToast('请输入API Key', 'error');
        return;
    }
    
    btn.disabled = true;
    btn.textContent = '验证中...';
    
    try {
        const res = await fetch('/api/validate-api', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey, base_url: baseUrl })
        });
        
        const data = await res.json();
        
        if (data.success) {
            validatedModels = data.models;
            updateMemoryModelSelect();
            showToast(data.message, 'success');
        } else {
            showToast(data.error, 'error');
        }
    } catch (e) {
        showToast('验证失败', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '✓ 校验';
    }
}

function updateMemoryModelSelect() {
    const select = document.getElementById('config_MEMORY_MODEL');
    select.innerHTML = '<option value="">-- 选择模型 --</option>';
    
    validatedModels.forEach(m => {
        const option = document.createElement('option');
        option.value = m.id;
        option.textContent = m.name || m.id;
        select.appendChild(option);
    });
}

async function saveSettings() {
    if (!isAdmin) {
        showToast('只有管理员可以保存配置', 'error');
        return;
    }
    
    const config = {
        OPENAI_API_KEY: document.getElementById('config_OPENAI_API_KEY').value,
        OPENAI_BASE_URL: document.getElementById('config_OPENAI_BASE_URL').value,
        MEMORY_INTERVAL_VALUE: document.getElementById('config_memory_interval_value').value,
        MEMORY_INTERVAL_UNIT: document.getElementById('config_memory_interval_unit').value,
        MEMORY_MODEL: document.getElementById('config_MEMORY_MODEL').value,
        WORKING_MEMORY_CAPACITY: document.getElementById('config_WORKING_MEMORY_CAPACITY').value
    };
    
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('保存成功', 'success');
            closeSettings();
            loadModels();
        } else {
            showToast('保存失败', 'error');
        }
    } catch (e) {
        showToast('保存失败', 'error');
    }
}

// ============ 提示词设置 ============

async function openPromptSettings() {
    const dropdown = document.getElementById('inputDropdown');
    if (dropdown) dropdown.classList.add('hidden');
    
    try {
        const res = await fetch('/api/prompt');
        const data = await res.json();
        
        document.getElementById('systemPromptInput').value = data.prompt || data.default_prompt;
        document.getElementById('promptModal').classList.remove('hidden');
    } catch (e) {
        showToast('加载提示词失败', 'error');
    }
}

function closePromptSettings() {
    document.getElementById('promptModal').classList.add('hidden');
}

async function savePromptSettings() {
    const prompt = document.getElementById('systemPromptInput').value;
    
    try {
        const res = await fetch('/api/prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('保存成功', 'success');
            closePromptSettings();
        } else {
            showToast('保存失败', 'error');
        }
    } catch (e) {
        showToast('保存失败', 'error');
    }
}

async function resetPromptToDefault() {
    try {
        const res = await fetch('/api/prompt');
        const data = await res.json();
        document.getElementById('systemPromptInput').value = data.default_prompt;
    } catch (e) {
        showToast('获取默认提示词失败', 'error');
    }
}

// ============ 记忆处理 ============

async function processMemories() {
    const dropdown = document.getElementById('inputDropdown');
    if (dropdown) dropdown.classList.add('hidden');
    
    try {
        const res = await fetch('/api/memory/process', { method: 'POST' });
        const data = await res.json();
        
        if (data.success) {
            showToast('记忆处理完成', 'success');
            updateMemoryStats();
        } else {
            showToast(data.error || '处理失败', 'error');
        }
    } catch (e) {
        showToast('处理失败', 'error');
    }
}

// ============ 模型切换 ============

function switchModel() {
    const modelId = document.getElementById('modelSelect').value;
    socket.emit('switch_model', { model_id: modelId, username: currentUser });
}

// ============ 记忆管理 ============

async function updateMemoryStats() {
    if (!isLoggedIn) return;
    
    try {
        const res = await fetch('/api/memory/stats');
        if (!res.ok) return;
        const data = await res.json();
        
        const longTermEl = document.getElementById('longTermCount');
        const workingEl = document.getElementById('workingCount');
        const shortTermEl = document.getElementById('shortTermCount');
        
        if (longTermEl) longTermEl.textContent = `📋 长期: ${data.long_term || 0}`;
        if (workingEl) workingEl.textContent = `💡 工作: ${data.working || 0}`;
        if (shortTermEl) shortTermEl.textContent = `📝 短期: ${data.short_term || 0}`;
        
        const modalBadge = document.getElementById('memoryStatsBadge');
        if (modalBadge) {
            modalBadge.textContent = `长期:${data.long_term || 0} | 工作:${data.working || 0} | 短期:${data.short_term || 0}`;
        }
    } catch (e) {
        console.error('获取记忆统计失败:', e);
    }
}

function openMemoryManager() {
    if (!isLoggedIn) {
        showToast('请先登录', 'error');
        return;
    }
    document.getElementById('memoryModal').classList.remove('hidden');
    selectedMemoryIds.clear();
    updateBatchActions();
    loadMemories();
    toggleAddMemoryInput();
}

function closeMemoryManager() {
    document.getElementById('memoryModal').classList.add('hidden');
    selectedMemoryIds.clear();
}

function switchMemoryTab(type) {
    currentMemoryTab = type;
    selectedMemoryIds.clear();
    updateBatchActions();
    
    document.querySelectorAll('.memory-nav-btn').forEach(btn => {
        btn.classList.remove('active');
        btn.style.background = 'transparent';
        btn.style.borderLeftColor = 'transparent';
        btn.style.color = '#374151';
    });
    
    const activeBtn = document.getElementById(`nav-${type}`);
    activeBtn.classList.add('active');
    activeBtn.style.background = 'white';
    activeBtn.style.borderLeftColor = '#667eea';
    activeBtn.style.color = '#667eea';
    
    const addContainer = document.getElementById('addMemoryContainer');
    addContainer.style.display = type === 'long' ? 'block' : 'none';
    
    loadMemories();
}

function toggleAddMemoryInput() {
    const addContainer = document.getElementById('addMemoryContainer');
    if (addContainer) addContainer.style.display = currentMemoryTab === 'long' ? 'block' : 'none';
}

async function loadMemories() {
    const listEl = document.getElementById('memoryList');
    
    listEl.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px 20px; color: #9ca3af;">
            <div class="loading-spinner" style="width: 40px; height: 40px; border-width: 3px; margin-bottom: 16px;"></div>
            <div style="font-size: 14px;">加载记忆中...</div>
        </div>
    `;
    
    try {
        const res = await fetch(`/api/memory/all?type=${currentMemoryTab}`);
        if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
        
        const data = await res.json();
        const memories = data.memories || [];
        
        updateMemoryStats();
        
        if (memories.length === 0) {
            const typeNames = { long: '长期', working: '工作', short: '短期' };
            const typeDesc = {
                long: 'AI会自动保存重要的长期记忆，您也可以手动添加',
                working: '工作记忆存储当前对话的关键信息，帮助AI理解上下文',
                short: '对话历史会自动保存为短期记忆，用于上下文理解'
            };
            
            listEl.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; 
                            padding: 60px 20px; color: #9ca3af; text-align: center;">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="margin-bottom: 16px; opacity: 0.4;">
                        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                    </svg>
                    <div style="font-size: 16px; font-weight: 500; margin-bottom: 8px; color: #6b7280;">
                        暂无${typeNames[currentMemoryTab]}记忆
                    </div>
                    <div style="font-size: 13px; opacity: 0.8; max-width: 300px;">${typeDesc[currentMemoryTab]}</div>
                </div>
            `;
            return;
        }
        
        const typeColors = { long: '#667eea', working: '#d97706', short: '#6b7280' };
        
        listEl.innerHTML = memories.map((m, index) => `
            <div class="memory-card ${selectedMemoryIds.has(m.id) ? 'selected' : ''}" 
                 data-memory-id="${m.id}"
                 style="background: white; border: 1px solid #e5e7eb; border-radius: 12px; 
                     padding: 16px; margin-bottom: 12px;
                     border-left: 4px solid ${typeColors[currentMemoryTab]};">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;">
                    <div style="display: flex; align-items: flex-start; gap: 12px; flex: 1;">
                        <input type="checkbox" class="memory-checkbox" 
                               data-id="${m.id}" 
                               ${selectedMemoryIds.has(m.id) ? 'checked' : ''}
                               onchange="toggleMemorySelection('${m.id}')"
                               onclick="event.stopPropagation();">
                        <div style="flex: 1; min-width: 0;">
                            <div style="font-size: 14px; color: #1f2937; line-height: 1.6; word-break: break-word; font-weight: 500;">
                                ${escapeHtml(m.content)}
                            </div>
                            <div style="margin-top: 10px; display: flex; align-items: center; gap: 8px; font-size: 12px; color: #9ca3af;">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="12" r="10"></circle>
                                    <polyline points="12 6 12 12 16 14"></polyline>
                                </svg>
                                ${new Date(m.created_at).toLocaleString()}
                                ${m.score ? `<span style="background: #f3f4f6; padding: 2px 10px; border-radius: 12px; margin-left: 8px;">相关度: ${(m.score * 100).toFixed(0)}%</span>` : ''}
                                ${m.priority !== undefined ? `<span style="background: #fef3c7; padding: 2px 10px; border-radius: 12px; margin-left: 8px;">优先级: ${m.priority}</span>` : ''}
                            </div>
                        </div>
                    </div>
                    <button onclick="deleteMemory('${m.id}')" 
                            style="padding: 8px; background: transparent; color: #9ca3af; border: none; 
                                   border-radius: 8px; cursor: pointer;">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>
            </div>
        `).join('');
        
    } catch (e) {
        console.error('加载记忆失败:', e);
        listEl.innerHTML = `<div style="text-align: center; padding: 40px; color: #9ca3af;">加载失败</div>`;
    }
}

function toggleMemorySelection(memoryId) {
    if (selectedMemoryIds.has(memoryId)) selectedMemoryIds.delete(memoryId);
    else selectedMemoryIds.add(memoryId);
    updateBatchActions();
    updateMemoryCardStyles();
}

function updateBatchActions() {
    const batchActions = document.getElementById('batchActions');
    const selectedCount = document.getElementById('selectedCount');
    
    if (selectedMemoryIds.size > 0) {
        batchActions.classList.add('visible');
        selectedCount.textContent = `已选择 ${selectedMemoryIds.size} 条`;
    } else {
        batchActions.classList.remove('visible');
    }
}

function updateMemoryCardStyles() {
    document.querySelectorAll('.memory-card').forEach(card => {
        const memoryId = card.dataset.memoryId;
        if (selectedMemoryIds.has(memoryId)) card.classList.add('selected');
        else card.classList.remove('selected');
    });
}

function toggleSelectAllMemories() {
    const selectAllCheckbox = document.getElementById('selectAllMemories');
    const allCheckboxes = document.querySelectorAll('.memory-checkbox');
    
    if (selectAllCheckbox.checked) {
        allCheckboxes.forEach(cb => { selectedMemoryIds.add(cb.dataset.id); cb.checked = true; });
    } else {
        allCheckboxes.forEach(cb => { selectedMemoryIds.delete(cb.dataset.id); cb.checked = false; });
    }
    updateBatchActions();
    updateMemoryCardStyles();
}

function clearSelection() {
    selectedMemoryIds.clear();
    document.querySelectorAll('.memory-checkbox').forEach(cb => cb.checked = false);
    updateBatchActions();
    updateMemoryCardStyles();
}

async function addMemory() {
    const input = document.getElementById('newMemoryInput');
    const content = input.value.trim();
    
    if (!content) {
        showToast('请输入记忆内容', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/memory/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, type: 'long' })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('记忆添加成功', 'success');
            input.value = '';
            loadMemories();
            updateMemoryStats();
        } else {
            showToast(data.error || '添加失败', 'error');
        }
    } catch (e) {
        showToast('添加失败', 'error');
    }
}

async function deleteMemory(memoryId) {
    showConfirmDialog('确定要删除这条记忆吗？', async () => {
        try {
            const res = await fetch(`/api/memory/${memoryId}?type=${currentMemoryTab}`, { method: 'DELETE' });
            const data = await res.json();
            
            if (data.success) {
                showToast('已删除', 'success');
                loadMemories();
                updateMemoryStats();
            } else {
                showToast('删除失败', 'error');
            }
        } catch (e) {
            showToast('删除失败', 'error');
        }
    });
}

async function deleteSelectedMemories() {
    if (selectedMemoryIds.size === 0) {
        showToast('请先选择要删除的记忆', 'error');
        return;
    }
    
    showConfirmDialog(`确定要删除选中的 ${selectedMemoryIds.size} 条记忆吗？`, async () => {
        try {
            const res = await fetch('/api/memory/batch-delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: currentMemoryTab, ids: Array.from(selectedMemoryIds) })
            });
            
            const data = await res.json();
            if (data.success) {
                showToast(`已删除 ${data.deleted_count} 条记忆`, 'success');
                selectedMemoryIds.clear();
                loadMemories();
                updateMemoryStats();
            } else {
                showToast('删除失败: ' + (data.error || '未知错误'), 'error');
            }
        } catch (e) {
            showToast('删除失败', 'error');
        }
    });
}

function confirmClearAllMemory() {
    const typeNames = { long: '长期', working: '工作', short: '短期' };
    
    showConfirmDialog(`确定要清空所有${typeNames[currentMemoryTab]}记忆吗？此操作不可恢复。`, async () => {
        try {
            const res = await fetch('/api/memory/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: currentMemoryTab })
            });
            
            const data = await res.json();
            if (data.success) {
                showToast(`已清空${typeNames[currentMemoryTab]}记忆`, 'success');
                selectedMemoryIds.clear();
                loadMemories();
                updateMemoryStats();
            } else {
                showToast('清空失败', 'error');
            }
        } catch (e) {
            showToast('清空失败', 'error');
        }
    });
}

// ============ 工具函数 ============

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdown(text) {
    try {
        return DOMPurify.sanitize(marked.parse(text));
    } catch (e) {
        return escapeHtml(text);
    }
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    
    const colors = {
        success: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
        error: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
        warning: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
        info: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    };
    
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };
    
    const toast = document.createElement('div');
    toast.style.cssText = `
        background: ${colors[type]};
        color: white;
        padding: 12px 20px;
        border-radius: 10px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 14px;
        animation: slideIn 0.3s ease;
        min-width: 200px;
    `;
    toast.innerHTML = `<span style="font-size: 16px;">${icons[type]}</span> ${escapeHtml(message)}`;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// 确认对话框
let confirmCallback = null;

function showConfirmDialog(message, callback) {
    document.getElementById('confirmContent').textContent = message;
    document.getElementById('confirmModal').classList.remove('hidden');
    confirmCallback = callback;
}

function closeConfirmDialog() {
    document.getElementById('confirmModal').classList.add('hidden');
    confirmCallback = null;
}

function executeConfirm() {
    if (confirmCallback) {
        confirmCallback();
    }
    closeConfirmDialog();
}

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
    @keyframes fadeOut {
        from { opacity: 1; }
        to { opacity: 0; }
    }
`;
document.head.appendChild(style);
