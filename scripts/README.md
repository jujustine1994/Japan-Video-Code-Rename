# scripts/

開發與維護工具，不是應用程式主程式。

## Index

| 腳本 | 狀態 | 說明 |
|------|------|------|
| bulk_enrich.py | 使用中 | 初始建庫：爬 JavDB 列表頁批量填入 javdb_lookup.json |
| bulk_enrich_javlibrary.py | 使用中 | 全量建置：爬 javlibrary 列表頁，完整資料（番號 + 片名 + 女優名），反向爬取，斷點續跑 |
| bulk_enrich_by_actress.py | 使用中 | 全量建置（女優路線）：Phase1 收集所有女優 ID，Phase2 逐女優爬 listing 取 code+title，覆蓋全時間段，斷點續跑 |
| test_javlibrary_nodriver.py | 使用中 | 開發驗證：nodriver 繞過 javlibrary Cloudflare 可行性測試 |
| test_javlibrary_multi.py | 使用中 | 開發驗證：多番號查詢 + Chrome 隱藏方案測試 |

## bulk_enrich.py

一次性開發端工具，用於建立完整的 `data/javdb_lookup.json`。

**用法：**
```bash
venv\Scripts\python.exe scripts/bulk_enrich.py --max-pages 500
```

支援斷點續跑：進度存在 `data/enrich_state.json`（已 gitignore）。
建議每天跑 300-500 頁（≈ 7200-12000 筆），分多天完成後再 commit lookup.json。
