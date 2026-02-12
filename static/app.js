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
        
        chatBox.innerHTML = data.messages.map((m, index) => {
            const msgId = `msg-${sessionId}-${index}`;
            
            if (m.role === 'user') {
                return `
                    <div class="flex justify-end message-wrapper" data-msg-id="${msgId}">
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
                    <div class="flex flex-col items-start gap-2 message-wrapper" data-msg-id="${msgId}">
                        <div class="flex items-start gap-2 w-full">
                            <div class="flex-1">
                                ${thinkingHtml}
                                <div class="message-assistant" data-raw-text="${escapeHtml(content)}">${renderMarkdown(content)}</div>
                            </div>
                        </div>
                        ${createMessageActions(m.duration, content)}
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

function createMessageActions(duration, content) {
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
                <button class="action-btn" onclick="regenerate()" title="重新生成">
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

function createAIMessageWrapper() {
    messageCounter++;
    const uniqueId = `new-${Date.now()}-${messageCounter}`;
    
    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col items-start gap-2 message-wrapper';
    wrapper.dataset.thinkingId = uniqueId;
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
                <button class="action-btn" onclick="regenerate()" title="重新生成">
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
    
    const userWrapper = document.createElement('div');
    userWrapper.className = 'flex justify-end message-wrapper';
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
    
    const aiMessageWrapper = createAIMessageWrapper();
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

function regenerate() {
    if (isStreaming) return;
    
    const chatBox = document.getElementById('chatBox');
    const messages = chatBox.querySelectorAll('.message-wrapper');
    
    if (messages.length > 0) messages[messages.length - 1].remove();
    
    const aiMessageWrapper = createAIMessageWrapper();
    chatBox.appendChild(aiMessageWrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
    
    const uniqueId = aiMessageWrapper.dataset.thinkingId;
    currentMessageDiv = aiMessageWrapper.querySelector('.message-assistant');
    currentThinkingDiv = document.getElementById(`thinking-content-${uniqueId}`);
    
    currentThinkingContent = "";
    currentFullText = "";
    
    isStreaming = true;
    updateSendButton(true);
    
    socket.emit('regenerate', { session_id: currentSession });
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

function refreshMemories() {
    selectedMemoryIds.clear();
    loadMemories();
    updateMemoryStats();
}

// ============ Toast ============

function showToast(message, type = 'success') {
    const existing = document.querySelector('.toast-notification');
    if (existing) existing.remove();
    
    const colors = { success: { bg: '#10b981', icon: '✓' }, error: { bg: '#ef4444', icon: '✗' }, warning: { bg: '#f59e0b', icon: '!' } };
    const style = colors[type] || colors.success;
    
    const toast = document.createElement('div');
    toast.className = 'toast-notification';
    toast.style.cssText = `
        position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
        background: ${style.bg}; color: white; padding: 16px 24px; border-radius: 12px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.2); z-index: 9999; font-size: 14px; font-weight: 500;
        display: flex; align-items: center; gap: 10px; min-width: 200px; justify-content: center;
    `;
    toast.innerHTML = `<span style="font-size: 18px; font-weight: bold;">${style.icon}</span><span>${message}</span>`;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}

// ============ 设置 ============

function switchModel() {
    const modelId = document.getElementById('modelSelect').value;
    socket.emit('switch_model', { model_id: modelId });
}

async function openSettings() {
    document.getElementById('settingsModal').classList.remove('hidden');
    try {
        const res = await fetch('/api/config');
        const config = await res.json();
        document.getElementById('config_OPENAI_API_KEY').value = config.OPENAI_API_KEY || '';
        document.getElementById('config_OPENAI_BASE_URL').value = config.OPENAI_BASE_URL || 'https://api.openai.com/v1';
        document.getElementById('config_memory_interval_value').value = config.MEMORY_INTERVAL_VALUE || '30';
        document.getElementById('config_memory_interval_unit').value = config.MEMORY_INTERVAL_UNIT || 'minutes';
        document.getElementById('config_MEMORY_MODEL').value = config.MEMORY_MODEL || '';
        document.getElementById('config_WORKING_MEMORY_CAPACITY').value = config.WORKING_MEMORY_CAPACITY || '10';
    } catch (e) {
        console.error('加载配置失败:', e);
    }
}

function closeSettings() {
    document.getElementById('settingsModal').classList.add('hidden');
}

async function saveSettings() {
    const config = {
        OPENAI_API_KEY: document.getElementById('config_OPENAI_API_KEY')?.value?.trim() || '',
        OPENAI_BASE_URL: document.getElementById('config_OPENAI_BASE_URL')?.value?.trim() || 'https://api.openai.com/v1',
        MEMORY_INTERVAL_VALUE: document.getElementById('config_memory_interval_value')?.value || '30',
        MEMORY_INTERVAL_UNIT: document.getElementById('config_memory_interval_unit')?.value || 'minutes',
        MEMORY_MODEL: document.getElementById('config_MEMORY_MODEL')?.value?.trim() || '',
        WORKING_MEMORY_CAPACITY: document.getElementById('config_WORKING_MEMORY_CAPACITY')?.value || '10'
    };
    
    if (!config.OPENAI_API_KEY) { showToast('请输入 OPENAI_API_KEY', 'error'); return; }
    
    try {
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        
        const result = await res.json();
        if (result.success) {
            closeSettings();
            showToast('设置已保存并生效', 'success');
            loadModels();
        } else showToast('保存失败: ' + (result.error || '未知错误'), 'error');
    } catch (e) {
        console.error('保存设置失败:', e);
        showToast('保存失败', 'error');
    }
}

function toggleApiKeyVisibility() {
    const input = document.getElementById('config_OPENAI_API_KEY');
    const btn = event.target.closest('button');
    if (input.type === 'password') { input.type = 'text'; btn.textContent = '🙈 隐藏'; }
    else { input.type = 'password'; btn.textContent = '👁️ 显示'; }
}

// ============ 工具函数 ============

function showConfirmDialog(message, onConfirm) {
    const existing = document.querySelector('.confirm-dialog-overlay');
    if (existing) existing.remove();
    
    const dialog = document.createElement('div');
    dialog.className = 'modal-overlay confirm-dialog-overlay';
    dialog.style.display = 'flex';
    dialog.style.zIndex = '9999';
    dialog.innerHTML = `
        <div class="modal" style="max-width: 400px; margin: auto;">
            <div class="confirm-dialog-content">${escapeHtml(message)}</div>
            <div class="confirm-dialog-buttons">
                <button class="btn-cancel" id="confirmCancelBtn">取消</button>
                <button class="btn-confirm" id="confirmOkBtn">确定</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(dialog);
    dialog.querySelector('#confirmCancelBtn').onclick = () => dialog.remove();
    dialog.querySelector('#confirmOkBtn').onclick = () => { dialog.remove(); onConfirm(); };
    dialog.onclick = (e) => { if (e.target === dialog) dialog.remove(); };
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdown(text) {
    try {
        // 配置 marked 选项
        if (typeof marked !== 'undefined') {
            marked.setOptions({
                breaks: true,        // 支持 GitHub 风格换行
                gfm: true,          // 启用 GitHub 风格 Markdown
                headerIds: false,   // 禁用自动生成的 header ID
                mangle: false       // 禁用邮箱混淆
            });
        }
        
        let html = DOMPurify.sanitize(marked.parse(text), {
            ADD_ATTR: ['target'],  // 允许 target 属性
            ADD_TAGS: ['iframe']   // 允许 iframe（可选）
        });
        
        // 为代码块添加复制按钮和语言标签
        html = addCodeBlockFeatures(html);
        
        return html;
    } catch (e) {
        console.error('Markdown 渲染错误:', e);
        return escapeHtml(text);
    }
}

function addCodeBlockFeatures(html) {
    // 创建临时容器解析 HTML
    const temp = document.createElement('div');
    temp.innerHTML = html;
    
    // 找到所有 pre > code 代码块
    const codeBlocks = temp.querySelectorAll('pre > code');
    
    codeBlocks.forEach((codeBlock, index) => {
        const pre = codeBlock.parentElement;
        
        // 获取语言类名 (如 language-python)
        let lang = '';
        const classes = codeBlock.className.split(' ');
        for (const cls of classes) {
            if (cls.startsWith('language-')) {
                lang = cls.replace('language-', '');
                break;
            }
        }
        
        // 创建包装容器
        const wrapper = document.createElement('div');
        wrapper.className = 'code-block-wrapper';
        wrapper.style.cssText = 'position: relative; margin: 12px 0; border-radius: 8px; overflow: hidden; background: #1e1e1e;';
        
        // 创建头部栏
        const header = document.createElement('div');
        header.className = 'code-block-header';
        header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: #2d2d2d; border-bottom: 1px solid #404040;';
        
        // 语言标签
        const langLabel = document.createElement('span');
        langLabel.className = 'code-lang-label';
        langLabel.style.cssText = 'font-size: 12px; color: #888; font-family: monospace;';
        langLabel.textContent = lang || 'code';
        
        // 复制按钮
        const copyBtn = document.createElement('button');
        copyBtn.className = 'code-copy-btn';
        copyBtn.style.cssText = 'padding: 4px 12px; background: #404040; border: none; border-radius: 4px; color: #ccc; font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 4px; transition: all 0.2s;';
        copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg> 复制`;
        copyBtn.onclick = function() {
            const code = codeBlock.textContent;
            navigator.clipboard.writeText(code).then(() => {
                copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg> 已复制`;
                copyBtn.style.color = '#10b981';
                setTimeout(() => {
                    copyBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg> 复制`;
                    copyBtn.style.color = '#ccc';
                }, 2000);
            });
        };
        
        header.appendChild(langLabel);
        header.appendChild(copyBtn);
        
        // 设置 pre 的样式
        pre.style.cssText = 'margin: 0; padding: 12px; overflow-x: auto; background: #1e1e1e;';
        codeBlock.style.cssText = 'font-family: "Fira Code", "Consolas", "Monaco", monospace; font-size: 13px; line-height: 1.5; color: #d4d4d4;';
        
        // 组装
        wrapper.appendChild(header);
        wrapper.appendChild(pre);
        
        // 替换原来的 pre
        pre.parentNode.replaceChild(wrapper, pre);
    });
    
    return temp.innerHTML;
}

function handleInputKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// ============ 输入框菜单 ============

function showInputMenu(event) {
    event.stopPropagation();
    
    const existing = document.querySelector('.input-dropdown');
    if (existing) { existing.remove(); return; }
    
    const btn = event.currentTarget;
    const rect = btn.getBoundingClientRect();
    
    const menu = document.createElement('div');
    menu.className = 'input-dropdown';
    menu.innerHTML = `
        <div class="menu-item" onclick="openPromptSettings(); closeInputMenu();">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 20h9"></path>
                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
            </svg>
            <span>提示词设置</span>
        </div>
        <div class="menu-item" onclick="clearContext(); closeInputMenu();">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
            <span>清空上下文</span>
        </div>
        <div class="menu-item" onclick="openMemoryManager(); closeInputMenu();">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
            <span>记忆管理</span>
        </div>
    `;
    
    menu.style.position = 'fixed';
    menu.style.visibility = 'hidden';
    menu.style.zIndex = '10000';
    document.body.appendChild(menu);
    
    const menuRect = menu.getBoundingClientRect();
    let leftPos = rect.left + (rect.width / 2) - (menuRect.width / 2);
    if (leftPos < 10) leftPos = 10;
    if (leftPos + menuRect.width > window.innerWidth - 10) leftPos = window.innerWidth - menuRect.width - 10;
    
    const spaceAbove = rect.top;
    const spaceBelow = window.innerHeight - rect.bottom;
    let topPos = spaceAbove >= menuRect.height + 8 ? rect.top - menuRect.height - 8 : rect.bottom + 8;
    
    menu.style.left = leftPos + 'px';
    menu.style.top = topPos + 'px';
    menu.style.visibility = 'visible';
    
    setTimeout(() => document.addEventListener('click', closeInputMenu), 0);
}

function closeInputMenu() {
    const menu = document.querySelector('.input-dropdown');
    if (menu) menu.remove();
    document.removeEventListener('click', closeInputMenu);
}

function clearContext() {
    if (!currentSession) { showToast('当前没有对话', 'warning'); return; }
    showConfirmDialog('确定要清空当前对话的上下文吗？这将创建一个新的对话。', () => {
        createNewChat();
        showToast('已创建新对话', 'success');
    });
}

// ============ 提示词设置 ============

let defaultPrompt = '';

async function openPromptSettings() {
    document.getElementById('promptModal').classList.remove('hidden');
    try {
        const res = await fetch('/api/prompt');
        const data = await res.json();
        document.getElementById('systemPromptInput').value = data.prompt || '';
        defaultPrompt = data.default_prompt || '';
    } catch (e) {
        console.error('加载提示词失败:', e);
        showToast('加载提示词失败', 'error');
    }
}

function closePromptSettings() {
    document.getElementById('promptModal').classList.add('hidden');
}

async function savePromptSettings() {
    const prompt = document.getElementById('systemPromptInput').value.trim();
    try {
        const res = await fetch('/api/prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: prompt })
        });
        const data = await res.json();
        if (data.success) {
            closePromptSettings();
            showToast('提示词已保存', 'success');
        } else showToast('保存失败', 'error');
    } catch (e) {
        showToast('保存失败', 'error');
    }
}

function resetPromptToDefault() {
    if (defaultPrompt) {
        document.getElementById('systemPromptInput').value = defaultPrompt;
        showToast('已恢复默认提示词', 'success');
    }
}
