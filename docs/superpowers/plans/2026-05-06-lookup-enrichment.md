# Lookup Enrichment & Update Feature — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `enricher.py` 模組支援批量建庫與定期更新，並在 GUI 加入「更新資料庫」按鈕，讓 `data/javdb_lookup.json` 主動累積至 10 萬筆級別。

**Architecture:** `LookupEnricher` 處理所有批量操作；`fetcher.py` 的 `query()` 加一條 partial 自動補全邏輯；`scripts/bulk_enrich.py` 是開發端一次性建庫工具；GUI 的「更新資料庫」按鈕觸發追新番 + 補漏。

**Tech Stack:** Python 3.12, Playwright (Chromium), playwright-stealth, tkinter, pytest

**Branch:** `feature/lookup-enrichment`

---

## File Map

| 動作 | 檔案 | 說明 |
|------|------|------|
| Create | `enricher.py` | LookupEnricher 主類別 |
| Create | `test_enricher.py` | enricher 單元測試 |
| Create | `scripts/bulk_enrich.py` | 開發端初始建庫 CLI |
| Create | `scripts/README.md` | scripts 目錄說明 |
| Modify | `fetcher.py:93-121` | query() 新增 partial 自動補全 |
| Modify | `test_fetch.py` | 新增 partial 自動補全測試 |
| Modify | `config.py:6-13` | DEFAULT_CONFIG 加兩個新 key |
| Modify | `main.py` | 新增「資料庫」LabelFrame + 更新按鈕 |
| Modify | `.gitignore` | 加入 data/enrich_state.json |

---

## Task 1: .gitignore 更新

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 加入 enrich_state.json**

在 `.gitignore` 末尾加一行：

```
data/enrich_state.json
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore data/enrich_state.json"
```

---

## Task 2: config.py 新增預設值

**Files:**
- Modify: `config.py`

- [ ] **Step 1: 寫 failing test**

在 `test_fetch.py` 末尾加：

```python
import config

def test_config_has_update_stop_after_known():
    cfg = config.load()
    assert cfg["update_stop_after_known"] == 50

def test_config_has_update_max_new_release_pages():
    cfg = config.load()
    assert cfg["update_max_new_release_pages"] == 10
```

- [ ] **Step 2: 確認測試失敗**

```
venv\Scripts\python.exe -m pytest test_fetch.py::test_config_has_update_stop_after_known -v
```

Expected: `FAILED` with `KeyError`

- [ ] **Step 3: 加入 DEFAULT_CONFIG**

在 `config.py` 的 `DEFAULT_CONFIG` 末尾加兩行：

```python
DEFAULT_CONFIG = {
    "target_dir": "",
    "cache_file": "cache/javdb_cache.json",
    "lookup_file": "data/javdb_lookup.json",
    "processed_log": "processed_log.json",
    "skipped_log": "skipped.json",
    "format_order": ["code", "actress", "title"],
    "update_stop_after_known": 50,
    "update_max_new_release_pages": 10,
}
```

- [ ] **Step 4: 確認測試通過**

```
venv\Scripts\python.exe -m pytest test_fetch.py::test_config_has_update_stop_after_known test_fetch.py::test_config_has_update_max_new_release_pages -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add config.py test_fetch.py
git commit -m "feat: add update config defaults"
```

---

## Task 3: enricher.py — 骨架 + merge_dict

**Files:**
- Create: `enricher.py`
- Create: `test_enricher.py`

- [ ] **Step 1: 寫 failing tests**

建立 `test_enricher.py`：

