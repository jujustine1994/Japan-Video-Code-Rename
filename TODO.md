# TODO

## 下一步

- [ ] 端對端測試（建議先複製 5-10 個檔案到測試資料夾再跑）
- [ ] 確認性別過濾正確（男優應被排除）
- [ ] 確認多集邏輯正確（同番號多檔案出現 `(1)` `(2)` 後綴）
- [ ] 若有 bug，回報錯誤訊息修復

## 已完成

- [x] 完成 TUI 設計與規格確認
- [x] 建立 implementation plan
- [x] `scanner.py`：掃描資料夾、辨識番號、過濾已處理檔案
- [x] `fetcher.py`：javdb Playwright 爬蟲、快取讀寫、性別過濾
- [x] `renamer.py`：套用命名規範、執行改名、寫入 log
- [x] `main.py`：4-Phase TUI 主程式
- [x] `requirements.txt`
- [x] `launcher.ps1`（含首次安裝說明）
- [x] `AV Code Rename 啟動器.bat`

## 已解決的設計決策

- 男優過濾：自動偵測（訪問 javdb 演員頁面，h2 含「男優」→ 排除）
- javdb `.origin-title` 後綴：自動從片名尾部去除女優名
- 查無資料的檔案：歸入「不確定」，維持原狀，記錄至 skipped.json
- 番號辨識：支援標準格式（DDT-435）+ 容錯（ddt435, ddt 435）
