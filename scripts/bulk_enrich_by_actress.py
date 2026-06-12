"""
全量建置 data/javdb_lookup.json（女優列表路線，覆蓋全時間段資料）

流程：
  Phase 1：爬 star_list.php 所有 prefix（A-Z, 0-9）
           → 收集全部女優 ID + 名字，存入 data/enrich_actress_list.json
  Phase 2：逐一爬每位女優的 vl_star.php listing 頁
           → listing 頁直接取 code + title（不進單片頁，速度快 8-10x）
           → partial entry 存入 lookup（actresses 只有當前女優，用戶查詢時自動補全）

⚠️ 工具擁有者自用，不面向一般用戶。

用法：
    venv\\Scripts\\python.exe scripts/bulk_enrich_by_actress.py
    venv\\Scripts\\python.exe scripts/bulk_enrich_by_actress.py --reset   # 從頭重新開始

進度存於 data/enrich_actress_state.json（已 gitignore）。
"""
import argparse
import asyncio
import json
import os
import signal
import sys
import threading
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ── 優雅停止 ────────────────────────────────────────────────────────────────

_stop_requested = threading.Event()

def _setup_stop_signal():
    def _handler(signum, frame):
        if _stop_requested.is_set():
            print("\n⚠ 強制中止", flush=True)
            os._exit(1)
        _stop_requested.set()
        print("\n⏸  收到停止信號，本頁跑完後自動停止（再按一次 Ctrl+C 強制中止）", flush=True)
    signal.signal(signal.SIGINT, _handler)

# ── 常數 ────────────────────────────────────────────────────────────────────

JAVLIB_BASE   = "https://www.javlibrary.com"
STAR_LIST_URL = f"{JAVLIB_BASE}/ja/star_list.php"
STAR_URL      = f"{JAVLIB_BASE}/ja/vl_star.php"
BROWSER_ARGS  = ["--window-position=-32000,0", "--window-size=1280,800"]
PAGE_DELAY    = 2   # 每次 page.get() 後的最短等待秒數
SAVE_INTERVAL = 50  # 每處理完多少位女優存一次 lookup.json

PREFIXES = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + [str(i) for i in range(10)]

ROOT              = Path(__file__).parent.parent
LOOKUP_FILE       = ROOT / "data" / "javdb_lookup.json"
STATE_FILE        = ROOT / "data" / "enrich_actress_state.json"
ACTRESS_LIST_FILE = ROOT / "data" / "enrich_actress_list.json"

# ── I/O ─────────────────────────────────────────────────────────────────────

