```
/*  ================================  *\
 *                                    *
 *          C  T  H                   *
 *        created by CTH              *
 *                                    *
\*  ================================  */
```

規則檔: windows-tool.md
類型: Windows 工具

# 超級老司機整理器

自動掃描資料夾，將命名不符規範的 AV 影片檔案，透過批次查詢 javdb.com 取得正確片名與女優名，產生更名清單後一次確認執行。

## 系統需求

- Windows 10 / 11
- Python 3.10+
- 網路連線（需存取 javdb.com）
- 約 200MB 磁碟空間（Playwright Chromium）

## 執行方式

雙擊 `AV Code Rename 啟動器.bat`

首次執行會自動安裝環境並詢問目標資料夾路徑。之後全自動批次處理，最後一次確認即可。

## 命名規範

詳見 `docs/naming_convention.md`。

標準格式：`[番號] [女優名(別名)] - [日文片名] [女優名].[副檔名]`

## 資料來源

- **主要**：javlibrary.com（nodriver 真實 Chrome，繞過 Cloudflare）
- **Fallback**：javdb.com（Playwright，需登入 session）
- javbus：地區封鎖（台灣 IP），無法使用（詳見 `docs/PITFALLS.md`）

## 首次設定

雙擊啟動器後自動完成（需要 `uv` 和 Python 3.10+，啟動器會自動偵測並安裝）。
