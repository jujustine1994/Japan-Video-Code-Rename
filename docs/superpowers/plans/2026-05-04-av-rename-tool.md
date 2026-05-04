# AV Code Rename Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows CLI tool that batch-queries javdb.com for AV file metadata, presents a rename preview, and executes all renames with a single confirmation.

**Architecture:** Five Python modules (`config`, `scanner`, `fetcher`, `renamer`, `main`) with a Windows BAT+PS1 launcher. `fetcher.py` uses Playwright headless Chromium with a local JSON cache. `main.py` orchestrates 4 phases and displays rich TUI output. Design spec at `docs/superpowers/specs/2026-05-04-av-rename-tool-design.md`.

**Tech Stack:** Python 3.10+, Playwright 1.40+, playwright-stealth 2.0+, rich, pytest, uv (package manager)

---

## File Map

| File | Responsibility |
|------|---------------|
| `config.py` | config.json 讀寫，首次設定路徑 |
| `scanner.py` | 掃描資料夾，提取番號，偵測多集，過濾已處理 |
| `fetcher.py` | javdb Playwright 爬蟲，性別過濾，快取 |
| `renamer.py` | 組成規範檔名，實際改名，寫 log |
| `main.py` | Phase 1-4 主流程，rich TUI 顯示 |
| `requirements.txt` | 套件清單 |
| `launcher.ps1` | 環境檢查、venv 建立、啟動 |
| `AV Code Rename 啟動器.bat` | 雙擊入口（呼叫 launcher.ps1）|
| `tests/test_scanner.py` | scanner 單元測試 |
| `tests/test_renamer.py` | renamer 單元測試 |
| `tests/test_config.py` | config 單元測試 |

---

## Task 1: 專案骨架 + 測試環境

**Files:**
- Create: `requirements.txt`
- Create: `tests/__init__.py`

- [ ] **Step 1: 建立 requirements.txt**

```text
playwright>=1.40.0
playwright-stealth>=2.0.0
beautifulsoup4
rich>=13.0.0
pytest
```

- [ ] **Step 2: 建立 tests/__init__.py（空檔）**

```python
```

- [ ] **Step 3: 安裝套件**

```bash
uv venv venv
uv pip install -r requirements.txt --python venv\Scripts\python.exe
```

- [ ] **Step 4: 安裝 Playwright Chromium**

```bash
venv\Scripts\python.exe -m playwright install chromium
```

- [ ] **Step 5: 確認 pytest 可執行**

```bash
venv\Scripts\python.exe -m pytest --version
```
Expected: `pytest X.X.X`

- [ ] **Step 6: Commit**

```bash
git init
git add requirements.txt tests/__init__.py
git commit -m "chore: project skeleton and test environment"
```

---

## Task 2: config.py — 設定讀寫

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_config.py
import json, os, tempfile
from pathlib import Path

