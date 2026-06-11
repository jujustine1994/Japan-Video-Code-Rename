"""
全量建置 data/javdb_lookup.json（title-only，partial=True）
從 javlibrary.com vl_newrelease 列表頁抓取，斷點續跑。
⚠️ 工具擁有者自用，不面向一般用戶。

用法：
    venv\Scripts\python.exe scripts/bulk_enrich_javlibrary.py
    venv\Scripts\python.exe scripts/bulk_enrich_javlibrary.py --start-page 50
    venv\Scripts\python.exe scripts/bulk_enrich_javlibrary.py --max-pages 100

進度存於 data/enrich_javlibrary_state.json（已 gitignore）。
不覆蓋已存在的完整 entry（無 partial flag 的資料）。
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

JAVLIB_BASE = "https://www.javlibrary.com"
LISTING_URL = f"{JAVLIB_BASE}/ja/vl_newrelease.php"
BROWSER_ARGS = ["--window-position=-32000,0", "--window-size=1280,800"]

ROOT = Path(__file__).parent.parent
LOOKUP_FILE = ROOT / "data" / "javdb_lookup.json"
STATE_FILE = ROOT / "data" / "enrich_javlibrary_state.json"
SAVE_EVERY = 10


def _load(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def _wait_ready(page, timeout: int = 30) -> bool:
    for _ in range(timeout // 2):
        title = await page.evaluate("document.title")
        if "請稍候" not in title and "Just a moment" not in title:
            return True
        await asyncio.sleep(2)
    return False


def _parse_listing(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items = []
    for a in soup.select("div.videos div.video a"):
        code_el = a.select_one("div.id")
        title_el = a.select_one("div.title")
        code = code_el.get_text(strip=True) if code_el else ""
        title = title_el.get_text(strip=True) if title_el else ""
        if code:
            items.append({"code": code, "title": title})
    return items


async def run(start_page: int, max_pages: int) -> None:
    import nodriver as uc

    lookup = _load(LOOKUP_FILE)
    state = _load(STATE_FILE)
    original_count = sum(1 for v in lookup.values() if not v.get("partial"))
    added = 0

    print(f"起始頁：{start_page}，最多 {max_pages} 頁")
    print(f"現有 lookup：{len(lookup)} 筆（其中完整 entry {original_count} 筆）")
    print("啟動 Chrome（off-screen）...")

    browser = await uc.start(headless=False, browser_args=BROWSER_ARGS)
    try:
        page = await browser.get(f"{JAVLIB_BASE}/ja/")
        print("等待 Cloudflare challenge...")
        if not await _wait_ready(page):
            print("❌ CF 未解，退出")
            return
        print("✅ CF 已解\n")

        for page_num in range(start_page, start_page + max_pages):
            url = f"{LISTING_URL}?page={page_num}"
            await page.get(url)
            if not await _wait_ready(page):
                print(f"[P{page_num}] ❌ CF timeout，停止")
                break

            html = await page.get_content()
            items = _parse_listing(html, url)

            if not items:
                print(f"[P{page_num}] 無資料，結束")
                break

            page_added = 0
            for item in items:
                code, title = item["code"], item["title"]
                existing = lookup.get(code)
                if existing and not existing.get("partial"):
                    continue  # 已有完整 entry，不覆蓋
                lookup[code] = {"title": title, "actresses": [], "partial": True}
                page_added += 1
            added += page_added
            print(f"[P{page_num}] +{page_added} 筆（本次累計 {added}，lookup 共 {len(lookup)}）")

            if page_num % SAVE_EVERY == 0:
                state["last_page"] = page_num + 1
                state["total_added"] = state.get("total_added", 0) + added
                _save(LOOKUP_FILE, lookup)
                _save(STATE_FILE, state)
                print(f"  💾 Checkpoint saved")

            await asyncio.sleep(2)

    finally:
        state["last_page"] = start_page + max_pages
        _save(LOOKUP_FILE, lookup)
        _save(STATE_FILE, state)
        browser.stop()

    print(f"\n完成：本次新增/更新 {added} 筆，lookup 共 {len(lookup)} 筆")


def main() -> None:
    parser = argparse.ArgumentParser(description="bulk_enrich_javlibrary — 全量建置 lookup")
    parser.add_argument("--start-page", type=int, default=None,
                        help="起始頁（預設：從 checkpoint 繼續）")
    parser.add_argument("--max-pages", type=int, default=9999,
                        help="最多處理頁數（預設：跑到無資料為止）")
    args = parser.parse_args()

    state = _load(STATE_FILE)
    start = args.start_page or state.get("last_page", 1)

    asyncio.run(run(start, args.max_pages))


if __name__ == "__main__":
    main()