```python
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from enricher import LookupEnricher


@pytest.fixture
def tmp_files(tmp_path):
    lookup = tmp_path / "lookup.json"
    cache = tmp_path / "cache.json"
    lookup.write_text("{}", encoding="utf-8")
    cache.write_text("{}", encoding="utf-8")
    return str(lookup), str(cache)


def test_merge_dict_adds_new_entries(tmp_files):
    lookup_file, cache_file = tmp_files
    enricher = LookupEnricher(lookup_file, cache_file)
    data = {
        "ABC-001": {"title": "テスト", "actresses": ["山田花子"]},
        "ABC-002": {"title": "テスト2", "actresses": []},
    }
    count = enricher.merge_dict(data)
    assert count == 2
    assert enricher.lookup["ABC-001"] == {"title": "テスト", "actresses": ["山田花子"]}
    assert enricher.lookup["ABC-002"] == {"title": "テスト2", "actresses": []}


def test_merge_dict_skips_existing(tmp_files):
    lookup_file, cache_file = tmp_files
    Path(lookup_file).write_text(
        json.dumps({"ABC-001": {"title": "既存", "actresses": ["既存女優"]}}),
        encoding="utf-8"
    )
    enricher = LookupEnricher(lookup_file, cache_file)
    count = enricher.merge_dict({"ABC-001": {"title": "上書き", "actresses": []}})
    assert count == 0
    assert enricher.lookup["ABC-001"]["title"] == "既存"


def test_merge_dict_persists_to_file(tmp_files):
    lookup_file, cache_file = tmp_files
    enricher = LookupEnricher(lookup_file, cache_file)
    enricher.merge_dict({"XYZ-001": {"title": "保存テスト", "actresses": []}})
    saved = json.loads(Path(lookup_file).read_text(encoding="utf-8"))
    assert "XYZ-001" in saved
```

- [ ] **Step 2: 確認測試失敗**

```
venv\Scripts\python.exe -m pytest test_enricher.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'enricher'`

- [ ] **Step 3: 建立 enricher.py 骨架**

```python
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

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
        raise NotImplementedError

    def retry_no_data(self, fetcher, progress_cb=None) -> int:
        raise NotImplementedError

    def scrape_listing_pages(self, fetcher, start_page: int = 1,
                             max_pages: int = 100, progress_cb=None) -> tuple[int, int]:
        raise NotImplementedError

    def _fetch_listing_page(self, fetcher, page_num: int) -> list[tuple[str, str]]:
        raise NotImplementedError
```

- [ ] **Step 4: 確認測試通過**

```
venv\Scripts\python.exe -m pytest test_enricher.py::test_merge_dict_adds_new_entries test_enricher.py::test_merge_dict_skips_existing test_enricher.py::test_merge_dict_persists_to_file -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add enricher.py test_enricher.py
git commit -m "feat: add LookupEnricher skeleton with merge_dict"
```

---

## Task 4: enricher.py — scrape_new_releases

**Files:**
- Modify: `enricher.py`
- Modify: `test_enricher.py`

- [ ] **Step 1: 寫 failing tests**

在 `test_enricher.py` 末尾加：

```python
from unittest.mock import patch


def test_scrape_new_releases_adds_new_entries(tmp_files):
    lookup_file, cache_file = tmp_files
    enricher = LookupEnricher(lookup_file, cache_file)
    mock_fetcher = MagicMock()

    call_count = [0]
    def mock_fetch(fetcher, page_num):
        call_count[0] += 1
        if page_num == 1:
            return [("NEW-001", "新作1"), ("NEW-002", "新作2")]
        return []

    enricher._fetch_listing_page = mock_fetch

    with patch("time.sleep"):
        result = enricher.scrape_new_releases(mock_fetcher, stop_after_known=50, max_pages=5)

    assert result == 2
    assert "NEW-001" in enricher.lookup
    assert enricher.lookup["NEW-001"]["partial"] is True


def test_scrape_new_releases_stops_on_consecutive_known(tmp_files):
    lookup_file, cache_file = tmp_files
    known = {f"KNOWN-{i:03d}": {"title": f"t{i}", "actresses": []} for i in range(60)}
    Path(lookup_file).write_text(json.dumps(known), encoding="utf-8")

    enricher = LookupEnricher(lookup_file, cache_file)
    mock_fetcher = MagicMock()
    page_calls = [0]

    def mock_fetch(fetcher, page_num):
        page_calls[0] += 1
        return [(f"KNOWN-{i:03d}", f"t{i}") for i in range(24)]

    enricher._fetch_listing_page = mock_fetch

    with patch("time.sleep"):
        result = enricher.scrape_new_releases(mock_fetcher, stop_after_known=50, max_pages=20)

    assert result == 0
    assert page_calls[0] <= 4  # 應在 50 筆連續已知後停止


def test_scrape_new_releases_respects_max_pages(tmp_files):
    lookup_file, cache_file = tmp_files
    enricher = LookupEnricher(lookup_file, cache_file)
    mock_fetcher = MagicMock()

    page_calls = [0]
    def mock_fetch(fetcher, page_num):
        page_calls[0] += 1
        return [(f"NEW-{page_num:02d}-{i:02d}", f"title") for i in range(5)]

    enricher._fetch_listing_page = mock_fetch

    with patch("time.sleep"):
        enricher.scrape_new_releases(mock_fetcher, stop_after_known=9999, max_pages=3)

    assert page_calls[0] == 3
```

