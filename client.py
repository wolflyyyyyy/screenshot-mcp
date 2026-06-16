"""
MCP Client — 测试截图 MCP Server
通过 subprocess 启动 server，通过 stdin/stdout 发送 JSON-RPC 请求
"""

import subprocess
import json
import sys
import io
import os
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class MCPClient:
    def __init__(self, server_path: str):
        self.process = subprocess.Popen(
            [sys.executable, "-X", "utf8", server_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.request_id = 0

    def send_request(self, method: str, params: dict = None) -> dict:
        """发送 JSON-RPC 请求并等待响应"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        # 发送（用 UTF-8 编码）
        line = json.dumps(request, ensure_ascii=False)
        self.process.stdin.write((line + "\n").encode("utf-8"))
        self.process.stdin.flush()

        # 接收（读取 UTF-8 编码的字节）
        response_line = self.process.stdout.readline().decode("utf-8")
        if response_line:
            return json.loads(response_line.strip())
        return None

    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """调用 MCP 工具"""
        result = self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        if result and "result" in result:
            content = result["result"].get("content", [])
            if content:
                return json.loads(content[0]["text"])
        elif result and "error" in result:
            return {"error": result["error"]}
        return {"error": "No response"}

    def initialize(self) -> dict:
        """初始化 MCP 连接"""
        return self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        })

    def list_tools(self) -> list:
        """列出所有可用工具"""
        result = self.send_request("tools/list")
        if result and "result" in result:
            return result["result"].get("tools", [])
        return []

    def close(self):
        self.process.terminate()
        self.process.wait()


def main():
    server_path = os.path.join(os.path.dirname(__file__), "server.py")
    client = MCPClient(server_path)

    print("=" * 60)
    print("MCP Screenshot Server 测试")
    print("=" * 60)

    # 1. 初始化
    print("\n[1] 初始化连接...")
    init_result = client.initialize()
    print(f"  服务端: {init_result.get('result', {}).get('serverInfo', {})}")

    # 2. 列出工具
    print("\n[2] 获取工具列表...")
    tools = client.list_tools()
    for t in tools:
        print(f"  🔧 {t['name']}: {t['description']}")

    # 3. 测试：精准截图「本周目标」
    print("\n[3] 测试 screenshot_element — 截图「本周目标」")
    result = client.call_tool("screenshot_element", {
        "url": "https://weekfupan.top/",
        "keyword": "本周目标"
    })
    print(f"  结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # 4. 测试：精准截图「周四」
    print("\n[4] 测试 screenshot_element — 截图「周四」")
    result = client.call_tool("screenshot_element", {
        "url": "https://weekfupan.top/",
        "keyword": "周四"
    })
    print(f"  结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # 5. 测试：段落截图「时间预算」
    print("\n[5] 测试 screenshot_section — 截图「时间预算」所在段落")
    result = client.call_tool("screenshot_section", {
        "url": "https://weekfupan.top/",
        "keyword": "时间预算"
    })
    print(f"  结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # 6. 测试：导航到「今日」标签页
    print("\n[6] 测试 navigate — 切换到「今日」标签页")
    result = client.call_tool("navigate", {
        "url": "https://weekfupan.top/",
        "click_text": "今日"
    })
    print(f"  结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # 7. 测试：长截图「每日安排」（今日页有 9 个时间格，适合长截图）
    print("\n[7] 测试 screenshot_long — 长截图「每日安排」")
    result = client.call_tool("screenshot_long", {
        "url": "https://weekfupan.top/",
        "keyword": "每日安排"
    })
    print(f"  结果: {json.dumps(result, ensure_ascii=False, indent=2)}")

    # 关闭
    client.close()
    print("\n" + "=" * 60)
    print("全部测试完成！截图文件在 screenshot_mcp/ 目录下")
    print("=" * 60)


if __name__ == "__main__":
    main()
