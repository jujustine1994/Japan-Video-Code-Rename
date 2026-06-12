# AV Code Rename — TODO

---

## 待辦（新）

- [ ] **論壇介紹文**：請 AI 撰寫一篇可發布到 PTT/巴哈/Dcard/各論壇的介紹文，說明工具功能（批次重命名電腦內的「寶物」）、如何下載安裝、如何貢獻資料庫。語氣輕鬆符合論壇文化，附上 GitHub 連結。

---

### Task: 專案結構整理 Step 2 — 源碼搬進 src/

> **前置狀態**：Step 1（2026-06-12）已完成，MD 文件移至 `docs/`，舊測試移至 `tests/`。
> 源碼 `.py` 仍在根目錄，此 Task 為下一步整理。

#### 目標結構

```
root/
  AV Code Rename 啟動器.bat
  bulk_enrich_javlibrary.bat
  launcher.ps1
  README.md
  .gitignore
  requirements.txt
  src/                   ← 所有 .py 源碼 + config.json
  docs/                  ← 所有 MD 文件（已完成）
  tests/                 ← 所有測試（已完成）
  data/
  cache/
  scripts/
  workers/
```

#### 需搬移的檔案（8 個 .py + 1 個 .json）

| 檔案 | 搬到 |
|------|------|
| `main.py` | `src/main.py` |
| `config.py` | `src/config.py` |
| `config.json` | `src/config.json` |
| `scanner.py` | `src/scanner.py` |
| `renamer.py` | `src/renamer.py` |
| `fetcher.py` | `src/fetcher.py` |
| `enricher.py` | `src/enricher.py` |
| `javlibrary_fetcher.py` | `src/javlibrary_fetcher.py` |
| `community_sync.py` | `src/community_sync.py` |

#### 同步需更新的地方

1. **`launcher.ps1`**：`python main.py` → `python src/main.py`
2. **`scripts/bulk_enrich_javlibrary.py`**：`sys.path.insert(0, ...)` 已指向 parent，搬後仍需確認 `from renamer import` 路徑正確
3. **`tests/`**：目前 pytest 自動把根目錄加入 sys.path，搬到 `src/` 後需在 `conftest.py` 補 `sys.path.insert(0, "src")` 或改用 `pyproject.toml` 的 `pythonpath` 設定
4. **`config.py` 內的相對路徑**：`SCRIPT_DIR = Path(__file__).parent` 用法需確認搬後仍指向正確根目錄（`cache/`、`data/` 在根目錄，不在 `src/`）
5. **`main.py` 的 `SCRIPT_DIR`**：同上，搬進 `src/` 後 `Path(__file__).parent` 會指向 `src/`，需改為 `Path(__file__).parent.parent`

#### 注意事項

- 使用 `git mv` 保留 git 歷史
- 搬移完立刻跑 `pytest --ignore=scripts/` 確認 85 passed
- 搬移完立刻雙擊啟動器確認 GUI 正常啟動
- **不可一次性全部移動**，建議逐檔搬移並測試

---

### Task: bulk_enrich_javlibrary.py 完善（owner-only，有空再做）

> 現況：`scripts/bulk_enrich_javlibrary.py` 已可運作（2026-06-11 測試通過）。
> 以下為讓這個工具更好用的改善項目，優先度不高，有空再處理。

#### 啟動方式
- [x] **建立 BAT 啟動器** `bulk_enrich_javlibrary.bat`（完成 2026-06-12）
  - 雙擊即可啟動，不需手動開終端機
  - 視窗跑完後顯示「按任意鍵關閉」不自動消失（`pause`）
  - 範例：
    ```bat
    @echo off
    cd /d "%~dp0"
    call venv\Scripts\activate
    python scripts\bulk_enrich_javlibrary.py %*
    pause
    ```
  - 放在專案根目錄，同 `AV Code Rename 啟動器.bat`

#### 進度顯示
- [ ] **ETA 預估**：記錄每筆平均耗時，顯示「已完成 X 筆，預估剩餘 Y 分鐘」
  - 實作方式：記錄 `start_time`，每個 listing 頁後計算 `elapsed / pages_done * pages_remaining`
  - 顯示格式：`[P45] 💾 Checkpoint：3500 筆 | 本次 +45 | 速度 6.2 秒/筆 | 預估剩餘 3 小時 12 分`
