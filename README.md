# Weaver - 智能AI助手系统

Weaver是一个功能强大的AI助手系统，集成了聊天、记忆管理、网络搜索和工具调用等功能，旨在提供智能、个性化的对话体验。

## ✨ 功能特性

- **🤖 智能对话**: 基于AI模型的自然语言对话
- **🧠 记忆系统**: 长期记忆存储和检索，支持向量化搜索
- **🌐 网络搜索**: 实时网络信息检索
- **🛠️ 工具集成**: 多种实用工具调用
- **⏰ 时间感知**: 内置时间工具和提醒功能
- **⚙️ 可配置**: 灵活的配置系统

## 📁 项目结构

```
Weaver/
├── main.py                    # 主程序入口
├── ai_chat.py                # AI聊天核心逻辑
├── web_search.py             # 网络搜索功能
├── time_utils.py             # 时间相关工具
├── config.py                 # 配置管理
├── config.json               # 配置文件
├── requirements.txt          # 依赖包列表
├── memory/                   # 记忆系统模块
│   ├── core.py              # 记忆核心逻辑
│   ├── database.py          # 数据库操作
│   ├── embedding.py         # 向量嵌入处理
│   ├── search.py            # 记忆搜索
│   ├── merge.py             # 记忆合并
│   └── tools.py             # 记忆工具
├── ai_memory/               # AI记忆存储
│   ├── MEMORY.md            # 记忆文档
│   ├── daily/               # 每日记忆
│   └── memory.db            # 记忆数据库
└── __init__.py              # 包初始化
```

## 🚀 快速开始

### 1. 环境要求

- Python 3.8+
- 依赖包（见requirements.txt）

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置设置

1. 复制配置文件模板：
```bash
cp config.json.example config.json
```

2. 编辑 `config.json` 配置您的API密钥和其他设置：
```json
{
  "openai_api_key": "your-api-key-here",
  "model": "gpt-4",
  "search_engine_api_key": "your-search-api-key",
  "memory_enabled": true
}
```

### 4. 运行程序

```bash
python main.py
```

## ⚙️ 配置说明

### 主要配置项

- `openai_api_key`: OpenAI API密钥
- `model`: 使用的AI模型（如gpt-4, gpt-3.5-turbo）
- `search_engine_api_key`: 搜索引擎API密钥
- `memory_enabled`: 是否启用记忆功能
- `max_tokens`: 最大token数
- `temperature`: 生成温度

### 环境变量

您也可以通过环境变量配置：
```bash
export OPENAI_API_KEY="your-api-key"
export WEAVER_MODEL="gpt-4"
```

## 🧠 记忆系统

Weaver的记忆系统支持：

1. **短期记忆**: 会话上下文
2. **长期记忆**: 存储在向量数据库中的记忆
3. **每日记忆**: 按日期组织的记忆片段
4. **记忆检索**: 基于语义相似度的搜索

### 记忆操作

```python
# 保存记忆
memory.save("用户偏好", "喜欢喝咖啡")

# 搜索记忆
results = memory.search("咖啡")
```

## 🔧 可用工具

系统集成了多种工具：

1. **网络搜索**: 实时信息检索
2. **时间工具**: 时间计算和提醒
3. **文件操作**: 文件读写管理
4. **计算工具**: 数学计算

## 📝 使用示例

### 基本对话
```
用户: 你好，Weaver
Weaver: 你好！我是Weaver，有什么可以帮助您的吗？
```

### 带记忆的对话
```
用户: 我昨天说我喜欢什么饮料？
Weaver: 根据记忆，您昨天提到喜欢喝咖啡。
```

### 网络搜索
```
用户: 搜索今天的新闻
Weaver: 正在搜索最新新闻...
[显示搜索结果]
```

## 🛠️ 开发指南

### 添加新工具

1. 在 `tools.py` 中添加工具函数：
```python
def new_tool_function(param1, param2):
    """工具描述"""
    # 工具逻辑
    return result
```

2. 在配置中注册工具

### 扩展记忆类型

1. 继承 `MemoryBase` 类
2. 实现存储和检索方法
3. 在核心系统中注册

## 📊 性能优化

- 使用向量索引加速记忆搜索
- 实现记忆缓存机制
- 支持批量操作
- 异步处理网络请求

## 🔒 安全注意事项

1. **API密钥安全**: 不要将API密钥提交到版本控制
2. **数据隐私**: 用户记忆数据本地存储
3. **输入验证**: 所有用户输入都经过验证
4. **速率限制**: 实现API调用速率限制

## 🤝 贡献指南

欢迎贡献！请遵循以下步骤：

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目基于 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 📞 支持与反馈

- 提交 Issue: [GitHub Issues]
- 功能请求: 使用Feature Request模板
- 问题反馈: 提供详细的重现步骤

## 🚧 已知问题

- [ ] 记忆合并算法需要优化
- [ ] 网络搜索有时会超时
- [ ] 大文件处理性能待提升

## 🔮 路线图

- [ ] 多语言支持
- [ ] 插件系统
- [ ] 移动端应用
- [ ] 语音交互
- [ ] 离线模式

---

**Weaver** - 编织智能，连接未来 🕸️