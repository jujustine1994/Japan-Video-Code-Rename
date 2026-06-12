# CHANGELOG

## 目前狀態

**階段：完整實作完成，tkinter GUI + 社群資料庫 + javlibrary 整合 + 全量建置爬蟲**

### 已完成
- [x] 命名規範文件（naming_convention.md）
- [x] 資料來源測試（javdb 可用、javbus/javlibrary 封鎖）
- [x] 確認 javdb 能回傳日文原名 + 女優名
- [x] 專案文件建立（README、ARCHITECTURE、CHANGELOG、TODO、PITFALLS）
- [x] config.py — 設定讀寫（config.json）
- [x] scanner.py — 番號提取、多集偵測、資料夾掃描
- [x] renamer.py — 命名規範組成、改名、log 寫入
- [x] fetcher.py — javdb Playwright 爬蟲、性別過濾、快取、登入狀態偵測
- [x] enricher.py — 追新 / 全量建置、暫停/中止、相鄰頁重複偵測
- [x] main.py — tkinter GUI（AVRenameApp + DatabaseManagerDialog + NamingFormatDialog）
- [x] launcher.ps1 + AV Code Rename 啟動器.bat
- [x] community_sync.py — 社群 DB 下載 / 貢獻（CommunitySync）
- [x] Cloudflare Worker（workers/index.js）— 代理貢獻請求，含完整安全驗證
- [x] GitHub Action（.github/workflows/process_contribution.yml + process_contribution.py）
- [x] 安全強化：Worker + GitHub Action 雙層驗證（番號格式、筆數、title 長度、body 大小）
- [x] Wrangler 部署設定（workers/wrangler.jsonc）— Worker 程式碼進 repo，`wrangler deploy` 即可更新
- [x] javlibrary_fetcher.py — nodriver 背景 Chrome，繞過 Cloudflare，主要查詢來源
- [x] scripts/bulk_enrich_javlibrary.py — 全量建置爬蟲（番號 + 片名 + 女優名，斷點續跑）
- [x] 全部 85 個單元測試通過

---

## 更新記錄

### 2026-06-12（feature/community-sync）— session 5

**專案結構整理（Step 2）**
- 所有源碼（`main.py`, `config.py`, `scanner.py`, `renamer.py`, `fetcher.py`, `enricher.py`, `javlibrary_fetcher.py`, `community_sync.py`）以 `git mv` 搬進 `src/`，保留 git 歷史
- `config.json` 一併移至 `src/`（gitignore 不追蹤，路徑同步更新）
- `src/main.py`：`SCRIPT_DIR` 改為 `Path(__file__).parent.parent`，指向專案根目錄（`cache/`、`data/` 仍在根目錄）
- `launcher.ps1`：`python main.py` → `python src/main.py`
- `scripts/bulk_enrich_javlibrary.py`：`sys.path.insert` 改指向 `src/`
- 新增 `conftest.py`（根目錄）：`sys.path.insert(0, "src")`，讓 pytest 找到已搬移的模組
- 85 個單元測試全程維持通過

**bulk_enrich_javlibrary.py — 總頁數偵測修正**
- `_parse_last_page()`：修正 `?&mode=&page=N` URL 的解析（`.lstrip("&")`）；加備用方案：所有分頁連結取最大值
- 移除 `fallback 9999`（會從不存在的頁碼起爬，立刻空頁結束）
- 新備用偵測：`_parse_last_page` 失敗時導航 `?page=99999`，javlibrary 自動 cap 到實際末頁，再從分頁讀回真正頁碼；也嘗試讀 `span.current`；全部失敗則印錯誤要求手動指定 `--start-page`

---

### 2026-06-12（feature/community-sync）— session 4

**Bug 修正**
- `renamer.strip_actress_suffix()`：改用 while 迴圈反覆移除，修正多女優片名只移除最後一個的問題
- 新增 `tests/test_renamer.py::test_strip_multi_actress` 測試覆蓋此 case

**Lookup 資料**
- 手動新增 14 筆 lookup（HSM-087、YMLW-068/069、USBA-089、SNOS-232/234/236/241、ROYD-319/321/324、ROE-509/510）

