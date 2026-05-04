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

# AV Code Rename

自動掃描資料夾，將命名不符規範的 AV 影片檔案，透過查詢 javdb.com 取得正確片名與女優名後，以互動式介面逐一確認並重新命名。

## 系統需求

- Windows 10 / 11
- Python 3.10+
- 網路連線（需存取 javdb.com）
- 約 200MB 磁碟空間（Playwright Chromium）

## 執行方式

雙擊 `AV Code Rename 啟動器.bat`（主工具尚未完成，見 TODO.md）

### 目前可用：資料來源測試

```
python test_sources.py
```

## 命名規範

詳見 `naming_convention.md`。

標準格式：`[番號] [女優名(別名)] - [日文片名] [女優名].[副檔名]`

## 資料來源

- **主要**：javdb.com（Playwright 無頭瀏覽器）
- javbus / javlibrary：已測試，因 bot 偵測機制無法使用（詳見 PITFALLS.md）

## 首次設定

```bash
pip install playwright playwright-stealth beautifulsoup4 requests
python -m playwright install chromium
```
