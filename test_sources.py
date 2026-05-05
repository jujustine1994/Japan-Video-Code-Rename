"""
AV 資料來源測試腳本
測試 javbus / javdb / javlibrary (Playwright) + javscraper + r18.dev API (輕量)
"""

import sys
import time
import os
import json

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
try:
    from playwright_stealth import stealth_sync
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

TEST_CODES = [
    "SSIS-001",  # 大廠有碼，DMM 一定有
    "GTJ-065",   # 常見大廠
    "DDT-435",   # 另一大廠
]

DEBUG_HTML = True


def save_debug_html(label: str, html: str):
    if not DEBUG_HTML:
        return
    os.makedirs("debug_html", exist_ok=True)
    path = f"debug_html/{label}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def clean(text: str) -> str:
    return " ".join(text.split()).strip()


# ── 來源 1：javbus ─────────────────────────────────────────────
def test_javbus(page, code: str):
    if HAS_STEALTH:
        stealth_sync(page)
    url = f"https://www.javbus.com/{code}"
    try:
        start = time.time()
        page.goto(url, wait_until="domcontentloaded", timeout=20000)

        # 處理年齡驗證（AJAX 提交 → 設 cookie → 手動跳轉）
        if "driver-verify" in page.url:
            try:
                page.wait_for_selector("#ageVerify", timeout=5000)
                page.check('#ageVerify input[type="checkbox"]')
                page.click('#submit')
                # AJAX 提交，等網路靜止（cookie 被寫入）
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            # 手動跳到真正的電影頁
            page.goto(url, wait_until="domcontentloaded", timeout=15000)

        # 等真正的內容
        try:
            page.wait_for_selector("h3", timeout=10000)
        except PlaywrightTimeout:
            save_debug_html(f"javbus_final_{code}", page.content())
            return False, f"timeout 等待 h3，當前URL: {page.url}", time.time() - start

        elapsed = time.time() - start

        # 片名
        save_debug_html(f"javbus_success_{code}", page.content())
        h3 = page.query_selector("h3")
        title = clean(h3.inner_text()) if h3 else ""

        # 女優：.star-name a
        actresses = []
        for el in page.query_selector_all(".star-name a"):
            name = el.inner_text().strip()
            if name:
                actresses.append(name)
        if not actresses:
            for el in page.query_selector_all('a[href*="/star/"]'):
                name = el.inner_text().strip()
                if name and len(name) >= 2:
                    actresses.append(name)

        if not title:
            save_debug_html(f"javbus_{code}", page.content())
            return False, "解析失敗（找不到 h3）", elapsed

        return True, {"title": title, "actresses": list(dict.fromkeys(actresses))}, elapsed

    except Exception as e:
        return False, str(e), 0


# ── 來源 2：javdb ──────────────────────────────────────────────
def test_javdb(page, code: str):
    try:
        start = time.time()
        # 直接設 over18 cookie，跳過年齡驗證 modal
        page.context.add_cookies([
            {"name": "over18", "value": "1", "domain": "javdb.com", "path": "/"},
            {"name": "locale",  "value": "ja",  "domain": "javdb.com", "path": "/"},
        ])

        # 搜尋頁
        search_url = f"https://javdb.com/search?q={code}&f=all"
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)

        try:
            page.wait_for_selector(".video-title", timeout=6000)
        except PlaywrightTimeout:
            save_debug_html(f"javdb_search_{code}", page.content())
            return False, "搜尋頁 timeout（可能還在年齡驗證）", time.time() - start

        # 找第一筆結果
        result = None
        for item in page.query_selector_all(".video-title strong"):
            if code.upper() in item.inner_text().upper():
                result = item.query_selector("xpath=ancestor::a")
                if not result:
                    result = item.evaluate_handle("el => el.closest('a')").as_element()
                break
        if not result:
            result = page.query_selector("div.item a.box")

        if not result:
            save_debug_html(f"javdb_search_{code}", page.content())
            return False, "搜尋無結果", time.time() - start

        # 點進詳細頁
        result.click()
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        elapsed = time.time() - start

        # 片名：優先用 .origin-title（日文原名）
        title = ""
        orig_el = page.query_selector(".origin-title")
        if orig_el:
            title = clean(orig_el.inner_text())
        else:
            # fallback：從 h2.title 取全文，去番號前綴和按鈕文字
            for sel in ["h2.title", ".title.is-4"]:
                el = page.query_selector(sel)
                if el:
                    full_text = clean(el.inner_text())
                    for noise in ["顯示原標題", "隱藏原標題"]:
                        full_text = full_text.replace(noise, "").strip()
                    if full_text.upper().startswith(code.upper()):
                        title = clean(full_text[len(code):])
                    else:
                        title = full_text
                    if title:
                        break

        # 女優
        actresses = []
        for el in page.query_selector_all('.panel-block a[href*="/actors/"]'):
            actresses.append(el.inner_text().strip())
        if not actresses:
            for el in page.query_selector_all(".cast .value a"):
                actresses.append(el.inner_text().strip())

        if not title:
            save_debug_html(f"javdb_detail_{code}", page.content())
            return False, "詳細頁解析失敗", elapsed

        return True, {"title": title, "actresses": actresses, "url": page.url}, elapsed

    except Exception as e:
        return False, str(e), 0


