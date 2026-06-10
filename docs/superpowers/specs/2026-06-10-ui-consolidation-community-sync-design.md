# Design: UI 整合 + 社群同步功能

**日期**: 2026-06-10
**Branch**: feature/community-sync（從 feature/lookup-enrichment 分出）
**Status**: Approved design

---

## 背景

兩個問題同時解決：

1. **UI 整理**：主視窗「命名格式順序」佔一整塊但幾乎不改，需要收納。資料庫管理功能擴充後按鈕過多，需要統一入口。
2. **社群同步**：JavDB 列表頁有分頁上限（~80 頁），無法靠單一帳號爬到 10 萬筆。改為讓使用者透過個別查詢各自累積，再透過社群同步機制匯聚成大型共享資料庫。

---

## 架構總覽

### 新增元件

```
社群資料庫 repo（獨立 GitHub public repo）
    └── javdb_community.json     # {"SSIS-001": "日文片名", ...}

community_sync.py                # 新增模組，負責貢獻與下載邏輯
```

### 修改元件

```
main.py
    ├── ToolApp._build_ui()       # 移除 frame_fmt，新增 ⚙ 命名格式... 按鈕
    ├── NamingFormatDialog        # 新增，原 frame_fmt 邏輯搬入
    └── DatabaseManagerDialog     # 擴充，新增社群同步 LabelFrame
```

### 不動的模組

```
fetcher.py / enricher.py / scanner.py / renamer.py / config.py
```

---

## 主視窗變動

### 移除

- `frame_fmt`（命名格式順序 LabelFrame，row=1）整個移除

### 新增

- `frame_dir` 右上角加一個 `[⚙ 命名格式...]` 按鈕，點擊開啟 `NamingFormatDialog`

### 結果佈局

```
┌─ 目標資料夾 ──────────────────────────────────┐
│  ◉ 整個資料夾  ○ 選擇檔案   [⚙ 命名格式...]  │
│  [路徑輸入框_____________________]   [瀏覽]   │
└───────────────────────────────────────────────┘
             [▶  開始掃描]
┌─ 處理進度 ────────────────────────────────────┐
│  等待開始...                                  │
│  [============進度條============]              │
│  （log 文字區）                               │
└───────────────────────────────────────────────┘
      [📋 開啟審閱清單]   [✖ 取消]
┌─ 資料庫 ──────────────────────────────────────┐
│  [資料庫管理...]                              │
└───────────────────────────────────────────────┘
```

---

## NamingFormatDialog

原 `frame_fmt` 的 Listbox + ↑↓ 按鈕搬入此 Toplevel。

```
┌─ 命名格式設定 ──────────┐
│  番號         [↑]       │
│  女優名       [↓]       │
│  片名                   │
│         [確定]  [取消]  │
└─────────────────────────┘
```

- 按「確定」才寫入 config.json（原行為：即時寫入，改為確定後才存）
- 按「取消」不儲存，還原選取前狀態
- 視窗大小固定，不可調整

---

## DatabaseManagerDialog 擴充

視窗尺寸：480 × 720

```
┌─ 資料庫管理 ─────────────────────────────────┐
│ ┌─ 我的資料庫 ───────────────────────────┐   │
│ │ 共 28,432 筆 · 上次更新：2026-06-10   │   │
│ │ 上次停在第 [80▲▼] 頁  [儲存]          │   │
│ │ [追新][ℹ]   [全量建置][ℹ]             │   │
│ │ 從第 [1▲▼] 頁，爬 [100▲▼] 頁         │   │
│ │ [⏸ 暫停]   [✖ 中止]                   │   │
│ └───────────────────────────────────────┘   │
│ ┌─ 社群同步 ────────────────────────────┐   │
│ │ 社群資料庫：1,234,567 筆              │   │
│ │ 可貢獻新番號：3,210 筆                │   │
│ │ [⬇ 下載最新]   [⬆ 貢獻我的資料]     │   │
│ └───────────────────────────────────────┘   │
│ ┌─ JavDB Session Cookie ────────────────┐   │
│ │ 狀態：已設定   [設定...]              │   │
│ └───────────────────────────────────────┘   │
│ ┌─ 進度 ─────────────────────────────────┐  │
│ │ （共用 log）                           │  │
│ └────────────────────────────────────────┘  │
│                                  [關閉]     │
└─────────────────────────────────────────────┘
```

