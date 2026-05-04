# AV Code Rename Tool — Design Spec
Date: 2026-05-04

## Overview

批次掃描影片資料夾，透過 javdb.com 查詢番號資訊，產生建議更名清單，使用者一次確認後執行全部更名。設計原則：使用者介入次數最少。

---

## Requirements

- 掃描指定資料夾（路徑可設定，存於 config.json）
- 批次查詢 javdb.com，取得日文片名 + 女優名（排除男性演員）
- 完成後呈現兩組清單：可更名 / 不確定
- 使用者一次確認執行全部更名
- 不確定的檔案維持原狀，記錄於 skipped.json
- 成功更名記錄於 processed_log.json（下次不再處理）
- 查詢結果快取於 cache/javdb_cache.json（避免重複連網）
- 審閱清單同步輸出 preview_YYYYMMDD_HHMMSS.txt

---

## Data Source

| 來源 | 狀況 |
|------|------|
| javdb.com | ✅ 唯一可用來源 |
| javbus.com | ❌ webdriver 偵測封鎖 |
| javlibrary.com | ❌ Cloudflare 封鎖 |

查詢方式：Playwright headless Chromium，設 over18 cookie 繞過年齡驗證。

---

## Naming Convention

```
[番號] [女優名(別名)] - [日文片名] [女優名].[副檔名]
```

詳見 `naming_convention.md`。

關鍵規則：
- 括號用半形 `()`
- 多集用 `(1)`, `(2)`
- 多女優空格分隔，尾部盡量全列
- 未知女優用 `未知女優`
- javdb `.origin-title` 後綴的女優名需從片名中去除

---

## Architecture

```
AV Code Rename 啟動器.bat
    └── launcher.ps1 (環境檢查、venv、套件安裝)
            └── main.py
                    ├── scanner.py      掃描、番號辨識、過濾已處理
                    ├── fetcher.py      javdb 爬蟲、快取、性別過濾
                    ├── renamer.py      命名規範、改名、log 寫入
                    └── config.py       config.json 讀寫
```

### File Layout

```
AV Code Rename/
├── main.py
├── scanner.py
├── fetcher.py
├── renamer.py
├── config.py
├── requirements.txt
├── launcher.ps1
├── AV Code Rename 啟動器.bat
├── config.json              (使用者設定，gitignore)
├── processed_log.json       (gitignore)
├── skipped.json             (gitignore)
├── cache/
│   └── javdb_cache.json     (gitignore)
└── preview_*.txt            (gitignore)
```

---

## Execution Flow

### Phase 1 — Scan（~1-2 秒）

- 讀取 config.json 取得 target_dir
- 掃描目標資料夾（.mp4, .webm, .srt）
- 過濾：processed_log 裡的檔案跳過
- 過濾：檔名已完全符合命名規範的跳過
- 回傳待處理清單

### Phase 2 — Batch Query（背景，有進度條）

輸入：待處理檔案清單
步驟：
1. 從每個檔名提取番號（regex，見下方）
2. 找不到番號 → 直接歸入「不確定」
3. 找到番號 → 查快取，有就用快取
4. 快取 miss → 查 javdb
5. javdb 查無資料 → 歸入「不確定」
6. javdb 有資料 → 過濾男性演員 → 組成建議檔名 → 歸入「可更名」

特殊處理：
- 多集（同番號多個檔案）：一次查詢，分別加 `(1)`, `(2)` 後綴
- .srt 檔：找同番號 .mp4 的新檔名直接套用，不查 javdb；
  若找不到對應 .mp4，fallback 自行查 javdb

### Phase 3 — Review（使用者唯一介入點）

- 顯示可更名清單（番號、舊名 → 新名）
- 顯示不確定清單（原因）
- 同步輸出 `preview_YYYYMMDD_HHMMSS.txt`
- 等待確認：[Enter] 執行 / Ctrl+C 取消

### Phase 4 — Execute

- 批次改名，顯示進度條
- 寫入 processed_log.json（成功更名的）
- 寫入 skipped.json（不確定的）
- 顯示統計結果

---

## Code Detection (scanner.py)

番號 regex（依優先序）：
```python
r'([A-Z]{2,8}-\d{2,5})'           # 標準格式：DDT-435, GTJ-065
r'([A-Za-z]{2,8})[-\s]?(\d{2,5})' # 容錯：ddt435, ddt 435
```

多集識別：
```python
# 同番號出現 2 次以上 → 視為多集
# 原始編號標記：-1, -2, (1), (2), 數字結尾等
r'.*?(-\d+|\(\d+\)|[\s_]\d+)\.(?:mp4|webm|srt)$'
```

---

## javdb Fetcher (fetcher.py)

### 查詢流程
```
query(code)
  → check cache
    → hit: return cached result
    → miss: launch Playwright page
      → goto search URL with over18 cookie
      → click first matching result
      → extract .origin-title (日文片名，含女優名後綴)
      → extract 演員 links
      → for each 演員: check gender (with cache，每位新演員多一次請求)
      → filter female only
      → strip actress names from title suffix
        （只去除片名尾端剛好 endswith 女優名的部分，避免誤刪片名中的人名）
      → cache result
      → return {title, actresses}
```

### 快取結構
```json
{
  "DDT-435": {
    "title": "解禁アナル・FUCK",
    "actresses": ["吉田花"],
    "queried_at": "2026-05-04T14:30:22"
  }
}
```

### 演員性別快取
```json
{
  "actors": {
    "/actors/xyz123": {"name": "吉田花", "gender": "female"},
    "/actors/abc456": {"name": "佐川銀次", "gender": "male"}
  }
}
```

---

## Renamer (renamer.py)

建議檔名組成：
```python
def build_filename(code, actresses, title, ext, part=None):
    actress_str = " ".join(actresses) if actresses else "未知女優"
    part_str = f"({part})" if part else ""
    name = f"{code} {actress_str} - {title} {actress_str}{part_str}{ext}"
    return sanitize(name)  # 去除 Windows 不合法字元
```

---

## Config (config.json)

```json
{
  "target_dir": "",
  "cache_file": "cache/javdb_cache.json",
  "processed_log": "processed_log.json",
  "skipped_log": "skipped.json"
}
```

首次執行：target_dir 為空 → 互動式詢問路徑 → 驗證存在 → 存檔。

---

## skipped.json Structure

```json
[
  {
    "filename": "1002.mp4",
    "reason": "找不到番號",
    "skipped_at": "2026-05-04T14:30:22"
  },
  {
    "filename": "DGEN-013 dgen013.mp4",
    "reason": "javdb 查無資料",
    "skipped_at": "2026-05-04T14:30:22"
  }
]
```

---

## Error Handling

| 情境 | 處理方式 |
|------|---------|
| 找不到番號 | 歸入不確定，記錄 skipped.json |
| javdb 查無資料 | 歸入不確定，記錄 skipped.json |
| javdb 超時 | 重試 2 次，仍失敗 → 歸入不確定 |
| 改名失敗（檔案被占用等） | 記錄錯誤，繼續下一個，最後統計顯示 |
| 目標路徑不存在 | 啟動時報錯，要求重新設定 |

---

## Dependencies (requirements.txt)

```
playwright>=1.40.0
playwright-stealth>=2.0.0
beautifulsoup4
rich                  # 進度條 + 彩色輸出
```