def test_load_returns_default_when_no_file(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    cfg = config.load()
    assert cfg["target_dir"] == ""
    assert "cache_file" in cfg

def test_save_and_load_roundtrip(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    config.save({"target_dir": "D:\\Videos", "cache_file": "cache/c.json",
                 "processed_log": "p.json", "skipped_log": "s.json"})
    cfg = config.load()
    assert cfg["target_dir"] == "D:\\Videos"
```

- [ ] **Step 2: 確認測試失敗**

```bash
venv\Scripts\python.exe -m pytest tests/test_config.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 實作 config.py**

```python
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "target_dir": "",
    "cache_file": "cache/javdb_cache.json",
    "processed_log": "processed_log.json",
    "skipped_log": "skipped.json",
}

def load() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return DEFAULT_CONFIG.copy()

def save(cfg: dict) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: 確認測試通過**

```bash
venv\Scripts\python.exe -m pytest tests/test_config.py -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: config read/write module"
```

---

## Task 3: scanner.py — 番號提取 + 多集偵測

**Files:**
- Create: `scanner.py`
- Create: `tests/test_scanner.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_scanner.py
from scanner import extract_code, group_by_code

def test_standard_code():
    assert extract_code("DDT-435 吉田花.mp4") == "DDT-435"

def test_lowercase_code():
    assert extract_code("ddt435.mp4") == "DDT-435"

def test_spaced_code():
    assert extract_code("ddt 435 something.mp4") == "DDT-435"

def test_no_hyphen():
    assert extract_code("ddt428 MR.srt") == "DDT-428"

def test_no_code():
    assert extract_code("1002.mp4") is None

def test_gsc_no_digits():
    assert extract_code("GSC.mp4") is None

def test_multipart_grouping():
    files = ["DDT-153 -1.mp4", "DDT-153 2.mp4", "DDT-435.mp4"]
    groups = group_by_code(files)
    assert groups["DDT-153"] == ["DDT-153 -1.mp4", "DDT-153 2.mp4"]
    assert groups["DDT-435"] == ["DDT-435.mp4"]
```

- [ ] **Step 2: 確認測試失敗**

```bash
venv\Scripts\python.exe -m pytest tests/test_scanner.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 實作 scanner.py**

```python
import re
import json
from pathlib import Path
from collections import defaultdict

SUPPORTED_EXTS = {".mp4", ".webm", ".srt"}
# 標準番號：DDT-435, GTJ-065（大小寫不限）
_CODE_RE = re.compile(r"([A-Za-z]{2,10})-(\d{2,5})")
# 無連字號：ddt435, ddt 435, ddt_435
_CODE_NOHYPHEN_RE = re.compile(r"([A-Za-z]{2,10})[\s_-]?(\d{3,5})")


def extract_code(filename: str) -> str | None:
    stem = Path(filename).stem
    # 優先嘗試標準格式
    m = _CODE_RE.search(stem)
    if m:
        return f"{m.group(1).upper()}-{m.group(2)}"
    # 容錯：無連字號，數字至少3位避免誤判
    m = _CODE_NOHYPHEN_RE.search(stem)
    if m:
        return f"{m.group(1).upper()}-{m.group(2)}"
    return None


def load_processed_log(log_file: str) -> set:
    path = Path(log_file)
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return set(json.load(f).keys())


def scan(target_dir: str, processed_log_file: str) -> tuple[list[Path], list[Path]]:
    """
    Returns (to_process, skipped_already_done).
    to_process: 未處理的支援格式檔案（含 .srt）
    """
    processed = load_processed_log(processed_log_file)
    to_process = []
    for f in Path(target_dir).iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in SUPPORTED_EXTS:
            continue
        if f.name in processed:
            continue
        to_process.append(f)
    return to_process


def group_by_code(filenames: list[str]) -> dict[str, list[str]]:
    """Group filenames by extracted code. Multi-part files get grouped together."""
    groups: dict[str, list[str]] = defaultdict(list)
    for name in filenames:
        code = extract_code(name)
        if code:
            groups[code].append(name)
    return dict(groups)
```

- [ ] **Step 4: 確認測試通過**

```bash
venv\Scripts\python.exe -m pytest tests/test_scanner.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scanner.py tests/test_scanner.py
git commit -m "feat: scanner - code extraction and file grouping"
```

---

## Task 4: renamer.py — 檔名組成 + 改名 + Log

**Files:**
- Create: `renamer.py`
- Create: `tests/test_renamer.py`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_renamer.py
from renamer import build_filename, strip_actress_suffix, sanitize

def test_build_single():
    r = build_filename("DDT-435", ["吉田花"], "解禁アナル・FUCK", ".mp4")
    assert r == "DDT-435 吉田花 - 解禁アナル・FUCK 吉田花.mp4"

def test_build_multi_actress():
    r = build_filename("DDT-406", ["美咲結衣", "結城みさ"], "義母・フィスト奴隷", ".mp4")
    assert r == "DDT-406 美咲結衣 結城みさ - 義母・フィスト奴隷 美咲結衣 結城みさ.mp4"

def test_build_with_part():
    r = build_filename("DDT-153", ["橘未稀"], "拘束椅子トランス", ".mp4", part=2)
    assert r == "DDT-153 橘未稀 - 拘束椅子トランス 橘未稀(2).mp4"

def test_build_unknown_actress():
    r = build_filename("DDT-518", [], "TOHJIRO全集", ".mp4")
    assert r == "DDT-518 未知女優 - TOHJIRO全集 未知女優.mp4"

def test_strip_suffix():
    assert strip_actress_suffix("解禁アナル・FUCK 吉田花", ["吉田花"]) == "解禁アナル・FUCK"

def test_strip_no_match():
    # 片名中間出現女優名不應被移除
    assert strip_actress_suffix("TOHJIRO全集 Vol.15", ["吉田花"]) == "TOHJIRO全集 Vol.15"

def test_sanitize():
    assert sanitize('test<>:"/\\|?*file') == "testfile"
```

- [ ] **Step 2: 確認測試失敗**

```bash
venv\Scripts\python.exe -m pytest tests/test_renamer.py -v
```
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 實作 renamer.py**

```python
import re
import json
from datetime import datetime
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str) -> str:
    return _ILLEGAL.sub("", name).strip()


def strip_actress_suffix(title: str, actresses: list[str]) -> str:
    """Remove actress names javdb appends to the end of origin-title."""
    result = title.strip()
    for name in actresses:
        if name and result.endswith(name):
            result = result[: -len(name)].strip()
    return result


def build_filename(
    code: str,
    actresses: list[str],
    title: str,
    ext: str,
    part: int | None = None,
) -> str:
    actress_str = " ".join(actresses) if actresses else "未知女優"
    part_str = f"({part})" if part else ""
    name = f"{code} {actress_str} - {title} {actress_str}{part_str}{ext}"
    return sanitize(name)


def rename_file(src: Path, new_name: str) -> bool:
    dst = src.parent / new_name
    try:
        src.rename(dst)
        return True
    except OSError:
        return False


def write_processed_log(log_file: str, original: str, new_name: str) -> None:
    path = Path(log_file)
    data: dict = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    data[original] = {
        "new_filename": new_name,
        "renamed_at": datetime.now().isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_skipped_log(log_file: str, entries: list[dict]) -> None:
    path = Path(log_file)
    existing: list = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    existing.extend(entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: 確認測試通過**

```bash
venv\Scripts\python.exe -m pytest tests/test_renamer.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add renamer.py tests/test_renamer.py
git commit -m "feat: renamer - filename building, rename, log writing"
```

---

## Task 5: fetcher.py — javdb 爬蟲 + 快取

**Files:**
- Create: `fetcher.py`

> 注意：fetcher 依賴 Playwright 外部服務，不寫自動化測試。用 Task 7 的手動測試驗證。

- [ ] **Step 1: 建立 fetcher.py 骨架**

```python
# fetcher.py
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, TimeoutError as PWTimeout
from playwright_stealth.stealth import Stealth
from renamer import strip_actress_suffix

JAVDB_BASE = "https://javdb.com"
CACHE_VERSION = 1


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
```

- [ ] **Step 2: 實作 Fetcher 類別（瀏覽器生命週期）**

將以下程式碼追加到 `fetcher.py`（接在骨架後）：

```python
class Fetcher:
    def __init__(self, cache_file: str):
        self.cache_file = cache_file
        self.cache: dict = _load_json(cache_file)
        self.gender_cache: dict = self.cache.get("_actors", {})
        self._pw = None
        self._browser: Browser | None = None
        self._ctx: BrowserContext | None = None

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
        self._ctx.add_cookies([
            {"name": "over18", "value": "1", "domain": "javdb.com", "path": "/"},
            {"name": "locale",  "value": "ja",  "domain": "javdb.com", "path": "/"},
        ])

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

    def _new_page(self) -> Page:
        page = self._ctx.new_page()
        Stealth().apply_stealth_sync(page)
        return page
```

- [ ] **Step 3: 實作 query(code) 主查詢方法**

追加到 `fetcher.py`（Fetcher 類別內）：

```python
    def query(self, code: str) -> dict | None:
        """
        Returns {"title": str, "actresses": [str]} or None if not found.
        Checks cache first; queries javdb on miss.
        """
        if code in self.cache:
            return self.cache[code]

        result = self._query_javdb(code)
        if result:
            self.cache[code] = result
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

            # 找第一筆完全符合番號的結果
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
```

- [ ] **Step 4: 實作 _extract_movie_data 資料提取**

追加到 `fetcher.py`（Fetcher 類別內）：

```python
    def _extract_movie_data(self, page: Page, code: str) -> dict | None:
        # 日文原名
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

        # 演員清單（含男女，下一步過濾）
        raw_actors = []
        for el in page.query_selector_all('.panel-block a[href*="/actors/"]'):
            href = el.get_attribute("href") or ""
            name = el.inner_text().strip()
            if name and href:
                raw_actors.append({"name": name, "href": href})

        # 過濾女性演員
        actresses = self._filter_actresses(raw_actors)

        # 去掉 javdb 在 origin-title 末尾附加的女優名
        clean_title = strip_actress_suffix(title, [a for a in actresses])

        return {
            "title": clean_title,
            "actresses": actresses,
            "queried_at": datetime.now().isoformat(),
        }
```

- [ ] **Step 5: Commit**

```bash
git add fetcher.py
git commit -m "feat: fetcher - javdb scraping and cache"
```

---

## Task 6: fetcher.py — 性別過濾

**Files:**
- Modify: `fetcher.py` (追加 _filter_actresses + _check_gender)

- [ ] **Step 1: 追加性別過濾方法到 fetcher.py（Fetcher 類別內）**

```python
    def _filter_actresses(self, raw_actors: list[dict]) -> list[str]:
        """Keep only female performers."""
        result = []
        for actor in raw_actors:
            gender = self._check_gender(actor["href"], actor["name"])
            if gender != "male":      # unknown → include (conservative)
                result.append(actor["name"])
        return result

    def _check_gender(self, actor_href: str, name: str) -> str:
        """
        Returns "female", "male", or "unknown".
        Checks actor detail page on javdb for gender tag.
        Result cached in self.gender_cache.
        """
        if actor_href in self.gender_cache:
            return self.gender_cache[actor_href]

        page = self._new_page()
        try:
            url = actor_href if actor_href.startswith("http") else f"{JAVDB_BASE}{actor_href}"
            page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # javdb actor page: look for gender tag
            # Female: tag contains "女優" or similar
            # Male: tag contains "男優" or similar
            gender = "unknown"
            for tag_el in page.query_selector_all(".tags .tag, .actor-bio span"):
                text = tag_el.inner_text().strip()
                if "女優" in text or "female" in text.lower():
                    gender = "female"
                    break
                if "男優" in text or "male" in text.lower():
                    gender = "male"
                    break

            # Fallback: check page title / heading
            if gender == "unknown":
                heading = page.query_selector("h2, .actor-name")
                if heading:
                    # If page mentions 女優 anywhere in metadata section
                    meta = page.query_selector(".actor-bio, .meta")
                    if meta and "女優" in meta.inner_text():
                        gender = "female"

            self.gender_cache[actor_href] = gender
            self._save_cache()
            return gender
        except Exception:
            self.gender_cache[actor_href] = "unknown"
            return "unknown"
        finally:
            page.close()
```

- [ ] **Step 2: Commit**

```bash
git add fetcher.py
git commit -m "feat: fetcher - gender filtering for actresses"
```

---

## Task 7: main.py — 4 個 Phase + TUI

**Files:**
- Create: `main.py`

- [ ] **Step 1: 建立 main.py 骨架 + banner + config 啟動檢查**

```python
# main.py
import sys
import os
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

import config
import scanner
import renamer
from fetcher import Fetcher

console = Console()


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


def ensure_target_dir(cfg: dict) -> dict:
    """First-run: ask for target dir if not set or invalid."""
    while not cfg["target_dir"] or not Path(cfg["target_dir"]).is_dir():
        if cfg["target_dir"]:
            console.print(f"[red]路徑不存在：{cfg['target_dir']}[/red]")
        console.print("[cyan]請輸入目標資料夾路徑：[/cyan]", end=" ")
        path = input().strip().strip('"')
        if Path(path).is_dir():
            cfg["target_dir"] = path
            config.save(cfg)
            console.print(f"[green]已儲存路徑：{path}[/green]\n")
        else:
            console.print(f"[red]路徑不存在，請重新輸入。[/red]")
    return cfg
```

- [ ] **Step 2: 實作 Phase 1（掃描）**

追加到 `main.py`：

```python
def phase1_scan(cfg: dict) -> list[Path]:
    console.print("[bold cyan]Phase 1 — 掃描資料夾...[/bold cyan]")
    files = scanner.scan(cfg["target_dir"], cfg["processed_log"])
    console.print(f"  找到 [bold]{len(files)}[/bold] 個待處理檔案\n")
    return files
```

- [ ] **Step 3: 實作 Phase 2（批次查詢）**

追加到 `main.py`：

```python
def phase2_query(files: list[Path], cfg: dict) -> tuple[list[dict], list[dict]]:
    """
    Returns (can_rename, uncertain)
    can_rename: [{"file": Path, "code": str, "new_name": str, "part": int|None}]
    uncertain:  [{"file": Path, "reason": str}]
    """
    can_rename = []
    uncertain = []

    # 分離 srt 和影片
    videos = [f for f in files if f.suffix.lower() in {".mp4", ".webm"}]
    srts   = [f for f in files if f.suffix.lower() == ".srt"]

    # 偵測多集
    groups = scanner.group_by_code([f.name for f in videos])
    # 記錄哪些 code 有多集
    multipart_codes = {code for code, names in groups.items() if len(names) > 1}

    fetcher = Fetcher(cfg["cache_file"])
    fetcher.start()

    try:
        with Progress(
            SpinnerColumn(),
            BarColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("查詢 javdb 中...", total=len(videos))

            for f in videos:
                from scanner import extract_code
                code = extract_code(f.name)
                progress.update(task, description=f"查詢 {code or f.name[:30]}...")

                if not code:
                    uncertain.append({"file": f, "reason": "找不到番號"})
                    progress.advance(task)
                    continue

                data = fetcher.query(code)
                if not data:
                    uncertain.append({"file": f, "reason": "javdb 查無資料"})
                    progress.advance(task)
                    continue

                # 決定集數
                part = None
                if code in multipart_codes:
                    parts_list = sorted(groups[code])
                    part = parts_list.index(f.name) + 1

                new_name = renamer.build_filename(
                    code, data["actresses"], data["title"], f.suffix, part
                )
                can_rename.append({
                    "file": f, "code": code,
                    "new_name": new_name, "part": part,
                    "data": data,
                })
                progress.advance(task)

        # 處理 .srt：找對應 mp4 新名稱
        _process_srts(srts, can_rename, uncertain, fetcher)

    finally:
        fetcher.stop()

    return can_rename, uncertain


def _process_srts(
    srts: list[Path],
    can_rename: list[dict],
    uncertain: list[dict],
    fetcher: Fetcher,
) -> None:
    from scanner import extract_code
    mp4_codes = {item["code"]: item["new_name"] for item in can_rename}

    for srt in srts:
        code = extract_code(srt.name)
        if not code:
            uncertain.append({"file": srt, "reason": "找不到番號"})
            continue
        if code in mp4_codes:
            # 跟著同番號 mp4 的新名字改，換副檔名
            base = Path(mp4_codes[code]).stem
            can_rename.append({
                "file": srt, "code": code,
                "new_name": base + ".srt", "part": None, "data": {},
            })
        else:
            # fallback: 直接查 javdb
            data = fetcher.query(code)
            if data:
                new_name = renamer.build_filename(
                    code, data["actresses"], data["title"], ".srt"
                )
                can_rename.append({
                    "file": srt, "code": code,
                    "new_name": new_name, "part": None, "data": data,
                })
            else:
                uncertain.append({"file": srt, "reason": "javdb 查無資料"})
```

- [ ] **Step 4: 實作 Phase 3（審閱 + preview.txt）**

追加到 `main.py`：

```python
def phase3_review(can_rename: list[dict], uncertain: list[dict]) -> bool:
    """Display review list. Returns True if user confirms."""
    console.print()
    console.rule("[bold]審閱清單[/bold]")
    console.print(
        f"  [green]可更名：{len(can_rename)} 筆[/green]  "
        f"[yellow]不確定：{len(uncertain)} 筆[/yellow]  "
        f"共 {len(can_rename) + len(uncertain)} 筆\n"
    )

    # 可更名清單
    if can_rename:
        console.print("[green]── 可更名 ──[/green]")
        for i, item in enumerate(can_rename, 1):
            console.print(f"  [dim]{i:03d}[/dim]  {item['file'].name}")
            console.print(f"       [green]→ {item['new_name']}[/green]")
        console.print()

    # 不確定清單
    if uncertain:
        console.print("[yellow]── 不確定（維持原狀）──[/yellow]")
        for i, item in enumerate(uncertain, 1):
            idx = len(can_rename) + i
            console.print(
                f"  [dim]{idx:03d}[/dim]  {item['file'].name}  "
                f"[dim]({item['reason']})[/dim]"
            )
        console.print()

    # 輸出 preview.txt
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    preview_path = Path(f"preview_{ts}.txt")
    _write_preview(preview_path, can_rename, uncertain)
    console.print(f"[dim]審閱清單已儲存至 {preview_path}，可用記事本開啟[/dim]\n")

    console.rule()
    console.print(
        f"按 [bold green]Enter[/bold green] 確認更名 {len(can_rename)} 個檔案  "
        "[dim]|[/dim]  [bold red]Ctrl+C[/bold red] 取消"
    )
    try:
        input()
        return True
    except KeyboardInterrupt:
        console.print("\n[yellow]已取消。[/yellow]")
        return False


def _write_preview(path: Path, can_rename: list[dict], uncertain: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"AV Code Rename — 審閱清單\n")
        f.write(f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"可更名：{len(can_rename)} 筆  不確定：{len(uncertain)} 筆\n\n")
        f.write("── 可更名 ──\n")
        for i, item in enumerate(can_rename, 1):
            f.write(f"{i:03d}  {item['file'].name}\n")
            f.write(f"     → {item['new_name']}\n")
        f.write("\n── 不確定（維持原狀）──\n")
        for i, item in enumerate(uncertain, 1):
            f.write(f"{len(can_rename)+i:03d}  {item['file'].name}  ({item['reason']})\n")
```

- [ ] **Step 5: 實作 Phase 4（執行改名）**

追加到 `main.py`：

```python
def phase4_execute(can_rename: list[dict], uncertain: list[dict], cfg: dict) -> None:
    console.print("\n[bold cyan]執行更名中...[/bold cyan]")
    success = 0
    failed = []

    with Progress(BarColumn(), TextColumn("{task.completed}/{task.total}"),
                  console=console) as progress:
        task = progress.add_task("", total=len(can_rename))
        for item in can_rename:
            ok = renamer.rename_file(item["file"], item["new_name"])
            if ok:
                renamer.write_processed_log(
                    cfg["processed_log"], item["file"].name, item["new_name"]
                )
                success += 1
            else:
                failed.append(item["file"].name)
            progress.advance(task)

    # 寫 skipped log
    if uncertain:
        skipped_entries = [
            {
                "filename": item["file"].name,
                "reason": item["reason"],
                "skipped_at": datetime.now().isoformat(),
            }
            for item in uncertain
        ]
        renamer.write_skipped_log(cfg["skipped_log"], skipped_entries)

    # 顯示結果
    console.print()
    console.print(f"  [green]✓ 成功更名：{success} 個[/green]")
    if failed:
        console.print(f"  [red]✗ 失敗（被占用等）：{len(failed)} 個[/red]")
        for name in failed:
            console.print(f"      {name}")
    console.print(f"  [dim]─ 不確定，維持原狀：{len(uncertain)} 個[/dim]")
    if uncertain:
        console.print(f"  [dim]  （已記錄至 {cfg['skipped_log']}）[/dim]")
    console.print()
```

- [ ] **Step 6: 實作 main() 進入點**

追加到 `main.py`：

```python
def main():
    os.system("cls")
    show_cth_banner()

    cfg = config.load()

    # 首次執行 or 路徑設定
    console.print(f"[dim]目標資料夾：{cfg['target_dir'] or '（未設定）'}[/dim]")
    if cfg["target_dir"]:
        console.print("按 [bold]Enter[/bold] 開始掃描  [dim]|[/dim]  輸入 [bold]C[/bold] 更改資料夾")
        ans = input().strip().upper()
        if ans == "C":
            cfg["target_dir"] = ""
    cfg = ensure_target_dir(cfg)

    files = phase1_scan(cfg)
    if not files:
        console.print("[green]沒有待處理的檔案，全部已處理完畢。[/green]")
        input("\n按 Enter 關閉")
        return

    can_rename, uncertain = phase2_query(files, cfg)

    confirmed = phase3_review(can_rename, uncertain)
    if not confirmed:
        return

    phase4_execute(can_rename, uncertain, cfg)
    input("按 Enter 關閉")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: 手動測試主程式**

```bash
venv\Scripts\python.exe main.py
```

預期：
1. 顯示 CTH banner
2. 詢問或顯示目標資料夾
3. 掃描 + 進度條查詢
4. 顯示審閱清單 + 生成 preview_*.txt
5. 按 Enter 執行改名

- [ ] **Step 8: Commit**

```bash
git add main.py
git commit -m "feat: main - 4-phase TUI orchestration"
```

---

## Task 8: Windows 啟動器

**Files:**
- Create: `launcher.ps1`
- Create: `AV Code Rename 啟動器.bat`

> 建立啟動器前確認已讀 `windows-tool-pitfalls.md`（地雷一：BAT 不能有中文；地雷五：PS1 需補 UTF-8 BOM）。

- [ ] **Step 1: 建立 AV Code Rename 啟動器.bat（全英文）**

```bat
@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher.ps1"
```

- [ ] **Step 2: 建立 launcher.ps1**

```powershell
# AV Code Rename Launcher

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$host.UI.RawUI.WindowTitle = "AV Code Rename"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Clear-Host
Write-Host "[INFO] Starting AV Code Rename..." -ForegroundColor Green
Write-Host ""

# ======================================
# [1/3] 檢查 Python
# ======================================
Write-Host "[1/3] 檢查 Python 環境..." -ForegroundColor Cyan
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[WARNING] 未偵測到 Python，本程式需要 Python 才能執行。" -ForegroundColor Yellow
    $ans = Read-Host "是否要立即安裝 Python？[Y/n] - 直接按 Enter 代表同意"
    if ($ans -eq "" -or $ans -ieq "Y") {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Host "[INFO] 透過 winget 安裝 Python，請稍候..." -ForegroundColor Gray
            winget install --id Python.Python.3 -e --silent --accept-source-agreements --accept-package-agreements
        } else {
            Write-Host "[ERROR] 找不到 winget，請手動至 https://www.python.org/ 安裝後重新執行。" -ForegroundColor Red
            Read-Host "按 Enter 關閉"; exit 1
        }
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
        if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
            Write-Host "[INFO] 安裝完成，請關閉視窗後重新點兩下啟動檔。" -ForegroundColor Yellow
            Read-Host "按 Enter 關閉"; exit 0
        }
        Write-Host "[OK] Python 安裝完成。" -ForegroundColor Green
    } else {
        Write-Host "已取消。" -ForegroundColor Gray; Read-Host "按 Enter 關閉"; exit 1
    }
} else {
    $pyVer = python --version 2>&1
    Write-Host "[OK] $pyVer 已安裝。" -ForegroundColor Green
}

