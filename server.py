"""
Screenshot MCP Server v2
========================
基于 MCP JSON-RPC over stdio 的精准截图服务
支持：精准截图、段落截图、长截图、SPA 页面导航
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
    """导航到页面，支持重试"""
    global _current_url
    page = get_browser()
    if _current_url == url:
        return page  # 已在目标页面
    for attempt in range(3):
        try:
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            _current_url = url
            return page
        except Exception:
            if attempt < 2:
                reset_browser()
                page = get_browser()
            else:
                raise


def find_element(page, keyword):
    """多种策略定位元素"""
    # 策略1: text= 选择器
    loc = page.locator(f"text={keyword}")
    if loc.count() > 0:
        return loc.first
    # 策略2: get_by_text
    loc = page.get_by_text(keyword, exact=False)
    if loc.count() > 0:
        return loc.first
    # 策略3: XPath 模糊匹配
    loc = page.locator(f"xpath=//*[contains(text(), '{keyword}')]")
    if loc.count() > 0:
        return loc.first
    return None


# ─── 工具实现 ────────────────────────────────────────────────

def tool_screenshot_element(url, keyword, output=None):
    """精准截图：只截取匹配关键词的那个元素本身"""
    page = goto(url)
    el = find_element(page, keyword)
    if not el:
        return {"success": False, "error": f"未找到「{keyword}」"}

    if not output:
        output = os.path.join(os.path.dirname(__file__), f"shot_{keyword}.png")
    el.screenshot(path=output)
    box = el.bounding_box()
    return {
        "success": True,
        "output": output,
        "position": box,
        "message": f"已截取「{keyword}」→ {output}"
    }


def tool_screenshot_section(url, keyword, output=None, padding=15):
    """段落截图：截取关键词所在的小节（标题+内容的完整区块）"""
    page = goto(url)
    el = find_element(page, keyword)
    if not el:
        return {"success": False, "error": f"未找到「{keyword}」"}

    # 用 JS 向上找标题，向下找下一个标题，确定区块边界
    result = page.evaluate("""
    (keyword) => {
        const allElements = document.querySelectorAll('*');
        let target = null;
        for (const el of allElements) {
            if (el.children.length === 0 && el.textContent.includes(keyword)) {
                target = el;
                break;
            }
        }
        if (!target) return null;

        // 向上找标题
        let sectionTop = target;
        let el = target;
        while (el && el.parentElement) {
            el = el.parentElement;
            const tag = el.tagName.toLowerCase();
            if (/^h[1-6]$/.test(tag)) { sectionTop = el; break; }
            if (el.className && typeof el.className === 'string' &&
                /heading|title|header/i.test(el.className)) { sectionTop = el; break; }
        }

        // 向下找下一个标题或容器底部
        let sectionBottom = target;
        let sibling = target.parentElement;
        while (sibling) {
            let next = sibling.nextElementSibling;
            while (next) {
                const tag = next.tagName.toLowerCase();
                if (/^h[1-6]$/.test(tag)) {
                    return {
                        top: sectionTop.getBoundingClientRect(),
                        bottom: next.getBoundingClientRect()
                    };
                }
                next = next.nextElementSibling;
            }
            sibling = sibling.parentElement;
        }

        // 没找到下一个标题，截到父容器底部
        let container = target;
        while (container.parentElement && container.parentElement !== document.body) {
            container = container.parentElement;
        }
        return {
            top: sectionTop.getBoundingClientRect(),
            bottom: container.getBoundingClientRect()
        };
    }
    """, keyword)

    if not result:
        return {"success": False, "error": f"未找到「{keyword}」的区块"}

    top = result["top"]
    bottom = result["bottom"]
    x = max(0, top["x"] - padding)
    y = max(0, top["y"] - padding)
    w = top["width"] + padding * 2
    h = (bottom["y"] + bottom["height"]) - y + padding

    if not output:
        output = os.path.join(os.path.dirname(__file__), f"section_{keyword}.png")
    page.screenshot(path=output, clip={"x": x, "y": y, "width": w, "height": h})
    return {
        "success": True,
        "output": output,
        "position": {"x": x, "y": y, "width": w, "height": h},
        "message": f"已截取「{keyword}」段落 → {output}"
    }


def tool_screenshot_long(url, keyword, output=None, max_scrolls=10):
    """长截图：元素超出一屏时，自动滚动多次截图并纵向拼接"""
    from PIL import Image
    from io import BytesIO

    page = goto(url)
    el = find_element(page, keyword)
    if not el:
        return {"success": False, "error": f"未找到「{keyword}」"}

    total_height = el.evaluate("el => el.scrollHeight")
    viewport_h = page.viewport_size["height"]

    if not output:
        output = os.path.join(os.path.dirname(__file__), f"long_{keyword}.png")

    # 不超一屏，直接截图
    if total_height <= viewport_h:
        el.screenshot(path=output)
        return {
            "success": True, "output": output,
            "message": f"「{keyword}」在一页内（{total_height}px），直接截图"
        }

    # 长截图：滚动 + 多次截图 + 拼接
    box = el.bounding_box()
    screenshots = []
    scroll_y = box["y"]
    remaining = total_height
    count = 0

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

    if screenshots:
        total_w = max(i.width for i in screenshots)
        total_h = sum(i.height for i in screenshots)
        final = Image.new("RGB", (total_w, total_h), (255, 255, 255))
        y_off = 0
        for i in screenshots:
            final.paste(i, (0, y_off))
            y_off += i.height
        final.save(output)

    return {
        "success": True, "output": output,
        "scrolls": count, "total_height": total_height,
        "message": f"「{keyword}」长截图完成（{count}次滚动, {total_height}px）→ {output}"
    }


def tool_navigate(url, click_text=None):
    """导航到页面，可选点击某个元素切换标签"""
    page = goto(url)
    if click_text:
        el = find_element(page, click_text)
        if el:
            el.click()
            page.wait_for_timeout(2000)
            return {"success": True, "message": f"已点击「{click_text}」"}
        return {"success": False, "error": f"未找到「{click_text}」"}
    return {"success": True, "message": f"已在 {url}"}


# ─── MCP JSON-RPC 协议 ───────────────────────────────────────

TOOLS = {
    "navigate": {
        "name": "navigate",
        "description": "导航到指定页面，可选点击元素切换标签",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标网页 URL"},
                "click_text": {"type": "string", "description": "要点击的文字（可选）"}
            },
            "required": ["url"]
        }
    },
    "screenshot_element": {
        "name": "screenshot_element",
        "description": "精准截图：只截取关键词对应的元素本身",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标网页 URL"},
                "keyword": {"type": "string", "description": "要截图的元素文字"},
                "output": {"type": "string", "description": "输出路径（可选）"}
            },
            "required": ["url", "keyword"]
        }
    },
    "screenshot_section": {
        "name": "screenshot_section",
        "description": "段落截图：截取关键词所在的小节完整区块",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标网页 URL"},
                "keyword": {"type": "string", "description": "要定位的关键词"},
                "output": {"type": "string", "description": "输出路径（可选）"},
                "padding": {"type": "integer", "description": "边距（默认15）"}
            },
            "required": ["url", "keyword"]
        }
    },
    "screenshot_long": {
        "name": "screenshot_long",
        "description": "长截图：内容超出一屏时自动滚动拼接为长图",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "目标网页 URL"},
                "keyword": {"type": "string", "description": "要截图的区域关键词"},
                "output": {"type": "string", "description": "输出路径（可选）"},
                "max_scrolls": {"type": "integer", "description": "最大滚动次数（默认10）"}
            },
            "required": ["url", "keyword"]
        }
    }
}

TOOL_FUNCS = {
    "navigate": tool_navigate,
    "screenshot_element": tool_screenshot_element,
    "screenshot_section": tool_screenshot_section,
    "screenshot_long": tool_screenshot_long,
}


def handle_request(req):
    method = req.get("method")
    rid = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "screenshot-mcp", "version": "2.0.0"}
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
