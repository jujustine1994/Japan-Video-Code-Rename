# UI Consolidation + Community Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收納主視窗命名格式區塊、合併資料庫管理 dialog，並新增社群同步功能（GitHub Issues 驅動的 crowd-sourced 番號資料庫）。

**Architecture:** `community_sync.py` 負責所有網路邏輯（下載 / 貢獻）；`DatabaseManagerDialog` 擴充社群同步 UI，共用 `_running` flag 互鎖；`NamingFormatDialog` 把原 `frame_fmt` 收進獨立 Toplevel。

**Tech Stack:** Python 3.10+, tkinter/ttk, urllib (stdlib only, 不加新依賴), GitHub Issues API, GitHub Actions

---

## 檔案清單

| 動作 | 路徑 | 說明 |
|------|------|------|
| 新增 | `community_sync.py` | CommunitySync class，所有社群同步邏輯 |
| 新增 | `tests/test_community_sync.py` | community_sync 單元測試 |
| 修改 | `main.py` | NamingFormatDialog 新增；frame_fmt 移除；DatabaseManagerDialog 擴充 |

社群 repo（另一個 GitHub repo，本 repo 不存這些）：
- `javdb_community.json`
- `community_stats.json`
- `.github/workflows/process_contribution.yml`
- `.github/scripts/process_contribution.py`

---

## Task 0：提交目前 WIP + 建新 branch

**Files:** 無新檔案，整理 git 狀態

- [ ] **Step 1：提交目前未 commit 的改動**

```bash
cd "C:\Users\CTH\Documents\Code\AV Code Rename"
git add enricher.py fetcher.py main.py data/javdb_lookup.json
git commit -m "feat: enricher pause/abort, session detection, DB dialog improvements"
```

- [ ] **Step 2：從目前 branch 建立新 branch**

```bash
git checkout -b feature/community-sync
```

---

## Task 1：community_sync.py 骨架 + get_community_stats / get_contribute_count（TDD）

**Files:**
- 新增 `community_sync.py`
- 新增 `tests/test_community_sync.py`

- [ ] **Step 1：建立測試檔，寫兩個失敗測試**

```python
# tests/test_community_sync.py
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
from community_sync import CommunitySync

SAMPLE_LOCAL = {
    "SSIS-001": {"title": "タイトルA", "actresses": ["女優A"], "partial": False},
    "IPX-001":  {"title": "タイトルB", "actresses": ["女優B"], "partial": False},
    "NEW-001":  {"title": "タイトルC", "actresses": [],         "partial": True},
    "OLD-001":  {"title": "タイトルD", "actresses": [],         "partial": False},
}
SAMPLE_COMMUNITY = {"SSIS-001": "タイトルA", "OLD-001": "タイトルD"}
SAMPLE_STATS = {"count": 2, "last_updated": "2026-06-10T00:00:00Z"}


def _make_sync(tmp_path):
    p = tmp_path / "javdb_lookup.json"
    p.write_text(json.dumps(SAMPLE_LOCAL), encoding="utf-8")
    return CommunitySync(p)


def test_get_community_stats_success(tmp_path):
    sync = _make_sync(tmp_path)
    with patch.object(sync, "_fetch_url", return_value=json.dumps(SAMPLE_STATS).encode()):
        result = sync.get_community_stats()
    assert result["count"] == 2
    assert result["last_updated"] == "2026-06-10T00:00:00Z"


def test_get_community_stats_error(tmp_path):
    sync = _make_sync(tmp_path)
    with patch.object(sync, "_fetch_url", side_effect=Exception("network error")):
        result = sync.get_community_stats()
    assert result["count"] == 0
    assert result["last_updated"] == "無法取得"


def test_get_contribute_count(tmp_path):
    sync = _make_sync(tmp_path)
    # SSIS-001 already in community → skip
    # IPX-001 not in community + partial=False + actresses → count
    # NEW-001 partial=True → skip
    # OLD-001 not partial but actresses=[] → skip
    with patch.object(sync, "_fetch_url", return_value=json.dumps(SAMPLE_COMMUNITY).encode()):
        count = sync.get_contribute_count()
    assert count == 1  # only IPX-001


def test_get_contribute_count_network_error(tmp_path):
    sync = _make_sync(tmp_path)
    with patch.object(sync, "_fetch_url", side_effect=Exception("timeout")):
        count = sync.get_contribute_count()
    assert count == 0
```

