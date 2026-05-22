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
    return {"total_imported": 0}


def _save_state(state: dict) -> None:
    p = Path(STATE_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="Bulk enrich javdb_lookup.json from listing pages"
    )
    parser.add_argument("--max-pages", type=int, default=100,
                        help="本次最多爬幾頁（預設 100，safety limit）")
    parser.add_argument("--stop-after-known", type=int, default=50,
                        help="連續幾筆已知番號後停止（預設 50）")
    args = parser.parse_args()

    state = _load_state()
    print(f"開始爬取，最多 {args.max_pages} 頁，連續 {args.stop_after_known} 筆已知後停止")

    fetcher  = Fetcher(CACHE_FILE, LOOKUP_FILE)
    enricher = LookupEnricher(LOOKUP_FILE, CACHE_FILE)

    fetcher.start()
    try:
        new_count = enricher.scrape_new_releases(
            fetcher,
            stop_after_known=args.stop_after_known,
            max_pages=args.max_pages,
            progress_cb=print,
        )
    finally:
        fetcher.stop()

    state["total_imported"] = state.get("total_imported", 0) + new_count
    _save_state(state)

    print(f"\n完成：本次 +{new_count} 筆，總計 {state['total_imported']} 筆")


if __name__ == "__main__":
    main()
