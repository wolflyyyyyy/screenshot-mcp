# Screenshot MCP Server

基于 MCP (Model Context Protocol) 的**精准网页截图服务**。通过 JSON-RPC over stdio 通信，为 AI Agent 提供网页元素级定位截图能力。

## 核心能力

| 工具 | 功能 | 示例 |
|------|------|------|
| `screenshot_element` | 精准截图某个元素本身 | 只截「本周目标」四个字 |
| `screenshot_section` | 截取关键词所在的完整段落/小节 | 截「时间预算」整个区块 |
| `screenshot_long` | 长截图（超一屏自动滚动拼接） | 截一整个长表格 |
| `navigate` | 导航到页面并可选点击标签 | 切换 SPA 的 Tab 页 |

## 原理

### 精准截图的本质

```
用户说："截图本周目标"
        │
        ▼
┌─ Playwright ─────────────────────────────────┐
│ 1. 在 DOM 树中找到文字"本周目标"所在的节点     │
│ 2. 调用 getBoundingClientRect() 获取坐标：    │
│    x:214, y:210, width:852, height:28        │
│ 3. 调用 Chromium CDP 协议：                   │
│    Page.captureScreenshot({ clip: 坐标区域 })  │
│ 4. 浏览器只渲染那一小块像素 → 保存为 PNG       │
└───────────────────────────────────────────────┘
```

**关键点：不是截整页再裁剪，而是直接在浏览器渲染层面只截那一块。**

### 三个层次的截图精度

```
screenshot_element  →  只截元素本身（如"本周目标"四个字）
screenshot_section  →  向上找标题、向下找边界，截整个小节
screenshot_long     →  元素超出一屏时，滚动多次截图 + Pillow 纵向拼接
```

## 安装

```bash
# 依赖
pip install playwright Pillow
playwright install chromium

# 克隆项目
git clone https://github.com/YOUR_USERNAME/screenshot-mcp.git
cd screenshot-mcp
```

## 使用方式

### 方式一：直接运行测试

```bash
python client.py
```

### 方式二：作为 MCP Server 被 Agent 调用

Server 通过 stdin/stdout 进行 JSON-RPC 通信，Agent 通过 subprocess 启动并交互：

```python
import subprocess, json

# 启动 MCP Server
proc = subprocess.Popen(
    ["python", "server.py"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE
)

def call_mcp(method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        request["params"] = params
    proc.stdin.write((json.dumps(request) + "\n").encode())
    proc.stdin.flush()
    return json.loads(proc.stdout.readline().decode())

# 1. 初始化
call_mcp("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "my-agent", "version": "1.0.0"}
})

# 2. 查看可用工具
tools = call_mcp("tools/list")

# 3. 调用截图工具
result = call_mcp("tools/call", {
    "name": "screenshot_element",
    "arguments": {
        "url": "https://weekfupan.top/",
        "keyword": "本周目标"
    }
})
# result["result"]["content"][0]["text"] 包含截图路径和位置信息
```

### 方式三：在 Claude Desktop 中配置

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "screenshot": {
      "command": "python",
      "args": ["E:\\path\\to\\screenshot_mcp\\server.py"]
    }
  }
}
```

然后在 Claude Desktop 中直接使用：

> "帮我截图 https://example.com 页面上的「用户协议」这一段"

## 工具详细说明

### navigate

导航到指定页面，可选点击某个元素（适用于 SPA 单页应用切换 Tab）。

```json
{
  "name": "navigate",
  "arguments": {
    "url": "https://weekfupan.top/",
    "click_text": "今日"
  }
}
```

### screenshot_element

精准截图某个元素本身，只包含该元素的视觉区域。

```json
{
  "name": "screenshot_element",
  "arguments": {
    "url": "https://weekfupan.top/",
    "keyword": "周四"
  }
}
```

返回示例：
```json
{
  "success": true,
  "output": "shot_周四.png",
  "position": {"x": 244, "y": 440, "width": 79, "height": 23}
}
```

### screenshot_section

截取关键词所在的完整段落。自动向上查找最近的标题元素，向下查找下一个标题或容器边界，确定截图范围。

```json
{
  "name": "screenshot_section",
  "arguments": {
    "url": "https://weekfupan.top/",
    "keyword": "时间预算",
    "padding": 15
  }
}
```

### screenshot_long

当内容超出一屏时，自动滚动多次截图并纵向拼接为一张长图。

```json
{
  "name": "screenshot_long",
  "arguments": {
    "url": "https://weekfupan.top/",
    "keyword": "每日安排",
    "max_scrolls": 10
  }
}
```

长截图流程：
```
1. 获取元素总高度（scrollHeight）
2. 计算需要截几次（总高度 / 视口高度）
3. 每次截一屏 → 向下滚动 → 再截 → 循环
4. 用 Pillow 纵向拼接所有截图
5. 输出一张完整的长图
```

## 典型应用场景

### 财务合规溯源

```
用户提问："差旅报销的审批流程是什么？"

Agent 执行：
1. 语义检索 → 找到《差旅管理制度》文档
2. navigate → 打开该文档
3. screenshot_section → 截取「审批流程」整个小节
4. 返回：截图 + 文字回答 + 来源标注
```

### 知识卡片复习

```
Agent 执行：
1. navigate → 打开知识管理系统
2. screenshot_element → 截取某个知识点
3. 返回截图给用户做视觉确认
```

## 技术栈

- **Playwright** — 浏览器自动化，DOM 定位 + 元素截图
- **Pillow** — 长截图的图片拼接
- **JSON-RPC over stdio** — MCP 协议通信
- **Chromium CDP** — 底层截图 API

## 文件结构

```
screenshot_mcp/
├── README.md       ← 本文档
├── server.py       ← MCP Server（核心服务）
├── client.py       ← 测试客户端
├── test_long.py    ← 长截图独立测试
└── *.png           ← 生成的截图文件
```

## License

MIT