- [ ] **Step 2：執行測試，確認 4 個都失敗**

```bash
cd "C:\Users\CTH\Documents\Code\AV Code Rename"
python -m pytest tests/test_community_sync.py -v
```

預期：`ModuleNotFoundError: No module named 'community_sync'`

- [ ] **Step 3：建立 community_sync.py**

```python
# community_sync.py
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
import urllib.request

COMMUNITY_REPO_OWNER = "PLACEHOLDER_OWNER"
COMMUNITY_REPO_NAME  = "PLACEHOLDER_REPO"
COMMUNITY_RAW_BASE   = (
    f"https://raw.githubusercontent.com"
    f"/{COMMUNITY_REPO_OWNER}/{COMMUNITY_REPO_NAME}/main"
)
COMMUNITY_API_BASE   = (
    f"https://api.github.com/repos"
    f"/{COMMUNITY_REPO_OWNER}/{COMMUNITY_REPO_NAME}"
)
COMMUNITY_TOKEN      = "PLACEHOLDER_TOKEN"

CHUNK_SIZE   = 1000
BACKUP_COUNT = 3
CODE_REGEX   = re.compile(r"^[A-Z]+-\d+$")


class CommunitySync:

    def __init__(self, local_lookup_path: Path):
        self.local_lookup_path = local_lookup_path

    def _load_local(self) -> dict:
        if not self.local_lookup_path.exists():
            return {}
        return json.loads(self.local_lookup_path.read_text(encoding="utf-8"))

    def _fetch_url(self, url: str) -> bytes:
        req = urllib.request.Request(
            url, headers={"User-Agent": "av-code-rename"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()

    def get_community_stats(self) -> dict:
        try:
            data = self._fetch_url(f"{COMMUNITY_RAW_BASE}/community_stats.json")
            return json.loads(data)
        except Exception:
            return {"count": 0, "last_updated": "無法取得"}

    def get_contribute_count(self) -> int:
        local = self._load_local()
        try:
            data = self._fetch_url(f"{COMMUNITY_RAW_BASE}/javdb_community.json")
            community = json.loads(data)
        except Exception:
            return 0
        return sum(
            1 for code, entry in local.items()
            if code not in community
            and not entry.get("partial", False)
            and entry.get("actresses")
        )

    def download(self, backup_dir: Path, progress_cb=None) -> int:
        raise NotImplementedError

    def contribute(self, progress_cb=None) -> int:
        raise NotImplementedError

    def _create_issue(self, title: str, body: str):
        raise NotImplementedError
```

- [ ] **Step 4：執行測試，確認全部通過**

```bash
python -m pytest tests/test_community_sync.py -v
```

預期：4 個 PASS

- [ ] **Step 5：Commit**

```bash
git add community_sync.py tests/test_community_sync.py
git commit -m "feat: add CommunitySync skeleton with get_community_stats/get_contribute_count"
```

---

## Task 2：download() 實作（TDD）

**Files:**
- 修改 `community_sync.py`（實作 `download()`）
- 修改 `tests/test_community_sync.py`（新增 download 測試）

- [ ] **Step 1：新增 download 測試到 tests/test_community_sync.py**

在現有測試檔末尾加入：