# ======================================
# [2/3] 檢查 uv
# ======================================
Write-Host "[2/3] 檢查 uv 套件管理工具..." -ForegroundColor Cyan
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[WARNING] 找不到 uv，正在安裝..." -ForegroundColor Yellow
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","User") + ";" + $env:PATH
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "[ERROR] uv 安裝失敗，請重新點兩下啟動檔。" -ForegroundColor Red
        Read-Host "按 Enter 關閉"; exit 1
    }
    Write-Host "[OK] uv 安裝完成。" -ForegroundColor Green
} else {
    $uvVer = uv --version
    Write-Host "[OK] $uvVer 已安裝。" -ForegroundColor Green
}

# ======================================
# [3/3] 虛擬環境 + 套件
# ======================================
Write-Host "[3/3] 檢查虛擬環境..." -ForegroundColor Cyan
if (-not (Test-Path "venv")) {
    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host "    AV Code Rename - 首次安裝說明" -ForegroundColor Cyan
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  接下來程式會自動幫你安裝以下東西：" -ForegroundColor White
    Write-Host ""
    Write-Host "    1. Python 虛擬環境（venv）" -ForegroundColor Yellow
    Write-Host "       讓這個工具有獨立乾淨的執行空間" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    2. Playwright + Chromium 瀏覽器（約 150MB）" -ForegroundColor Yellow
    Write-Host "       用來自動查詢 javdb.com 取得片名與演員資料" -ForegroundColor Gray
    Write-Host ""
    Write-Host "    3. rich（終端機美化套件）" -ForegroundColor Yellow
    Write-Host "       讓進度條和清單顯示更清楚" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  全程只需要一直按 Enter 同意即可。" -ForegroundColor Green
    Write-Host "  如果有任何疑問，可以把這段說明貼給 AI 詢問。" -ForegroundColor Green
    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host ""
    $ans = Read-Host "是否現在建立環境並安裝套件？[Y/n] - 直接按 Enter 代表同意"
    if ($ans -eq "" -or $ans -ieq "Y") {
        Write-Host "[INFO] 建立虛擬環境中..." -ForegroundColor Gray
        uv venv venv
        Write-Host "[INFO] 安裝套件中（Chromium 約需幾分鐘）..." -ForegroundColor Gray
        uv pip install -r requirements.txt --python venv\Scripts\python.exe
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] 套件安裝失敗，請確認網路後重新執行。" -ForegroundColor Red
            Read-Host "按 Enter 關閉"; exit 1
        }
        Write-Host "[INFO] 安裝 Playwright Chromium..." -ForegroundColor Gray
        venv\Scripts\python.exe -m playwright install chromium
        Write-Host "[OK] 安裝完成。" -ForegroundColor Green
    } else {
        Write-Host "已取消。" -ForegroundColor Gray; Read-Host "按 Enter 關閉"; exit 1
    }
} else {
    Write-Host "[OK] 虛擬環境已就緒，檢查套件..." -ForegroundColor Green
    $broken = Get-ChildItem "venv\Lib\site-packages" -Directory -Filter "*dist-info" -ErrorAction SilentlyContinue | Where-Object {
        -not (Test-Path (Join-Path $_.FullName "METADATA"))
    }
    foreach ($dir in $broken) {
        Write-Host "[INFO] 清理損壞套件：$($dir.Name)" -ForegroundColor Yellow
        Remove-Item -Recurse -Force $dir.FullName
    }
    uv pip install -r requirements.txt --python venv\Scripts\python.exe -q
}

