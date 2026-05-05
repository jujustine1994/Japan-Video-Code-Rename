import sys
sys.stdout.reconfigure(encoding="utf-8")
import time
from javscraper import DMM, MGStage, JAVLibrary

CODES = ["SSIS-001", "MIDE-123", "GTJ-065"]
SOURCES = [
    ("DMM",        DMM),
    ("MGStage",    MGStage),
    ("JAVLibrary", JAVLibrary),
]

for code in CODES:
    print(f"\n=== {code} ===")
    for name, cls in SOURCES:
        print(f"  {name}...", end="", flush=True)
        try:
            t = time.time()
            result = cls().get_video(code)
            el = time.time() - t
            if result:
                title = getattr(result, "name", None) or getattr(result, "title", None)
                actresses = getattr(result, "actresses", []) or []
                print(f" OK ({el:.1f}s)")
                print(f"    title:    {title}")
                print(f"    actress:  {actresses}")
            else:
                print(f" 查無資料 ({el:.1f}s)")
        except Exception as e:
            print(f" ERROR: {e}")
        time.sleep(1)
