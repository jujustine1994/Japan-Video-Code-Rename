# CHANGELOG

## 目前狀態

**階段：設計 + 資料來源測試完成，主工具尚未開始**

### 已完成
- [x] 命名規範文件（naming_convention.md）
- [x] 資料來源測試（javdb 可用、javbus/javlibrary 封鎖）
- [x] 確認 javdb 能回傳日文原名 + 女優名
- [x] 專案文件建立（README、ARCHITECTURE、CHANGELOG、TODO、PITFALLS）

### 未完成
- [ ] 主程式 TUI（main.py）
- [ ] javdb 爬蟲模組（fetcher.py）
- [ ] 掃描 + 番號辨識模組（scanner.py）
- [ ] 改名邏輯模組（renamer.py）
- [ ] 快取系統
- [ ] 已處理日誌
- [ ] 啟動器（launcher.ps1 + .bat）

---

## 更新記錄

### 2026-05-04
- 新增 naming_convention.md（命名規範）
- 新增 test_sources.py（資料來源測試腳本，Playwright 版）
- 測試結果：javdb 可用、javbus webdriver 偵測封鎖、javlibrary Cloudflare 封鎖
- 確認 javdb `.origin-title` 選擇器可取得日文原名
- 建立專案文件架構
