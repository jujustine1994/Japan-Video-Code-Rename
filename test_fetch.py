import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from fetcher import Fetcher
from renamer import build_filename
from scanner import extract_code

# ── extract_code 邊界案例 ─────────────────────────────────────

# 標準格式
def test_extract_standard():
    assert extract_code("SONE-001.mp4") == "SONE-001"

def test_extract_lowercase():
    assert extract_code("sone-001.mp4") == "SONE-001"

def test_extract_mixed_case():
    assert extract_code("Sone-001.mp4") == "SONE-001"

# 括弧包覆
def test_extract_brackets():
    assert extract_code("[SONE-001].mp4") == "SONE-001"

def test_extract_brackets_with_title():
    assert extract_code("[SONE-001] 葵つかさ 1080p.mp4") == "SONE-001"

def test_extract_brackets_multi_tag():
    assert extract_code("[Studio][SONE-001][葵つかさ][4K][H265].mp4") == "SONE-001"

# 無連字號
def test_extract_no_hyphen():
    assert extract_code("SONE001.mp4") == "SONE-001"

def test_extract_underscore_sep():
    assert extract_code("SONE_001.mp4") == "SONE-001"

def test_extract_space_sep():
    assert extract_code("SONE 001.mp4") == "SONE-001"

# 附加品質標籤
def test_extract_quality_suffix():
    assert extract_code("SONE-001_1080p.mp4") == "SONE-001"

def test_extract_date_dot_prefix():
    assert extract_code("2023.11.15.SONE-001.1080p.mp4") == "SONE-001"

# 已改名格式（再次掃描不應誤判）
def test_extract_already_renamed():
    assert extract_code("SONE-001 葵つかさ - タイトル名.mp4") == "SONE-001"

# 多集後綴
def test_extract_part_suffix_hyphen():
    assert extract_code("SONE-001-1.mp4") == "SONE-001"

def test_extract_part_suffix_underscore():
    assert extract_code("SONE-001_2.mp4") == "SONE-001"

# 較長番號前綴
def test_extract_long_prefix():
    assert extract_code("CARIB-001.mp4") == "CARIB-001"

def test_extract_very_short_prefix():
    assert extract_code("AB-12.mp4") == "AB-12"

# 不應匹配的情況
def test_extract_no_code_returns_none():
    assert extract_code("no_code_file.mp4") is None

def test_extract_japanese_only_returns_none():
    assert extract_code("日本語タイトルのみ.mp4") is None

def test_extract_digits_overflow_returns_none():
    assert extract_code("SONE-123456.mp4") is None  # 6 位超出上限

# ── build_filename 單元測試（pytest） ─────────────────────────

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

CACHE_FILE  = "cache/test_fetch_cache.json"
LOOKUP_FILE = "data/javdb_lookup.json"

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
    fetcher = Fetcher(CACHE_FILE, LOOKUP_FILE)
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