- [ ] **Step 2: 確認測試失敗**

```
venv\Scripts\python.exe -m pytest test_enricher.py::test_scrape_new_releases_adds_new_entries -v
```

Expected: `FAILED` with `NotImplementedError`

- [ ] **Step 3: 實作 scrape_new_releases**

在 `enricher.py` 把 `scrape_new_releases` 的 `raise NotImplementedError` 換成：

```python
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
```

- [ ] **Step 4: 確認測試通過**

```
venv\Scripts\python.exe -m pytest test_enricher.py::test_scrape_new_releases_adds_new_entries test_enricher.py::test_scrape_new_releases_stops_on_consecutive_known test_enricher.py::test_scrape_new_releases_respects_max_pages -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add enricher.py test_enricher.py
git commit -m "feat: implement scrape_new_releases with stop condition"
```

---

## Task 5: enricher.py — retry_no_data

**Files:**
- Modify: `enricher.py`
- Modify: `test_enricher.py`

- [ ] **Step 1: 寫 failing tests**

在 `test_enricher.py` 末尾加：

```python
def test_retry_no_data_recovers_expired_entries(tmp_files):
    lookup_file, cache_file = tmp_files
    old_time = (datetime.now() - timedelta(days=8)).isoformat()
    cache_data = {"RETRY-001": {"no_data": True, "queried_at": old_time}}
    Path(cache_file).write_text(json.dumps(cache_data), encoding="utf-8")

    enricher = LookupEnricher(lookup_file, cache_file)
    mock_fetcher = MagicMock()
    mock_fetcher._query_javdb.return_value = {
        "title": "復活した作品",
        "actresses": ["回収女優"],
        "queried_at": datetime.now().isoformat(),
    }

    with patch("time.sleep"):
        recovered = enricher.retry_no_data(mock_fetcher)

    assert recovered == 1
    assert enricher.lookup["RETRY-001"]["title"] == "復活した作品"
    mock_fetcher._query_javdb.assert_called_once_with("RETRY-001")


def test_retry_no_data_skips_fresh_entries(tmp_files):
    lookup_file, cache_file = tmp_files
    cache_data = {"FRESH-001": {"no_data": True, "queried_at": datetime.now().isoformat()}}
    Path(cache_file).write_text(json.dumps(cache_data), encoding="utf-8")

    enricher = LookupEnricher(lookup_file, cache_file)
    mock_fetcher = MagicMock()

    with patch("time.sleep"):
        recovered = enricher.retry_no_data(mock_fetcher)

    assert recovered == 0
    mock_fetcher._query_javdb.assert_not_called()


def test_retry_no_data_resets_ttl_on_failure(tmp_files):
    lookup_file, cache_file = tmp_files
    old_time = (datetime.now() - timedelta(days=8)).isoformat()
    cache_data = {"STILL-GONE-001": {"no_data": True, "queried_at": old_time}}
    Path(cache_file).write_text(json.dumps(cache_data), encoding="utf-8")

    enricher = LookupEnricher(lookup_file, cache_file)
    mock_fetcher = MagicMock()
    mock_fetcher._query_javdb.return_value = None

    with patch("time.sleep"):
        recovered = enricher.retry_no_data(mock_fetcher)

    assert recovered == 0
    assert enricher.cache["STILL-GONE-001"]["no_data"] is True
    # TTL 重設：queried_at 應比舊值新
    assert enricher.cache["STILL-GONE-001"]["queried_at"] > old_time
```

在 `test_enricher.py` 頂部加 import（在現有 import 之後）：

```python
from datetime import datetime, timedelta
```

- [ ] **Step 2: 確認測試失敗**

```
venv\Scripts\python.exe -m pytest test_enricher.py::test_retry_no_data_recovers_expired_entries -v
```

Expected: `FAILED` with `NotImplementedError`

- [ ] **Step 3: 實作 retry_no_data**

在 `enricher.py` 把 `retry_no_data` 的 `raise NotImplementedError` 換成：

