import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from playwright_stealth.stealth import Stealth
from renamer import strip_actress_suffix

JAVDB_BASE = "https://javdb.com"
NO_DATA_TTL_DAYS = 7


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


class Fetcher:
    def __init__(self, cache_file: str, lookup_file: str):
        self.cache_file  = cache_file
        self.lookup_file = lookup_file
        self.cache: dict  = _load_json(cache_file)
        self.gender_cache: dict = self.cache.get("_actors", {})
        self.lookup: dict = _load_json(lookup_file)

        # 把 cache 裡已成功的條目補進 lookup（首次遷移用）
        migrated = False
        for code, entry in self.cache.items():
            if code.startswith("_") or not isinstance(entry, dict):
                continue
            if not entry.get("no_data") and code not in self.lookup:
                self.lookup[code] = {"title": entry["title"], "actresses": entry["actresses"]}
                migrated = True
        if migrated:
            self._save_lookup()

        self._pw = None
        self._browser = None
        self._ctx = None

    def start(self) -> None:
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            viewport={"width": 1280, "height": 800},
        )
        cookies = [
            {"name": "over18", "value": "1", "domain": "javdb.com", "path": "/"},
            {"name": "locale",  "value": "ja",  "domain": "javdb.com", "path": "/"},
        ]
        session_file = Path("data/javdb_session.txt")
        if session_file.exists():
            session_val = session_file.read_text(encoding="utf-8").strip()
            if session_val:
                cookies.append({"name": "_jdb_session", "value": session_val, "domain": "javdb.com", "path": "/"})
        self._ctx.add_cookies(cookies)

    def stop(self) -> None:
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self._save_cache()

    def _save_cache(self) -> None:
        data = {k: v for k, v in self.cache.items() if not k.startswith("_")}
        data["_actors"] = self.gender_cache
        _save_json(self.cache_file, data)

    def _save_lookup(self) -> None:
        _save_json(self.lookup_file, self.lookup)

    def _new_page(self):
        page = self._ctx.new_page()
        Stealth().apply_stealth_sync(page)
        return page

    def query(self, code: str) -> dict | None:
        # 1. lookup 永久對照表（最優先，不過期）
        if code in self.lookup:
            entry = self.lookup[code]
            if entry.get("partial"):
                result = self._query_javdb(code)
                if result:
                    self.lookup[code] = {"title": result["title"], "actresses": result["actresses"]}
                    self._save_lookup()
                    self.cache[code] = result
                    self._save_cache()
                    return self.lookup[code]
                else:
                    # 確認找不到：移除 partial 旗標避免重複嘗試
                    self.lookup[code] = {"title": entry["title"], "actresses": []}
                    self._save_lookup()
            return self.lookup[code]

        # 2. 操作層快取（含 no_data TTL）
        if code in self.cache:
            cached = self.cache[code]
            if isinstance(cached, dict) and cached.get("no_data"):
                try:
                    age = datetime.now() - datetime.fromisoformat(cached["queried_at"])
                    if age < timedelta(days=NO_DATA_TTL_DAYS):
                        return None
                except Exception:
                    pass
            else:
                return cached

        # 3. 打 javdb
        result = self._query_javdb(code)
        time.sleep(random.uniform(1.0, 2.0))
        if result:
            self.cache[code] = result
            self.lookup[code] = {"title": result["title"], "actresses": result["actresses"]}
            self._save_lookup()
        else:
            self.cache[code] = {"no_data": True, "queried_at": datetime.now().isoformat()}
        self._save_cache()
        return result

    def _query_javdb(self, code: str) -> dict | None:
        page = self._new_page()
        try:
            url = f"{JAVDB_BASE}/search?q={code}&f=all"
            page.goto(url, wait_until="domcontentloaded", timeout=20000)

            try:
                page.wait_for_selector(".video-title", timeout=8000)
            except PWTimeout:
                return None

            result_link = None
            for item in page.query_selector_all(".video-title strong"):
                if code.upper() in item.inner_text().upper():
                    result_link = item.evaluate_handle(
                        "el => el.closest('a')"
                    ).as_element()
                    break
            if not result_link:
                result_link = page.query_selector("div.item a.box")
            if not result_link:
                return None

            result_link.click()
            page.wait_for_load_state("domcontentloaded", timeout=15000)

            return self._extract_movie_data(page, code)
        except Exception:
            return None
        finally:
            page.close()

    def _extract_movie_data(self, page, code: str) -> dict | None:
        title = ""
        orig_el = page.query_selector(".origin-title")
        if orig_el:
            title = orig_el.inner_text().strip()
        else:
            for sel in ["h2.title", ".title.is-4"]:
                el = page.query_selector(sel)
                if el:
                    t = el.inner_text().strip()
                    for noise in ["顯示原標題", "隱藏原標題"]:
                        t = t.replace(noise, "").strip()
                    if t.upper().startswith(code.upper()):
                        t = t[len(code):].strip()
                    title = t
                    break

        if not title:
            return None

        raw_actors = []
        for el in page.query_selector_all('.panel-block a[href*="/actors/"]'):
            href = el.get_attribute("href") or ""
            name = el.inner_text().strip()
            if name and href:
                raw_actors.append({"name": name, "href": href})

        actresses = self._filter_actresses(raw_actors)
        clean_title = strip_actress_suffix(title, actresses)

        return {
            "title": clean_title,
            "actresses": actresses,
            "queried_at": datetime.now().isoformat(),
        }

    def _filter_actresses(self, raw_actors: list) -> list:
        result = []
        for actor in raw_actors:
            gender = self._check_gender(actor["href"], actor["name"])
            if gender != "male":
                result.append(actor["name"])
        return result

    def _check_gender(self, actor_href: str, name: str) -> str:
        if actor_href in self.gender_cache:
            return self.gender_cache[actor_href]

        page = self._new_page()
        try:
            url = actor_href if actor_href.startswith("http") else f"{JAVDB_BASE}{actor_href}"
            page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # javdb actor page h2 format:
            #   male:   "{name}\n男優, {count} 部影片"
            #   female: "{name}\n{aliases}\n{count} 部影片"  (no gender label)
            gender = "unknown"
            h2 = page.query_selector("h2")
            if h2:
                text = h2.inner_text()
                if "男優" in text:
                    gender = "male"

            self.gender_cache[actor_href] = gender
            self._save_cache()
            return gender
        except Exception:
            self.gender_cache[actor_href] = "unknown"
            return "unknown"
        finally:
            page.close()