- [ ] **總頁數預估**：第一次跑時若能偵測 javlibrary 的最後一頁頁碼，可顯示進度百分比
  - 研究方向：listing 頁底部分頁元件是否有總頁數資訊（HTML selector 待確認）

#### 爬取方向

- [ ] **改為從最後一頁往第 1 頁爬**：解決 `vl_newrelease.php` 新作品上架後頁碼往後推移的問題。新作只會出現在第 1 頁附近，高頁碼（舊作）穩定不變，適合斷點續跑。實作需要先解析第 1 頁的分頁 HTML 取得總頁數，再從 `last_page` 往 1 方向迭代。需要先確認 javlibrary pagination HTML 結構（selector 待確認）。

#### 可靠性
- [ ] **解析失敗自動重試**：每個 listing 頁結束後，將 `❌ 解析失敗` 的番號收集起來，在 checkpoint 後立即重試一次（換 URL 格式或等 3 秒再試）
  - 目前約 1–2/6 筆解析失敗，原因可能是部分作品頁面 HTML 結構不同（例如 VR 作品）
  - 重試仍失敗則記入 `data/enrich_failed.json` 供事後人工確認
- [ ] **CF re-challenge 偵測**：若 `_wait_ready` timeout（30 秒），目前是 `❌ CF timeout，跳過`。應改為等待更長時間（如 120 秒）後再繼續，避免夜間跑時卡死整個 session
- [ ] **網路中斷重連**：若 `page.get()` 拋出 exception，捕捉後等 10 秒再重試最多 3 次，避免短暫斷線就終止整個 session

#### 執行完成摘要
- [ ] **結束時輸出統計摘要**，並寫入 `data/enrich_javlibrary_report.txt`（每次覆蓋）：
  ```
  ── 建置摘要 ──────────────────────
  日期：2026-06-12 03:14
  爬取範圍：listing 頁 1–500
  新增筆數：9,832
  跳過（已有）：1,204
  解析失敗：87（見 data/enrich_failed.json）
  lookup 總筆數：11,036
  耗時：5 小時 22 分
  ──────────────────────────────────
  ```

- [x] **社群資料庫安全性審查**（完成 2026-06-10）
  - [x] **Worker 層**：番號格式 `^[A-Z]+-\d+$`、entries 1–1000、title ≤200 字元（workers/index.js）
  - [x] **GitHub Action 層**：body ≤100KB、entries 1–1000、title ≤200，validate_payload / filter_entries 函數化（.github/scripts/process_contribution.py）
  - [x] **Rate limit**：Workers RateLimit binding，10 req/60s per IP（workers/index.js + wrangler.jsonc），免費，不佔 WAF rule 配額
  - [x] **Issue body 大小**：100KB 上限保護已加入
  - [x] **資料汙染回復**：git history 為備份；`wrangler rollback` 可快速回退 Worker

---

## 社群資料庫計畫（新）

### 目標
預建 `javdb_lookup.json`（只含番號+片名，無女優名）打包進工具，讓用戶不需自己爬就能快速命名。女優名在用戶第一次查詢時由工具自動補入本地 lookup。

### 架構
```
用戶啟動工具
  ├─ lookup 有且非 partial → 直接用
  ├─ lookup 有但 partial   → 顯示片名，女優名補爬 javdb
  └─ lookup 沒有           → fallback：爬 javdb 個別番號頁
```

### Task: 批次建置基礎資料庫（javlibrary 方案）

> ⚠️ **此功能為工具擁有者（CTH）自用，不面向一般用戶。**
> 建置完成後將 `data/javdb_lookup.json` 打包進 GitHub Release，用戶透過社群同步下載即可。

> ✅ **可行性驗證完成（2026-06-11）**：
> - 方案：`nodriver`（pip 安裝）+ javlibrary.com listing 頁
> - Cloudflare 繞過：headless=False，啟動時解一次 challenge（約 6–10 秒），之後同 session 瀏覽不需重解
> - listing URL：`https://www.javlibrary.com/ja/vl_newrelease.php?page=N`，每頁 20 筆
> - 可抓欄位：番號（`#video_id .text`）、片名（`h3.post-title`）、女優名（`span.star a`）、製作商、日期
> - **不需要 session cookie**，無 javdb 的設計缺陷
> - 參考：`scripts/test_javlibrary_nodriver.py`

