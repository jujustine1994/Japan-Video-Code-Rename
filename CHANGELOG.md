# CHANGELOG

## 目前狀態

**階段：完整實作完成，tkinter GUI 版本**

### 已完成
- [x] 命名規範文件（naming_convention.md）
- [x] 資料來源測試（javdb 可用、javbus/javlibrary 封鎖）
- [x] 確認 javdb 能回傳日文原名 + 女優名
- [x] 專案文件建立（README、ARCHITECTURE、CHANGELOG、TODO、PITFALLS）
- [x] config.py — 設定讀寫（config.json）
- [x] scanner.py — 番號提取、多集偵測、資料夾掃描
- [x] renamer.py — 命名規範組成、改名、log 寫入
- [x] fetcher.py — javdb Playwright 爬蟲、性別過濾、快取
- [x] main.py — 4-Phase TUI 主程式
- [x] launcher.ps1 + AV Code Rename 啟動器.bat
- [x] 全部 16 個單元測試通過

---

## 更新記錄

### 2026-05-06
- 修復 scanner.py regex：加 `(?!\d)` 防止超過 5 位數字被截斷（例如 `SONE-123456` 原本會錯誤抽出 `SONE-12345`）
- 新增 19 個 `extract_code` 邊界案例單元測試（大小寫、括弧、無連字號、品質標籤、日期前綴、多集後綴、溢位等），總計 24 tests passed
- 審閱清單改為獨立 Toplevel 視窗，查詢完顯示「開啟審閱清單（N 筆）」按鈕，點擊才開，視窗定位在主視窗右側
- 新增重複番號處理：同番號多檔案自動補 `(1)(2)(3)` 編號，審閱視窗頂部顯示橘色警告條，重複列底色標黃，可雙擊修改
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
