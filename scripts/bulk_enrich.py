# scripts/bulk_enrich.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import argparse
import json

from fetcher import Fetcher
from enricher import LookupEnricher

LOOKUP_FILE = "data/javdb_lookup.json"
CACHE_FILE  = "cache/javdb_cache.json"
STATE_FILE  = "data/enrich_state.json"


def _load_state() -> dict:
    p = Path(STATE_FILE)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"last_page": 0, "total_imported": 0}


def _save_state(state: dict) -> None:
    p = Path(STATE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Bulk enrich javdb_lookup.json from listing pages"
    )
    parser.add_argument("--max-pages", type=int, default=100,
                        help="本次最多爬幾頁（預設 100）")
    args = parser.parse_args()

    state      = _load_state()
    start_page = state.get("last_page", 0) + 1
    print(f"從第 {start_page} 頁開始，最多爬 {args.max_pages} 頁")

    fetcher  = Fetcher(CACHE_FILE, LOOKUP_FILE)
    enricher = LookupEnricher(LOOKUP_FILE, CACHE_FILE)

    fetcher.start()
    try:
        new_count, last_page = enricher.scrape_listing_pages(
            fetcher,
            start_page=start_page,
            max_pages=args.max_pages,
            progress_cb=print,
        )
    finally:
        fetcher.stop()

    state["last_page"]      = last_page
    state["total_imported"] = state.get("total_imported", 0) + new_count
    _save_state(state)

    print(f"\n完成：本次 +{new_count} 筆，總計 {state['total_imported']} 筆，停在第 {last_page} 頁")


if __name__ == "__main__":
    main()
