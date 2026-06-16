"""
直接测试长截图功能，不走 MCP 协议
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from playwright.sync_api import sync_playwright
from PIL import Image
from io import BytesIO

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto("https://weekfupan.top/", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # 点击今日
    page.locator("text=今日").first.click()
    page.wait_for_timeout(2000)

    # 截图当前状态
    page.screenshot(path="test_after_click_today.png", full_page=True)
    print("已截图当前页面状态")

    # 尝试各种方式找到"每日安排"
    print("\n=== 尝试定位 ===")
    print(f"  text=每日安排: {page.locator('text=每日安排').count()} 个")
    print(f"  text=安排: {page.locator('text=安排').count()} 个")
    print(f"  get_by_text('每日安排'): {page.get_by_text('每日安排').count()} 个")

    # 用 CSS 选择器找
    count = page.evaluate("""
    () => {
        const els = document.querySelectorAll('p');
        let found = 0;
        for (const el of els) {
            if (el.textContent.includes('每日安排')) {
                found++;
                console.log('Found:', el.tagName, el.textContent, el.getBoundingClientRect());
            }
        }
        return found;
    }
    """)
    print(f"  CSS p 标签包含'每日安排': {count} 个")

    # 直接用 JS 获取元素并截图
    result = page.evaluate("""
    () => {
        const els = document.querySelectorAll('p');
        for (const el of els) {
            if (el.textContent.includes('每日安排')) {
                const box = el.getBoundingClientRect();
                return {x: box.x, y: box.y, w: box.width, h: box.height, text: el.textContent};
            }
        }
        return null;
    }
    """)
    print(f"\n  JS 找到: {result}")

    if result:
        # 手动截图这个区域
        page.screenshot(
            path="test_manual_element.png",
            clip={"x": result["x"], "y": result["y"], "width": result["w"], "height": result["h"]}
        )
        print("  已手动截图该元素")

        # 长截图测试：截"每日安排"下方的时间表
        # 获取时间表区域（从 10:00 到 18:00）
        time_area = page.evaluate("""
        () => {
            const p10 = document.querySelector('p');
            const allP = document.querySelectorAll('p');
            let first = null, last = null;
            for (const p of allP) {
                const t = p.textContent.trim();
                if (/^\d{1,2}:00$/.test(t)) {
                    if (!first) first = p;
                    last = p;
                }
            }
            if (first && last) {
                const firstBox = first.getBoundingClientRect();
                const lastBox = last.getBoundingClientRect();
                return {
                    x: firstBox.x - 10,
                    y: firstBox.y - 10,
                    w: firstBox.width + 20,
                    h: (lastBox.y + lastBox.height + 30) - firstBox.y,
                    total_height: (lastBox.y + lastBox.height + 30) - firstBox.y
                };
            }
            return null;
        }
        """)
        print(f"\n  时间表区域: {time_area}")

        if time_area and time_area["total_height"] > 900:
            print(f"\n=== 长截图测试（高度 {time_area['total_height']:.0f}px > 900px 屏幕高度）===")

            screenshots = []
            viewport_h = 900
            total = time_area["total_height"]
            scroll_y = time_area["y"]
            remaining = total
            scroll_count = 0

            while remaining > 0 and scroll_count < 10:
                page.evaluate(f"window.scrollTo(0, {scroll_y})")
                page.wait_for_timeout(500)

                img_bytes = page.screenshot()
                img = Image.open(BytesIO(img_bytes))

                # 裁剪当前可视区域中属于时间表的部分
                relative_y = scroll_y - page.evaluate("window.scrollY")
                crop_top = max(0, relative_y)
                crop_bottom = min(img.height, crop_top + min(remaining, viewport_h))

                if crop_top < img.height:
                    cropped = img.crop((0, int(crop_top), img.width, int(crop_bottom)))
                    screenshots.append(cropped)
                    print(f"  截图 {scroll_count+1}: crop y={crop_top:.0f}-{crop_bottom:.0f}, 实际高度={cropped.height}")

                scroll_y += viewport_h
                remaining -= viewport_h
                scroll_count += 1

            # 拼接
            if screenshots:
                total_w = max(img.width for img in screenshots)
                total_h = sum(img.height for img in screenshots)
                final = Image.new("RGB", (total_w, total_h), (255, 255, 255))
                y_offset = 0
                for img in screenshots:
                    final.paste(img, (0, y_offset))
                    y_offset += img.height
                final.save("test_long_screenshot.png")
                print(f"\n✅ 长截图完成: {total_w}x{total_h}, 滚动 {scroll_count} 次")
        elif time_area:
            print(f"\n区域高度 {time_area['total_height']:.0f}px < 900px，不需要长截图")
            page.screenshot(path="test_short_section.png",
                          clip={"x": time_area["x"], "y": time_area["y"],
                                "width": time_area["w"], "height": time_area["h"]})

    browser.close()
