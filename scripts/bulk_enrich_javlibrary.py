"""
全量建置 data/javdb_lookup.json（番號 + 片名 + 女優名，完整資料）
流程：
  1. 爬 javlibrary vl_newrelease listing 頁，每頁 20 筆，取得番號 + 影片頁 URL
  2. 進每個影片頁抓片名 + 女優名
  3. 寫入 lookup（已有完整 entry 的番號跳過）
  4. 每爬完一個 listing 頁存一次 checkpoint（斷點續跑）

⚠️ 工具擁有者自用，不面向一般用戶。

用法：
    venv\\Scripts\\python.exe scripts/bulk_enrich_javlibrary.py
    venv\\Scripts\\python.exe scripts/bulk_enrich_javlibrary.py --start-page 50
    venv\\Scripts\\python.exe scripts/bulk_enrich_javlibrary.py --max-pages 100

進度存於 data/enrich_javlibrary_state.json（已 gitignore）。
速度參考：每個影片頁約 3–6 秒，每 listing 頁（20 筆）約 1–2 分鐘。
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 把專案根目錄加入 path 以便 import renamer
sys.path.insert(0, str(Path(__file__).parent.parent))
from renamer import strip_actress_suffix

JAVLIB_BASE = "https://www.javlibrary.com"
LISTING_URL = f"{JAVLIB_BASE}/ja/vl_newrelease.php"
BROWSER_ARGS = ["--window-position=-32000,0", "--window-size=1280,800"]
PAGE_DELAY = 2  # 兩次 page.get() 之間的間隔（秒）

ROOT = Path(__file__).parent.parent
LOOKUP_FILE = ROOT / "data" / "javdb_lookup.json"
STATE_FILE = ROOT / "data" / "enrich_javlibrary_state.json"


# ── I/O ──────────────────────────────────────────────────────────────────────

def _load(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(path: Path, data: dict) -> None:
    """原子寫入：先寫暫存檔再 replace，防止中途強制關閉造成 JSON 損壞。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ── Browser helpers ───────────────────────────────────────────────────────────

async def _fetch_page(page, url: str, retries: int = 3, delay: int = 15) -> bool:
    """載入 URL，網路錯誤自動重試。回傳 True 代表頁面有載入（不保證 CF 已解）。"""
    for attempt in range(retries):
        try:
            await page.get(url)
            return True
        except Exception as e:
            if attempt < retries - 1:
                print(f"  ⚠ 網路錯誤（{e}），等 {delay} 秒重試（第 {attempt + 1} 次）...")
                await asyncio.sleep(delay)
            else:
                print(f"  ❌ 網路錯誤，重試 {retries} 次仍失敗")
                return False
    return False