```python
def test_download_merges_new_entries(tmp_path):
    sync = _make_sync(tmp_path)
    backup_dir = tmp_path / "backups"

    def fake_fetch(url):
        return json.dumps({"SSIS-001": "タイトルA", "BRAND_NEW-001": "新タイトル"}).encode()

    with patch.object(sync, "_fetch_url", side_effect=fake_fetch):
        added = sync.download(backup_dir)

    assert added == 1
    result = json.loads(sync.local_lookup_path.read_text(encoding="utf-8"))
    assert "BRAND_NEW-001" in result
    assert result["BRAND_NEW-001"]["partial"] is True
    assert result["BRAND_NEW-001"]["actresses"] == []
    # 原有資料不被覆蓋
    assert result["SSIS-001"]["actresses"] == ["女優A"]


def test_download_creates_backup(tmp_path):
    sync = _make_sync(tmp_path)
    backup_dir = tmp_path / "backups"

    with patch.object(sync, "_fetch_url", return_value=b"{}"):
        sync.download(backup_dir)

    backups = list(backup_dir.glob("javdb_lookup_*.json"))
    assert len(backups) == 1


def test_download_keeps_max_backups(tmp_path):
    sync = _make_sync(tmp_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # 預先放 3 個舊備份
    for i in range(3):
        (backup_dir / f"javdb_lookup_2026010{i}_000000.json").write_text("{}")

    with patch.object(sync, "_fetch_url", return_value=b"{}"):
        sync.download(backup_dir)

    backups = list(backup_dir.glob("javdb_lookup_*.json"))
    assert len(backups) == 3  # 舊最舊的被刪，維持 3 份


def test_download_network_error_returns_zero(tmp_path):
    sync = _make_sync(tmp_path)
    with patch.object(sync, "_fetch_url", side_effect=Exception("timeout")):
        added = sync.download(tmp_path / "backups")
    assert added == 0
```

- [ ] **Step 2：執行測試，確認新增的 4 個測試失敗**

```bash
python -m pytest tests/test_community_sync.py::test_download_merges_new_entries -v
```

預期：FAIL `NotImplementedError`

- [ ] **Step 3：實作 download() — 替換 community_sync.py 裡的 NotImplementedError**

```python
def download(self, backup_dir: Path, progress_cb=None) -> int:
    if progress_cb:
        progress_cb("下載社群資料庫中...")
    try:
        data = self._fetch_url(f"{COMMUNITY_RAW_BASE}/javdb_community.json")
        community: dict = json.loads(data)
    except Exception as e:
        if progress_cb:
            progress_cb(f"[ERROR] 無法下載社群資料庫：{e}")
        return 0

    backup_dir.mkdir(parents=True, exist_ok=True)
    if self.local_lookup_path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = backup_dir / f"javdb_lookup_{ts}.json"
        shutil.copy2(self.local_lookup_path, dst)
        if progress_cb:
            progress_cb(f"已備份至 {dst.name}")
        backups = sorted(backup_dir.glob("javdb_lookup_*.json"))
        for old in backups[:-BACKUP_COUNT]:
            old.unlink()

    local = self._load_local()
    added = 0
    for code, title in community.items():
        if code not in local:
            local[code] = {"title": title, "actresses": [], "partial": True}
            added += 1

    self.local_lookup_path.parent.mkdir(parents=True, exist_ok=True)
    self.local_lookup_path.write_text(
        json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if progress_cb:
        progress_cb(f"下載完成：新增 {added:,} 筆")
    return added
```

- [ ] **Step 4：執行所有測試，確認全部通過**

```bash
python -m pytest tests/test_community_sync.py -v
```

預期：8 個 PASS

- [ ] **Step 5：Commit**

```bash
git add community_sync.py tests/test_community_sync.py
git commit -m "feat: implement CommunitySync.download() with backup logic"
```

---

## Task 3：contribute() 實作（TDD）

**Files:**
- 修改 `community_sync.py`（實作 `contribute()` + `_create_issue()`）
- 修改 `tests/test_community_sync.py`（新增 contribute 測試）

- [ ] **Step 1：新增 contribute 測試**

在 tests/test_community_sync.py 末尾加入：