**bulk_enrich_javlibrary.py 功能完善**
- 新增雙擊啟動器 `bulk_enrich_javlibrary.bat`
- CF timeout 自動重試：listing 頁等 30 秒重試一次；影片頁等 10 秒重試最多 2 次
- 解析失敗（result=None）也重試，不只 CF timeout 才重試
- 網路錯誤自動重試（`_fetch_page`，15 秒 × 3 次）
- 原子寫入：`_save()` 改寫暫存檔再 `os.replace()`，防止強制關閉造成 JSON 損壞
- 啟動時顯示操作說明（Ctrl+C 本頁後停止、Ctrl+C×2 強制中止、續跑方式）
- 啟動時顯示 checkpoint 資訊（全新 / 從第 X 頁繼續）
- **Ctrl+C 優雅停止**：signal handler 攔截，本頁跑完才停；每頁 header 常駐顯示 `[Ctrl+C：本頁後停止]`
- **反向爬取**（最後一頁 → 第 1 頁）：啟動後動態偵測總頁數（`a.last` selector），新作品只影響前幾頁，高頁碼穩定，checkpoint 可靠

**文件更新**
- `docs/PITFALLS.md` P2：javlibrary 改為「已用 nodriver 解決」，補禁止事項
- `README.md`：資料來源更正（javlibrary 主 / javdb fallback）；文件路徑加 `docs/` 前綴
- `docs/ARCHITECTURE.md`：目錄結構補 BAT、測試路徑更正；查詢流程圖更新；資料來源表格順序互換
- `scripts/README.md`：`bulk_enrich_javlibrary.py` 說明更正（完整資料 + 反向爬取）

**專案結構整理（Step 1）**
- `ARCHITECTURE.md`, `CHANGELOG.md`, `PITFALLS.md`, `TODO.md`, `naming_convention.md` 移至 `docs/`
- `test_fetch.py`, `test_enricher.py` 移至 `tests/`（85 tests 仍全過）
- Step 2（源碼搬進 `src/`）詳細計畫記錄於 `docs/TODO.md`

---

### 2026-06-11（feature/community-sync）— session 3

**javlibrary 整合為主要查詢來源**
- 新增 `javlibrary_fetcher.py`（`JavlibraryFetcher` 類別）
  - nodriver（真實 Chrome）繞過 Cloudflare JS Challenge，headless=False + 視窗推到螢幕外不可見
  - 背景 daemon thread 跑獨立 asyncio event loop；`start()` 同步等 CF 解除；`query()` 同步呼叫
  - 整個 session 只開一次 Chrome，1000 筆查詢不需重啟瀏覽器
  - 每筆查詢結果即時寫回 `javdb_lookup.json`，重啟工具已查過的番號直接命中快取
  - `_wait_ready()`：先 check title，偵測到 CF 才 sleep 2 秒，消除每筆強制 4 秒延遲
  - `start()` 正確處理 30 秒 timeout（`_ready.wait` 回傳值納入判斷）
- 修正 `renamer.strip_actress_suffix()`：改用 while 迴圈處理多女優尾端移除，原本只能移除最後一個
- 新增 `tests/test_javlibrary_fetcher.py`：4 個單元測試（純 HTML parse，不需 browser）
- `main.py _worker()` 整合新查詢順序：
  1. lookup 完整 entry → 直接用（毫秒，不打網路）
  2. javlibrary live query（主）
  3. javdb fallback（懶啟動，第一次 javlibrary miss 才啟動）
  4. 兩者皆失敗 → 記入 skipped
- GUI log 新增：「🌐 正在啟動背景瀏覽器」/ 「✅ 背景瀏覽器就緒」/ 「⚠ javlibrary 查無結果，啟動 javdb...」

**全量建置爬蟲（owner-only）**
- 新增 `scripts/bulk_enrich_javlibrary.py`
  - 爬 javlibrary `vl_newrelease.php` listing 頁，每頁 20 筆
  - 對每個番號進影片頁抓片名 + 女優名，寫入完整 entry
  - 不覆蓋已有完整 entry，斷點續跑（進度存 `data/enrich_javlibrary_state.json`）
  - `--start-page`、`--max-pages` CLI 參數支援
  - 測試通過：3 頁 × 6 筆，CF 自動解，checkpoint 正常
- 支援 partial entry（`partial: true`）：`JavlibraryFetcher.query()` 遇到 partial 仍進行 live query 補女優名