async def _wait_ready(page, timeout: int = 30) -> bool:
    """等 Cloudflare challenge 解除。title 不含 CF 標記就回傳 True。"""
    for _ in range(timeout // 2):
        title = await page.evaluate("document.title")
        if "請稍候" not in title and "Just a moment" not in title:
            return True
        await asyncio.sleep(2)
    return False


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_listing(html: str, base_url: str) -> list[dict]:
    """從 listing 頁取得番號清單與對應影片頁 URL。"""
    soup = BeautifulSoup(html, "lxml")
    items = []
    for a in soup.select("div.videos div.video a"):
        href = a.get("href", "")
        if not href:
            continue
        code_el = a.select_one("div.id")
        code = code_el.get_text(strip=True) if code_el else ""
        if code:
            items.append({"code": code, "url": urljoin(base_url, href)})
    return items


def _parse_video(html: str, code: str) -> dict | None:
    """從影片頁取得片名 + 女優名（與 JavlibraryFetcher._parse_video 邏輯相同）。"""
    soup = BeautifulSoup(html, "lxml")

    code_el = soup.select_one("#video_id .text")
    found_code = code_el.get_text(strip=True) if code_el else code

    title_raw = ""
    for sel in ["h3.post-title", "#video_title strong"]:
        el = soup.select_one(sel)
        if el:
            title_raw = el.get_text(strip=True)
            break
    if not title_raw:
        return None

    actresses = [a.get_text(strip=True) for a in soup.select("span.star a")]

    title = title_raw
    if found_code and title.upper().startswith(found_code.upper()):
        title = title[len(found_code):].strip()
    title = strip_actress_suffix(title, actresses)

    return {"title": title, "actresses": actresses}


# ── Main ──────────────────────────────────────────────────────────────────────

async def run(start_page: int, max_pages: int) -> None:
    import nodriver as uc

    lookup = _load(LOOKUP_FILE)
    state = _load(STATE_FILE)
    original_count = len(lookup)
    session_added = 0
    session_skipped = 0

    print("=" * 54)
    print("  bulk_enrich_javlibrary — 全量建置")
    print(f"  起始頁：{start_page}，最多 {max_pages} 個 listing 頁")
    print(f"  現有 lookup：{len(lookup)} 筆")
    print()
    print("  ▶ 中途要停止：按 Ctrl+C（安全，checkpoint 會存好）")
    print("  ▶ 直接關視窗：也可以，但建議用 Ctrl+C 比較保險")
    print("  ▶ 續跑：重新雙擊 BAT，自動從上次停止頁碼繼續")
    print("=" * 54)
    print()
    print("啟動 Chrome（off-screen）...")

    browser = await uc.start(headless=False, browser_args=BROWSER_ARGS)
    try:
        try:
            page = await browser.get(f"{JAVLIB_BASE}/ja/")
        except Exception as e:
            print(f"❌ 無法連線（{e}），退出")
            return
        print("等待 Cloudflare challenge...")
        if not await _wait_ready(page):
            print("❌ CF 未解，退出")
            return
        print("✅ CF 已解\n")

        for listing_page_num in range(start_page, start_page + max_pages):
            listing_url = f"{LISTING_URL}?page={listing_page_num}"
            print(f"── Listing 頁 {listing_page_num} ──────────────────")

            # Listing 頁：網路錯誤 → _fetch_page 內部重試；CF timeout → 等 30 秒重試一次
            if not await _fetch_page(page, listing_url):
                print(f"  ❌ 網路持續失敗，停止")
                break
            if not await _wait_ready(page):
                print(f"  ⚠ CF timeout，等 30 秒重試...")
                await asyncio.sleep(30)
                if not await _fetch_page(page, listing_url) or not await _wait_ready(page):
                    print(f"  ❌ CF timeout 重試仍失敗，停止")
                    break

            html = await page.get_content()
            items = _parse_listing(html, listing_url)

            if not items:
                # 無資料也重試一次，排除偶發性空頁
                print(f"  ⚠ 頁面無資料，等 30 秒重試...")
                await asyncio.sleep(30)
                if not await _fetch_page(page, listing_url) or not await _wait_ready(page):
                    print(f"  ❌ CF timeout，停止")
                    break
                html = await page.get_content()
                items = _parse_listing(html, listing_url)
                if not items:
                    print(f"  無資料，結束（共爬 {listing_page_num - start_page} 個 listing 頁）")
                    break

            print(f"  取得 {len(items)} 筆番號，開始逐一爬影片頁...")

            for idx, item in enumerate(items, 1):
                code, video_url = item["code"], item["url"]

                # 已有完整 entry 就跳過
                existing = lookup.get(code)
                if existing and not existing.get("partial"):
                    session_skipped += 1
                    print(f"  [{idx:2d}/{len(items)}] {code:15s} ✓ 已有資料，跳過")
                    continue

                # 影片頁：網路錯誤 → _fetch_page 內部重試；CF timeout → 等 10 秒重試最多 2 次
                result = None
                for attempt in range(3):
                    if attempt > 0:
                        print(f"  [{idx:2d}/{len(items)}] {code:15s} ⚠ CF timeout，等 10 秒重試（第 {attempt} 次）...")
                        await asyncio.sleep(10)
                    if not await _fetch_page(page, video_url):
                        break  # 網路持續失敗，跳過這筆
                    if not await _wait_ready(page):
                        continue  # CF 未解，進下一次重試
                    html2 = await page.get_content()
                    result = _parse_video(html2, code)
                    break  # 成功取得頁面，離開重試迴圈

                if result:
                    lookup[code] = {"title": result["title"], "actresses": result["actresses"]}
                    session_added += 1
                    actress_str = "、".join(result["actresses"]) if result["actresses"] else "（無女優名）"
                    print(f"  [{idx:2d}/{len(items)}] {code:15s} ✅ {result['title'][:30]}  [{actress_str}]")
                else:
                    print(f"  [{idx:2d}/{len(items)}] {code:15s} ❌ 解析失敗/逾時，跳過")

                await asyncio.sleep(PAGE_DELAY)

            # 每個 listing 頁結束後存 checkpoint
            state["last_page"] = listing_page_num + 1
            state["total_added"] = original_count + session_added
            _save(LOOKUP_FILE, lookup)
            _save(STATE_FILE, state)
            print(f"  💾 Checkpoint：lookup {len(lookup)} 筆（本次 +{session_added}）\n")

    finally:
        _save(LOOKUP_FILE, lookup)
        _save(STATE_FILE, state)
        browser.stop()

    print(f"完成：本次新增 {session_added} 筆，跳過 {session_skipped} 筆，lookup 共 {len(lookup)} 筆")


def main() -> None:
    parser = argparse.ArgumentParser(description="bulk_enrich_javlibrary — 全量建置 lookup（含女優名）")
    parser.add_argument("--start-page", type=int, default=None,
                        help="起始 listing 頁（預設：從 checkpoint 繼續，或從第 1 頁開始）")
    parser.add_argument("--max-pages", type=int, default=9999,
                        help="最多處理幾個 listing 頁（預設：跑到無資料為止）")
    args = parser.parse_args()

    state = _load(STATE_FILE)
    start = args.start_page if args.start_page is not None else state.get("last_page", 1)

    asyncio.run(run(start, args.max_pages))


if __name__ == "__main__":
    main()
