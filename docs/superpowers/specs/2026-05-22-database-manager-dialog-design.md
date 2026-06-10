# Design: 資料庫管理對話框

**日期**: 2026-05-22
**範圍**: 合併「更新資料庫」與「批次建置」兩個按鈕為單一「資料庫管理...」入口，新增 `DatabaseManagerDialog` Toplevel

---

## 背景

原本主視窗資料庫區塊有兩個按鈕：
- **更新資料庫** → `scrape_new_releases` + `retry_no_data`（無頁碼狀態，有上限問題）
- **批次建置** → `scrape_listing_pages`（有 resume state）

兩者底層都在爬 javdb listing 頁，功能重疊且對用戶定義不清。合併為一個管理入口，各功能分開說明。

---

## UI 佈局

### 主視窗變更

資料庫區塊（`frame_db`）：
- 移除「更新資料庫」與「批次建置」兩個按鈕
- 改為單一按鈕：`[資料庫管理...]`

### DatabaseManagerDialog（`tk.Toplevel`）

```
┌────────────────────────────────────────┐
│  資料庫管理                        [X] │
├────────────────────────────────────────┤
│  共 28,432 筆 · 上次更新：2026-05-22   │
├────────────────────────────────────────┤
│  [  追新  ] [ℹ]                        │
│  [繼續建置] [ℹ]  最多頁數: [100 ▲▼]   │
├────────────────────────────────────────┤
│  ┌──────────────────────────────────┐  │
│  │（進度 log）                      │  │
│  └──────────────────────────────────┘  │
│                            [關閉]      │
└────────────────────────────────────────┘
```

**ℹ 說明文字（點擊彈出 messagebox）：**

- 追新：`從最新番號開始掃描，遇到連續已知番號自動停止，同時補回之前查無資料的番號。適合每週執行一次。`
- 繼續建置：`從上次停止的頁碼繼續爬取，用於初次建庫或大規模補充。每次執行指定頁數，可多次執行直到完成。`

**資料庫狀態列** 顯示：
- 筆數：`data/javdb_lookup.json` 的 key 數量
- 上次更新：`enrich_state.json` 新增欄位 `last_updated`（ISO 格式，每次繼續建置或追新結束時寫入）
- 若無 `enrich_state.json` 則顯示「尚未建置」

**最多頁數 spinbox** 預設值 `100`，範圍 `10–5000`，步進 `100`。

---

## 執行流程

### 追新

```
scrape_new_releases(stop_after_known=50, max_pages=20)
  └─ 從第 1 頁開始，遇到連續 50 筆已知番號停止，最多 20 頁
  └─ 新增為 partial 條目（title only）

retry_no_data(max_retries=50)
  └─ 自動接續執行，不顯示獨立按鈕
  └─ 最多重試 50 筆 7 天以上的 no_data 條目

log 輸出：追新 +N 筆，補回 +M 筆
```

### 繼續建置

```
讀 enrich_state.json → 取得 last_page（無則從第 1 頁）
scrape_listing_pages(start_page=last_page+1, max_pages=用戶設定值)
  └─ 每頁結束後存回 enrich_state.json

log 輸出：本次 +N 筆，累計 X 筆，停在第 Y 頁
```

### 互鎖規則

- 任一操作執行中，兩個按鈕皆 disable
- 關閉按鈕執行中 disable（防止中途強關 Playwright）
- 操作完成後恢復所有按鈕

---

## 程式修改範圍

| 檔案 | 動作 |
|------|------|
| `main.py` | 移除 `_update_db()`、`_bulk_build_db()` 及對應按鈕；新增「資料庫管理...」按鈕；新增 `DatabaseManagerDialog` class |
| `enricher.py` | `retry_no_data()` 新增 `max_retries: int = 50` 參數，超過上限即停止 |

`fetcher.py`、`scanner.py`、`renamer.py`、`config.py` 不動。

---

## 不在本次範圍

- 女優名主動補填（partial → 完整）
- 社群貢獻 / GitHub PR 流程
- 資料庫匯出 / 匯入功能