```python
def retry_no_data(self, fetcher, progress_cb=None) -> int:
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
    for code in to_retry:
        result = fetcher._query_javdb(code)
        if result:
            self.lookup[code] = {"title": result["title"], "actresses": result["actresses"]}
            fetcher.cache[code] = result  # 更新 fetcher 的 cache（由 fetcher._save_cache 存檔）
            recovered += 1
            if progress_cb:
                progress_cb(f"補回: {code} → {result['title']}")
        else:
            fetcher.cache[code] = {"no_data": True, "queried_at": datetime.now().isoformat()}
        time.sleep(random.uniform(1.0, 2.0))

    self._save_lookup()
    fetcher._save_cache()
    if progress_cb:
        progress_cb(f"retry 完成：{recovered}/{len(to_retry)} 筆補回")
    return recovered
```

- [ ] **Step 4: 確認測試通過**

```
venv\Scripts\python.exe -m pytest test_enricher.py::test_retry_no_data_recovers_expired_entries test_enricher.py::test_retry_no_data_skips_fresh_entries test_enricher.py::test_retry_no_data_resets_ttl_on_failure -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add enricher.py test_enricher.py
git commit -m "feat: implement retry_no_data"
```

---

## Task 6: enricher.py — _fetch_listing_page + scrape_listing_pages

**Files:**
- Modify: `enricher.py`
- Modify: `test_enricher.py`

- [ ] **Step 1: 寫 failing test**

在 `test_enricher.py` 末尾加：

```python
def test_scrape_listing_pages_uses_start_page_and_returns_count(tmp_files):
    lookup_file, cache_file = tmp_files
    enricher = LookupEnricher(lookup_file, cache_file)
    mock_fetcher = MagicMock()

    pages_visited = []
    def mock_fetch(fetcher, page_num):
        pages_visited.append(page_num)
        if page_num > 102:
            return []
        return [(f"CODE-{page_num}-{i}", f"title{i}") for i in range(3)]

    enricher._fetch_listing_page = mock_fetch

    with patch("time.sleep"):
        new_count, last_page = enricher.scrape_listing_pages(
            mock_fetcher, start_page=100, max_pages=5
        )

    assert pages_visited == [100, 101, 102, 103]  # 103 以後回空，停止
    assert new_count == 3 * 3  # 頁 100-102 各 3 筆
    assert last_page == 102
```

- [ ] **Step 2: 確認測試失敗**

```
venv\Scripts\python.exe -m pytest test_enricher.py::test_scrape_listing_pages_uses_start_page_and_returns_count -v
```

Expected: `FAILED` with `NotImplementedError`

- [ ] **Step 3: 實作 _fetch_listing_page**

在 `enricher.py` 把 `_fetch_listing_page` 的 `raise NotImplementedError` 換成：

```python
def _fetch_listing_page(self, fetcher, page_num: int) -> list[tuple[str, str]]:
    from playwright.sync_api import TimeoutError as PWTimeout

    page = fetcher._new_page()
    try:
        url = f"https://javdb.com/videos?page={page_num}"
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
```

- [ ] **Step 4: 實作 scrape_listing_pages**

在 `enricher.py` 把 `scrape_listing_pages` 的 `raise NotImplementedError` 換成：

```python
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
```

- [ ] **Step 5: 確認測試通過**

```
venv\Scripts\python.exe -m pytest test_enricher.py -v
```

Expected: 全部 passed（目前所有 enricher 測試）

- [ ] **Step 6: Commit**

```bash
git add enricher.py test_enricher.py
git commit -m "feat: implement scrape_listing_pages and _fetch_listing_page"
```

---

## Task 7: fetcher.py — partial 自動補全

**Files:**
- Modify: `fetcher.py:93-121`
- Modify: `test_fetch.py`

- [ ] **Step 1: 寫 failing test**

在 `test_fetch.py` 末尾加：

