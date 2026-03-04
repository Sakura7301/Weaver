const socket = io();
let currentSession = null;
let currentMessageDiv = null;
let currentThinkingDiv = null;
let isStreaming = false;
let currentThinkingContent = "";
let currentFullText = "";
let messageCounter = 0;
let loadingIndicator = null;
let currentMemoryTab = 'long';
let selectedMemoryIds = new Set();
let modelsData = []; // 存储模型数据（包含特性信息）
let validatedModels = []; // 校验成功后获取的模型列表，用于记忆管理模型选择

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadModels();
    loadSessions();
    updateMemoryStats();
    setInterval(updateMemoryStats, 10000);
});

// ============ 模型和会话管理 ============

// 模型特性图标
const MODEL_FEATURE_ICONS = {
    vision: {
        icon: '👁️',
        title: '支持视觉/图片'
    },
    tools: {
        icon: '🔧',
        title: '支持工具调用'
    },
    reasoning: {
        icon: '🧠',
        title: '推理增强'
    },
    fast: {
        icon: '⚡',
        title: '快速响应'
    }
};

async function loadModels() {
    try {
        const res = await fetch('/api/models');
        modelsData = await res.json(); // 保存完整数据
        
        const select = document.getElementById('modelSelect');
        
        // 自定义渲染函数，在option中显示特性图标
        select.innerHTML = '';
        
        modelsData.forEach(m => {
            const option = document.createElement('option');
            option.value = m.id;
            
            // 构建显示文本：模型名 + 特性图标
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
            option.title = getModelFeatureTooltip(features); // 鼠标悬停提示
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
        if (!res.ok) {
            throw new Error(`HTTP error! status: ${res.status}`);
        }
        
        const data = await res.json();
        
        // 跟踪用户消息索引
        let userMsgIndex = -1;
        
        chatBox.innerHTML = data.messages.map((m, index) => {
            const msgId = `msg-${sessionId}-${index}`;
            
            if (m.role === 'user') {
                userMsgIndex = index; // 更新用户消息索引
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
                // AI消息记录对应的用户消息索引
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
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" 
                     style="margin-bottom: 16px; opacity: 0.5;">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="8" x2="12" y2="12"></line>
                    <line x1="12" y1="16" x2="12.01" y2="16"></line>
                </svg>
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
    const menuWidth = menuRect.width;
    const menuHeight = menuRect.height;
    
    const windowWidth = window.innerWidth;
    const windowHeight = window.innerHeight;
    
    let leftPos = rect.left - menuWidth + rect.width / 2 + 40;
    if (leftPos < 8) leftPos = 8;
    if (leftPos + menuWidth > windowWidth - 8) leftPos = windowWidth - menuWidth - 8;
    
    let topPos = rect.bottom + 4;
    if (topPos + menuHeight > windowHeight - 8) topPos = rect.top - menuHeight - 4;
    
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
    
    const sessionItem = document.querySelector(`[data-session-id="${sessionId}"]`);
    if (!sessionItem) return;
    
    const contentDiv = sessionItem.querySelector('.session-content');
    
    contentDiv.innerHTML = `
        <input type="text" class="rename-input" value="${escapeHtml(currentTitle)}" 
               onkeydown="handleRenameKeydown(event, '${sessionId}')" 
               onblur="cancelRename('${sessionId}', '${escapeHtml(currentTitle)}')" 
               autofocus>
    `;
    
    const input = contentDiv.querySelector('input');
    input.focus();
    input.select();
}

function handleRenameKeydown(event, sessionId) {
    if (event.key === 'Enter') {
        const newTitle = event.target.value.trim();
        if (newTitle) saveRename(sessionId, newTitle);
    } else if (event.key === 'Escape') {
        loadSessions();
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
        else { alert('重命名失败'); loadSessions(); }
    } catch (e) {
        console.error('重命名失败:', e);
        loadSessions();
    }
}

function cancelRename(sessionId, originalTitle) {
    setTimeout(() => loadSessions(), 200);
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
                    document.getElementById('chatBox').innerHTML = '';
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
                document.getElementById('chatBox').innerHTML = '';
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
    try {
        const res = await fetch('/api/sessions', { method: 'POST' });
        const data = await res.json();
        currentSession = data.session_id;
        document.getElementById('chatBox').innerHTML = '';
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
        // 变成停止按钮
        btn.className = 'stop-btn';
        btnText.textContent = '停止';
        btnIcon.innerHTML = `
            <rect x="6" y="6" width="12" height="12" fill="currentColor"></rect>
        `;
    } else {
        // 恢复发送按钮
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

// 修改：添加 userMsgIndex 参数，用于定位要重新生成的消息
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
    if (isStreaming) return;
    
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message) return;
    
    const chatBox = document.getElementById('chatBox');
    
    // 获取当前用户消息索引（在发送前计算）
    const existingMessages = chatBox.querySelectorAll('.message-wrapper');
    const userMsgIndex = existingMessages.length; // 新消息的索引
    
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
    isStreaming = true;
    updateSendButton(true); // 更新为停止按钮
    
    socket.emit('chat', {
        message: message,
        session_id: currentSession
    });
}

// 修改：regenerate 接收 userMsgIndex 参数，指定要重新生成的是哪条回复
function regenerate(userMsgIndex = -1) {
    if (isStreaming) return;
    
    const chatBox = document.getElementById('chatBox');
    const messages = chatBox.querySelectorAll('.message-wrapper');
    
    // 如果指定了用户消息索引，找到对应的AI回复并删除
    if (userMsgIndex >= 0) {
        // 找到该用户消息之后的AI回复
        for (let i = 0; i < messages.length; i++) {
            const msg = messages[i];
            const msgUserIndex = parseInt(msg.dataset.userMsgIndex || -1);
            if (msgUserIndex === userMsgIndex) {
                msg.remove();
                break;
            }
        }
    } else {
        // 兼容旧逻辑：删除最后一条消息
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
    
    // 发送重新生成请求，包含用户消息索引
    socket.emit('regenerate', { 
        session_id: currentSession,
        user_msg_index: userMsgIndex
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
    updateSendButton(false); // 恢复发送按钮
    
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

// ============ 记忆管理 ============

async function updateMemoryStats() {
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

async function deleteSelectedMemories() {
    if (selectedMemoryIds.size === 0) { showToast('请先选择要删除的记忆', 'warning'); return; }
    
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
            } else showToast('删除失败: ' + (data.error || '未知错误'), 'error');
        } catch (e) {
            console.error('批量删除失败:', e);
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
            } else showToast('清空失败: ' + (data.error || '未知错误'), 'error');
        } catch (e) {
            console.error('清空记忆失败:', e);
            showToast('清空失败', 'error');
        }
    });
}

async function addMemoryManually() {
    const input = document.getElementById('manualMemoryInput');
    const content = input.value.trim();
    if (!content) { showToast('请输入记忆内容', 'warning'); return; }
    
    try {
        const res = await fetch('/api/memory/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: content, type: 'long' })
        });
        
        const data = await res.json();
        if (data.success) {
            input.value = '';
            loadMemories();
            updateMemoryStats();
            showToast('记忆已保存', 'success');
        } else showToast('保存失败: ' + (data.error || '未知错误'), 'error');
    } catch (e) {
        console.error('保存记忆失败:', e);
        showToast('保存失败', 'error');
    }
}

async function deleteMemory(id) {
    if (!confirm('确定要删除这条记忆吗？')) return;
    
    try {
        const res = await fetch(`/api/memory/${id}?type=${currentMemoryTab}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.success) {
            selectedMemoryIds.delete(id);
            loadMemories();
            updateMemoryStats();
            showToast('已删除记忆', 'success');
        } else showToast('删除失败', 'error');
    } catch (e) {
        console.error('删除记忆失败:', e);
        showToast('删除失败', 'error');
    }
}

// ============ 设置 ============

async function openSettings() {
    try {
        const res = await fetch('/api/config');
        const config = await res.json();
        
        document.getElementById('config_OPENAI_API_KEY').value = config.OPENAI_API_KEY || '';
        document.getElementById('config_OPENAI_BASE_URL').value = config.OPENAI_BASE_URL || '';
        document.getElementById('config_memory_interval_value').value = config.MEMORY_INTERVAL_VALUE || '30';
        document.getElementById('config_memory_interval_unit').value = config.MEMORY_INTERVAL_UNIT || 'minutes';
        document.getElementById('config_WORKING_MEMORY_CAPACITY').value = config.WORKING_MEMORY_CAPACITY || '10';
        
        // 初始化记忆管理模型下拉框
        const memoryModelSelect = document.getElementById('config_MEMORY_MODEL');
        const currentMemoryModel = config.MEMORY_MODEL || '';
        
        // 如果已有校验过的模型列表，使用它；否则从主模型列表获取
        if (validatedModels.length > 0) {
            updateMemoryModelSelect(validatedModels, currentMemoryModel);
        } else {
            // 使用当前的模型列表
            updateMemoryModelSelect(modelsData.map(m => ({ id: m.id, name: m.name || m.id })), currentMemoryModel);
        }
        
        document.getElementById('settingsModal').classList.remove('hidden');
    } catch (e) {
        console.error('加载配置失败:', e);
        showToast('加载配置失败', 'error');
    }
}

// 更新记忆管理模型下拉框
function updateMemoryModelSelect(models, selectedModel) {
    const select = document.getElementById('config_MEMORY_MODEL');
    select.innerHTML = '<option value="">-- 使用对话模型 --</option>';
    
    models.forEach(m => {
        const option = document.createElement('option');
        option.value = m.id;
        option.textContent = m.name || m.id;
        if (m.id === selectedModel) option.selected = true;
        select.appendChild(option);
    });
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

// ============ API Key 校验 ============

async function validateApiKey() {
    const apiKey = document.getElementById('config_OPENAI_API_KEY').value.trim();
    const baseUrl = document.getElementById('config_OPENAI_BASE_URL').value.trim() || 'https://api.openai.com/v1';
    
    if (!apiKey) {
        showToast('请先输入 API Key', 'warning');
        return;
    }
    
    const btn = document.getElementById('validateApiBtn');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner" style="width: 14px; height: 14px; border-width: 2px;"></span> 校验中...';
    
    try {
        const res = await fetch('/api/validate-api', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey, base_url: baseUrl })
        });
        
        const data = await res.json();
        
        if (data.success) {
            showToast('校验成功！获取到 ' + data.models.length + ' 个模型', 'success');
            
            // 保存校验成功后的模型列表
            validatedModels = data.models;
            
            // 更新记忆管理模型下拉框
            const currentMemoryModel = document.getElementById('config_MEMORY_MODEL').value;
            updateMemoryModelSelect(validatedModels, currentMemoryModel);
            
            btn.innerHTML = '✅ 校验成功';
            btn.style.background = '#10b981';
            btn.style.color = 'white';
            btn.style.borderColor = '#10b981';
            
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.style.background = '';
                btn.style.color = '';
                btn.style.borderColor = '';
                btn.disabled = false;
            }, 2000);
        } else {
            showToast('校验失败: ' + (data.error || '未知错误'), 'error');
            btn.innerHTML = '❌ 校验失败';
            btn.style.background = '#ef4444';
            btn.style.color = 'white';
            btn.style.borderColor = '#ef4444';
            
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.style.background = '';
                btn.style.color = '';
                btn.style.borderColor = '';
                btn.disabled = false;
            }, 2000);
        }
    } catch (e) {
        console.error('校验失败:', e);
        showToast('校验请求失败', 'error');
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

async function saveSettings() {
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
            showToast('设置已保存', 'success');
            closeSettings();
            loadModels(); // 重新加载模型列表
        } else {
            showToast('保存失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        console.error('保存设置失败:', e);
        showToast('保存失败', 'error');
    }
}

async function switchModel() {
    const modelId = document.getElementById('modelSelect').value;
    if (!modelId) return;
    
    socket.emit('switch_model', { model_id: modelId });
}

// ============ 提示词设置 ============

async function openPromptSettings() {
    try {
        const res = await fetch('/api/prompt');
        const data = await res.json();
        document.getElementById('systemPromptInput').value = data.prompt || data.default_prompt;
        document.getElementById('promptModal').classList.remove('hidden');
    } catch (e) {
        console.error('加载提示词失败:', e);
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
            body: JSON.stringify({ prompt: prompt })
        });
        
        const data = await res.json();
        if (data.success) {
            showToast('提示词已保存', 'success');
            closePromptSettings();
        } else {
            showToast('保存失败', 'error');
        }
    } catch (e) {
        console.error('保存提示词失败:', e);
        showToast('保存失败', 'error');
    }
}

async function resetPromptToDefault() {
    try {
        const res = await fetch('/api/prompt');
        const data = await res.json();
        document.getElementById('systemPromptInput').value = data.default_prompt;
        showToast('已恢复默认提示词', 'success');
    } catch (e) {
        console.error('恢复默认提示词失败:', e);
    }
}

// ============ 工具函数 ============

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdown(text) {
    if (!text) return '';
    try {
        const html = marked.parse(text);
        return DOMPurify.sanitize(html);
    } catch (e) {
        return escapeHtml(text);
    }
}

function showConfirmDialog(message, onConfirm) {
    const overlay = document.getElementById('confirmDialogOverlay');
    const content = document.getElementById('confirmDialogContent');
    const confirmBtn = document.getElementById('confirmDialogBtn');
    
    content.textContent = message;
    overlay.classList.remove('hidden');
    
    const handleConfirm = () => {
        overlay.classList.add('hidden');
        confirmBtn.removeEventListener('click', handleConfirm);
        onConfirm();
    };
    
    confirmBtn.addEventListener('click', handleConfirm);
}

function closeConfirmDialog() {
    document.getElementById('confirmDialogOverlay').classList.add('hidden');
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
    const toast = document.createElement('div');
    
    const bgColors = {
        success: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
        error: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
        warning: 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
        info: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
    };
    
    toast.style.cssText = `
        background: ${bgColors[type] || bgColors.info};
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        font-size: 14px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        animation: slideInRight 0.3s ease;
        display: flex;
        align-items: center;
        gap: 8px;
    `;
    
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };
    
    toast.innerHTML = `<span style="font-weight: bold;">${icons[type] || icons.info}</span> ${escapeHtml(message)}`;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOutRight 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// 输入处理
function handleInputKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// 自动调整输入框高度
document.addEventListener('DOMContentLoaded', () => {
    const textarea = document.getElementById('messageInput');
    if (textarea) {
        textarea.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 100) + 'px';
        });
    }
});

// 输入菜单
function showInputMenu(event) {
    event.stopPropagation();
    
    const existingMenu = document.querySelector('.input-dropdown');
    if (existingMenu) existingMenu.remove();
    
    const btn = event.currentTarget;
    const rect = btn.getBoundingClientRect();
    
    const menu = document.createElement('div');
    menu.className = 'input-dropdown';
    menu.innerHTML = `
        <div class="menu-item" onclick="openPromptSettings()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
            </svg>
            <span>设置系统提示词</span>
        </div>
        <div class="menu-item" onclick="openMemoryManager()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
            <span>管理记忆库</span>
        </div>
    `;
    
    menu.style.position = 'fixed';
    menu.style.visibility = 'hidden';
    menu.style.zIndex = '10000';
    
    document.body.appendChild(menu);
    
    const menuRect = menu.getBoundingClientRect();
    const menuWidth = menuRect.width;
    const menuHeight = menuRect.height;
    
    const windowWidth = window.innerWidth;
    const windowHeight = window.innerHeight;
    
    let leftPos = rect.left - menuWidth + rect.width;
    if (leftPos < 8) leftPos = 8;
    if (leftPos + menuWidth > windowWidth - 8) leftPos = windowWidth - menuWidth - 8;
    
    let topPos = rect.top - menuHeight - 4;
    if (topPos < 8) topPos = rect.bottom + 4;
    
    menu.style.left = leftPos + 'px';
    menu.style.top = topPos + 'px';
    menu.style.visibility = 'visible';
    
    setTimeout(() => {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target) && e.target !== btn) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        });
    }, 0);
}

// 添加CSS动画
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from { opacity: 0; transform: translateX(20px); }
        to { opacity: 1; transform: translateX(0); }
    }
    @keyframes slideOutRight {
        from { opacity: 1; transform: translateX(0); }
        to { opacity: 0; transform: translateX(20px); }
    }
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
`;
document.head.appendChild(style);
