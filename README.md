# Screenshot MCP Server

基于 MCP (Model Context Protocol) 的**精准网页范围截图服务**。

核心能力：给定一个网页 URL、起始句和结束句，**精准截图两者之间的所有内容**。

## 一句话说明

> 你告诉我"从哪句话开始截，到哪句话结束"，我帮你把中间的内容截图出来。

## 原理

```
用户输入：
  URL: https://xxx.feishu.cn/docx/xxx
  起始句: "差旅报销需先由部门经理审批"
  结束句: "财务部复核后三个工作日内打款"

Playwright 做的事：
  1. 用 TreeWalker 遍历 DOM 文本节点，逐字匹配起始句
  2. 同样方式匹配结束句
  3. 两个节点的 bounding_box 就是坐标：
     起始句 → { x:200, y:300, w:800, h:40 }
     结束句 → { x:200, y:580, w:800, h:40 }
  4. 截图区域 = 起始句顶部 → 结束句底部
  5. page.screenshot(clip={...}) 精准截取
```

## 使用方式

### 工具参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `url` | ✅ | 目标网页的完整 URL |
| `start_text` | ✅ | 截图起始位置的文字（**一字不差**） |
| `end_text` | ✅ | 截图结束位置的文字（**一字不差**） |
| `output` | ❌ | 输出文件路径，默认自动生成 |
| `padding` | ❌ | 截图边距像素，默认 20 |

### 调用示例

#### 示例 1：截一个完整段落

```json
{
  "name": "range_screenshot",
  "arguments": {
    "url": "https://xxx.feishu.cn/docx/xxxxxxxx",
    "start_text": "一、差旅报销标准",
    "end_text": "四、其他注意事项"
  }
}
```

#### 示例 2：只截某两段话

```json
{
  "name": "range_screenshot",
  "arguments": {
    "url": "https://xxx.feishu.cn/docx/xxxxxxxx",
    "start_text": "国内差旅住宿标准为每晚不超过500元",
    "end_text": "国际差旅住宿标准按目的地城市等级另行规定"
  }
}
```

#### 示例 3：截一个表格（表格内容也在两句话之间）

```json
{
  "name": "range_screenshot",
  "arguments": {
    "url": "https://xxx.feishu.cn/docx/xxxxxxxx",
    "start_text": "各级别差旅标准如下表所示",
    "end_text": "以上标准自2024年1月1日起执行"
  }
}
```

### 返回结果

成功时返回：

```json
{
  "success": true,
  "output": "E:\\screenshot_mcp\\range_差旅报销标准.png",
  "position": {
    "x": 194,
    "y": 190,
    "width": 892,
    "height": 346
  },
  "scroll_count": 0,
  "message": "已截取「差旅报销标准...」到「四、其他注意事项...」→ range_差旅报销标准.png"
}
```

| 字段 | 说明 |
|------|------|
| `success` | 是否成功 |
| `output` | 截图文件的完整路径 |
| `position` | 截图区域的坐标和尺寸 |
| `scroll_count` | 滚动次数（0 = 同一屏，>0 = 跨屏拼接） |
| `message` | 结果描述 |

失败时返回：

```json
{
  "success": false,
  "error": "未找到起始句「差旅报销标准...」"
}
```

## 交互流程

```
Agent 收到用户问题
    ↓
判断需要截图溯源
    ↓
调用 range_screenshot:
  - url:        文档的 URL
  - start_text: 内容的第一句
  - end_text:   内容的最后一句
    ↓
MCP Server 返回:
  - 截图文件路径
  - 坐标信息
    ↓
Agent 将截图 + 文字回答一起返回给用户
```

## 跨屏长截图

当起始句和结束句之间**超出一屏**时，MCP 自动处理：

```
1. 获取两句话之间的总高度
2. 按屏幕高度分段
3. 每段截图 → 向下滚动 → 再截 → 循环
4. 用 Pillow 纵向拼接所有截图
5. 输出一张完整的长图
```

用户无需关心这个过程，MCP 自动判断并处理。

## 安装与运行

```bash
# 依赖
pip install playwright Pillow
playwright install chromium

# 运行测试
python client.py
```

## 作为 MCP Server 被 Agent 调用

```python
import subprocess, json

proc = subprocess.Popen(
    ["python", "-X", "utf8", "server.py"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE
)

def call_mcp(method, params=None):
    req = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        req["params"] = params
    proc.stdin.write((json.dumps(req, ensure_ascii=False) + "\n").encode())
    proc.stdin.flush()
    return json.loads(proc.stdout.readline().decode())

# 初始化
call_mcp("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "my-agent", "version": "1.0.0"}
})

# 调用范围截图
result = call_mcp("tools/call", {
    "name": "range_screenshot",
    "arguments": {
        "url": "https://xxx.feishu.cn/docx/xxx",
        "start_text": "第一句话",
        "end_text": "最后一句话"
    }
})

# 获取截图路径
screenshot_path = json.loads(
    result["result"]["content"][0]["text"]
)["output"]
```

## 在 Claude Desktop 中配置

`claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "screenshot": {
      "command": "python",
      "args": ["-X", "utf8", "E:\\path\\to\\server.py"]
    }
  }
}
```

## 重要提示

### 起始句和结束句必须一字不差

```
✅ 正确：
  start_text: "差旅报销需先由部门经理审批"
  页面上：    "差旅报销需先由部门经理审批"

❌ 错误：
  start_text: "差旅报销需先由部门经理审批。"  ← 多了个句号
  start_text: "差旅报销需先由部门经理"         ← 少了"审批"
```

### 如何确认文字内容

1. 在浏览器中打开目标页面
2. 用 DevTools (F12) 选中目标文字
3. 复制 element 的 textContent
4. 粘贴到参数中

### 特殊字符处理

如果起始句或结束句包含引号、括号等特殊字符，正常传入即可，JSON 会自动处理转义。

## 文件结构

```
screenshot_mcp/
├── README.md       ← 本文档
├── server.py       ← MCP Server（核心）
├── client.py       ← 测试客户端
└── .gitignore
```

## License

MIT
