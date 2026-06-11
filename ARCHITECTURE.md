# ARCHITECTURE

## 工具概覽

掃描指定資料夾內的影片檔案，辨識番號，透過 javdb.com 查詢片名與女優資訊，以 tkinter GUI 一次確認後批次重新命名。支援社群資料庫：用戶可下載他人貢獻的片名資料、也可貢獻自己的查詢結果。

## 執行方式

雙擊 `AV Code Rename 啟動器.bat` → 呼叫 `launcher.ps1` → 啟動 `main.py`

## 目錄結構

```
AV Code Rename/
├── AV Code Rename 啟動器.bat   雙擊入口
├── launcher.ps1                環境檢查、venv 建立、套件安裝、啟動主程式
├── main.py                     tkinter GUI 主程式
├── config.py                   config.json 讀寫
├── scanner.py                  資料夾掃描、番號辨識、多集偵測
├── fetcher.py                  javdb Playwright 爬蟲、快取管理、登入狀態偵測
├── javlibrary_fetcher.py       javlibrary nodriver 爬蟲、背景瀏覽器管理
├── enricher.py                 批次建置（追新 / 全量爬 listing 頁）
├── renamer.py                  命名規範套用、實際改名、log 寫入
├── community_sync.py           社群資料庫下載 / 貢獻（CommunitySync 類別）
├── requirements.txt
├── requirements_test.txt
│
├── data/
│   ├── javdb_lookup.json       永久番號對照表（git 追蹤，無時間戳）
│   ├── javdb_community.json    社群共享資料庫（番號→片名，git 追蹤）
│   └── community_stats.json    社群統計（筆數、更新時間）
│
├── tests/
│   ├── test_config.py
│   ├── test_scanner.py
│   ├── test_renamer.py
│   ├── test_javlibrary_fetcher.py
│   ├── test_community_sync.py
│   └── test_process_contribution.py
├── test_fetch.py               fetcher / renamer / enricher 測試（root，歷史遺留）
├── test_enricher.py            enricher 測試（root，歷史遺留）
│
├── workers/
│   ├── index.js                Cloudflare Worker 程式碼（安全驗證 + GitHub Issue 建立）
│   └── wrangler.jsonc          Wrangler 部署設定
│
├── .github/
│   ├── workflows/
│   │   └── process_contribution.yml   GitHub Action：Issue 觸發驗證流程
│   └── scripts/
│       └── process_contribution.py    驗證 + 合併 + 推送社群 DB
│
├── cache/                      執行期快取（gitignore）
├── docs/                       設計文件、規格、計畫（superpowers 用）
└── scripts/                    工具腳本
```

## 核心執行流程

```
AV Code Rename 啟動器.bat
    └── launcher.ps1 (環境檢查、venv、套件)
            └── main.py (AVRenameApp tkinter)
                    ├── scanner.py      掃描資料夾、辨識番號
                    ├── fetcher.py      javdb Playwright 爬蟲
                    │       快取順序：javdb_lookup → cache → javdb 爬蟲
                    ├── enricher.py     批次建置（追新 / 全量）
                    ├── renamer.py      命名規範套用、改名
                    └── community_sync.py  社群 DB 下載 / 貢獻
```

## 社群資料庫架構

```
App (community_sync.py)
    └── POST → Cloudflare Worker (workers/index.js)
                    驗證：POST only、entries 1–1000 筆、
                          番號 ^[A-Z]+-\d+$、title ≤200 字元
                    └── GitHub API → 建立 Issue ([community-db] 標題)
                                        └── GitHub Action (process_contribution.yml)
                                                    └── process_contribution.py
                                                            驗證：body ≤100KB、
                                                                  entries 1–1000、
                                                                  title ≤200
                                                            通過 → 合併進 javdb_community.json → push
```

**Worker 端點**：`av-community-db.jujustine1994.workers.dev`
**Secrets**：`GITHUB_TOKEN`（Cloudflare Secret）、`GITHUB_REPO`（Cloudflare Var）

## 快取策略（雙層）

| 層 | 路徑 | 說明 |
|----|------|------|
| 永久對照表 | `data/javdb_lookup.json` | 完整結果（含女優名），git 追蹤，不過期 |
| 社群資料庫 | `data/javdb_community.json` | 番號→片名（無女優名），可下載更新 |
| 操作快取 | `cache/javdb_cache.json` | 含 no_data，7 天 TTL，gitignore |

查詢順序：lookup → cache → javdb 爬蟲；成功後同步寫入 lookup + cache。

## GUI 主要元件

| 元件 | 說明 |
|------|------|
| `AVRenameApp` | 主視窗，掃描/查詢/改名流程 |
| `DatabaseManagerDialog` | 資料庫管理：追新、全量建置、社群同步、Cookie 設定 |
| `NamingFormatDialog` | 命名格式排列（番號/女優名/片名順序） |
| `ReviewListWindow` | 審閱清單 Toplevel，顯示待改名清單 |

## Config 結構（config.json）

```json
{
  "target_dir": "...",
  "cache_file": "cache/javdb_cache.json",
  "lookup_file": "data/javdb_lookup.json",
  "processed_log": "processed_log.json",
  "skipped_log": "skipped.json",
  "format_order": ["code", "actress", "title"]
}
```

## 測試

```
pytest --ignore=scripts/        → 85 tests（全部通過）
```

| 測試檔 | 涵蓋範圍 |
|--------|---------|
| `tests/test_config.py` | config 讀寫 |
| `tests/test_scanner.py` | 番號辨識、邊界案例 |
| `tests/test_renamer.py` | build_filename、改名邏輯 |
| `tests/test_javlibrary_fetcher.py` | `_parse_video()` 解析邏輯（單女優、多女優、無片名、番號去頭） |
| `tests/test_community_sync.py` | CommunitySync 下載 / 貢獻 |
| `tests/test_process_contribution.py` | GitHub Action 驗證邏輯 |
| `test_fetch.py` | fetcher、enricher（root，歷史遺留） |
| `test_enricher.py` | enricher 進階（root，歷史遺留） |

## 資料來源

> **注意**：全量建置（`enricher.py` / `DatabaseManagerDialog` → 全量建置）為**工具擁有者自用功能**，非面向一般用戶。
> 需要有效的登入 session cookie，且需數小時人工監控。建置完成後將 `data/javdb_lookup.json` 打包進 Release 供用戶下載。

| 來源 | 狀況 |
|------|------|
| javdb.com | ✅ 可用（需登入 session；設計缺陷：未登入時所有分頁回傳相同 40 筆） |
| javlibrary.com | ✅ 可用（nodriver headless=False 繞過 Cloudflare；全量建置用，owner-only） |
| javbus.com | ❌ 地區封鎖（台灣 IP） |
| r18.dev | ❌ 台灣地區封鎖 |