**測試**
- 整體 85 個測試全過（`pytest --ignore=scripts/`）

---

### 2026-06-10（feature/community-sync）— session 2

**GitHub Action 安全強化**
- `process_contribution.py` 重構：將驗證邏輯提取為 `validate_payload()` + `filter_entries()` 兩個純函數，方便單元測試
- 新增 Issue body 大小保護（> 100KB 直接拒絕，防止超大 payload 讓 Action 爆炸）
- 新增 entries 筆數上限（< 1 或 > 1,000 筆直接拒絕）
- 新增 title 長度上限（單筆 > 200 字元則跳過）
- 新增 `tests/test_process_contribution.py`：15 個單元測試覆蓋上述所有安全檢查，全部通過
- 整體 80 個測試全過

**Worker 端（已 deploy）**
- `workers/index.js` + `workers/wrangler.jsonc` 進 repo，透過 `wrangler deploy` 部署，不再需要 Dashboard 手動編輯
- 加入與 GitHub Action 一致的驗證：番號格式 `^[A-Z]+-\d+$`、entries 筆數 1–1000、title 長度 1–200

---

### 2026-06-10（feature/community-sync）

**社群同步功能**
- 新增 `community_sync.py`（`CommunitySync` 類別）：下載社群資料庫 + 貢獻本機資料
- 貢獻流程：diff 本機 vs 社群 → 只送 `partial=False` 且有女優名的完整筆數 → 每 1,000 筆一批送出
- 下載流程：從 GitHub raw URL 下載社群 DB → 備份本機（保留最近 3 份）→ 合併（社群有本機無則新增，本機已有不覆蓋）
- 新增 `data/javdb_community.json`（社群共享資料庫，初始空白）
- 新增 `data/community_stats.json`（社群統計，記錄筆數與更新時間）

**Cloudflare Worker Token Proxy**
- 貢獻時改由 Cloudflare Worker 代理，app 端不持有 GitHub token
- Worker URL：`av-community-db.jujustine1994.workers.dev`
- GITHUB_TOKEN 存為 Cloudflare Secret；GITHUB_REPO 存為 Plaintext 環境變數

**GitHub Action 自動驗證**
- 新增 `.github/workflows/process_contribution.yml`：issues.opened 觸發
- 新增 `.github/scripts/process_contribution.py`：驗證來源、格式、不覆蓋現有 key，通過後 commit + 關閉 Issue

**UI 整合**
- 主視窗移除「命名格式順序」區塊（frame_fmt），改為 `⚙ 命名格式...` 按鈕開啟 `NamingFormatDialog` popup
- `DatabaseManagerDialog` 視窗高度 640 → 720，新增「社群同步」LabelFrame
  - 顯示社群筆數、可貢獻筆數
  - 「⬇ 下載最新」「⬆ 貢獻我的資料」按鈕，與其他操作互鎖

**測試**
- 新增 `tests/test_community_sync.py`：11 個單元測試，全部通過
- 修正 `test_enricher.py`：4 個 mock 補 `progress_cb=None` 參數（與 `_fetch_listing_page` 簽名對齊）
- 整體 65 個測試全過

**整合測試結果**
- Worker 驗證（空 entries → 400、GET → 405、正常送出 → ok:true）✅
- GitHub raw URL 可讀（community_stats、community DB）✅
- GitHub Action 端到端流程（Issue 建立 → 驗證 → 合併 → 關閉）✅

---

### 2026-06-10
- 修正：`winget install Python` 加入 `--override "/quiet PrependPath=1 Include_pip=1"`，確保靜默安裝後 Python 自動加進 PATH
- 修正：`launcher.ps1` 加入全域 `trap`，攔截未處理例外，防止執行失敗時視窗直接閃退

### 2026-05-24（feature/lookup-enrichment）— session 3

**全量建置除錯強化**
- `enricher._fetch_listing_page`：失敗時改為記錄實際 URL 與頁面標題（原本靜默回傳 `[]`，無法分辨是 session 失效還是網路問題）

