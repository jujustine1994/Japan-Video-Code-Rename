# JavlibraryFetcher — 設計文件

**Date:** 2026-06-11
**Branch:** feature/community-sync（接續）
**Status:** Approved design

---

## Goal

將 javlibrary.com 整合為主要查詢來源（取代 javdb），javdb 保留為 fallback。使用者啟動工具後，放著 AFK 跑完即可，無需手動操作。

---

## Background

- javdb 全量建置有設計缺陷（未登入時所有分頁回傳相同 40 筆），且需要定期手動更新 session cookie
- javlibrary 資料更完整，透過 nodriver（真實 Chrome，off-screen）可繞過 Cloudflare JS Challenge
- lookup table 目前為空，一般用戶需要 live 查詢，預期單次執行 1000 筆約 1–2 小時（AFK 可接受）

---

## Architecture

### 新增模組

```
javlibrary_fetcher.py    ← 新增，JavlibraryFetcher class
tests/test_javlibrary_fetcher.py  ← 新增，parse 邏輯單元測試
```

### 不動的模組

```
fetcher.py      ← 不動（保留作 javdb fallback）
enricher.py     ← 不動
scanner.py      ← 不動
renamer.py      ← 已修正 strip_actress_suffix（本 session 完成）
config.py       ← 不動
```

### 修改模組

```
main.py         ← _worker() 局部修改（約 15 行）
```

---

## JavlibraryFetcher 設計

### 介面

```python
class JavlibraryFetcher:
    def __init__(self, lookup_file: str, cache_file: str)
    def start(self) -> bool          # 啟動瀏覽器，等 CF 解完；回傳 True/False
    def query(self, code: str) -> dict | None  # 同步呼叫
    def stop(self)                   # 關閉瀏覽器和 event loop
```

回傳格式與 `Fetcher.query()` 一致：
```python
{"title": str, "actresses": list[str]}
```

### 內部結構

| 屬性 | 說明 |
|---|---|
| `_thread` | daemon Thread，跑獨立 asyncio event loop |
| `_loop` | asyncio.AbstractEventLoop |
| `_browser` | nodriver browser 物件 |
| `_page` | 單一 Page，所有查詢共用（不開新分頁） |
| `_ready` | threading.Event，`start()` 等此 signal |
| `_start_error` | 啟動失敗時存錯誤訊息 |
| `_lookup` | dict，`__init__` 時從 lookup_file 載入；成功查詢後同步寫回磁碟 |

### 查詢結果寫入

每筆成功查詢後，同步寫入 `lookup_file`（格式與現有 `javdb_lookup.json` 一致：`{code: {title, actresses}}`）。這樣下次重啟工具時，已查過的番號直接命中 lookup，不需要重打網路。cache_file 參數目前保留介面一致性，本版本不寫入（javdb cache 格式含時間戳，javlibrary 結果直接進 lookup 即可）。

### Chrome 啟動參數

```python
browser_args=["--window-position=-32000,0", "--window-size=1280,800"]
```

視窗推到螢幕外，使用者不可見，但 JS 正常執行可解 CF Challenge。

### 查詢流程（每筆）

```
1. page.get(vl_searchbyid.php?keyword={code})
2. wait_ready()  ← 偵測「請稍候...」，CF re-challenge 也在此等待
3. 解析搜尋結果，取第一筆 href（urljoin 解析相對路徑）
4. 若無結果 → 回傳 None
5. page.get(video_url)
6. wait_ready()
7. 解析：
   - 番號：#video_id .text
   - 片名原始：h3.post-title（格式：「番號 片名 女優名...」）
   - 女優名：span.star a（可多筆）
   - 片名清理：去開頭番號 + 循環呼叫 strip_actress_suffix()
8. 回傳 {title, actresses}
```

### CF Re-Challenge 處理

`wait_ready()` 每 2 秒輪詢 `document.title`，偵測到「請稍候...」或「Just a moment」就繼續等。timeout 預設 30 秒（比初始啟動的 20 秒長，應對長時間 AFK 跑時偶發的 re-challenge）。

---

## main.py `_worker()` 修改

### 查詢順序

```
lookup.json 命中 → 直接回傳（毫秒，不打網路）
cache 命中       → 直接回傳（毫秒）
以上皆無         → javlibrary query
                    → 失敗 → javdb query（懶啟動）
                              → 失敗 → 跳過，記 skipped
```

### 修改重點

1. `_worker()` 開頭加 `JavlibraryFetcher` 初始化與啟動
2. `Fetcher`（javdb）改為懶啟動：第一次需要 fallback 時才 `start()`
3. log 訊息：
   - `"🌐 正在啟動背景瀏覽器（首次需 5–10 秒）..."`
   - `"✅ 背景瀏覽器就緒"` 或 `"⚠ 背景瀏覽器啟動失敗，改用 javdb"`
4. skipped 原因從 `"javdb 查無資料"` 改為 `"查無資料"`
5. `finally` 區塊確保兩個 fetcher 都 stop

---

## 測試

### 單元測試（新增 `tests/test_javlibrary_fetcher.py`）

`_parse_video()` 為純函式，直接傳 HTML 字串測試，不需要 browser。

| 測試 | 驗證 |
|---|---|
| `test_parse_single_actress` | 單女優：片名、女優名正確 |
| `test_parse_multi_actress` | 多女優：尾端兩個名字全部移除 |
| `test_parse_no_title` | HTML 無片名元素 → 回傳 None |
| `test_parse_code_prefix_stripped` | 片名開頭番號被移除 |

### 手動整合測試

現有 `scripts/test_javlibrary_multi.py` 已驗證：
- Cloudflare 繞過 ✅
- 多番號查詢（SSIS-001、ABW-001、STARS-001、MIDE-001）✅
- off-screen 瀏覽器不可見 ✅

---

## 不在本次範圍內

- javlibrary 全量建置（enricher.py 的 javlibrary 版本，另立 task）
- lookup table 預建與打包（全量建置完成後）
- 查詢速率限制（2–3 秒間隔，在 JavlibraryFetcher 內部實作，本 spec 不規定數值）
- 多番號並行查詢