```python
def test_contribute_sends_only_complete_entries(tmp_path):
    sync = _make_sync(tmp_path)
    issues_created = []

    def fake_fetch(url):
        return json.dumps(SAMPLE_COMMUNITY).encode()

    def fake_create_issue(title, body):
        issues_created.append((title, json.loads(body)))

    with patch.object(sync, "_fetch_url", side_effect=fake_fetch), \
         patch.object(sync, "_create_issue", side_effect=fake_create_issue):
        sent = sync.contribute()

    # IPX-001 only (SSIS-001 already in community; NEW-001 partial; OLD-001 no actresses)
    assert sent == 1
    assert len(issues_created) == 1
    title, body = issues_created[0]
    assert title.startswith("[community-db]")
    assert body["source"] == "av-code-rename"
    assert body["version"] == 1
    assert "IPX-001" in body["entries"]
    assert "NEW-001" not in body["entries"]


def test_contribute_chunks_large_dataset(tmp_path):
    # 2500 筆，應建立 3 個 Issue
    large_local = {
        f"CODE-{i:04d}": {"title": f"タイトル{i}", "actresses": ["女優"], "partial": False}
        for i in range(2500)
    }
    p = tmp_path / "javdb_lookup.json"
    p.write_text(json.dumps(large_local), encoding="utf-8")
    sync = CommunitySync(p)

    issues_created = []
    with patch.object(sync, "_fetch_url", return_value=b"{}"), \
         patch.object(sync, "_create_issue", side_effect=lambda t, b: issues_created.append(t)), \
         patch("time.sleep"):
        sent = sync.contribute()

    assert sent == 2500
    assert len(issues_created) == 3  # ceil(2500 / 1000)


def test_contribute_nothing_to_send(tmp_path):
    sync = _make_sync(tmp_path)
    # community already has all complete entries
    full_community = {
        "SSIS-001": "A", "IPX-001": "B", "OLD-001": "D"
    }
    with patch.object(sync, "_fetch_url", return_value=json.dumps(full_community).encode()), \
         patch.object(sync, "_create_issue") as mock_issue:
        sent = sync.contribute()
    assert sent == 0
    mock_issue.assert_not_called()
```

- [ ] **Step 2：執行，確認新 3 個測試失敗**

```bash
python -m pytest tests/test_community_sync.py::test_contribute_sends_only_complete_entries -v
```

預期：FAIL `NotImplementedError`

- [ ] **Step 3：實作 contribute() + _create_issue() — 替換 community_sync.py 的 NotImplementedError**

```python
def contribute(self, progress_cb=None) -> int:
    if progress_cb:
        progress_cb("計算可貢獻筆數中...")
    try:
        data = self._fetch_url(f"{COMMUNITY_RAW_BASE}/javdb_community.json")
        community: dict = json.loads(data)
    except Exception as e:
        if progress_cb:
            progress_cb(f"[ERROR] 無法下載社群資料庫：{e}")
        return 0

    local = self._load_local()
    new_entries = {
        code: entry["title"]
        for code, entry in local.items()
        if code not in community
        and not entry.get("partial", False)
        and entry.get("actresses")
    }

    if not new_entries:
        if progress_cb:
            progress_cb("沒有可貢獻的新番號")
        return 0

    total = len(new_entries)
    if progress_cb:
        progress_cb(f"共 {total:,} 筆可貢獻，開始送出...")

    sent = 0
    codes = list(new_entries.items())
    for batch_start in range(0, total, CHUNK_SIZE):
        chunk = dict(codes[batch_start:batch_start + CHUNK_SIZE])
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        title = f"[community-db] batch +{len(chunk)} entries {ts}"
        body = json.dumps(
            {"source": "av-code-rename", "version": 1, "entries": chunk},
            ensure_ascii=False,
        )
        try:
            self._create_issue(title, body)
            sent += len(chunk)
            if progress_cb:
                progress_cb(f"已送出 {sent:,} / {total:,} 筆")
            time.sleep(2)
        except Exception as e:
            if progress_cb:
                progress_cb(f"[ERROR] 送出失敗：{e}")
            break

    if progress_cb:
        progress_cb(f"貢獻完成：送出 {sent:,} 筆，等待 GitHub Action 驗證後合併")
    return sent

def _create_issue(self, title: str, body: str):
    payload = json.dumps({"title": title, "body": body}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMMUNITY_API_BASE}/issues",
        data=payload,
        headers={
            "Authorization": f"Bearer {COMMUNITY_TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "av-code-rename",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status not in (200, 201):
            raise RuntimeError(f"HTTP {resp.status}")
```

- [ ] **Step 4：執行所有測試，確認全部通過**

```bash
python -m pytest tests/test_community_sync.py -v
```

預期：11 個 PASS

- [ ] **Step 5：Commit**

```bash
git add community_sync.py tests/test_community_sync.py
git commit -m "feat: implement CommunitySync.contribute() with chunked GitHub Issues"
```

---

## Task 4：NamingFormatDialog + 移除 frame_fmt（main.py）

**Files:**
- 修改 `main.py`

- [ ] **Step 1：在 main.py 的 `DatabaseManagerDialog` class 上方新增 `NamingFormatDialog` class**

