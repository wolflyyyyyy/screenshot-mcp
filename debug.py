import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto("https://weekfupan.top/", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # 点击今日
    page.locator("text=今日").first.click()
    page.wait_for_timeout(2000)
    page.screenshot(path="debug_today.png", full_page=True)

    # 查找页面上所有包含文字的元素
    result = page.evaluate("""
    () => {
        const elements = document.querySelectorAll('*');
        const texts = [];
        for (const el of elements) {
            const t = el.textContent.trim();
            if (t && t.length < 50 && t.length > 0 && el.children.length === 0) {
                texts.push({tag: el.tagName, text: t, className: el.className?.substring(0, 50)});
            }
        }
        return texts;
    }
    """)
    print("=== 页面上的所有文字节点 ===")
    for item in result:
        print(f"  <{item['tag']}> {item['text']}  (class: {item['className']})")

    # 搜索包含"安排"的元素
    print("\n=== 搜索包含'安排'的元素 ===")
    result2 = page.evaluate("""
    () => {
        const elements = document.querySelectorAll('*');
        const found = [];
        for (const el of elements) {
            if (el.textContent.includes('安排') && el.children.length === 0) {
                const box = el.getBoundingClientRect();
                found.push({tag: el.tagName, text: el.textContent.trim().substring(0, 50),
                            x: box.x, y: box.y, w: box.width, h: box.height,
                            className: (el.className || '').substring(0, 50)});
            }
        }
        return found;
    }
    """)
    for item in result2:
        print(f"  <{item['tag']}> {item['text']}  pos:({item['x']:.0f},{item['y']:.0f}) size:{item['w']:.0f}x{item['h']:.0f}")

    browser.close()
