"""
Screenshot MCP Server v3
========================
基于 MCP 的精准网页截图服务
核心工具：range_screenshot — 给定起始句和结束句，精准截图之间的内容
"""

import sys
import json
import os
import traceback
from playwright.sync_api import sync_playwright

# ─── 浏览器管理 ───────────────────────────────────────────────
_pw = None
_browser = None
_page = None
_current_url = None


def get_browser():
    global _pw, _browser, _page
    if _browser is None:
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True)
        _page = _browser.new_page(viewport={"width": 1280, "height": 900})
    return _page


def reset_browser():
    global _pw, _browser, _page, _current_url
    try:
        if _browser:
            _browser.close()
    except Exception:
        pass
    _pw = None
    _browser = None
    _page = None
    _current_url = None


def goto(url):
    global _current_url
    page = get_browser()
    if _current_url == url:
        return page
    for attempt in range(3):
        try:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            _current_url = url
            return page
        except Exception:
            if attempt < 2:
                reset_browser()
                page = get_browser()
            else:
                raise


# ─── 核心工具：范围截图 ───────────────────────────────────────

def tool_range_screenshot(url, start_text, end_text, output=None, padding=20):
    """
    范围截图：截取从 start_text 到 end_text 之间的所有内容。

    参数：
      url        - 目标网页地址
      start_text - 截图起始位置的文字（第一句，一字不差）
      end_text   - 截图结束位置的文字（最后一句，一字不差）
      output     - 输出文件路径（可选，默认自动生成）
      padding    - 截图边距像素（默认20）

    返回：
      success    - 是否成功
      output     - 截图文件路径
      position   - 截图区域坐标 {x, y, width, height}
      scroll_count - 滚动次数（跨屏时 >0）
      message    - 结果描述
    """
    from PIL import Image
    from io import BytesIO

    page = goto(url)

    # ── 第一步：找到起始句的位置 ──
    start_js = page.evaluate("""
    (text) => {
        const cleaned = text.replace(/\\s+/g, '');

        // 策略1：精确匹配单个文本节点
        const walker = document.createTreeWalker(
            document.body, NodeFilter.SHOW_TEXT, null, false
        );
        while (walker.nextNode()) {
            const node = walker.currentNode;
            if (node.textContent.includes(text)) {
                const box = node.parentElement.getBoundingClientRect();
                return { x: box.x, y: box.y, width: box.width, height: box.height };
            }
        }

        // 策略2：跨节点拼接，但只取匹配到的最后一个节点的坐标
        // （这样起点就是目标文字实际所在的行）
        const allText = [];
        const walker2 = document.createTreeWalker(
            document.body, NodeFilter.SHOW_TEXT, null, false
        );
        while (walker2.nextNode()) {
            allText.push({
                text: walker2.currentNode.textContent,
                el: walker2.currentNode.parentElement
            });
        }

        for (let i = 0; i < allText.length; i++) {
            let combined = '';
            for (let j = i; j < Math.min(i + 15, allText.length); j++) {
                combined += allText[j].text;
                if (combined.replace(/\\s+/g, '').includes(cleaned)) {
                    // 起点 = 匹配序列中最后一个节点（目标文字实际所在行）
                    const box = allText[j].el.getBoundingClientRect();
                    return { x: box.x, y: box.y, width: box.width, height: box.height };
                }
            }
        }
        return null;
    }
    """, start_text)

    if not start_js:
        return {"success": False, "error": f"未找到起始句「{start_text[:20]}...」"}

    # ── 第二步：找到结束句的位置 ──
    end_js = page.evaluate("""
    (text) => {
        const cleaned = text.replace(/\\s+/g, '');

        // 辅助函数：找到包含文本的最合适的父容器
        // 如果文字在 <pre>/<code>/<td> 等容器中，返回容器的坐标
        function getContainerBox(el) {
            let current = el;
            while (current && current !== document.body) {
                const tag = current.tagName.toLowerCase();
                if (['pre', 'code', 'td', 'th', 'li', 'blockquote'].includes(tag)) {
                    return current.getBoundingClientRect();
                }
                current = current.parentElement;
            }
            return el.getBoundingClientRect();
        }

        // 策略1：精确匹配
        const walker = document.createTreeWalker(
            document.body, NodeFilter.SHOW_TEXT, null, false
        );
        while (walker.nextNode()) {
            const node = walker.currentNode;
            if (node.textContent.includes(text)) {
                const box = getContainerBox(node.parentElement);
                return { x: box.x, y: box.y, width: box.width, height: box.height };
            }
        }

        // 策略2：跨节点拼接
        const allText = [];
        const walker2 = document.createTreeWalker(
            document.body, NodeFilter.SHOW_TEXT, null, false
        );
        while (walker2.nextNode()) {
            allText.push({
                text: walker2.currentNode.textContent,
                el: walker2.currentNode.parentElement
            });
        }

        for (let i = 0; i < allText.length; i++) {
            let combined = '';
            for (let j = i; j < Math.min(i + 15, allText.length); j++) {
                combined += allText[j].text;
                if (combined.replace(/\\s+/g, '').includes(cleaned)) {
                    const box = getContainerBox(allText[j].el);
                    return { x: box.x, y: box.y, width: box.width, height: box.height };
                }
            }
        }
        return null;
    }
    """, end_text)

    if not end_js:
        return {"success": False, "error": f"未找到结束句「{end_text[:20]}...」"}

    # ── 第三步：计算截图区域 ──
    # 先滚动到起始句可见，重新获取坐标（因为滚动后坐标会变）
    page.evaluate(f"window.scrollTo(0, {start_js['y'] + page.evaluate('window.scrollY') - 50})")
    page.wait_for_timeout(500)

    # 重新获取两个节点的坐标（滚动后坐标变了）
    start_js = page.evaluate("""
    (text) => {
        const cleaned = text.replace(/\\s+/g, '');
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        while (walker.nextNode()) {
            const node = walker.currentNode;
            if (node.textContent.includes(text)) {
                const box = node.parentElement.getBoundingClientRect();
                return { x: box.x, y: box.y, width: box.width, height: box.height };
            }
        }
        // 跨节点
        const allText = [];
        const w2 = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        while (w2.nextNode()) allText.push({ text: w2.currentNode.textContent, el: w2.currentNode.parentElement });
        for (let i = 0; i < allText.length; i++) {
            let c = '';
            for (let j = i; j < Math.min(i+15, allText.length); j++) {
                c += allText[j].text;
                if (c.replace(/\\s+/g,'').includes(cleaned)) {
                    const box = allText[j].el.getBoundingClientRect();
                    return { x: box.x, y: box.y, width: box.width, height: box.height };
                }
            }
        }
        return null;
    }
    """, start_text)

    end_js = page.evaluate("""
    (text) => {
        const cleaned = text.replace(/\\s+/g, '');
        function getContainerBox(el) {
            let cur = el;
            while (cur && cur !== document.body) {
                const tag = cur.tagName.toLowerCase();
                if (['pre','code','td','th','li','blockquote'].includes(tag))
                    return cur.getBoundingClientRect();
                cur = cur.parentElement;
            }
            return el.getBoundingClientRect();
        }
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        while (walker.nextNode()) {
            const node = walker.currentNode;
            if (node.textContent.includes(text)) {
                return getContainerBox(node.parentElement);
            }
        }
        const allText = [];
        const w2 = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
        while (w2.nextNode()) allText.push({ text: w2.currentNode.textContent, el: w2.currentNode.parentElement });
        for (let i = 0; i < allText.length; i++) {
            let c = '';
            for (let j = i; j < Math.min(i+15, allText.length); j++) {
                c += allText[j].text;
                if (c.replace(/\\s+/g,'').includes(cleaned))
                    return getContainerBox(allText[j].el);
            }
        }
        return null;
    }
    """, end_text)

    if not start_js or not end_js:
        return {"success": False, "error": "滚动后重新定位失败"}

    extra_bottom = 30
    x = max(0, start_js["x"] - padding)
    y = max(0, start_js["y"] - padding)
    end_bottom = end_js["y"] + end_js["height"] + padding + extra_bottom
    w = max(start_js["width"], end_js["width"]) + padding * 2
    h = end_bottom - y

    if not output:
        safe_name = start_text[:10].replace("/", "_").replace("\\", "_")
        output = os.path.join(os.path.dirname(__file__), f"range_{safe_name}.png")

    # ── 第四步：判断是否跨屏 ──
    viewport_h = page.viewport_size["height"]

    if h <= viewport_h:
        # 同一屏内，直接截图
        page.screenshot(path=output, clip={"x": x, "y": y, "width": w, "height": h})
        return {
            "success": True,
            "output": output,
            "position": {"x": x, "y": y, "width": w, "height": h},
            "scroll_count": 0,
            "message": f"已截取「{start_text[:15]}...」到「{end_text[:15]}...」→ {output}"
        }

    # ── 跨屏：滚动截图 + 拼接 ──
    screenshots = []
    scroll_y = y
    remaining = h
    count = 0
    max_scrolls = 20

    while remaining > 0 and count < max_scrolls:
        page.evaluate(f"window.scrollTo(0, {scroll_y})")
        page.wait_for_timeout(500)

        img_bytes = page.screenshot()
        img = Image.open(BytesIO(img_bytes))

        relative_y = scroll_y - page.evaluate("window.scrollY")
        crop_top = max(0, relative_y)
        crop_bottom = min(img.height, crop_top + min(remaining, viewport_h))

        if crop_top < img.height:
            cropped = img.crop((0, int(crop_top), img.width, int(crop_bottom)))
            screenshots.append(cropped)

        scroll_y += viewport_h
        remaining -= viewport_h
        count += 1

    # 纵向拼接
    if screenshots:
        total_w = max(i.width for i in screenshots)
        total_h = sum(i.height for i in screenshots)
        final = Image.new("RGB", (total_w, total_h), (255, 255, 255))
        y_off = 0
        for img in screenshots:
            final.paste(img, (0, y_off))
            y_off += img.height
        final.save(output)

    return {
        "success": True,
        "output": output,
        "position": {"x": x, "y": y, "width": w, "height": h},
        "scroll_count": count,
        "message": f"已截取「{start_text[:15]}...」到「{end_text[:15]}...」（跨屏，滚动{count}次）→ {output}"
    }


