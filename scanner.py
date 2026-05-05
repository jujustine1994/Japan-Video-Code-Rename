import re
import json
from pathlib import Path
from collections import defaultdict

SUPPORTED_EXTS = {".mp4", ".webm", ".srt"}
_CODE_RE = re.compile(r"([A-Za-z]{2,10})-(\d{2,5})")
_CODE_NOHYPHEN_RE = re.compile(r"([A-Za-z]{2,10})[\s_-]?(\d{3,5})")


def extract_code(filename: str) -> str | None:
    stem = Path(filename).stem
    m = _CODE_RE.search(stem)
    if m:
        return f"{m.group(1).upper()}-{m.group(2)}"
    m = _CODE_NOHYPHEN_RE.search(stem)
    if m:
        return f"{m.group(1).upper()}-{m.group(2)}"
    return None


def load_processed_log(log_file: str) -> set:
    path = Path(log_file)
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    names = set(data.keys())
    for entry in data.values():
        if isinstance(entry, dict) and "new_filename" in entry:
            names.add(entry["new_filename"])
    return names


def scan(target_dir: str, processed_log_file: str) -> list:
    processed = load_processed_log(processed_log_file)
    to_process = []
    for f in Path(target_dir).iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in SUPPORTED_EXTS:
            continue
        if f.name in processed:
            continue
        to_process.append(f)
    return to_process


def group_by_code(filenames: list) -> dict:
    groups: dict = defaultdict(list)
    for name in filenames:
        code = extract_code(name)
        if code:
            groups[code].append(name)
    return dict(groups)
