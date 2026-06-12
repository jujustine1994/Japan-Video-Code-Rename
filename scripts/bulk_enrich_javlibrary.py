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
import signal
import sys
import threading
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 把專案根目錄加入 path 以便 import renamer
sys.path.insert(0, str(Path(__file__).parent.parent))
from renamer import strip_actress_suffix

# ── 優雅停止（Ctrl+C 跑完本頁後停止）─────────────────────────────────────────

_stop_requested = threading.Event()

def _setup_stop_signal() -> None:
    def _handler(signum, frame):
        if _stop_requested.is_set():
            print("\n⚠ 強制中止", flush=True)
            os._exit(1)
        _stop_requested.set()
        print("\n⏸  收到停止信號，本頁跑完後自動停止（再按一次 Ctrl+C 立即強制中止）", flush=True)
    signal.signal(signal.SIGINT, _handler)

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

def _parse_last_page(html: str) -> int | None:
    """從 listing 頁 HTML 取得最後一頁頁碼。selector: .page_selector a.last"""
    from urllib.parse import urlparse, parse_qs
    soup = BeautifulSoup(html, "lxml")
    last_a = soup.select_one(".page_selector a.last")
    if not last_a:
        return None
    qs = parse_qs(urlparse(last_a.get("href", "")).query)
    pages = qs.get("page", [])
    return int(pages[0]) if pages else None


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

    checkpoint_page = state.get("last_page")
    if start_page is None:
        resume_msg = f"  📍 全新建置：啟動後自動偵測最後一頁，從末頁往前爬"
    elif checkpoint_page and start_page == checkpoint_page and state.get("direction") == "desc":
        resume_msg = f"  📍 從 checkpoint 繼續：第 {start_page} 頁往前（上次累計 {state.get('total_added', '?')} 筆）"
    else:
        resume_msg = f"  📍 從第 {start_page} 頁開始（手動指定）"

    _setup_stop_signal()

    print("=" * 54)
    print("  bulk_enrich_javlibrary — 全量建置")
    print(resume_msg)
    print(f"  現有 lookup：{len(lookup)} 筆")
    print()
    print("  ▶ Ctrl+C   ：本頁跑完後停止（checkpoint 安全儲存）")
    print("  ▶ Ctrl+C×2 ：立即強制中止")
    print("  ▶ 續跑     ：重新雙擊 BAT，從上次停止頁碼繼續")
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
        print("✅ CF 已解")

        # 偵測總頁數（從 page 1 的分頁 HTML）
        print("偵測總頁數...")
        if not await _fetch_page(page, f"{LISTING_URL}?page=1") or not await _wait_ready(page):
            print("❌ 無法取得第 1 頁，退出")
            return
        html_p1 = await page.get_content()
        total_pages = _parse_last_page(html_p1)
        if not total_pages:
            print("⚠ 無法解析總頁數，預設使用 9999")
            total_pages = 9999
        print(f"✅ 總頁數：{total_pages}\n")

        # 決定起始頁（從最後一頁往前）
        actual_start = start_page if start_page is not None else total_pages
        end_page = max(1, actual_start - max_pages + 1)

        print(f"  爬取範圍：第 {actual_start} 頁 → 第 {end_page} 頁（往前）")
        print()

        for listing_page_num in range(actual_start, end_page - 1, -1):
            if _stop_requested.is_set():
                print(f"✅ 停止於第 {listing_page_num} 頁前，下次從此頁繼續。")
                break
            listing_url = f"{LISTING_URL}?page={listing_page_num}"
            print(f"── Listing 頁 {listing_page_num}/{total_pages} ── [Ctrl+C：本頁後停止] ──")

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

                # 影片頁：CF timeout 或解析失敗都重試，最多 3 次
                result = None
                for attempt in range(3):
                    if attempt > 0:
                        await asyncio.sleep(10)
                    if not await _fetch_page(page, video_url):
                        print(f"  [{idx:2d}/{len(items)}] {code:15s} ❌ 網路失敗，跳過")
                        break
                    if not await _wait_ready(page):
                        print(f"  [{idx:2d}/{len(items)}] {code:15s} ⚠ CF timeout（第 {attempt + 1}/3），重試...")
                        continue
                    html2 = await page.get_content()
                    result = _parse_video(html2, code)
                    if result:
                        break
                    # 解析失敗（頁面可能沒載完或結構不同）
                    if attempt < 2:
                        print(f"  [{idx:2d}/{len(items)}] {code:15s} ⚠ 解析失敗（第 {attempt + 1}/3），重試...")

                if result:
                    lookup[code] = {"title": result["title"], "actresses": result["actresses"]}
                    session_added += 1
                    actress_str = "、".join(result["actresses"]) if result["actresses"] else "（無女優名）"
                    print(f"  [{idx:2d}/{len(items)}] {code:15s} ✅ {result['title'][:30]}  [{actress_str}]")
                else:
                    print(f"  [{idx:2d}/{len(items)}] {code:15s} ❌ 跳過（3 次皆失敗）")

                await asyncio.sleep(PAGE_DELAY)

            # 每個 listing 頁結束後存 checkpoint（往前爬，下次從 listing_page_num-1 繼續）
            state["last_page"] = listing_page_num - 1
            state["direction"] = "desc"
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
    if args.start_page is not None:
        start = args.start_page          # 手動指定
    elif state.get("direction") == "desc" and state.get("last_page", 0) > 0:
        start = state["last_page"]       # 從上次 checkpoint 繼續往前
    else:
        start = None                     # 自動偵測最後一頁（全新建置）

    asyncio.run(run(start, args.max_pages))


if __name__ == "__main__":
    main()