**全量建置自動暫停**
- `scrape_listing_pages` 新增 `pause_event` 參數與連續零新增偵測
- 條件（`prev_last_page` 邊界）：只在「從未爬過的新頁碼範圍」偵測連續 2 頁 `page_new == 0` → 自動暫停，回傳上次成功頁碼
- 改用 `prev_last_page` 取代舊的 `had_new_entries` flag，修正從已知區段重新開始時誤判的問題
- `scrape_new_releases` 亦加入 `pause_event` 支援（手動暫停）

**相鄰頁重複偵測（新）**
- `scrape_listing_pages` 新增相鄰頁比對：若第 N 頁與第 N+1 頁的番號集合**完全相同**，立刻暫停並告警
- 根本原因：session 失效時 JavDB 把所有頁碼請求都回傳第 1 頁內容（固定 40 筆），舊邏輯要等連續 2 頁零新增才發現，新偵測第 2 頁就能抓到

**⏸ 手動暫停 / ✖ 中止按鈕（DatabaseManagerDialog）**
- 執行中顯示「⏸ 暫停」與「✖ 中止」兩個按鈕
- 暫停：設 `pause_event`，下一頁迭代前生效，進度正常儲存
- 中止：同時設 `abort_event` + `pause_event`，本次新增不儲存，起始頁 Spinbox 還原

**全量建置頁碼手動控制**
- UI 新增「從第 X 頁，爬 N 頁」設定列（起始頁 + 頁數各一個 Spinbox）
- 不再從 state 自動算 `start_page`，由使用者在 UI 確認後執行
- 每次跑完自動更新起始頁 Spinbox 至 `last_page + 1`

**資料庫狀態顯示**
- 新增「上次停在第 X 頁（可手動修改）+ 儲存」：直接在 UI 改寫 `enrich_state.json` 的 `last_page`，同步更新起始頁 Spinbox

**Bug 修正**
- `_run_build`：修正 `prev_last` UnboundLocalError（Python closure 變數先用後賦值）→ 移至 `state` 讀取後立刻賦值
- `last_page` 污染：中止時不再更新 `enrich_state.json`，保留原始頁碼

**Session Cookie UI**
- Cookie 輸入改為彈出視窗（原本是 inline Entry），可完整檢視現有值，貼入新值後儲存

**登入狀態偵測（新）**
- `fetcher.check_login_status()`：啟動後抓首頁，偵測是否有 `sign_in` 連結判斷登入狀態
- 追新 / 全量建置開始時 log 顯示 `✅ 已登入` 或 `❌ 未登入`，方便確認 session 是否有效

---

⚠ **待確認（下次測試前需處理）**
- [ ] session cookie 是否有效：需重新登入 javdb.com 取得新 `_jdb_session`
- [ ] `enrich_state.json` 的 `last_page` 需手動修正回正確值（上一輪 session 失效導致數值被污染）
- [ ] 相鄰頁重複偵測、自動暫停、中止按鈕尚未實際跑過完整測試

---

### 2026-05-22（feature/lookup-enrichment）— session 2

**修正全量建置爬蟲無法翻頁**
- 根本原因：JavDB 把 `/videos?page=X` 重導向至首頁 `/`，非登入狀態下所有頁碼回傳相同 40 筆，造成爬 315 頁只累積 85 筆
- `enricher._fetch_listing_page` URL 修正：`/videos?page={n}` → `/?page={n}`
- 確認登入後翻頁正常（Page 1 / 2 / 10 各不相同）

**JavDB Session Cookie 支援**
- `Fetcher.start()` 改為自動讀取 `data/javdb_session.txt`，若存在則注入 `_jdb_session` cookie
- `data/javdb_session.txt` 加入 `.gitignore`（敏感資訊）
- `DatabaseManagerDialog` 新增「JavDB Session Cookie」區塊：顯示目前設定狀態，可直接貼入 URL-encoded 或 decoded 的 cookie 值並儲存（`_save_cookie` 自動 URL decode）
- Cookie 到期後只需重新貼入，追新 / 全量建置 / `bulk_enrich.py` 全部自動生效

### 2026-05-22（feature/lookup-enrichment）

**資料庫管理對話框**
- 主視窗資料庫區塊從「更新資料庫」+「批次建置」兩個按鈕合併為單一「資料庫管理...」入口
- 新增 `DatabaseManagerDialog` Toplevel：追新 / 全量建置兩個獨立按鈕，各附 ℹ 說明
- 執行中兩按鈕互鎖，關閉按鈕 disable 防止中途強關 Playwright
- `enrich_state.json` 新增 `last_updated` 欄位，對話框顯示統計列

