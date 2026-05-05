# ARCHITECTURE

## 工具概覽

掃描指定資料夾內的影片檔案，辨識番號，透過 javdb.com 查詢片名與女優資訊，以互動式 TUI 逐一確認後重新命名。

## 目標資料夾

```
D:\Adobe Reader\Adobe Acrobat XI Pro繁體中文\Adobe Acrobat XI Pro v11.0.9 for Mac\
```

共約 1473 個檔案（1434 .mp4、13 .webm、11 .srt）

## 目前檔案清單

| 檔案 | 狀態 | 用途 |
|------|------|------|
| `naming_convention.md` | ✅ 完成 | 命名規範文件 |
| `test_sources.py` | ✅ 完成 | 資料來源可行性測試 |
| `requirements_test.txt` | ✅ 完成 | 測試腳本相依套件 |
| `config.py` | ✅ 完成 | config.json 讀寫，首次設定路徑 |
| `scanner.py` | ✅ 完成 | 掃描資料夾、番號辨識、多集偵測 |
| `fetcher.py` | ✅ 完成 | javdb Playwright 爬蟲、性別過濾、快取 |
| `renamer.py` | ✅ 完成 | 命名規範、改名、log 寫入 |
| `main.py` | ✅ 完成 | 主程式（4-Phase TUI） |
| `launcher.ps1` | ✅ 完成 | 環境檢查 + 啟動器 |
| `AV Code Rename 啟動器.bat` | ✅ 完成 | 雙擊入口 |
| `requirements.txt` | ✅ 完成 | 主程式相依套件 |

## 計畫架構

```
AV Code Rename 啟動器.bat
    └── launcher.ps1 (環境檢查、venv 建立、套件安裝)
            └── main.py (主程式)
                    ├── scanner.py      掃描資料夾、辨識番號、判斷哪些需要處理
                    ├── fetcher.py      javdb Playwright 爬蟲、快取管理
                    ├── renamer.py      命名規範套用、實際改名
                    └── processed_log   已處理檔案紀錄（JSON）
```

## 主程式流程（4 Phase，使用者只需介入一次）

**Phase 1 — 掃描**：讀 config.json 取得目標資料夾，過濾已在 processed_log 的檔案，回傳待處理清單。

**Phase 2 — 批次查詢**（背景，有進度條）：每個檔案提取番號 → 查快取 → cache miss 才查 javdb → 過濾男性演員 → 組成建議檔名。查不到番號或 javdb 無資料 → 歸入「不確定」，維持原狀。

**Phase 3 — 審閱**（唯一介入點）：
- 顯示可更名清單（舊名 → 新名）
- 顯示不確定清單（原因）
- 同步輸出 `preview_YYYYMMDD_HHMMSS.txt`
- 等待：[Enter] 執行全部 / Ctrl+C 取消

**Phase 4 — 執行**：批次改名，成功寫入 processed_log.json，不確定的寫入 skipped.json（維持原狀）。

**設計原則：使用者介入次數最少，不逐一確認每個檔案。**

## 資料來源

| 來源 | 狀況 | URL 格式 |
|------|------|---------|
| javdb.com | ✅ 可用 | `https://javdb.com/search?q={CODE}&f=all` |
| javbus.com | ❌ webdriver 偵測 | 無法使用 |
| javlibrary.com | ❌ Cloudflare | 無法使用 |

## 快取策略

- 路徑：`cache/javdb_cache.json`
- 格式：`{ "DDT-435": { "title": "...", "actresses": [...], "queried_at": "..." } }`
- 查無資料時不寫入（下次仍會嘗試）
- 快取無過期機制（片名不會變，不需要）

## 處理日誌

- 路徑：`processed_log.json`
- 格式：`{ "original_filename": { "new_filename": "...", "renamed_at": "..." } }`
- 只記錄成功改名的檔案

## 關鍵設定變數

```python
TARGET_DIR = r"D:\Adobe Reader\Adobe Acrobat XI Pro繁體中文\Adobe Acrobat XI Pro v11.0.9 for Mac"
CACHE_FILE = "cache/javdb_cache.json"
LOG_FILE   = "processed_log.json"
```