> **待實作**：`enricher.py` 新增 `scrape_javlibrary_listing_pages()`，用 nodriver 替代目前的 Playwright + javdb 方案。

- [x] 確認替代來源（javlibrary 可行性測試）
- [x] 實作 `scripts/bulk_enrich_javlibrary.py`（2026-06-11，完整版：番號 + 片名 + 女優名，斷點續跑）
- [x] 測試跑通（2026-06-11，3 頁 × 6 筆 = 17 筆，CF 自動解，checkpoint 正常）
- [ ] 跑全量建置（從 `vl_newrelease.php?page=1` 開始往後跑到無資料）
- [ ] 把 lookup.json 打包進 GitHub Release

### Task: GUI 提示文字
- [x] 在「資料庫」區塊加一行說明 label（完成 2026-06-10）

### Task: 社群協作
> ✅ **已以 GitHub Issues 流程取代 PR 流程**（完成 2026-06-10）
> App → Cloudflare Worker → GitHub Issue → GitHub Action → javdb_community.json
> 驗證、合併、push 全自動。無需用戶 fork 或 PR。

- [x] 設計貢獻格式（JSON payload，含 source/version/entries）
- [x] GUI 加「貢獻我的資料」按鈕（DatabaseManagerDialog 社群同步區塊）
- [x] GitHub Action 驗證（番號格式、append-only、格式 schema）
- [x] 決定流程：Issue 上傳（已實作）

### 說明：按鈕對應功能
| 按鈕 | 功能 |
|------|------|
| 更新資料庫 | `scrape_new_releases`：追最新幾頁，遇到已知番號停止 |
| 批次建置 | `scrape_listing_pages`：大量爬 listing 頁建基礎庫（同 bulk_enrich.py） |

---

# AV Code Rename — Implementation Plan: tkinter UI + 命名格式選擇

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將現有 rich TUI 全面改寫為 tkinter GUI，新增命名格式三元件排列功能，維持全自動批次改名流程。

**Architecture:** `main.py` 完整改寫為 `AVRenameApp` tkinter class，背景執行緒跑掃描+查詢，queue 回傳 UI 更新。`renamer.build_filename()` 新增 `format_order` 參數。`config.py` 新增 `format_order` 欄位。`fetcher.py`、`scanner.py` 不動。

**Tech Stack:** Python tkinter/ttk（內建）、rich 移除、現有 scanner/fetcher/renamer/config 模組

**Spec:** `docs/superpowers/specs/2026-05-05-tkinter-ui-naming-format-design.md`

---

## 修改範圍

| 檔案 | 動作 |
|---|---|
| `config.py` | 新增 `format_order` 至 DEFAULT_CONFIG |
| `renamer.py` | `build_filename()` 新增 `format_order` 參數 |
| `main.py` | 完整改寫為 tkinter ToolApp |
| `requirements.txt` | 移除 rich |
| `test_fetch.py` | 新增 `build_filename` 單元測試 |
| `ARCHITECTURE.md` | 更新流程說明 |
| `CHANGELOG.md` | 新增更新記錄 |

---

## Task 1: config.py — 新增 format_order 欄位

**Files:**
- Modify: `config.py:6-11`

- [x] **Step 1: 新增 format_order 至 DEFAULT_CONFIG**

```python
DEFAULT_CONFIG = {
    "target_dir": "",
    "cache_file": "cache/javdb_cache.json",
    "processed_log": "processed_log.json",
    "skipped_log": "skipped.json",
    "format_order": ["code", "actress", "title"],
}
```

- [x] **Step 2: 確認 load() 正常合併新欄位**

```
venv\Scripts\python.exe -c "import config; print(config.load())"
```

期待：輸出 dict 包含 `'format_order': ['code', 'actress', 'title']`

- [x] **Step 3: Commit**

```
git add config.py
git commit -m "feat: add format_order to config"
```

---

## Task 2: renamer.py — build_filename 支援 format_order

**Files:**
- Modify: `renamer.py:21-25`
- Modify: `test_fetch.py`

- [x] **Step 1: 在 test_fetch.py 頂部加入單元測試**

在 `import sys` 後、`CACHE_FILE = ...` 前加入：