```python
import json
from unittest.mock import MagicMock
from datetime import datetime

def test_query_auto_completes_partial_entry(tmp_path):
    lookup_file = tmp_path / "lookup.json"
    cache_file = tmp_path / "cache.json"
    lookup_file.write_text(
        json.dumps({"PARTIAL-001": {"title": "仮タイトル", "actresses": [], "partial": True}}),
        encoding="utf-8"
    )
    cache_file.write_text("{}", encoding="utf-8")

    fetcher = Fetcher(str(cache_file), str(lookup_file))
    fetcher._query_javdb = MagicMock(return_value={
        "title": "正式タイトル",
        "actresses": ["完全女優"],
        "queried_at": datetime.now().isoformat(),
    })

    result = fetcher.query("PARTIAL-001")

    fetcher._query_javdb.assert_called_once_with("PARTIAL-001")
    assert result["actresses"] == ["完全女優"]
    assert result["title"] == "正式タイトル"
    assert "partial" not in fetcher.lookup.get("PARTIAL-001", {})


def test_query_non_partial_entry_skips_network(tmp_path):
    lookup_file = tmp_path / "lookup.json"
    cache_file = tmp_path / "cache.json"
    lookup_file.write_text(
        json.dumps({"FULL-001": {"title": "完全作品", "actresses": ["既存女優"]}}),
        encoding="utf-8"
    )
    cache_file.write_text("{}", encoding="utf-8")

    fetcher = Fetcher(str(cache_file), str(lookup_file))
    fetcher._query_javdb = MagicMock()

    result = fetcher.query("FULL-001")

    fetcher._query_javdb.assert_not_called()
    assert result["title"] == "完全作品"
```

- [ ] **Step 2: 確認測試失敗**

```
venv\Scripts\python.exe -m pytest test_fetch.py::test_query_auto_completes_partial_entry -v
```

Expected: `FAILED`（partial 不會觸發 _query_javdb）

- [ ] **Step 3: 修改 fetcher.py 的 query() 方法**

把 `fetcher.py` 的 `query()` 方法（第 93 行起）改成：

```python
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
```

- [ ] **Step 4: 確認全部測試通過**

```
venv\Scripts\python.exe -m pytest test_fetch.py test_enricher.py -v
```

Expected: 全部 passed（原有 24 + 新增 tests）

- [ ] **Step 5: Commit**

```bash
git add fetcher.py test_fetch.py
git commit -m "feat: auto-complete partial lookup entries on query"
```

---

## Task 8: scripts/bulk_enrich.py + scripts/README.md

**Files:**
- Create: `scripts/bulk_enrich.py`
- Create: `scripts/README.md`

（此 task 為 CLI 工具，無自動化單元測試，執行 smoke test 驗證）

- [ ] **Step 1: 建立 scripts/ 目錄並寫 bulk_enrich.py**

```python
# scripts/bulk_enrich.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import argparse
import json

from fetcher import Fetcher
from enricher import LookupEnricher

LOOKUP_FILE = "data/javdb_lookup.json"
CACHE_FILE  = "cache/javdb_cache.json"
STATE_FILE  = "data/enrich_state.json"


def _load_state() -> dict:
    p = Path(STATE_FILE)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"last_page": 0, "total_imported": 0}


def _save_state(state: dict) -> None:
    p = Path(STATE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Bulk enrich javdb_lookup.json from listing pages")
    parser.add_argument("--max-pages", type=int, default=100,
                        help="本次最多爬幾頁（預設 100）")
    args = parser.parse_args()

    state = _load_state()
    start_page = state["last_page"] + 1
    print(f"從第 {start_page} 頁開始，最多爬 {args.max_pages} 頁")

    fetcher  = Fetcher(CACHE_FILE, LOOKUP_FILE)
    enricher = LookupEnricher(LOOKUP_FILE, CACHE_FILE)

    fetcher.start()
    try:
        new_count, last_page = enricher.scrape_listing_pages(
            fetcher,
            start_page=start_page,
            max_pages=args.max_pages,
            progress_cb=print,
        )
    finally:
        fetcher.stop()

    state["last_page"]      = last_page
    state["total_imported"] = state.get("total_imported", 0) + new_count
    _save_state(state)

    total = state["total_imported"]
    print(f"\n完成：本次 +{new_count} 筆，總計 {total} 筆，上次爬到第 {last_page} 頁")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 建立 scripts/README.md**

```markdown
# scripts/

開發與維護工具，不是應用程式主程式。

## Index

| 腳本 | 狀態 | 說明 |
|------|------|------|
| bulk_enrich.py | 使用中 | 初始建庫：爬 JavDB 列表頁批量填入 javdb_lookup.json |

## bulk_enrich.py

一次性開發端工具，用於建立完整的 `data/javdb_lookup.json`。

**用法：**
```bash
venv\Scripts\python.exe scripts/bulk_enrich.py --max-pages 500
```