在 `class DatabaseManagerDialog:` 這一行之前插入：

```python
class NamingFormatDialog:
    def __init__(self, parent: tk.Tk, current_order: list,
                 on_save):
        self._on_save = on_save
        self._order = list(current_order)

        self.win = tk.Toplevel(parent)
        self.win.title("命名格式設定")
        self.win.resizable(False, False)
        self.win.grab_set()

        parent.update_idletasks()
        x = parent.winfo_x() + 40
        y = parent.winfo_y() + 40
        self.win.geometry(f"200x160+{x}+{y}")

        self._fmt_list = tk.Listbox(
            self.win, height=3, selectmode="single",
            width=16, font=("", 10),
        )
        for key in self._order:
            self._fmt_list.insert("end", LABELS[key])
        self._fmt_list.grid(row=0, column=0, rowspan=2,
                            padx=(14, 0), pady=14, sticky="ns")
        self._fmt_list.selection_set(0)

        ttk.Button(self.win, text="↑", width=4,
                   command=self._move_up).grid(row=0, column=1, padx=8, pady=(14, 2))
        ttk.Button(self.win, text="↓", width=4,
                   command=self._move_down).grid(row=1, column=1, padx=8, pady=(2, 0))

        btn_row = tk.Frame(self.win)
        btn_row.grid(row=2, column=0, columnspan=2, pady=(8, 12))
        ttk.Button(btn_row, text="確定", width=10,
                   command=self._ok).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="取消", width=10,
                   command=self.win.destroy).pack(side="left")

    def _move_up(self):
        sel = self._fmt_list.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        val = self._fmt_list.get(i)
        self._fmt_list.delete(i)
        self._fmt_list.insert(i - 1, val)
        self._fmt_list.selection_set(i - 1)

    def _move_down(self):
        sel = self._fmt_list.curselection()
        if not sel or sel[0] == self._fmt_list.size() - 1:
            return
        i = sel[0]
        val = self._fmt_list.get(i)
        self._fmt_list.delete(i)
        self._fmt_list.insert(i + 1, val)
        self._fmt_list.selection_set(i + 1)

    def _ok(self):
        new_order = [KEYS[self._fmt_list.get(i)]
                     for i in range(self._fmt_list.size())]
        cfg = config.load()
        cfg["format_order"] = new_order
        config.save(cfg)
        self._on_save(new_order)
        self.win.destroy()
```

- [ ] **Step 2：在 `ToolApp._build_ui()` 裡移除 frame_fmt 區塊，調整 row 號，新增 ⚙ 按鈕**

移除第 71–82 行（命名格式 LabelFrame + Listbox + 按鈕），同時調整後面所有 row 號：

```python
# 目標資料夾（在 frame_dir 內，row=0 的 Radiobutton 那行之後新增一個按鈕到同 row）
# 在 ttk.Radiobutton(frame_dir, text="選擇檔案"...).grid(row=0, column=1...) 之後插入：
ttk.Button(frame_dir, text="⚙ 命名格式...",
           command=self._open_fmt_dialog).grid(
    row=0, column=2, padx=(12, 0), sticky="e")

# frame_btn 改為 row=1
frame_btn = tk.Frame(self.root)
frame_btn.grid(row=1, column=0, pady=6)

# frame_prog 改為 row=2
frame_prog = ttk.LabelFrame(self.root, text=" 處理進度 ", padding=8)
frame_prog.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 4))

# frame_action 改為 row=3
self.frame_action = tk.Frame(self.root)
self.frame_action.grid(row=3, column=0, pady=(0, 12))

# frame_db 改為 row=4
frame_db = ttk.LabelFrame(self.root, text=" 資料庫 ", padding=8)
frame_db.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 8))
```

- [ ] **Step 3：移除 ToolApp 的 _move_up / _move_down / _save_fmt / self.fmt_list，新增 _open_fmt_dialog**

刪除 main.py 第 147–174 行（`_move_up`, `_move_down`, `_save_fmt`）。

在 `_browse` 方法之後新增：

```python
def _open_fmt_dialog(self):
    NamingFormatDialog(
        self.root,
        self._format_order,
        on_save=lambda order: setattr(self, "_format_order", order),
    )
```

