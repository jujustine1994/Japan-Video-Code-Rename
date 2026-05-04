import re
import json
from datetime import datetime
from pathlib import Path

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str) -> str:
    return _ILLEGAL.sub("", name).strip()


def strip_actress_suffix(title: str, actresses: list) -> str:
    result = title.strip()
    for name in actresses:
        if name and result.endswith(name):
            result = result[: -len(name)].strip()
    return result


def build_filename(code: str, actresses: list, title: str, ext: str, part=None) -> str:
    actress_str = " ".join(actresses) if actresses else "未知女優"
    part_str = f"({part})" if part else ""
    name = f"{code} {actress_str} - {title} {actress_str}{part_str}{ext}"
    return sanitize(name)


def rename_file(src: Path, new_name: str) -> bool:
    dst = src.parent / new_name
    try:
        src.rename(dst)
        return True
    except OSError:
        return False


def write_processed_log(log_file: str, original: str, new_name: str) -> None:
    path = Path(log_file)
    data: dict = {}
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    data[original] = {
        "new_filename": new_name,
        "renamed_at": datetime.now().isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_skipped_log(log_file: str, entries: list) -> None:
    path = Path(log_file)
    existing: list = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    existing.extend(entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
