# Lookup Table Enrichment & Update Feature

**Date:** 2026-05-06
**Branch:** feature/lookup-enrichment
**Status:** Approved design

---

## Goal

將 `data/javdb_lookup.json` 從被動累積（掃描時順帶寫入）升級為主動維護的完整對照表，目標 10 萬筆級別，讓絕大多數番號在 lookup 命中，無需 fall back 到即時爬蟲。

---

## Architecture

### 新增模組

```
enricher.py          ← 新增，批量建庫與更新邏輯
scripts/bulk_enrich.py  ← 新增，開發端初始建庫腳本
```

### 不動的模組

```
fetcher.py   ← 單筆查詢邏輯不變，但補一條：查到 actresses:[] 時自動補詳細頁
renamer.py   ← 不動
scanner.py   ← 不動
main.py      ← 只新增一個 LabelFrame + 一個按鈕
config.py    ← 新增兩個 config key 的預設值
```

---

## enricher.py 設計

```python
class LookupEnricher:
    def __init__(self, lookup_file: str, cache_file: str): ...

    def scrape_listing_pages(
        self, fetcher, start_page: int, max_pages: int, progress_cb=None
    ) -> tuple[int, int]:
        """
        爬 javdb.com/videos?page=N 列表頁。
        每頁取番號 + 片名，存 {"title": "...", "actresses": []}。
        每 100 頁重啟 browser session。
        延遲 3-8 秒（random）。
        回傳 (新增筆數, 最後爬到的頁碼)。
        """

    def scrape_new_releases(
        self, fetcher, stop_after_known: int = 50,
        max_pages: int = 10, progress_cb=None
    ) -> int:
        """
        從第 1 頁往後爬，直到：連續 stop_after_known 筆「番號」已在 lookup，
        或已爬 max_pages 頁，兩者取先到者停止。
        GUI 更新按鈕使用。回傳新增筆數。
        """

    def retry_no_data(self, fetcher, progress_cb=None) -> int:
        """
        重查 cache 裡 no_data 且已過 TTL 的番號（重用 fetcher._query_javdb）。
        回傳成功補回的筆數。
        """
```

---

## 女優資料策略

- **初始建庫（bulk_enrich.py）**：只爬列表頁，存 `actresses: []`。速度快，~3-4 小時跑完 10 萬筆 title-only。
- **自動補全**：`fetcher.query()` 發現 lookup 命中但 `actresses == []` 時，自動補一次詳細頁請求並更新 lookup。使用者掃到該番號時才觸發，不需主動全量補。

---

## scripts/bulk_enrich.py（開發端工具）

```
python scripts/bulk_enrich.py --max-pages 500
```

行為：
1. 讀取 `data/enrich_state.json` 取得 `last_page`（預設 1）
2. 從 `last_page` 開始爬，最多爬 `--max-pages` 頁
3. 每頁寫入 lookup，並更新 `enrich_state.json`（斷點續跑）
4. 結束時印出總計新增筆數

`data/enrich_state.json` 格式：
```json
{ "last_page": 423, "total_imported": 10032 }
```

此檔案加入 `.gitignore`，不追蹤。

### IP 防封措施

| 措施 | 實作 |
|---|---|
| 爬列表頁而非搜尋頁 | `GET /videos?page=N` |
| 隨機延遲 | `random.uniform(3.0, 8.0)` 秒 |
| 每 100 頁重啟 browser | `fetcher.stop()` + `fetcher.start()` |
| 分批跑 | `--max-pages` 參數，每天跑幾百頁 |

---

## GUI 變動（main.py）

在主視窗新增 LabelFrame「資料庫」：

```
┌─ 資料庫 ─────────────────────────┐
│  [更新資料庫]                      │
└───────────────────────────────────┘
```

按鈕行為：
- 啟動背景執行緒，依序執行 `scrape_new_releases` → `retry_no_data`
- 執行中：按鈕 disable，文字改為「更新中...」
- log 區即時顯示進度（透過現有 `msg_queue`）
- 完成後：按鈕恢復，log 顯示總計結果

---

## config.json 新增欄位

```json
{
  "update_stop_after_known": 50,
  "update_max_new_release_pages": 10
}
```

- `update_stop_after_known`：追新時連續幾筆已知就停（預設 50）
- `update_max_new_release_pages`：GUI 更新最多爬幾頁（預設 10，≈ 240 筆），防止按一下跑數小時

---

## 資料流

```
初始建庫（開發端）：
  bulk_enrich.py
    └─ LookupEnricher.scrape_listing_pages()
         └─ javdb /videos?page=N  →  title-only  →  lookup.json

GUI 更新按鈕：
  [更新資料庫]
    ├─ LookupEnricher.scrape_new_releases()
    │    └─ javdb /videos?page=1..N  →  新番號  →  lookup.json
    └─ LookupEnricher.retry_no_data()
         └─ fetcher._query_javdb()  →  補回舊 no_data  →  lookup.json + cache.json

使用者掃描時（現有流程 + 補全）：
  fetcher.query(code)
    ├─ lookup 命中且 actresses 非空  →  直接回傳
    ├─ lookup 命中但 actresses=[]   →  補詳細頁  →  更新 lookup  →  回傳
    └─ lookup 未命中                →  現有 cache/javdb 流程
```

---

## 不在本次範圍內

- 自動定時更新（不加 scheduler）
- 多資料來源合併
- 使用者介面顯示 lookup 統計數字（筆數等）