- [ ] **Step 4：手動啟動程式，確認主視窗正常顯示，⚙ 命名格式... 可開關 dialog，確定後格式存入 config.json**

```bash
cd "C:\Users\CTH\Documents\Code\AV Code Rename"
python main.py
```

確認：
- 主視窗不再有「命名格式順序」LabelFrame
- ⚙ 命名格式... 按鈕出現在目標資料夾區域右側
- 點開 dialog → 拖動順序 → 確定 → 重新開啟 dialog 確認順序保持

- [ ] **Step 5：Commit**

```bash
git add main.py
git commit -m "refactor: move naming format to NamingFormatDialog, simplify main window"
```

---

## Task 5：DatabaseManagerDialog 擴充社群同步 UI

**Files:**
- 修改 `main.py`（`DatabaseManagerDialog._build_ui` + `_set_running` + `_refresh_stats`）

- [ ] **Step 1：擴大視窗，在 Cookie frame 和 log frame 之間插入社群同步 LabelFrame**

在 `DatabaseManagerDialog._build_ui()` 裡，找到 `cookie_frame` 和 `log_frame` 之間（約第 607–620 行），插入：

```python
# 社群同步
sync_frame = ttk.LabelFrame(self.win, text=" 社群同步 ", padding=8)
sync_frame.pack(fill="x", padx=14, pady=(0, 6))

self.lbl_community_count = ttk.Label(sync_frame, text="社群資料庫：載入中...")
self.lbl_community_count.pack(anchor="w")
self.lbl_contribute_count = ttk.Label(sync_frame, text="可貢獻：計算中...")
self.lbl_contribute_count.pack(anchor="w", pady=(2, 6))

sync_btn_row = tk.Frame(sync_frame)
sync_btn_row.pack(anchor="w")
self.btn_download = ttk.Button(sync_btn_row, text="⬇ 下載最新",
                               command=self._run_download, width=16)
self.btn_download.pack(side="left", padx=(0, 8))
self.btn_contribute = ttk.Button(sync_btn_row, text="⬆ 貢獻我的資料",
                                 command=self._run_contribute, width=16)
self.btn_contribute.pack(side="left")
```

同時把視窗高度從 640 改為 720：

```python
self.win.geometry(f"480x720+{x}+{y}")
```

- [ ] **Step 2：在 `_set_running()` 加入 btn_download / btn_contribute**

找到 `_set_running` 方法，在 `self.btn_close.config(state=state)` 之後加入：

```python
self.btn_download.config(state=state)
self.btn_contribute.config(state=state)
```

- [ ] **Step 3：在 `_refresh_stats()` 之後新增 `_refresh_community_stats()` 並在 `__init__` 呼叫**

在 `_refresh_stats` 方法之後新增：

```python
def _refresh_community_stats(self):
    import threading
    from community_sync import CommunitySync
    from pathlib import Path
    lookup_path = Path(__file__).parent / self._cfg.get(
        "lookup_file", "data/javdb_lookup.json")
    sync = CommunitySync(lookup_path)

    def worker():
        stats = sync.get_community_stats()
        count_str = f"社群資料庫：{stats['count']:,} 筆（更新：{stats['last_updated'][:10]}）"
        contrib = sync.get_contribute_count()
        contrib_str = f"可貢獻新番號：{contrib:,} 筆"
        self.win.after(0, lambda: self.lbl_community_count.config(text=count_str))
        self.win.after(0, lambda: self.lbl_contribute_count.config(text=contrib_str))

    threading.Thread(target=worker, daemon=True).start()
```

在 `__init__` 的 `self._refresh_stats()` 之後加上：

```python
self._refresh_community_stats()
```

- [ ] **Step 4：新增 _run_download / _run_contribute stub（確保按鈕可點）**

在 `_refresh_community_stats` 之後新增：

```python
def _run_download(self):
    self._log("（下載功能待 Task 6 接線）\n")

def _run_contribute(self):
    self._log("（貢獻功能待 Task 6 接線）\n")
```

- [ ] **Step 5：手動測試**

```bash
python main.py
```

確認：
- 「資料庫管理」dialog 開啟後高度 720，出現「社群同步」LabelFrame
- 兩個標籤開始顯示「載入中...」，數秒後更新（或顯示「無法取得」若無網路）
- 下載 / 貢獻按鈕可點，顯示 stub 訊息