```python
from renamer import build_filename

def test_build_filename_default():
    assert build_filename("GTJ-065", ["宮崎あや"], "串刺し拷問", ".mp4") == \
        "GTJ-065 宮崎あや - 串刺し拷問.mp4"

def test_build_filename_actress_last():
    assert build_filename("GTJ-065", ["宮崎あや"], "串刺し拷問", ".mp4",
                          format_order=["code", "title", "actress"]) == \
        "GTJ-065 - 串刺し拷問 宮崎あや.mp4"

def test_build_filename_actress_first():
    assert build_filename("GTJ-065", ["宮崎あや"], "串刺し拷問", ".mp4",
                          format_order=["actress", "code", "title"]) == \
        "宮崎あや GTJ-065 - 串刺し拷問.mp4"

def test_build_filename_title_first():
    assert build_filename("GTJ-065", ["宮崎あや"], "串刺し拷問", ".mp4",
                          format_order=["title", "code", "actress"]) == \
        "串刺し拷問 GTJ-065 宮崎あや.mp4"

def test_build_filename_with_part():
    assert build_filename("GTJ-065", ["宮崎あや"], "串刺し拷問", ".mp4",
                          part=1, format_order=["code", "actress", "title"]) == \
        "GTJ-065 宮崎あや - 串刺し拷問(1).mp4"
```

- [x] **Step 2: 跑測試確認失敗**

```
venv\Scripts\python.exe -m pytest test_fetch.py::test_build_filename_default -v
```

期待：FAILED（TypeError: unexpected keyword argument 'format_order'）

- [x] **Step 3: 改寫 build_filename（renamer.py:21-25）**

```python
def build_filename(code: str, actresses: list, title: str, ext: str,
                   part=None, format_order=None) -> str:
    if format_order is None:
        format_order = ["code", "actress", "title"]

    actress_str = " ".join(actresses) if actresses else "未知女優"
    part_str = f"({part})" if part else ""
    components = {"code": code, "actress": actress_str, "title": title}

    parts = []
    for i, key in enumerate(format_order):
        val = components[key]
        if key == "title" and i > 0:
            parts.append(f"- {val}")
        else:
            parts.append(val)

    return sanitize(f"{' '.join(parts)}{part_str}{ext}")
```

- [x] **Step 4: 跑測試確認全過**

```
venv\Scripts\python.exe -m pytest test_fetch.py -k "test_build_filename" -v
```

期待：5 passed

- [ ] **Step 5: Commit**

```
git add renamer.py test_fetch.py
git commit -m "feat: build_filename supports format_order"
```

---

## Task 3: main.py — 完整改寫為 tkinter

**Files:**
- Rewrite: `main.py`

- [x] **Step 1: 完整替換 main.py**