**bulk_enrich 邏輯修正**
- 全量建置改回 `scrape_listing_pages`（無 stop 條件，`last_page` resume）：page drift 只造成多幾個 request，不漏抓
- 追新移除 `max_pages=20` 上限，改為 `max_pages=9999`，只靠連續已知條件停止，確保久未執行時（如 Day 125）仍能完整覆蓋所有新番
- `retry_no_data` 加入 `max_retries=50` 上限，避免大量 no_data 造成 GUI 卡頓

**命名規範修正**
- `build_filename()` 修正：女優名在片名後再出現一次（符合命名規範 `[番號] [女優名] - [片名] [女優名].[副檔名]`）
- 更新 `test_fetch.py` 對應測試，目前共 54 tests passed

**修正全量建置說明文字**
- 原說明「從第 1 頁開始」、「遇到連續已知番號自動停止」與實際行為不符
- 修正為：從上次停止的頁碼繼續、沒有連續已知判斷、穿越已知區段繼續往後爬

### 2026-05-06
- 修復 scanner.py regex：加 `(?!\d)` 防止超過 5 位數字被截斷（例如 `SONE-123456` 原本會錯誤抽出 `SONE-12345`）
- 新增 19 個 `extract_code` 邊界案例單元測試（大小寫、括弧、無連字號、品質標籤、日期前綴、多集後綴、溢位等），總計 24 tests passed
- 審閱清單改為獨立 Toplevel 視窗，查詢完顯示「開啟審閱清單（N 筆）」按鈕，點擊才開，視窗定位在主視窗右側
- 新增重複番號處理：同番號多檔案自動補 `(1)(2)(3)` 編號，審閱視窗頂部顯示橘色警告條，重複列底色標黃，可雙擊修改
- 新增 `data/javdb_lookup.json`：永久番號對照表，格式乾淨（無時間戳、無 no_data），git 追蹤；已從 cache 遷移 22 筆
- 快取改為雙層架構：lookup（永久，最優先）→ cache（含 no_data TTL）→ 打 javdb；查詢成功後同步寫入兩層
- 研究替代資料來源（javscraper、r18.dev API）
- 實測結論：台灣 IP 下 DMM/r18.dev 鎖區（403）、javbus 改為地區封鎖，javscraper 三個來源均失敗
- 新增 PITFALLS P7（javscraper DMM 鎖區）、P8（r18.dev 403）、P9（javbus 地區封鎖）
- 更新 test_sources.py：加入 javscraper 與 r18.dev 輕量來源測試

### 2026-05-05（第四版）
- 查詢 javdb 每筆間隔 1–2 秒隨機延遲，避免 rate limit
- 查無資料的番號寫入 cache（`no_data: true`），7 天內重啟不重查

### 2026-05-05（第三版）
- 修復 processed_log bug：改名後的檔案下次掃描仍會重複出現
- `load_processed_log()` 現在同時比對原始檔名（key）與改名後檔名（new_filename），命中任一即跳過

### 2026-05-05（第二版 — tkinter GUI）
- 主程式從 rich TUI 改寫為 tkinter GUI
- 新增命名格式排列功能（番號/女優名/片名可 ↑↓ 調序）
- `build_filename()` 支援 `format_order` 參數
- `format_order` 存入 config.json，下次啟動自動還原
- 修復性別過濾 bug（改用 h2 selector 偵測男優）
- 移除 rich 依賴

### 2026-05-05（第一版）
- 完整實作所有模組：config.py、scanner.py、renamer.py、fetcher.py、main.py
- 建立 Windows 啟動器（launcher.ps1 + AV Code Rename 啟動器.bat）
- 全部 16 個單元測試通過
- 初始化 git repo，建立完整 commit 記錄

### 2026-05-04
- 新增 naming_convention.md（命名規範）
- 新增 test_sources.py（資料來源測試腳本，Playwright 版）
- 測試結果：javdb 可用、javbus webdriver 偵測封鎖、javlibrary Cloudflare 封鎖
- 確認 javdb `.origin-title` 選擇器可取得日文原名
- 建立專案文件架構