# ── 來源 3：javlibrary ─────────────────────────────────────────
def test_javlibrary(page, code: str):
    try:
        if HAS_STEALTH:
            stealth_sync(page)
        start = time.time()
        search_url = f"https://www.javlibrary.com/en/?vm=search2&sstr={code}&stype=1"
        page.goto(search_url, wait_until="domcontentloaded", timeout=25000)

        # 等 Cloudflare 解完
        try:
            page.wait_for_selector(".video", timeout=12000)
        except PlaywrightTimeout:
            content = page.content()
            save_debug_html(f"javlibrary_search_{code}", content)
            if "Just a moment" in content or "cf-browser" in content:
                return False, "Cloudflare 驗證未通過", time.time() - start
            return False, "搜尋頁 timeout", time.time() - start

        # 找第一筆結果
        result = page.query_selector(".video a")
        if not result:
            save_debug_html(f"javlibrary_search_{code}", page.content())
            return False, "搜尋無結果", time.time() - start

        result.click()
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        elapsed = time.time() - start

        # 片名
        title_el = page.query_selector("#video_title .post-title")
        title = clean(title_el.inner_text()) if title_el else ""

        # 女優
        actresses = []
        for el in page.query_selector_all("#video_cast .cast .star"):
            actresses.append(el.inner_text().strip())

        if not title:
            save_debug_html(f"javlibrary_detail_{code}", page.content())
            return False, "詳細頁解析失敗", elapsed

        return True, {"title": title, "actresses": actresses}, elapsed

    except Exception as e:
        return False, str(e), 0


# ── 來源 4：javscraper（cloudscraper，不需要 Playwright）─────────
def test_javscraper_fn(code: str) -> tuple[bool, dict | str, float]:
    try:
        from javscraper import JAVScraper
        start = time.time()
        scraper = JAVScraper()
        result = scraper.get_video(code)
        elapsed = time.time() - start
        if result is None:
            return False, "查無資料", elapsed
        title = getattr(result, "name", None) or getattr(result, "title", None) or ""
        actresses_raw = getattr(result, "actresses", []) or getattr(result, "cast", []) or []
        actresses = [str(a) for a in actresses_raw]
        source = str(getattr(result, "source", "unknown"))
        return True, {"title": title, "actresses": actresses, "source": source}, elapsed
    except Exception as e:
        return False, str(e), 0


# ── 來源 5：r18.dev JSON API（純 HTTP，最輕量）─────────────────────
def test_r18dev_fn(code: str) -> tuple[bool, dict | str, float]:
    try:
        start = time.time()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        # r18.dev 支援 dvd_id 格式（含 -）
        url = f"https://r18.dev/videos/vod/movies/detail/-/dvd_id={code}/json/"
        r = requests.get(url, headers=headers, timeout=12)
        elapsed = time.time() - start
        if r.status_code != 200:
            # 試 content_id（無 -，小寫）
            clean = code.replace("-", "").lower()
            url2 = f"https://r18.dev/videos/vod/movies/detail/-/content_id={clean}/json/"
            r = requests.get(url2, headers=headers, timeout=12)
            elapsed = time.time() - start
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}", elapsed
        data = r.json()
        if isinstance(data, list):
            data = data[0] if data else {}
        if not data:
            return False, "空回應", elapsed
        actresses = []
        for a in data.get("actresses", []) or []:
            name = a.get("name_romaji") or a.get("name_kanji") or a.get("name") or ""
            if name:
                actresses.append(name)
        title = data.get("title_ja") or data.get("title") or ""
        return True, {"title": title, "actresses": actresses, "release": data.get("release_date", "")}, elapsed
    except Exception as e:
        return False, str(e), 0