```python
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from pathlib import Path

import config
from scanner import scan, extract_code
from fetcher import Fetcher
from renamer import build_filename, rename_file, write_processed_log

SCRIPT_DIR = Path(__file__).parent
LABELS = {"code": "番號", "actress": "女優名", "title": "片名"}
KEYS = {"番號": "code", "女優名": "actress", "片名": "title"}


class AVRenameApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AV Code Rename")
        self.root.resizable(False, False)

        self.msg_queue: queue.Queue = queue.Queue()
        self._pending: list = []   # (Path, str)
        self._skipped: list = []   # (str, str)

        self._cfg = config.load()
        self._format_order: list = self._cfg.get("format_order", ["code", "actress", "title"])

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}

        # 目標資料夾
        frame_dir = ttk.LabelFrame(self.root, text=" 目標資料夾 ", padding=8)
        frame_dir.grid(row=0, column=0, sticky="ew", **pad)
        frame_dir.columnconfigure(0, weight=1)
        self.dir_var = tk.StringVar(value=self._cfg.get("target_dir", ""))
        ttk.Entry(frame_dir, textvariable=self.dir_var, width=52).grid(row=0, column=0, sticky="ew")
        ttk.Button(frame_dir, text="瀏覽", command=self._browse).grid(row=0, column=1, padx=(6, 0))

        # 命名格式
        frame_fmt = ttk.LabelFrame(self.root, text=" 命名格式順序 ", padding=8)
        frame_fmt.grid(row=1, column=0, sticky="ew", **pad)
        self.fmt_list = tk.Listbox(frame_fmt, height=3, selectmode="single",
                                   width=16, font=("", 10))
        for key in self._format_order:
            self.fmt_list.insert("end", LABELS[key])
        self.fmt_list.grid(row=0, column=0, rowspan=2, sticky="ns")
        self.fmt_list.selection_set(0)
        ttk.Button(frame_fmt, text="↑", width=4, command=self._move_up).grid(
            row=0, column=1, padx=8, pady=(4, 2))
        ttk.Button(frame_fmt, text="↓", width=4, command=self._move_down).grid(
            row=1, column=1, padx=8, pady=(2, 4))

        # 開始按鈕
        frame_btn = tk.Frame(self.root)
        frame_btn.grid(row=2, column=0, pady=6)
        self.btn_start = ttk.Button(frame_btn, text="▶  開始掃描",
                                    command=self._start, width=22)
        self.btn_start.pack(ipady=6)

        # 進度
        frame_prog = ttk.LabelFrame(self.root, text=" 處理進度 ", padding=8)
        frame_prog.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 6))
        self.lbl_progress = ttk.Label(frame_prog, text="等待開始...")
        self.lbl_progress.pack(anchor="w")
        self.progress_bar = ttk.Progressbar(frame_prog, mode="indeterminate", length=420)
        self.progress_bar.pack(fill="x", pady=(4, 8))
        self.log_text = scrolledtext.ScrolledText(
            frame_prog, width=62, height=16, state="disabled", font=("Consolas", 9)
        )
        self.log_text.pack(fill="x")

        # 確認/取消（初始隱藏）
        self.frame_confirm = tk.Frame(self.root)
        self.frame_confirm.grid(row=4, column=0, pady=(0, 12))
        self.btn_confirm = ttk.Button(self.frame_confirm, text="✔  確認改名",
                                      command=self._confirm, width=18)
        self.btn_cancel = ttk.Button(self.frame_confirm, text="✖  取消",
                                     command=self._cancel, width=12)

        self.root.columnconfigure(0, weight=1)

    def _browse(self):
        d = filedialog.askdirectory()
        if d:
            self.dir_var.set(d)

    def _move_up(self):
        sel = self.fmt_list.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        val = self.fmt_list.get(i)
        self.fmt_list.delete(i)
        self.fmt_list.insert(i - 1, val)
        self.fmt_list.selection_set(i - 1)
        self._save_fmt()

    def _move_down(self):
        sel = self.fmt_list.curselection()
        if not sel or sel[0] == self.fmt_list.size() - 1:
            return
        i = sel[0]
        val = self.fmt_list.get(i)
        self.fmt_list.delete(i)
        self.fmt_list.insert(i + 1, val)
        self.fmt_list.selection_set(i + 1)
        self._save_fmt()

    def _save_fmt(self):
        self._format_order = [KEYS[self.fmt_list.get(i)]
                               for i in range(self.fmt_list.size())]
        cfg = config.load()
        cfg["format_order"] = self._format_order
        config.save(cfg)

    def _start(self):
        target_dir = self.dir_var.get().strip()
        if not os.path.isdir(target_dir):
            messagebox.showerror("錯誤", "請選擇有效的目標資料夾")
            return
        cfg = config.load()
        cfg["target_dir"] = target_dir
        cfg["format_order"] = self._format_order
        config.save(cfg)

        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self.btn_confirm.pack_forget()
        self.btn_cancel.pack_forget()
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(10)
        self.lbl_progress.config(text="掃描中...")
        self.btn_start.config(state="disabled")
        self._pending = []
        self._skipped = []

        threading.Thread(target=self._worker, args=(target_dir,), daemon=True).start()

    def _worker(self, target_dir: str):
        try:
            cfg = config.load()
            log_file = str(SCRIPT_DIR / cfg["processed_log"])
            cache_file = str(SCRIPT_DIR / cfg["cache_file"])

            files = scan(target_dir, log_file)
            self._put("log", f"掃描完成，找到 {len(files)} 個待處理檔案\n")

            if not files:
                self._put("done_query", None)
                return

            self._put("switch_progress", len(files))
            fetcher = Fetcher(cache_file)
            fetcher.start()
            try:
                for i, f in enumerate(files, 1):
                    code = extract_code(f.name)
                    self._put("progress", (i, len(files), f"查詢中 {i}/{len(files)}"))
                    if not code:
                        self._skipped.append((f.name, "無法辨識番號"))
                        self._put("log", f"⚠ {f.name}\n  → 無法辨識番號\n")
                        continue
                    result = fetcher.query(code)
                    if not result:
                        self._skipped.append((f.name, "javdb 查無資料"))
                        self._put("log", f"⚠ {f.name}\n  → javdb 查無資料\n")
                        continue
                    new_name = build_filename(
                        code, result["actresses"], result["title"],
                        f.suffix, format_order=self._format_order
                    )
                    self._pending.append((f, new_name))
                    self._put("log", f"✓ {f.name}\n  → {new_name}\n")
            finally:
                fetcher.stop()
            self._put("done_query", None)
        except Exception as e:
            self._put("log", f"\n[ERROR] {e}\n")
            self._put("error", str(e))

    def _confirm(self):
        self.btn_confirm.config(state="disabled")
        self.btn_cancel.config(state="disabled")
        threading.Thread(target=self._do_rename, daemon=True).start()

    def _cancel(self):
        self.btn_confirm.pack_forget()
        self.btn_cancel.pack_forget()
        self.btn_start.config(state="normal")
        self.lbl_progress.config(text="已取消")
        self._put("log", "已取消，未執行任何改名。\n")

    def _do_rename(self):
        cfg = config.load()
        log_file = str(SCRIPT_DIR / cfg["processed_log"])
        skipped_file = str(SCRIPT_DIR / cfg["skipped_log"])
        success = fail = 0
        for src, new_name in self._pending:
            if rename_file(src, new_name):
                write_processed_log(log_file, src.name, new_name)
                success += 1
            else:
                fail += 1
                self._put("log", f"✗ 改名失敗: {src.name}\n")
        if self._skipped:
            sk_path = Path(skipped_file)
            existing = {}
            if sk_path.exists():
                with open(sk_path, encoding="utf-8") as f:
                    existing = json.load(f)
            for fname, reason in self._skipped:
                existing[fname] = reason
            with open(sk_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        self._put("done_rename", (success, fail, len(self._skipped)))

    def _put(self, msg_type: str, data):
        self.msg_queue.put((msg_type, data))

    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "log":
                    self.log_text.config(state="normal")
                    self.log_text.insert("end", data)
                    self.log_text.see("end")
                    self.log_text.config(state="disabled")
                elif msg_type == "progress":
                    cur, total, label = data
                    self.progress_bar["value"] = cur
                    self.lbl_progress.config(text=label)
                elif msg_type == "switch_progress":
                    self.progress_bar.stop()
                    self.progress_bar.config(mode="determinate", maximum=data, value=0)
                elif msg_type == "done_query":
                    self.progress_bar.stop()
                    n_ok, n_skip = len(self._pending), len(self._skipped)
                    self.lbl_progress.config(text=f"查詢完成 — {n_ok} 筆可改名，{n_skip} 筆跳過")
                    self._put("log", f"\n── 共 {n_ok} 筆可改名，{n_skip} 筆跳過 ──\n")
                    if n_ok > 0:
                        self.btn_confirm.pack(side="left", padx=(0, 8), ipady=4)
                    self.btn_cancel.pack(side="left", ipady=4)
                elif msg_type == "done_rename":
                    success, fail, skipped = data
                    self.lbl_progress.config(
                        text=f"完成 — 成功 {success} / 失敗 {fail} / 跳過 {skipped}")
                    self.btn_confirm.pack_forget()
                    self.btn_cancel.pack_forget()
                    self.btn_start.config(state="normal")
                elif msg_type == "error":
                    self.progress_bar.stop()
                    self.lbl_progress.config(text="發生錯誤，請查看上方記錄")
                    self.btn_start.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


def main():
    root = tk.Tk()
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    AVRenameApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
```

