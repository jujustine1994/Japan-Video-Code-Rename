# PITFALLS

## 已踩過的坑

---

### P1：javbus /doc/driver-verify 無法繞過

**問題**：javbus.com 偵測到 Playwright webdriver，所有請求重導向至 `/doc/driver-verify`。
**原因**：javbus 使用 navigator.webdriver 等瀏覽器指紋偵測自動化工具，即使套用 playwright-stealth v2 仍無效。
**解法**：放棄 javbus，改用 javdb。
**禁止**：不要再嘗試用 requests、cloudscraper 或 Playwright 存取 javbus。

---

### P2：javlibrary Cloudflare 封鎖

**問題**：javlibrary.com 被 Cloudflare 完全封鎖，返回 HTTP 403。
**原因**：Cloudflare 的 Bot Management，headless Playwright 無法通過。
**解法**：放棄 javlibrary，改用 javdb。

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