# ── 主程式 ────────────────────────────────────────────────────
def show_cth_banner():
    b = "\033[90m"
    c = "\033[96m"
    y = "\033[93m"
    r = "\033[0m"
    print(f"{b}/*  ================================  *\\{r}")
    print(f"{b} *                                    *{r}")
    print(f"{b} *    {c}██████╗████████╗██╗  ██╗{b}        *{r}")
    print(f"{b} *   {c}██╔════╝   ██║   ██║  ██║{b}        *{r}")
    print(f"{b} *   {c}██║        ██║   ███████║{b}        *{r}")
    print(f"{b} *   {c}██║        ██║   ██╔══██║{b}        *{r}")
    print(f"{b} *   {c}╚██████╗   ██║   ██║  ██║{b}        *{r}")
    print(f"{b} *    {c}╚═════╝   ╚═╝   ╚═╝  ╚═╝{b}        *{r}")
    print(f"{b} *                                    *{r}")
    print(f"{b} *          {y}created by CTH{b}            *{r}")
    print(f"{b}\\*  ================================  */{r}")
    print()


PW_SOURCES = [
    ("javbus",      test_javbus),
    ("javdb",       test_javdb),
    ("javlibrary",  test_javlibrary),
]

LIGHT_SOURCES = [
    ("javscraper",  test_javscraper_fn),
    ("r18.dev API", test_r18dev_fn),
]

ALL_SOURCE_NAMES = [s for s, _ in LIGHT_SOURCES] + [s for s, _ in PW_SOURCES]


def _print_result(source_name: str, success: bool, result, elapsed: float, code_results: dict):
    if success:
        title = result.get("title", "N/A")
        actress_str = "、".join(result.get("actresses", [])) or "（無女優資料）"
        extra = f"  [{result.get('source', '')}]" if "source" in result else ""
        print(f"  [OK] {source_name:<14} ({elapsed:.1f}s){extra}")
        print(f"       片名：{title}")
        print(f"       女優：{actress_str}")
        if "release" in result and result["release"]:
            print(f"       日期：{result['release']}")
        code_results[source_name] = "OK"
    else:
        print(f"  [--] {source_name:<14} ({elapsed:.1f}s) -> {result}")
        code_results[source_name] = "FAIL"


def main():
    os.system("cls")
    show_cth_banner()
    print("  AV 資料來源測試")
    print("  輕量來源（javscraper / r18.dev）+ Playwright 來源（javbus / javdb / javlibrary）\n")

    results_summary = {}

    for code in TEST_CODES:
        print(f"{'─'*60}")
        print(f"  番號：{code}")
        print(f"{'─'*60}")
        code_results = {}

        # 輕量來源（不需要 Playwright）
        for source_name, test_fn in LIGHT_SOURCES:
            print(f"  查詢 {source_name}...", end="", flush=True)
            success, result, elapsed = test_fn(code)
            print("\r", end="")
            _print_result(source_name, success, result, elapsed, code_results)
            time.sleep(0.5)

        # Playwright 來源
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for source_name, test_fn in PW_SOURCES:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    locale="ja-JP",
                    viewport={"width": 1280, "height": 800},
                )
                page = context.new_page()
                print(f"  查詢 {source_name}...", end="", flush=True)
                success, result, elapsed = test_fn(page, code)
                context.close()
                print("\r", end="")
                _print_result(source_name, success, result, elapsed, code_results)
            browser.close()

        results_summary[code] = code_results
        print()

    # 總覽
    all_sources = ALL_SOURCE_NAMES
    print(f"{'═'*60}")
    print("  結果總覽")
    print(f"{'─'*60}")
    header = f"  {'番號':<12}" + "".join(f"  {s:<16}" for s in all_sources)
    print(header)
    for code, res in results_summary.items():
        row = f"  {code:<12}"
        for src in all_sources:
            status = "[OK]" if res.get(src) == "OK" else "[--]"
            row += f"  {status:<16}"
        print(row)
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
