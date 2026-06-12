import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout

NO_DATA_TTL_DAYS = 7  # 與 fetcher.NO_DATA_TTL_DAYS 保持一致


def _load_json(path: str) -> dict:
    p = Path(path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_json(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class LookupEnricher:
    def __init__(self, lookup_file: str, cache_file: str):
        self.lookup_file = lookup_file
        self.cache_file = cache_file
        self.lookup: dict = _load_json(lookup_file)
        self.cache: dict = _load_json(cache_file)

    def _save_lookup(self) -> None:
        _save_json(self.lookup_file, self.lookup)

    def merge_dict(self, data: dict) -> int:
        count = 0
        for code, entry in data.items():
            if code not in self.lookup:
                self.lookup[code] = {
                    "title": entry.get("title", ""),
                    "actresses": entry.get("actresses", []),
                }
                count += 1
        self._save_lookup()
        return count

    def scrape_new_releases(self, fetcher, stop_after_known: int = 50,
                            max_pages: int = 10, progress_cb=None, pause_event=None) -> int:
        new_entries = 0
        consecutive_known = 0

        for page_num in range(1, max_pages + 1):
            if pause_event and pause_event.is_set():
                if progress_cb:
                    progress_cb("⏸ 手動暫停")
                break

            items = self._fetch_listing_page(fetcher, page_num, progress_cb)
            if not items:
                break

            page_new = 0
            for code, title in items:
                if code in self.lookup:
                    consecutive_known += 1
                    if consecutive_known >= stop_after_known:
                        self._save_lookup()
                        if progress_cb:
                            progress_cb(f"連續 {stop_after_known} 筆已知，停止追新，新增 {new_entries} 筆")
                        return new_entries
                else:
                    consecutive_known = 0
                    self.lookup[code] = {"title": title, "actresses": [], "partial": True}
                    new_entries += 1
                    page_new += 1

            self._save_lookup()
            if progress_cb:
                progress_cb(f"頁 {page_num}: +{page_new} 新番號（累計 {new_entries}）")
            time.sleep(random.uniform(3.0, 8.0))

        return new_entries

    def retry_no_data(self, fetcher, max_retries: int = 50, progress_cb=None) -> int:
        to_retry = []
        for code, entry in self.cache.items():
            if code.startswith("_") or not isinstance(entry, dict):
                continue
            if not entry.get("no_data"):
                continue
            try:
                age = datetime.now() - datetime.fromisoformat(entry["queried_at"])
                if age >= timedelta(days=NO_DATA_TTL_DAYS):
                    to_retry.append(code)
            except Exception:
                to_retry.append(code)

        recovered = 0
        for code in to_retry[:max_retries]:
            result = fetcher._query_javdb(code)
            if result:
                self.lookup[code] = {"title": result["title"], "actresses": result["actresses"]}
                fetcher.cache[code] = result
                self.cache[code] = result  # keep in sync
                recovered += 1
                if progress_cb:
                    progress_cb(f"補回: {code} → {result['title']}")
            else:
                reset_entry = {"no_data": True, "queried_at": datetime.now().isoformat()}
                fetcher.cache[code] = reset_entry
                self.cache[code] = reset_entry  # keep enricher.cache in sync
            time.sleep(random.uniform(1.0, 2.0))

        self._save_lookup()
        fetcher._save_cache()
        if progress_cb:
            progress_cb(f"retry 完成：{recovered}/{len(to_retry)} 筆補回")
        return recovered

    def scrape_listing_pages(self, fetcher, start_page: int = 1,
                             max_pages: int = 100, progress_cb=None,
                             pause_event=None, prev_last_page: int = 0) -> tuple[int, int]:
        new_entries = 0
        last_page = start_page - 1
        consecutive_zero_new = 0
        ZERO_PAUSE_THRESHOLD = 2
        prev_codes: set | None = None  # 上一頁的番號集合，用於重複頁偵測

        for i, page_num in enumerate(range(start_page, start_page + max_pages)):
            if pause_event and pause_event.is_set():
                if progress_cb:
                    progress_cb("⏸ 手動暫停")
                break

            if i > 0 and i % 100 == 0:
                fetcher.stop()
                fetcher.start()

            items = self._fetch_listing_page(fetcher, page_num, progress_cb)
            if not items:
                break

            # 偵測相鄰頁內容完全相同（session 失效時所有頁都回傳第 1 頁）
            curr_codes = {code for code, _ in items}
            if prev_codes is not None and curr_codes == prev_codes:
                self._save_lookup()
                if progress_cb:
                    progress_cb(
                        f"⚠ 頁 {page_num} 與頁 {page_num - 1} 番號完全相同（{len(curr_codes)} 筆），"
                        f"session 可能已失效，已自動暫停。上次成功停在第 {last_page} 頁。"
                    )
                if pause_event:
                    pause_event.set()
                return new_entries, last_page
            prev_codes = curr_codes

            page_new = 0
            for code, title in items:
                if code not in self.lookup:
                    self.lookup[code] = {"title": title, "actresses": [], "partial": True}
                    new_entries += 1
                    page_new += 1

            # 只在「新區域」（超過上次停止頁）才偵測連續零新增
            if page_num > prev_last_page:
                if page_new == 0:
                    consecutive_zero_new += 1
                    if consecutive_zero_new >= ZERO_PAUSE_THRESHOLD:
                        self._save_lookup()
                        if progress_cb:
                            progress_cb(
                                f"⚠ 連續 {ZERO_PAUSE_THRESHOLD} 頁無新增"
                                f"（頁 {page_num - consecutive_zero_new + 1}–{page_num}），"
                                f"疑似 session 失效，已自動暫停。"
                                f"上次成功停在第 {last_page} 頁。"
                            )
                        if pause_event:
                            pause_event.set()
                        return new_entries, last_page
                else:
                    consecutive_zero_new = 0

            self._save_lookup()
            last_page = page_num

            if progress_cb:
                progress_cb(f"頁 {page_num}: 找到 {len(items)} 筆，新增 {page_new}（累計 {new_entries}）")
            time.sleep(random.uniform(3.0, 8.0))

        return new_entries, last_page

    def _fetch_listing_page(self, fetcher, page_num: int,
                            progress_cb=None) -> list[tuple[str, str]]:
        page = fetcher._new_page()
        try:
            url = f"https://javdb.com/?page={page_num}"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)

            # 偵測 JavDB 分頁上限 redirect（如第 81 頁被導回第 80 頁）
            actual_url = page.url
            m = re.search(r"[?&]page=(\d+)", actual_url)
            actual_page_num = int(m.group(1)) if m else 1
            if actual_page_num != page_num:
                msg = (f"⚠ 頁 {page_num}: JavDB 重導至第 {actual_page_num} 頁，"
                       f"已到達分頁上限（最多 {actual_page_num} 頁）")
                print(msg)
                if progress_cb:
                    progress_cb(msg)
                return []

            try:
                page.wait_for_selector(".video-title", timeout=8000)
            except PWTimeout:
                page_title = page.title()
                msg = (f"[WARN] 頁 {page_num}: 找不到 .video-title（8s timeout）"
                       f" | 實際URL={actual_url} | 頁標題={page_title}")
                print(msg)
                if progress_cb:
                    progress_cb(msg)
                return []

            items = []
            for card in page.query_selector_all("div.item"):
                code_el = card.query_selector(".video-title strong")
                title_el = card.query_selector(".video-title")
                if not code_el or not title_el:
                    continue
                code = code_el.inner_text().strip()
                full_text = title_el.inner_text().strip()
                title = full_text.replace(code, "").strip()
                if code:
                    items.append((code, title))
            return items
        except Exception as e:
            msg = f"[ERROR] 頁 {page_num}: 例外 {e}"
            print(msg)
            if progress_cb:
                progress_cb(msg)
            return []
        finally:
            page.close()
