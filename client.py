"""
MCP Client — 测试 range_screenshot
"""
import subprocess, json, sys, io, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class MCPClient:
    def __init__(self, server_path):
        self.proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", server_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        self._id = 0

    def call(self, method, params=None):
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params:
            req["params"] = params
        self.proc.stdin.write((json.dumps(req, ensure_ascii=False) + "\n").encode())
        self.proc.stdin.flush()
        resp = json.loads(self.proc.stdout.readline().decode())
        return resp

    def tool(self, name, args):
        resp = self.call("tools/call", {"name": name, "arguments": args})
        if "result" in resp and "content" in resp["result"]:
            return json.loads(resp["result"]["content"][0]["text"])
        return resp

    def close(self):
        self.proc.terminate()


def main():
    client = MCPClient(os.path.join(os.path.dirname(__file__), "server.py"))

    print("=" * 60)
    print("  Screenshot MCP v3 — range_screenshot 测试")
    print("=" * 60)

    # 初始化
    client.call("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0.0"}
    })

    # 列出工具
    tools = client.call("tools/list")
    print("\n可用工具：")
    for t in tools["result"]["tools"]:
        print(f"  🔧 {t['name']}")

    # ── 测试1：同一屏内的范围截图 ──
    print("\n" + "─" * 60)
    print("测试1：同一屏 — 截图「本周目标」到「周五 (6/19)」")
    print("─" * 60)
    r = client.tool("range_screenshot", {
        "url": "https://weekfupan.top/",
        "start_text": "本周目标",
        "end_text": "周五 (6/19)"
    })
    print(json.dumps(r, ensure_ascii=False, indent=2))

    # ── 测试2：整个页面的范围截图 ──
    print("\n" + "─" * 60)
    print("测试2：跨区域 — 截图「本周目标」到「总计：9h」")
    print("─" * 60)
    r = client.tool("range_screenshot", {
        "url": "https://weekfupan.top/",
        "start_text": "本周目标",
        "end_text": "总计：9h"
    })
    print(json.dumps(r, ensure_ascii=False, indent=2))

    # ── 测试3：精准截一行 ──
    print("\n" + "─" * 60)
    print("测试3：精准 — 只截「周一 (6/15)」到「周二 (6/16)」")
    print("─" * 60)
    r = client.tool("range_screenshot", {
        "url": "https://weekfupan.top/",
        "start_text": "周一 (6/15)",
        "end_text": "周二 (6/16)"
    })
    print(json.dumps(r, ensure_ascii=False, indent=2))

    # ── 测试4：导航到「今日」页再截图 ──
    print("\n" + "─" * 60)
    print("测试4：导航到「今日」→ 截图「每日安排」到「0/0 项完成」")
    print("─" * 60)
    client.tool("navigate", {"url": "https://weekfupan.top/", "click_text": "今日"})
    r = client.tool("range_screenshot", {
        "url": "https://weekfupan.top/",
        "start_text": "每日安排",
        "end_text": "0/0 项完成"
    })
    print(json.dumps(r, ensure_ascii=False, indent=2))

    client.close()
    print("\n" + "=" * 60)
    print("全部完成！截图在 screenshot_mcp/ 目录下")
    print("=" * 60)


if __name__ == "__main__":
    main()