- [ ] **Step 6：Commit**

```bash
git add main.py
git commit -m "feat: add community sync section to DatabaseManagerDialog"
```

---

## Task 6：接線 DatabaseManagerDialog ↔ CommunitySync

**Files:**
- 修改 `main.py`（實作 `_run_download` / `_run_contribute`）

- [ ] **Step 1：替換 _run_download stub**

```python
def _run_download(self):
    if self._running:
        return
    self._set_running(True)
    self._pause_event.clear()
    self._abort_event.clear()

    from community_sync import CommunitySync
    lookup_path = SCRIPT_DIR / self._cfg.get("lookup_file", "data/javdb_lookup.json")
    backup_dir  = SCRIPT_DIR / "data" / "backups"
    sync = CommunitySync(lookup_path)

    def worker():
        try:
            added = sync.download(backup_dir, progress_cb=lambda m: self.win.after(
                0, lambda msg=m: self._log(msg + "\n")))
            self.win.after(0, lambda: self._refresh_stats())
            self.win.after(0, lambda: self._refresh_community_stats())
        finally:
            self.win.after(0, lambda: self._set_running(False))

    import threading
    threading.Thread(target=worker, daemon=True).start()
```

- [ ] **Step 2：替換 _run_contribute stub**

```python
def _run_contribute(self):
    if self._running:
        return
    from tkinter import messagebox
    contrib_text = self.lbl_contribute_count.cget("text")
    if not messagebox.askyesno(
        "確認貢獻",
        f"將把本機的新番號送出到社群資料庫。\n{contrib_text}\n\n確定送出？",
        parent=self.win,
    ):
        return

    self._set_running(True)
    from community_sync import CommunitySync
    lookup_path = SCRIPT_DIR / self._cfg.get("lookup_file", "data/javdb_lookup.json")
    sync = CommunitySync(lookup_path)

    def worker():
        try:
            sync.contribute(progress_cb=lambda m: self.win.after(
                0, lambda msg=m: self._log(msg + "\n")))
        finally:
            self.win.after(0, lambda: self._set_running(False))

    import threading
    threading.Thread(target=worker, daemon=True).start()
```

- [ ] **Step 3：手動測試 download 流程（用無效 URL 確認 error handling）**

此時 `COMMUNITY_RAW_BASE` 仍指向 `PLACEHOLDER`，`download()` 應在 log 顯示 `[ERROR] 無法下載社群資料庫：...`，不 crash，按鈕恢復可用。

```bash
python main.py
# 開啟 資料庫管理 → 點「⬇ 下載最新」
# 確認：log 顯示 error，按鈕恢復，視窗不 freeze
```

- [ ] **Step 4：Commit**

```bash
git add main.py
git commit -m "feat: wire up DatabaseManagerDialog download/contribute to CommunitySync"
```

---

## Task 7：建立社群 GitHub Repo（手動步驟）

**Files:** 無本 repo 異動，在 GitHub 上建立新 repo

- [ ] **Step 1：在 GitHub 建立新 public repo**

名稱建議：`av-community-db`（owner 用你的帳號 `jujustine1994`）

- [ ] **Step 2：在新 repo 建立初始檔案**

建立 `javdb_community.json`（初始為空 DB，後續可把現有 javdb_lookup.json 的完整筆數匯入）：

```json
{}
```

建立 `community_stats.json`：

```json
{
  "count": 0,
  "last_updated": "2026-06-10T00:00:00Z"
}
```

- [ ] **Step 3：建立 GitHub Action 腳本**

建立 `.github/scripts/process_contribution.py`（在新 repo）：

