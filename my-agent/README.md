# My-Agent: Local Windows AI Agent

## ⚠️ 安全警告

**本系统具有控制您电脑的完整权限！**

- **默认开启安全模式**：每一步操作都需要您手动确认
- **不要随意切换到信任模式**，除非您完全理解工作流的内容
- **不要在无人看管的情况下运行自动化脚本**
- **敏感操作**（如文件删除、代码执行）请务必仔细审查

---

## 项目介绍

一个**本地化、可视化、可定制的 Windows 个人 AI Agent 系统**，类似 OpenManus 但更极简。支持本地模型 (Ollama)、Web 可视化界面，能安全地操控电脑执行浏览器自动化和系统操作。

### 核心特性

- 🖥️ **可视化仪表盘**：实时查看 Agent 状态、日志流和手动控制台
- 🔒 **混合安全模式**：默认每步确认，可信工作流可自动执行
- 🤖 **本地 LLM**：通过 Ollama 运行 qwen2.5-coder 等模型，无需联网
- 🌐 **浏览器自动化**：基于 Playwright 操作 Chrome/Edge
- 🪟 **Windows 控制**：窗口管理、键盘鼠标模拟
- ⏰ **定时任务**：支持 Cron 表达式的自动化工作流
- 🔧 **可扩展工具**：简单添加新工具函数即可让 Agent 调用

---

## 前置准备

### 1. 安装 Python 3.10+

确保已安装 Python 3.10 或更高版本：

```bash
python --version
```

### 2. 安装 Ollama

**Windows 用户**：