**互鎖**：`_running` flag 共用，任一操作進行中所有操作按鈕全部 disable。

---

## 社群同步：community_sync.py

```python
class CommunitySync:
    REPO_RAW_URL = "https://raw.githubusercontent.com/<owner>/<repo>/main/javdb_community.json"
    ISSUES_API   = "https://api.github.com/repos/<owner>/<repo>/issues"
    TOKEN        = "<fine-grained PAT，issues:write only>"
    CHUNK_SIZE   = 1000  # 每個 Issue 最多幾筆

    def get_community_stats(self) -> dict:
        """回傳 {"count": N, "last_updated": "..."}，從 raw URL 下載"""

    def get_contribute_count(self, local_lookup: dict) -> int:
        """計算本機有、社群沒有的番號數量"""

    def download(self, local_lookup_path: Path,
                 backup_dir: Path, progress_cb=None) -> int:
        """
        1. 本機備份（backup_dir/javdb_lookup_YYYYMMDD_HHMMSS.json，保留最近 3 份）
        2. 下載社群 DB
        3. 合併：社群有、本機沒有 → 新增；本機已有 → 不覆蓋
        4. 回傳新增筆數
        """

    def contribute(self, local_lookup: dict,
                   progress_cb=None) -> int:
        """
        1. 下載社群 DB，計算 diff（本機有、社群沒有）
        2. 過濾：只保留 {"title": "...", "partial": false} 的完整筆數
           （partial=True 的只有片名無女優，品質較低，不貢獻）
        3. 分批建立 GitHub Issue（每批 CHUNK_SIZE 筆）
        4. 回傳送出筆數
        """
```

---

## 貢獻流程（詳細）

### 程式端

1. 下載最新社群 DB
2. diff：找出本機有、社群沒有的番號
3. 只貢獻 `partial=False` 的完整筆數（有片名且有女優名）
4. 每 1,000 筆建一個 GitHub Issue，body 格式：

```json
{
  "source": "av-code-rename",
  "version": 1,
  "entries": {
    "SSIS-001": "清楚な嘘",
    "IPX-001": "..."
  }
}
```

5. Issue title：`[community-db] batch +N entries YYYYMMDD_HHMMSS`

### GitHub Action 端（on: issues.opened）

1. 驗證 Issue title 開頭為 `[community-db]`，否則忽略
2. 解析 body JSON，驗證：
   - `source == "av-code-rename"`
   - `version == 1`
   - 每個 key 符合番號 regex（`[A-Z]+-\d+`）
   - 每個 value 非空字串
   - key 不存在於現有社群 DB（不覆蓋）
3. 通過：merge 進 javdb_community.json，commit，關閉 Issue 留言 `✓ +N 筆已合併`
4. 失敗：關閉 Issue 留言錯誤原因，不動資料庫

### 安全性

| 風險 | 對策 |
|------|------|
| Token 被從程式碼挖走 | Token 只有 `issues:write`，無法直接 push |
| 惡意覆蓋現有資料 | Action 驗證不覆蓋現有 key |
| 惡意刪除資料 | Action 只做新增，無刪除邏輯 |
| 大量 spam Issue | GitHub 預設 rate limit；Action 驗證失敗直接關閉 |
| 資料毀損 | git history 是完整備份，每次合併都是獨立 commit |

---

## 下載合併策略

- 社群有、本機沒有 → **新增**（`partial=True`，等實際查到才補女優）
- 本機已有 → **不覆蓋**（保留本機的女優資訊）

本機備份：`data/backups/javdb_lookup_YYYYMMDD_HHMMSS.json`，最多保留 3 份，超過刪最舊的。

---

## 社群資料庫 repo 設定

- 獨立 public repo（與程式 repo 分開）
- 主要檔案：`javdb_community.json`
- Branch protection：禁止任何人直接 push main，只有 GitHub Action 可寫
- Fine-grained PAT 設定：`issues:write` only，對象為此 repo

---

## 不在本次範圍

- Token 混淆/加密（已知風險，接受）
- 使用者身份驗證（無帳號機制）
- 貢獻統計顯示（誰貢獻多少）
- 社群 DB 自動定時下載
- partial 筆數的批量補全
