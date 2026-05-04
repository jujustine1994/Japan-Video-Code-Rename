# CHANGELOG

## 目前狀態

**階段：完整實作完成，可執行**

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

### 2026-05-05
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