支援斷點續跑：進度存在 `data/enrich_state.json`（已 gitignore）。
建議每天跑 300-500 頁（≈ 7200-12000 筆），分多天完成後再 commit lookup.json。
```

- [ ] **Step 3: Smoke test（確認腳本可啟動，不需真正爬網頁）**

```
venv\Scripts\python.exe scripts/bulk_enrich.py --help
```

Expected: 印出 usage 說明，無報錯

- [ ] **Step 4: Commit**

```bash
git add scripts/bulk_enrich.py scripts/README.md
git commit -m "feat: add bulk_enrich.py script with resume support"
```

---

## Task 9: main.py — 資料庫管理 UI

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 在 _build_ui() 中加入資料庫 LabelFrame**

在 `main.py` 的 `_build_ui()` 方法，找到：

```python
        self.root.columnconfigure(0, weight=1)
```

在此行**之前**插入：

```python
        # 資料庫管理
        frame_db = ttk.LabelFrame(self.root, text=" 資料庫 ", padding=8)
        frame_db.grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 8))
        self.btn_update_db = ttk.Button(
            frame_db, text="更新資料庫", command=self._update_db, width=18
        )
        self.btn_update_db.pack(anchor="w")

```

- [ ] **Step 2: 加入 _update_db 方法**

在 `main.py` 的 `_put` 方法（第 457 行）之前插入：

```python
    def _update_db(self):
        self.btn_update_db.config(state="disabled", text="更新中...")
        self._put("log", "開始更新資料庫...\n")

        cfg = self._cfg
        stop_known  = cfg.get("update_stop_after_known", 50)
        max_pages   = cfg.get("update_max_new_release_pages", 10)
        lookup_file = cfg.get("lookup_file", "data/javdb_lookup.json")
        cache_file  = cfg.get("cache_file", "cache/javdb_cache.json")

        def run():
            from fetcher import Fetcher
            from enricher import LookupEnricher

            fetcher  = Fetcher(cache_file, lookup_file)
            enricher = LookupEnricher(lookup_file, cache_file)

            fetcher.start()
            try:
                new = enricher.scrape_new_releases(
                    fetcher,
                    stop_after_known=stop_known,
                    max_pages=max_pages,
                    progress_cb=lambda msg: self.msg_queue.put(("log", msg + "\n")),
                )
                recovered = enricher.retry_no_data(
                    fetcher,
                    progress_cb=lambda msg: self.msg_queue.put(("log", msg + "\n")),
                )
                self.msg_queue.put(("log", f"更新完成：追新 +{new} 筆，補漏 +{recovered} 筆\n"))
            except Exception as e:
                self.msg_queue.put(("log", f"更新失敗：{e}\n"))
            finally:
                fetcher.stop()
                self.msg_queue.put(("db_done", None))

        threading.Thread(target=run, daemon=True).start()

```

- [ ] **Step 3: 在 _poll_queue 中處理 db_done 訊息**

在 `_poll_queue` 方法（第 460 行），找到：

```python
                elif msg_type == "error":
```

在此行**之前**插入：

```python
                elif msg_type == "db_done":
                    self.btn_update_db.config(state="normal", text="更新資料庫")
```

- [ ] **Step 4: 手動測試 GUI**

```
venv\Scripts\python.exe main.py
```

確認：
- 主視窗出現「資料庫」區塊與「更新資料庫」按鈕
- 點按鈕後按鈕變灰顯示「更新中...」
- log 區有進度輸出
- 完成後按鈕恢復（注意：實際爬網頁需約 30-60 秒）

- [ ] **Step 5: 全部測試確認**

```
venv\Scripts\python.exe -m pytest test_fetch.py test_enricher.py -v
```

Expected: 全部 passed

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "feat: add update database button to GUI"
```

---

## 完成後提醒

所有 task 完成後，回報以下資訊讓使用者決定是否 merge 回 main：

1. 執行 `venv\Scripts\python.exe -m pytest test_fetch.py test_enricher.py -v` 確認全綠
2. 手動測試 GUI 的「更新資料庫」按鈕
3. 手動跑一次 `venv\Scripts\python.exe scripts/bulk_enrich.py --max-pages 2` 確認腳本正常
4. 確認後提醒使用者：`git checkout main && git merge feature/lookup-enrichment`