# ─── 辅助工具：导航 ──────────────────────────────────────────

def tool_navigate(url, click_text=None):
    """导航到页面，可选点击某个元素切换标签"""
    page = goto(url)
    if click_text:
        el = page.get_by_text(click_text, exact=False)
        if el.count() > 0:
            el.first.click()
            page.wait_for_timeout(2000)
            return {"success": True, "message": f"已点击「{click_text}」"}
        return {"success": False, "error": f"未找到「{click_text}」"}
    return {"success": True, "message": f"已在 {url}"}


# ─── MCP JSON-RPC 协议 ───────────────────────────────────────

TOOLS = {
    "range_screenshot": {
        "name": "range_screenshot",
        "description": "范围截图：给定起始句和结束句，精准截图两者之间的所有内容。支持同一屏直接截图，跨屏自动滚动拼接长图。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "目标网页 URL"
                },
                "start_text": {
                    "type": "string",
                    "description": "截图起始位置的文字（第一句，一字不差）"
                },
                "end_text": {
                    "type": "string",
                    "description": "截图结束位置的文字（最后一句，一字不差）"
                },
                "output": {
                    "type": "string",
                    "description": "输出文件路径（可选，默认自动生成）"
                },
                "padding": {
                    "type": "integer",
                    "description": "截图边距像素（默认20）"
                }
            },
            "required": ["url", "start_text", "end_text"]
        }
    },
    "navigate": {
        "name": "navigate",
        "description": "导航到指定页面，可选点击元素切换标签（适用于 SPA 单页应用）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标网页 URL"},
                "click_text": {"type": "string", "description": "要点击的文字（可选）"}
            },
            "required": ["url"]
        }
    }
}

TOOL_FUNCS = {
    "range_screenshot": tool_range_screenshot,
    "navigate": tool_navigate,
}


def handle_request(req):
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "screenshot-mcp", "version": "3.0.0"}
        }}
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": list(TOOLS.values())}}
    elif method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {})
        if name not in TOOL_FUNCS:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
        try:
            result = TOOL_FUNCS[name](**args)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            }}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps({
                    "success": False, "error": str(e), "traceback": traceback.format_exc()
                }, ensure_ascii=False)}],
                "isError": True
            }}
    elif method == "notifications/initialized":
        return None
    else:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"Unknown method: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception:
            pass


if __name__ == "__main__":
    main()