```python
import json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

CODE_REGEX = re.compile(r'^[A-Z]+-\d+$')
DB_PATH    = Path('javdb_community.json')
STATS_PATH = Path('community_stats.json')

issue_number = os.environ['ISSUE_NUMBER']
body         = os.environ['ISSUE_BODY']


def close_issue(comment):
    comment_escaped = comment.replace('"', '\\"')
    os.system(f'gh issue comment {issue_number} --body "{comment_escaped}"')
    os.system(f'gh issue close {issue_number}')
    sys.exit(0)


try:
    payload = json.loads(body)
except json.JSONDecodeError:
    close_issue("❌ 解析失敗：JSON 格式錯誤")

if payload.get('source') != 'av-code-rename' or payload.get('version') != 1:
    close_issue("❌ 驗證失敗：source 或 version 不符")

community = json.loads(DB_PATH.read_text('utf-8')) if DB_PATH.exists() else {}
entries   = payload.get('entries', {})

added = skipped = 0
for code, title in entries.items():
    if not CODE_REGEX.match(str(code)):
        skipped += 1
        continue
    if not isinstance(title, str) or not title.strip():
        skipped += 1
        continue
    if code in community:
        skipped += 1
        continue
    community[code] = title
    added += 1

if added == 0:
    close_issue(f"ℹ️ 無新增（跳過 {skipped} 筆，已存在或格式不符）")

DB_PATH.write_text(json.dumps(community, ensure_ascii=False, indent=2), 'utf-8')

stats = {
    'count': len(community),
    'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
}
STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), 'utf-8')

subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
subprocess.run(['git', 'config', 'user.email',
                'github-actions[bot]@users.noreply.github.com'], check=True)
subprocess.run(['git', 'add', 'javdb_community.json', 'community_stats.json'], check=True)
subprocess.run(['git', 'commit', '-m',
                f'community: +{added} entries (issue #{issue_number})'], check=True)
subprocess.run(['git', 'push'], check=True)

close_issue(f"✓ 已合併 {added:,} 筆新番號（跳過 {skipped} 筆）")
```

建立 `.github/workflows/process_contribution.yml`（在新 repo）：

```yaml
name: Process Community Contribution

on:
  issues:
    types: [opened]

permissions:
  contents: write
  issues: write

jobs:
  process:
    runs-on: ubuntu-latest
    if: startsWith(github.event.issue.title, '[community-db]')
    steps:
      - uses: actions/checkout@v4

      - name: Process contribution
        env:
          ISSUE_NUMBER: ${{ github.event.issue.number }}
          ISSUE_BODY: ${{ github.event.issue.body }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python .github/scripts/process_contribution.py
```

- [ ] **Step 4：設定 branch protection**

在新 repo Settings → Branches → Add rule：
- Branch name pattern: `main`
- 勾選 "Require a pull request before merging"（可不用 review，防直接 push 即可）
- 勾選 "Do not allow bypassing the above settings"（除 GitHub Actions 外）

- [ ] **Step 5：建立 Fine-grained PAT**

GitHub → Settings → Developer settings → Fine-grained tokens → Generate new token

設定：
- Repository access: Only select repositories → 選 `av-community-db`
- Permissions → Issues: Read and write
- 其他全部 No access

複製 token 備用。

---

## Task 8：填入 token + repo URL，最終整合測試

**Files:**
- 修改 `community_sync.py`（填入真實 owner / repo / token）

- [ ] **Step 1：更新 community_sync.py 常數**

```python
COMMUNITY_REPO_OWNER = "jujustine1994"
COMMUNITY_REPO_NAME  = "av-community-db"          # 依實際名稱修改
COMMUNITY_TOKEN      = "github_pat_XXXXX..."       # 貼上 Task 7 Step 5 的 token
```

- [ ] **Step 2：執行所有測試，確認仍全部通過**

```bash
python -m pytest tests/ -v
```

預期：全部 PASS（tests 全用 mock，不打真實網路）

- [ ] **Step 3：手動整合測試 — 下載**

```bash
python main.py
# 資料庫管理 → ⬇ 下載最新
# 確認：顯示「新增 N 筆」，data/backups/ 出現備份檔
```

- [ ] **Step 4：手動整合測試 — 貢獻**

```bash
# 資料庫管理 → ⬆ 貢獻我的資料 → 確認送出
# 確認：log 顯示「已送出 N 筆」
# 到 github.com/jujustine1994/av-community-db/issues 確認 Issue 被建立且自動關閉
# 確認 javdb_community.json + community_stats.json 被更新
```

- [ ] **Step 5：Final commit + push branch**

```bash
git add community_sync.py
git commit -m "feat: configure community sync with actual GitHub repo and token"
git push -u origin feature/community-sync
```