- [x] **Step 2: 確認視窗可啟動**

```
venv\Scripts\python.exe main.py
```

期待：視窗出現，三個區塊正常顯示，↑↓ 可移動清單，瀏覽按鈕可選資料夾

- [x] **Step 3: Commit**

```
git add main.py
git commit -m "feat: rewrite main.py as tkinter GUI"
```

---

## Task 4: requirements.txt — 移除 rich

**Files:**
- Modify: `requirements.txt`

- [x] **Step 1: 刪除含 `rich` 的那行，存檔**

- [x] **Step 2: Commit**

```
git add requirements.txt
git commit -m "chore: remove rich dependency"
```

---

## Task 5: 更新文件

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `CHANGELOG.md`

- [x] **Step 1: 更新 ARCHITECTURE.md 主程式流程段落**

將「主程式流程」段落替換為：

```markdown
## 主程式（tkinter GUI）

啟動 → 讀 config.json 預填資料夾路徑 + 格式順序

使用者操作：
1. 設定目標資料夾（或用瀏覽按鈕）
2. 用 ↑↓ 調整命名格式元件順序（番號/女優名/片名）
3. 按「開始掃描」

背景執行緒（Phase 1+2）：
- scanner.py 掃描 → 過濾 processed_log
- fetcher.py 批次查詢 javdb，log 區即時顯示進度
- 查不到者記入 skipped 清單

查詢完畢 → 顯示結果清單 + 「確認改名」「取消」按鈕

Phase 3（使用者確認後）：批次改名
- 成功 → processed_log.json
- 查不到 → skipped.json
```