. ".\venv\Scripts\Activate.ps1"

Write-Host ""
Write-Host "[START] 啟動中..." -ForegroundColor Green
Write-Host ""

python main.py
$exitCode = $LASTEXITCODE

if (Test-Path "__pycache__") { Remove-Item -Recurse -Force "__pycache__" }

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] 程式意外停止，請回報上方錯誤訊息。" -ForegroundColor Red
    Read-Host "按 Enter 關閉"
} else {
    Write-Host ""
    Write-Host "5 秒後自動關閉..." -ForegroundColor Gray
    Start-Sleep -Seconds 5
}
```

- [ ] **Step 3: 補 UTF-8 BOM 給 launcher.ps1（地雷五）**

```powershell
$c = Get-Content 'launcher.ps1' -Raw -Encoding UTF8
[System.IO.File]::WriteAllText((Resolve-Path 'launcher.ps1'), $c, [System.Text.UTF8Encoding]::new($true))
```

- [ ] **Step 4: 雙擊測試 AV Code Rename 啟動器.bat**

預期：視窗出現，顯示 Python/uv 檢查，首次安裝說明，最後啟動主程式。

- [ ] **Step 5: Commit**

```bash
git add launcher.ps1 "AV Code Rename 啟動器.bat"
git commit -m "feat: Windows launcher (BAT + PS1)"
```

---

## Task 9: 整合測試 + 文件更新

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `ARCHITECTURE.md`

- [ ] **Step 1: 全部測試執行**

```bash
venv\Scripts\python.exe -m pytest tests/ -v
```
Expected: 全部 pass（至少 16 個測試）

- [ ] **Step 2: 小批量端對端測試**

建立測試資料夾，複製 5-10 個真實檔案進去，設定 config.json 指向測試資料夾，執行主程式驗證完整流程。

- [ ] **Step 3: 更新 CHANGELOG.md**

將「未完成」欄位移至已完成，新增 2026-05-04 完成記錄。

- [ ] **Step 4: 更新 ARCHITECTURE.md**

將所有 `⏳ 未建` 改為 `✅ 完成`。

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete AV Code Rename tool - all phases implemented"
```
