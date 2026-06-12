# PITFALLS

## 已踩過的坑

---

### P1：javbus /doc/driver-verify 無法繞過

**問題**：javbus.com 偵測到 Playwright webdriver，所有請求重導向至 `/doc/driver-verify`。
**原因**：javbus 使用 navigator.webdriver 等瀏覽器指紋偵測自動化工具，即使套用 playwright-stealth v2 仍無效。
**解法**：放棄 javbus，改用 javdb。
**禁止**：不要再嘗試用 requests、cloudscraper 或 Playwright 存取 javbus。

---

### P2：javlibrary Cloudflare 封鎖（已解決，2026-06）

**問題**：javlibrary.com 被 Cloudflare 完全封鎖，返回 HTTP 403。
**原因**：Cloudflare 的 Bot Management，headless Playwright 無法通過。
**解法**：改用 `nodriver`（真實 Chrome，`headless=False`，視窗推到螢幕外 `-32000,0`）。CF challenge 啟動時解一次（約 6–10 秒），同 session 後續請求不需重解。
**現狀**：`javlibrary_fetcher.py` 已整合為主要查詢來源；`bulk_enrich_javlibrary.py` 用於全量建置。
**禁止**：不要改回 headless Playwright，CF 偵測 headless 屬性，headless=False 才能過。

---

### P3：playwright-stealth v2 API 改變

**問題**：`from playwright_stealth import stealth_sync` 在 v2 會 ImportError。
**原因**：v2 改為 `Stealth` 類別。
**正確用法**：
```python
from playwright_stealth.stealth import Stealth
Stealth().apply_stealth_sync(page)
```

---

### P4：javdb 片名含女優名後綴

**問題**：javdb 的 `.origin-title` 元素文字格式為 `片名 女優名`（例：`解禁アナル・FUCK 吉田花`）。
**原因**：javdb 顯示慣例，片名後面帶女優名。
**解法**：建檔名時，需取得女優名清單後，從 origin-title 尾部去除女優名，只留純片名。

---

### P5：javdb 演員清單混入男性

**問題**：javdb `演員` 欄位同時列出女優和男導演/男優（例 GTJ-065 的 `佐川銀次`）。
**原因**：javdb 不區分性別，一律歸類為演員。
**解法**：自動偵測——對每位演員訪問其 javdb 頁面，檢查 `h2` 是否含「男優」字串。含「男優」→ 排除；否則視為女優保留。結果快取於 `cache/javdb_cache.json` 的 `_actors` 欄位。
**注意**：javdb actor 頁面 h2 格式：男優顯示 `{名}\n男優, N 部影片`；女優無性別標籤。

---

### P6：Windows 終端機 cp950 編碼問題

**問題**：Python 腳本直接用 `print()` 輸出 Unicode（emoji、日文）時報 UnicodeEncodeError。
**原因**：Windows cmd/PowerShell 預設 cp950，無法編碼 Unicode 字元。
**解法**：腳本開頭加：
```python
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
```

---

### P7：javscraper 的 DMM 來源台灣地區封鎖

**問題**：`javscraper.DMM().get_video("SSIS-001")` 拋出 `list index out of range`。
**原因**：`dmm.co.jp` 對台灣 IP 回傳地區封鎖頁面，XPath 解析不到預期的 HTML 元素，取 `[0]` 時炸掉。
**解法**：不適用（除非走日本 IP proxy）。
**禁止**：不要嘗試用 javscraper 搭配 DMM/MGStage/JAVLibrary 在台灣直連——三個來源全部失敗。

---

### P8：r18.dev JSON API 台灣地區封鎖

**問題**：`GET https://r18.dev/videos/vod/movies/detail/-/dvd_id=SSIS-001/json/` 回傳 HTTP 403。
**原因**：r18.dev 是 DMM 的海外平台，現已對台灣 IP 封鎖。
**解法**：不適用（除非走非封鎖地區 IP）。
**禁止**：不要再嘗試 r18.dev API。

---

### P9：javbus 改為地區偵測封鎖（2026-05）

**問題**：javbus 搜尋結果頁顯示「所在地區年齡檢測」，無法取得影片資料。
**原因**：javbus 從原本的 `driver-verify`（偵測 webdriver）改為地區封鎖，台灣 IP 直接被擋。
**解法**：放棄 javbus。
**禁止**：不要再嘗試任何方式存取 javbus（requests / cloudscraper / Playwright 均無效）。

---

### P10：.bat 啟動器無法自訂 Windows 工具列圖示

**問題**：雙擊 `.bat` 啟動程式後，工具列顯示的是 `powershell.exe` 的原生圖示，無法顯示自訂圖示。
**原因**：Windows 工具列圖示是依照實際執行的程序（process）決定的。本專案鏈結為 `.bat` → `launcher.ps1` → `python main.py`，工具列看到的是 PowerShell 程序，不是啟動器本身。
**已評估方案**：
- 建立帶圖示的捷徑並釘選到工具列（需從捷徑啟動才有效，直接點 `.bat` 無效）
- 用 PyInstaller 打包 `main.py` 為 `.exe`（最完整，但 Playwright 相依複雜）
**決定**：暫不處理，維持原生圖示。若日後要打包分發再考慮 PyInstaller。