- [x] **Step 2: 在 CHANGELOG.md 頂部新增記錄**

```markdown
### 2026-05-05（第二版）
- 主程式從 rich TUI 改寫為 tkinter GUI
- 新增命名格式排列功能（番號/女優名/片名可 ↑↓ 調序，存入 config.json）
- build_filename() 支援 format_order 參數
- 移除 rich 依賴
```

- [x] **Step 3: Commit**

```
git add ARCHITECTURE.md CHANGELOG.md
git commit -m "docs: update for tkinter rewrite"
```

---

## 完成條件

- [x] `venv\Scripts\python.exe main.py` 視窗正常啟動
- [ ] ↑↓ 調整格式順序後重啟，順序仍還原（待 UI 手動驗證）
- [ ] 指定測試資料夾後按開始，log 區顯示查詢進度（待 UI 手動驗證）
- [ ] 查詢完畢顯示「確認改名」，按下後執行改名並顯示統計（待 UI 手動驗證）
- [ ] 查不到番號的檔案進 `skipped.json`（待 UI 手動驗證）
- [x] `pytest test_fetch.py` → 24 passed（含 19 個 extract_code 邊界案例）

---

## 已完成（舊版）

- [x] `scanner.py`、`fetcher.py`、`renamer.py`、`config.py` 基礎模組
- [x] `launcher.ps1` + `AV Code Rename 啟動器.bat`
- [x] 性別過濾 bug 修復（h2 selector）
- [x] 16 個單元測試通過

---

## ~~Pending Bug: processed_log 無法正確過濾已改名檔案~~ ✅ 已修（2026-05-05）

### 問題描述

`processed_log.json` 以**原始檔名**為 key（例如 `"abw-001.mp4"`）。
改名後磁碟上的檔案變成新名稱（例如 `"ABW-001 葵つかさ - 片名.mp4"`）。
下次啟動時 `scanner.py` 的 `scan()` 用 `f.name`（即新名稱）比對 processed_log，
比對不到 → 已改過的檔案重新出現在待處理清單。

### 影響

每次執行都會重複處理已改名的檔案，除非手動清除 `processed_log.json`。

### 修法選項

**A. Scanner 雙向比對（推薦）**
在 `scan()` 過濾時，同時比對 processed_log 的 key（原始名）和 value 裡的 `new_filename`（新名）。
只要 `f.name` 命中其中一個，就跳過該檔案。

```python
# scanner.py scan() 修改處
processed = set()
if log_path.exists():
    with open(log_path, encoding="utf-8") as f:
        data = json.load(f)
    for orig, entry in data.items():
        processed.add(orig)
        processed.add(entry.get("new_filename", ""))

# 過濾時
if f.name in processed:
    continue
```

**B. Renamer 同時記錄新舊名**
`write_processed_log()` 已記錄 `new_filename`，只需在 scanner 端讀取並納入比對（即 A 方案）。

### 受影響檔案

- `scanner.py`：`scan()` 函數（約第 30-50 行）
- `test_fetch.py`：補一個 integration test 驗證已改名檔案不會重複出現

### 優先度

中（功能不影響首次使用，但重複執行時造成浪費）




研究做為fallback的方案
* Javinizer (https://github.com/joshua-st/Javinizer): 非常強大的 CLI 工具，支援從多個來源（DMM, JavLibrary,
     MGS）抓取資料並自動重新命名檔案、下載封面。
   * javscraper (https://github.com/hibikidesu/javscraper): Python
     庫，整合了多個網站的爬蟲，適合想自己寫一點簡單腳本的人。
