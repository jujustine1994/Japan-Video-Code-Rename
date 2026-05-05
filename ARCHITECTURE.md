# ARCHITECTURE

## 工具概覽

掃描指定資料夾內的影片檔案，辨識番號，透過 javdb.com 查詢片名與女優資訊，以 tkinter GUI 一次確認後批次重新命名。

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
| `main.py` | ✅ 完成 | 主程式（tkinter GUI） |
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

## 主程式（tkinter GUI）

啟動 → 讀 config.json 預填資料夾路徑 + 格式順序

使用者操作：
1. 設定目標資料夾（或用瀏覽按鈕）
2. 用 ↑↓ 調整命名格式元件順序（番號 / 女優名 / 片名）
3. 按「開始掃描」

背景執行緒（Phase 1+2）：
- scanner.py 掃描 → 過濾 processed_log
- fetcher.py 批次查詢 javdb，log 區即時顯示進度
- 查不到者記入 skipped 清單

查詢完畢 → log 區顯示完整結果清單 + 出現「確認改名」「取消」按鈕

Phase 3（使用者確認後）：批次改名
- 成功 → processed_log.json
- 查不到 → skipped.json

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

## Config 結構（config.json）

```json
{
  "target_dir": "D:\\...",
  "cache_file": "cache/javdb_cache.json",
  "processed_log": "processed_log.json",
  "skipped_log": "skipped.json",
  "format_order": ["code", "actress", "title"]
}
```

`format_order` 決定命名元件順序，片名前自動插入 ` - `（若非第一位）。
