import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import random
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
                            max_pages: int = 10, progress_cb=None) -> int:
        new_entries = 0
        consecutive_known = 0

        for page_num in range(1, max_pages + 1):
            items = self._fetch_listing_page(fetcher, page_num)
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
                             max_pages: int = 100, progress_cb=None) -> tuple[int, int]:
        new_entries = 0
        last_page = start_page - 1

        for i, page_num in enumerate(range(start_page, start_page + max_pages)):
            if i > 0 and i % 100 == 0:
                fetcher.stop()
                fetcher.start()

            items = self._fetch_listing_page(fetcher, page_num)
            if not items:
                break

            for code, title in items:
                if code not in self.lookup:
                    self.lookup[code] = {"title": title, "actresses": [], "partial": True}
                    new_entries += 1

            self._save_lookup()
            last_page = page_num

            if progress_cb:
                progress_cb(f"頁 {page_num}: 累計新增 {new_entries} 筆")
            time.sleep(random.uniform(3.0, 8.0))

        return new_entries, last_page

    def _fetch_listing_page(self, fetcher, page_num: int) -> list[tuple[str, str]]:
        page = fetcher._new_page()
        try:
            url = f"https://javdb.com/?page={page_num}"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            try:
                page.wait_for_selector(".video-title", timeout=8000)
            except PWTimeout:
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
        except Exception:
            return []
        finally:
            page.close()
