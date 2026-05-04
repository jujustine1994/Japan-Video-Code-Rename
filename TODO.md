# TODO

## 下一步（照順序）

- [ ] 完成 TUI 設計與規格確認（brainstorming）
- [ ] 建立 implementation plan
- [ ] 建立 `scanner.py`：掃描資料夾、辨識番號、過濾已處理檔案
- [ ] 建立 `fetcher.py`：javdb Playwright 爬蟲、快取讀寫
- [ ] 建立 `renamer.py`：套用命名規範、執行改名、寫入 log
- [ ] 建立 `main.py`：主迴圈 TUI
- [ ] 建立 `requirements.txt`
- [ ] 建立 `launcher.ps1`（含首次安裝說明）
- [ ] 建立 `AV Code Rename 啟動器.bat`
- [ ] 端對端測試（小批量）

## 已知待決策

- javdb 演員清單包含男性（導演/男優），TUI 需讓使用者確認女優名單
- javdb `.origin-title` 後面帶女優名，需在建檔名時去除
- 番號辨識 regex 需處理各種格式（小寫、無連字號、特殊前綴）
