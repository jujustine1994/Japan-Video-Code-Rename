import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from fetcher import Fetcher
from renamer import build_filename

# ── 單元測試（pytest） ────────────────────────────────────────

def test_build_filename_default():
    assert build_filename("GTJ-065", ["宮崎あや"], "串刺し拷問", ".mp4") == \
        "GTJ-065 宮崎あや - 串刺し拷問.mp4"

def test_build_filename_actress_last():
    assert build_filename("GTJ-065", ["宮崎あや"], "串刺し拷問", ".mp4",
                          format_order=["code", "title", "actress"]) == \
        "GTJ-065 - 串刺し拷問 宮崎あや.mp4"

def test_build_filename_actress_first():
    assert build_filename("GTJ-065", ["宮崎あや"], "串刺し拷問", ".mp4",
                          format_order=["actress", "code", "title"]) == \
        "宮崎あや GTJ-065 - 串刺し拷問.mp4"

def test_build_filename_title_first():
    assert build_filename("GTJ-065", ["宮崎あや"], "串刺し拷問", ".mp4",
                          format_order=["title", "code", "actress"]) == \
        "串刺し拷問 GTJ-065 宮崎あや.mp4"

def test_build_filename_with_part():
    assert build_filename("GTJ-065", ["宮崎あや"], "串刺し拷問", ".mp4",
                          part=1, format_order=["code", "actress", "title"]) == \
        "GTJ-065 宮崎あや - 串刺し拷問(1).mp4"

# ─────────────────────────────────────────────────────────────

CACHE_FILE = "cache/test_fetch_cache.json"

# 測試用番號清單
# GTJ-065 → 已知含男優「佐川銀次」，測試性別過濾
# SONE-001、ABW-001 → 一般女優作品
# FAKE-999 → 故意放一個查無結果的番號
TEST_CODES = [
    ("GTJ-065",  ".mp4"),   # 含男優，測過濾
    ("SONE-001", ".mp4"),   # 一般
    ("ABW-001",  ".mp4"),   # 一般
    ("FAKE-999", ".mp4"),   # 查無結果
]

SEP = "-" * 60


def main():
    fetcher = Fetcher(CACHE_FILE)
    fetcher.start()

    try:
        for code, ext in TEST_CODES:
            print(SEP)
            print(f"番號: {code}")
            result = fetcher.query(code)

            if not result:
                print("  ❌ javdb 查無資料")
                continue

            print(f"  片名: {result['title']}")
            print(f"  女優: {result['actresses']}")

            filename = build_filename(code, result["actresses"], result["title"], ext)
            print(f"  新檔名: {filename}")
    finally:
        fetcher.stop()

    print(SEP)
    print("測試完成")


if __name__ == "__main__":
    main()
