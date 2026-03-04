# Weaver 智能对话助手

一个支持三级记忆架构的智能对话助手，具有流式响应、记忆管理和多模型切换功能。

## 更新内容 (本次修改)

### 1. 重新生成按钮功能修复
- **问题**: 每条AI回复都有重新生成按钮，但点击后总是重新生成对最后一条问题的回复
- **解决**: 每条AI回复现在会记录对应的用户消息索引，点击重新生成按钮时会重新生成对应的那条回复

### 2. API Key 校验功能
- 在设置页面，API Key 右侧添加了"校验"按钮
- 点击校验按钮会验证 API Key 和 Base URL 的有效性
- 校验成功后，会自动获取可用模型列表并提示成功
- 校验失败会显示具体错误信息

### 3. 记忆管理模型选择改进
- 将手动输入框改为下拉框选择
- 校验成功后，获取到的模型列表会自动填充到下拉框中供选择
- 默认选项为"-- 先校验API获取模型列表 --"

### 4. 界面美化
- 优化了整体界面设计，增加了渐变效果和阴影
- 改进了按钮、输入框和卡片的视觉效果
- 优化了记忆管理弹窗的布局和交互

## 文件结构

```
Weaver/
├── LICENSE
├── README.md
├── agent_manager.py
├── app.py                 # 主程序
├── chat_history.py
├── .env                   # 环境配置 (需自行创建)
├── history                # 对话历史目录
├── log.py
├── memory_data            # 记忆数据目录
│   ├── long_term.db
│   └── session_log.md
├── memory_system.py
├── requirements.txt
├── run.sh
├── static
│   ├── app.js
│   ├── favicon.png
│   └── favicon.svg
├── templates
│   └── index.html
└── tools.py
```

## 安装和使用

### 1. 安装依赖

```bash
pip install flask flask-socketio python-socketio openai pydantic-ai python-dotenv requests apscheduler beautifulsoup4 numpy
```

### 2. 创建 .env 文件

在项目根目录创建 `.env` 文件：

```env
# OpenAI API 配置
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1

# 模型配置 (可选，默认从 API 获取)
# MEMORY_MODEL=gpt-4o

# 记忆处理间隔
MEMORY_INTERVAL_VALUE=30
MEMORY_INTERVAL_UNIT=minutes

# 工作记忆容量
WORKING_MEMORY_CAPACITY=10

# 日志级别
LOG_LEVEL=INFO
LOG_MODE=console

# Web 服务配置
WEB_HOST=0.0.0.0
WEB_PORT=5000
```

### 3. 创建必要目录

```bash
mkdir -p templates static history memory_data logs
```

### 4. 移动前端文件

```bash
# 将 index.html 移动到 templates 目录
mv index.html templates/

# 将 app.js 移动到 static 目录
mv app.js static/
```

### 5. 启动服务

```bash
python app.py
```

访问 http://localhost:5000 即可使用。

## 功能说明

### 三级记忆系统

1. **长期记忆**: 永久保存的重要信息，使用向量检索
2. **工作记忆**: 当前对话的关键信息，保存在内存中
3. **短期记忆**: 对话历史，用于上下文理解

### API 校验

在设置页面:
1. 填写 API Key 和 Base URL
2. 点击"校验"按钮
3. 校验成功后，模型列表会自动填充
4. 在"记忆处理专用模型"下拉框中选择模型
5. 点击"保存设置"

### 重新生成

- 每条 AI 回复下方都有重新生成按钮
- 点击后会重新生成该条回复对应的响应
- 不再影响其他消息

## 技术栈

- **后端**: Flask, Flask-SocketIO, Pydantic-AI
- **前端**: HTML, CSS, JavaScript, TailwindCSS
- **AI**: OpenAI API (兼容接口)
- **存储**: SQLite, Markdown, JSON

## 注意事项

1. 确保 `.env` 文件不被提交到版本控制
2. 首次使用需要配置有效的 API Key
3. 建议定期备份 `memory_data` 和 `history` 目录
