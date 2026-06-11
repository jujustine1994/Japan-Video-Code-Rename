# javlibrary_fetcher.py
import asyncio
import json
import threading
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from renamer import strip_actress_suffix

JAVLIB_BASE = "https://www.javlibrary.com"
_BROWSER_ARGS = ["--window-position=-32000,0", "--window-size=1280,800"]
_QUERY_DELAY = 2.0


class JavlibraryFetcher:
    def __init__(self, lookup_file: str, cache_file: str):  # cache_file: interface parity with Fetcher
        self._lookup_path = Path(lookup_file)
        self._lookup: dict = self._load_json(lookup_file)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._browser = None
        self._page = None
        self._ready = threading.Event()
        self._start_error: str | None = None

    # ── persistence ──────────────────────────────────────────────

    @staticmethod
    def _load_json(path: str) -> dict:
        p = Path(path)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_lookup(self) -> None:
        self._lookup_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lookup_path, "w", encoding="utf-8") as f:
            json.dump(self._lookup, f, ensure_ascii=False, indent=2)

    # ── public interface ──────────────────────────────────────────

    def start(self) -> bool:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        timed_out = not self._ready.wait(timeout=30)
        return self._start_error is None and not timed_out

    def query(self, code: str) -> dict | None:
        entry = self._lookup.get(code)
        if entry and not entry.get("partial"):
            return entry  # full entry, skip live query
        if self._start_error is not None or self._loop is None or not self._loop.is_running():
            return None
        future = asyncio.run_coroutine_threadsafe(self._query_async(code), self._loop)
        try:
            return future.result(timeout=90)
        except Exception:
            return None

    def stop(self) -> None:
        if self._browser and self._loop and self._loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
                future.result(timeout=10)
            except Exception:
                pass
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    # ── private async ─────────────────────────────────────────────

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._init_browser())
        self._loop.run_forever()

    async def _init_browser(self) -> None:
        try:
            import nodriver as uc
            self._browser = await uc.start(headless=False, browser_args=_BROWSER_ARGS)
            self._page = await self._browser.get(f"{JAVLIB_BASE}/ja/")
            ok = await self._wait_ready(self._page, timeout=30)
            if not ok:
                self._start_error = "Cloudflare challenge timeout at startup"
        except Exception as e:
            self._start_error = str(e)
        finally:
            self._ready.set()

    async def _shutdown(self) -> None:
        try:
            self._browser.stop()
        except Exception:
            pass

    @staticmethod
    async def _wait_ready(page, timeout: int = 30) -> bool:
        for _ in range(timeout // 2):
            title = await page.evaluate("document.title")
            if "請稍候" not in title and "Just a moment" not in title:
                return True
            await asyncio.sleep(2)
        return False

    async def _query_async(self, code: str) -> dict | None:
        try:
            search_url = f"{JAVLIB_BASE}/ja/vl_searchbyid.php?keyword={code}"
            await self._page.get(search_url)
            if not await self._wait_ready(self._page):
                return None

            html = await self._page.get_content()
            soup = BeautifulSoup(html, "lxml")
            result_el = soup.select_one("div.videos div.video a")
            if not result_el:
                return None

            video_url = urljoin(search_url, result_el["href"])
            await self._page.get(video_url)
            if not await self._wait_ready(self._page):
                return None

            html2 = await self._page.get_content()
            parsed = self._parse_video(html2, code)
            if parsed:
                self._lookup[code] = {"title": parsed["title"], "actresses": parsed["actresses"]}
                self._save_lookup()
                await asyncio.sleep(_QUERY_DELAY)
            return parsed
        except Exception:
            return None

    # ── parse (pure function, testable without browser) ──────────

    @staticmethod
    def _parse_video(html: str, code: str) -> dict | None:
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
