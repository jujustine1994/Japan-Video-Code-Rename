# community_sync.py
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
import urllib.request

COMMUNITY_REPO_OWNER = "PLACEHOLDER_OWNER"
COMMUNITY_REPO_NAME  = "PLACEHOLDER_REPO"
COMMUNITY_RAW_BASE   = (
    f"https://raw.githubusercontent.com"
    f"/{COMMUNITY_REPO_OWNER}/{COMMUNITY_REPO_NAME}/main"
)
COMMUNITY_API_BASE   = (
    f"https://api.github.com/repos"
    f"/{COMMUNITY_REPO_OWNER}/{COMMUNITY_REPO_NAME}"
)
COMMUNITY_TOKEN      = "PLACEHOLDER_TOKEN"

CHUNK_SIZE   = 1000
BACKUP_COUNT = 3
CODE_REGEX   = re.compile(r"^[A-Z]+-\d+$")


class CommunitySync:

    def __init__(self, local_lookup_path: Path):
        self.local_lookup_path = local_lookup_path

    def _load_local(self) -> dict:
        if not self.local_lookup_path.exists():
            return {}
        return json.loads(self.local_lookup_path.read_text(encoding="utf-8"))

    def _fetch_url(self, url: str) -> bytes:
        req = urllib.request.Request(
            url, headers={"User-Agent": "av-code-rename"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read()

    def get_community_stats(self) -> dict:
        try:
            data = self._fetch_url(f"{COMMUNITY_RAW_BASE}/community_stats.json")
            return json.loads(data)
        except Exception:
            return {"count": 0, "last_updated": "無法取得"}

    def get_contribute_count(self) -> int:
        local = self._load_local()
        try:
            data = self._fetch_url(f"{COMMUNITY_RAW_BASE}/javdb_community.json")
            community = json.loads(data)
        except Exception:
            return 0
        return sum(
            1 for code, entry in local.items()
            if code not in community
            and not entry.get("partial", False)
            and entry.get("actresses")
        )

    def download(self, backup_dir: Path, progress_cb=None) -> int:
        raise NotImplementedError

    def contribute(self, progress_cb=None) -> int:
        raise NotImplementedError

    def _create_issue(self, title: str, body: str):
        raise NotImplementedError