def _load(path: Path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default

def _save(path: Path, data) -> None:
    """原子寫入，防止中途強制關閉造成 JSON 損壞。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

# ── Browser helpers ──────────────────────────────────────────────────────────

async def _fetch(page, url: str, retries: int = 3, delay: int = 15) -> bool:
    for attempt in range(retries):
        try:
            await page.get(url)
            return True
        except Exception as e:
            if attempt < retries - 1:
                print(f"  ⚠ 網路錯誤，{delay}s 後重試（第 {attempt+1} 次）...", flush=True)
                await asyncio.sleep(delay)
            else:
                print(f"  ❌ 網路持續失敗，跳過", flush=True)
    return False

async def _wait_ready(page, timeout: int = 30) -> bool:
    for _ in range(timeout // 2):
        title = await page.evaluate("document.title")
        if "請稍候" not in title and "Just a moment" not in title:
            await asyncio.sleep(2)
            return True
        await asyncio.sleep(2)
    return False

# ── Parsers ──────────────────────────────────────────────────────────────────

def _parse_last_page(html: str) -> int | None:
    soup = BeautifulSoup(html, "lxml")

    def _n(href):
        raw = urlparse(href).query.lstrip("&")
        qs  = parse_qs(raw)
        try:
            return int(qs.get("page", [])[0])
        except (IndexError, ValueError):
            return None

    last_a = soup.select_one(".page_selector a.last")
    if last_a:
        n = _n(last_a.get("href", ""))
        if n:
            return n
    nums = [_n(a.get("href","")) for a in soup.select(".page_selector a[href*='page=']")]
    nums = [n for n in nums if n]
    return max(nums) if nums else None

def _parse_actress_list(html: str) -> list[dict]:
    """star_list.php 頁面 → 女優 [{id, name}]"""
    soup = BeautifulSoup(html, "lxml")
    result = []
    for a in soup.select("a[href*='vl_star.php?s=']"):
        href = a.get("href", "")
        name = a.get_text(strip=True)
        if not name:
            continue
        star_id = parse_qs(urlparse(href).query.lstrip("&")).get("s", [""])[0]
        if star_id:
            result.append({"id": star_id, "name": name})
    return result

def _parse_video_listing(html: str) -> list[dict]:
    """vl_star.php listing 頁 → [{code, title}]（不需進單片頁）"""
    soup = BeautifulSoup(html, "lxml")
    items = []
    for a in soup.select("div.videos div.video a"):
        code_el  = a.select_one("div.id")
        title_el = a.select_one("div.title")
        code  = code_el.get_text(strip=True)  if code_el  else ""
        title = title_el.get_text(strip=True) if title_el else ""
        if code and title:
            items.append({"code": code, "title": title})
    return items

# ── Phase 1：收集女優清單 ──────────────────────────────────────────────────

async def phase1(page, state: dict) -> bool:
    """回傳 True = 完成；False = Ctrl+C 中斷"""
    actress_list: list = _load(ACTRESS_LIST_FILE, [])
    seen_ids = {a["id"] for a in actress_list}

    prefix_idx  = state.get("prefix_idx",  0)
    prefix_page = state.get("prefix_page", 1)
    total_p     = len(PREFIXES)

    for pi in range(prefix_idx, total_p):
        if _stop_requested.is_set():
            _checkpoint_p1(state, actress_list, pi, prefix_page)
            return False

        prefix      = PREFIXES[pi]
        start_page  = prefix_page if pi == prefix_idx else 1
        prefix_page = 1

        url = f"{STAR_LIST_URL}?prefix={prefix}&page={start_page}"
        print(f"\n── [P1] prefix={prefix} ({pi+1}/{total_p})  已收集 {len(actress_list)} 位女優  [Ctrl+C：安全停止] ──")

        if not await _fetch(page, url) or not await _wait_ready(page):
            print(f"  ❌ 跳過 prefix={prefix}")
            continue

        html       = await page.get_content()
        last_page  = _parse_last_page(html) or 1

        for pg in range(start_page, last_page + 1):
            if _stop_requested.is_set():
                _checkpoint_p1(state, actress_list, pi, pg)
                return False

            if pg > start_page:
                url = f"{STAR_LIST_URL}?prefix={prefix}&page={pg}"
                if not await _fetch(page, url) or not await _wait_ready(page):
                    continue
                html = await page.get_content()

            batch = _parse_actress_list(html)
            new   = [a for a in batch if a["id"] not in seen_ids]
            for a in new:
                actress_list.append(a)
                seen_ids.add(a["id"])

            print(f"  page {pg}/{last_page}  +{len(new)} 位", flush=True)
            await asyncio.sleep(PAGE_DELAY)

        # prefix 完成 → checkpoint
        _checkpoint_p1(state, actress_list, pi + 1, 1)

    # Phase 1 全部完成
    state.update({"phase": 2, "phase1_done": True,
                  "actress_idx": 0, "actress_page": 1})
    _save(STATE_FILE, state)
    _save(ACTRESS_LIST_FILE, actress_list)
    print(f"\n✅ Phase 1 完成！共 {len(actress_list)} 位女優\n")
    return True

def _checkpoint_p1(state, actress_list, pi, pg):
    state["prefix_idx"]  = pi
    state["prefix_page"] = pg
    _save(STATE_FILE, state)
    _save(ACTRESS_LIST_FILE, actress_list)
    print(f"  💾 Checkpoint：prefix_idx={pi} page={pg}，共 {len(actress_list)} 位女優")

# ── Phase 2：逐女優爬影片 ─────────────────────────────────────────────────

async def phase2(page, state: dict, actress_list: list) -> None:
    lookup         = _load(LOOKUP_FILE, {})
    session_added  = 0
    session_total  = 0  # 含跳過
    since_last_save = 0

    actress_idx  = state.get("actress_idx",  0)
    actress_page = state.get("actress_page", 1)
    total        = len(actress_list)

    print(f"[P2] 從第 {actress_idx+1}/{total} 位女優開始")
    print(f"  lookup 現有：{len(lookup)} 筆\n")

    for i in range(actress_idx, total):
        if _stop_requested.is_set():
            _checkpoint_p2(state, lookup, i, 1, session_added)
            print(f"\n✅ 停止，本次 +{session_added} 筆")
            return

        actress     = actress_list[i]
        star_id     = actress["id"]
        star_name   = actress["name"]
        start_page  = actress_page if i == actress_idx else 1
        actress_page = 1

        print(f"── [{i+1}/{total}] {star_name}  [Ctrl+C：安全停止] ──")

        url = f"{STAR_URL}?s={star_id}&page={start_page}"
        if not await _fetch(page, url) or not await _wait_ready(page):
            print("❌ 跳過")
            continue

        html      = await page.get_content()
        last_page = _parse_last_page(html) or 1
        added     = 0

        for pg in range(start_page, last_page + 1):
            if _stop_requested.is_set():
                _checkpoint_p2(state, lookup, i, pg, session_added)
                print(f"\n✅ 停止於 {star_name} page={pg}，本次 +{session_added} 筆")
                return

            if pg > start_page:
                url = f"{STAR_URL}?s={star_id}&page={pg}"
                if not await _fetch(page, url) or not await _wait_ready(page):
                    continue
                html = await page.get_content()

            for v in _parse_video_listing(html):
                code, title = v["code"], v["title"]
                existing = lookup.get(code)
                if existing and not existing.get("partial"):
                    continue  # 已有完整 entry，不覆蓋
                lookup[code] = {"title": title, "actresses": [star_name], "partial": True}
                added         += 1
                session_added += 1

            await asyncio.sleep(PAGE_DELAY)

        since_last_save += 1
        print(f"   +{added} 筆  (lookup 總計 {len(lookup)})")

        # state 與 lookup 必須一起存，避免強制關閉後 state 超前 lookup 造成資料遺漏
        if since_last_save >= SAVE_INTERVAL:
            state["actress_idx"]  = i + 1
            state["actress_page"] = 1
            state["total_added"]  = state.get("total_added", 0) + session_added
            _save(LOOKUP_FILE, lookup)
            _save(STATE_FILE, state)
            since_last_save = 0
            print(f"  💾 Checkpoint：{i+1}/{total} 位，lookup {len(lookup)} 筆")

    # Phase 2 全部完成
    _save(LOOKUP_FILE, lookup)
    state["phase2_done"] = True
    _save(STATE_FILE, state)
    print(f"\n✅ Phase 2 完成！本次 +{session_added} 筆，lookup 總計 {len(lookup)} 筆")

def _checkpoint_p2(state, lookup, actress_idx, actress_page, session_added):
    state["actress_idx"]  = actress_idx
    state["actress_page"] = actress_page
    state["total_added"]  = state.get("total_added", 0) + session_added
    _save(STATE_FILE, state)
    _save(LOOKUP_FILE, lookup)

# ── 主流程 ────────────────────────────────────────────────────────────────

async def run(reset: bool) -> None:
    import nodriver as uc

    state = {} if reset else _load(STATE_FILE, {})
    if reset:
        print("⚠ --reset：清除舊進度，從頭開始\n")
        _save(STATE_FILE, {"phase": 1, "prefix_idx": 0, "prefix_page": 1})
        state = _load(STATE_FILE, {})

    phase        = state.get("phase", 1)
    phase1_done  = state.get("phase1_done", False)
    phase2_done  = state.get("phase2_done", False)

    actress_list = _load(ACTRESS_LIST_FILE, [])

    _setup_stop_signal()

    print("=" * 60)
    print("  bulk_enrich_by_actress — 全量建置（女優路線）")
    print(f"  來源：{STAR_LIST_URL}?prefix=X")
    if phase1_done:
        print(f"  Phase 1 已完成（{len(actress_list)} 位女優）")
        print(f"  Phase 2：從第 {state.get('actress_idx',0)+1} 位繼續")
    else:
        print(f"  Phase 1：從 prefix={PREFIXES[state.get('prefix_idx',0)]} page={state.get('prefix_page',1)} 繼續")
    print(f"  lookup 現有：{len(_load(LOOKUP_FILE, {}))} 筆")
    print()
    print("  ▶ Ctrl+C   ：本頁跑完後安全停止（checkpoint 儲存）")
    print("  ▶ Ctrl+C×2 ：立即強制中止")
    print("  ▶ 續跑     ：重新雙擊 BAT")
    print("=" * 60)
    print()

    if phase2_done:
        print("✅ 已全部完成！如需重新建置請加 --reset 參數。")
        return

    print("啟動 Chrome（off-screen）...")
    browser = await uc.start(headless=False, browser_args=BROWSER_ARGS)
    try:
        try:
            page = await browser.get(f"{JAVLIB_BASE}/ja/")
        except Exception as e:
            print(f"❌ 無法連線（{e}）")
            return

        print("等待 Cloudflare challenge...")
        if not await _wait_ready(page):
            print("❌ CF 未解，退出")
            return
        print("✅ CF 已解\n")

        # Phase 1
        if not phase1_done:
            completed = await phase1(page, state)
            if not completed:
                return
            state        = _load(STATE_FILE, {})
            actress_list = _load(ACTRESS_LIST_FILE, [])

        # Phase 2
        if not state.get("phase2_done"):
            await phase2(page, state, actress_list)

    finally:
        browser.stop()


def main():
    parser = argparse.ArgumentParser(description="全量建置 lookup（女優路線）")
    parser.add_argument("--reset", action="store_true", help="清除進度，從頭重新開始")
    args = parser.parse_args()
    asyncio.run(run(reset=args.reset))


if __name__ == "__main__":
    main()