1. 访问 [https://ollama.com](https://ollama.com)
2. 下载 Windows 安装包并安装
3. 安装完成后，Ollama 会自动在后台运行

**拉取模型**：

```bash
ollama pull qwen2.5-coder:7b
```

> 推荐使用 `qwen2.5-coder:7b` 或 `phi3:mini`，前者代码能力更强，后者更轻量

**验证安装**：

```bash
ollama run qwen2.5-coder:7b "Hello"
```

### 3. 安装 Playwright 浏览器

```bash
python -m playwright install
```

这会安装 Chromium、Firefox 和 WebKit 浏览器内核。

### 4. 安装 Firecrawl 爬虫

```bash
pip install firecrawl-py
```

然后在环境变量里设置 `FIRECRAWL_API_KEY`，或者在 `config.yaml` 里填写：

```yaml
firecrawl:
  api_key: "fc-your-key"
```

---

## Quick Start

### 1. 安装依赖

```bash
cd my-agent
pip install -r requirements.txt
```

### 2. 配置系统

编辑 `config.yaml` 文件：

```yaml
llm:
  model: "qwen2.5-coder:7b"  # 模型名称
  base_url: "http://localhost:11434"  # Ollama API 地址
  context_limit: 10  # 历史对话轮次限制

security:
  mode: "safe"  # safe=安全模式 (每步确认), trusted=信任模式 (自动执行)

automation:
  browser: "chromium"  # chromium/firefox/webkit
  headless: false  # 是否无头模式 (建议关闭以便观察)

scheduler:
  enabled: true  # 是否启用定时任务
```

### 3. 启动系统

```bash
python main.py
```

启动后，终端会显示：

```
NiceGUI ready to go on http://localhost:8080
```

### 4. 访问界面

打开浏览器访问：**http://localhost:8080**

您将看到：
- Agent 状态指示器
- 实时日志流
- 指令输入框
- 定时任务管理面板

---

## 使用指南

### 手动执行指令

在界面底部的"发送指令"输入框中输入自然语言指令，例如：

```
打开谷歌搜索"Python 教程"
```

在**安全模式**下，您会看到：
1. LLM 思考过程
2. 计划调用的工具及参数
3. **确认对话框** → 点击"批准"执行或"拒绝"取消

### 创建工作流

工作流是预定义的工具序列，可保存为可信任务自动执行。

**示例：每日新闻收集**

1. 在界面点击"新建工作流"
2. 输入步骤（或用自然语言描述）
3. 设置为定时任务（如每天 8:00）
4. 标记为"可信"后，到时会自动执行

### 查看日志

所有操作记录保存在 `agent.db` SQLite 数据库中，可在界面的"日志"标签页查看。

---

## 自定义工具

系统支持轻松扩展新工具。只需在 `tools/` 目录下创建新的 Python 文件。

### 步骤 1：创建工具文件

在 `tools/` 目录下创建 `my_tool.py`：

```python
from tools.base import Tool, tool

@tool
def send_email(to: str, subject: str, body: str) -> str:
    """
    发送邮件到指定地址
    
    Args:
        to: 收件人邮箱
        subject: 邮件主题
        body: 邮件正文
    
    Returns:
        执行结果信息
    """
    # 你的实现代码
    print(f"发送邮件到 {to}: {subject}")
    return f"邮件已发送到 {to}"
```

### 步骤 2：工具自动注册

系统启动时会自动扫描 `tools/` 目录下的所有 `.py` 文件，并注册带有 `@tool` 装饰器的函数。

### 步骤 3：让 Agent 使用

重启系统后，Agent 即可在响应中调用您的新工具。

### Firecrawl 爬虫工具

系统还内置了基于 Firecrawl 的网页抓取工具，可直接读取页面内容而不依赖视觉自动化。

示例：

```python
firecrawl_scrape(
  url="www.google.com/search?q=薯片算不算UPF",
  only_main_content=False,
  max_age=172800000,
  parsers=["pdf"],
  formats=["markdown"],
)
```

该工具会优先返回 markdown 结果，适合抓取搜索页、文章页和 PDF 解析结果。

### 工具开发规范

1. **函数签名**：必须包含类型注解
2. **文档字符串**：清晰描述功能、参数和返回值（LLM 靠这个理解工具）
3. **错误处理**：捕获异常并返回有意义的错误信息
4. **幂等性**：尽量保证多次调用结果一致

---

## 项目结构

```
my-agent/
├── main.py             # 入口文件，启动 NiceGUI 和调度器
├── agent_core.py       # Agent 核心逻辑 (ReAct 循环，含确认机制)
├── llm_provider.py     # Ollama 接口封装
├── database.py         # SQLite 操作 (任务/日志)
├── config.yaml         # 用户配置
├── requirements.txt    # Python 依赖
├── README.md           # 本文档
└── tools/              # 工具集目录
    ├── __init__.py     # 工具注册和导出
    ├── base.py         # 工具基类和装饰器
    ├── browser.py      # Playwright 浏览器自动化
  ├── firecrawl.py    # Firecrawl 网页抓取
    ├── system.py       # Windows 系统控制
    └── code.py         # Python 代码执行
```

---

## 常见问题

### Q: Agent 响应很慢？
A: 本地模型推理需要时间，7B 模型通常需要 10-30 秒。可尝试更小的模型如 `phi3:mini`。

### Q: 浏览器无法打开？
A: 确保运行了 `playwright install`。如果是 Windows，可能需要以管理员身份运行。

### Q: 如何切换模型？
A: 修改 `config.yaml` 中的 `llm.model` 字段，然后重启系统。

### Q: 安全模式和信任模式有什么区别？
A: 
- **安全模式**：每个工具调用前都会弹出确认框
- **信任模式**：只有首次创建的工作流需要确认，之后自动执行

### Q: 如何停止系统？
A: 在终端按 `Ctrl+C`，或在界面点击"停止 Agent"按钮。

---

## 技术栈

- **界面**: [NiceGUI](https://nicegui.io/) - 基于 Python 的 Web UI
- **LLM**: [Ollama](https://ollama.com/) - 本地模型推理
- **浏览器**: [Playwright](https://playwright.dev/) - 跨浏览器自动化
- **系统控制**: `pywinauto` + `pyautogui` - Windows GUI 自动化
- **调度**: [APScheduler](https://apscheduler.readthedocs.io/) - 定时任务
- **存储**: `SQLite` - 轻量级数据库

---

## License

MIT License

---

## Contributing

欢迎提交 Issue 和 Pull Request！
