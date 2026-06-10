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

COMMUNITY_REPO_OWNER = "jujustine1994"
COMMUNITY_REPO_NAME  = "Japan-Video-Code-Rename"
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
            data = self._fetch_url(f"{COMMUNITY_RAW_BASE}/data/community_stats.json")
            return json.loads(data)
        except Exception:
            return {"count": 0, "last_updated": "無法取得"}

    def get_contribute_count(self) -> int:
        local = self._load_local()
        try:
            data = self._fetch_url(f"{COMMUNITY_RAW_BASE}/data/javdb_community.json")
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
        if progress_cb:
            progress_cb("下載社群資料庫中...")
        try:
            data = self._fetch_url(f"{COMMUNITY_RAW_BASE}/data/javdb_community.json")
            community: dict = json.loads(data)
        except Exception as e:
            if progress_cb:
                progress_cb(f"[ERROR] 無法下載社群資料庫：{e}")
            return 0

        backup_dir.mkdir(parents=True, exist_ok=True)
        if self.local_lookup_path.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = backup_dir / f"javdb_lookup_{ts}.json"
            shutil.copy2(self.local_lookup_path, dst)
            if progress_cb:
                progress_cb(f"已備份至 {dst.name}")
            backups = sorted(backup_dir.glob("javdb_lookup_*.json"))
            for old in backups[:-BACKUP_COUNT]:
                old.unlink()

        local = self._load_local()
        added = 0
        for code, title in community.items():
            if code not in local:
                local[code] = {"title": title, "actresses": [], "partial": True}
                added += 1

        self.local_lookup_path.parent.mkdir(parents=True, exist_ok=True)
        self.local_lookup_path.write_text(
            json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if progress_cb:
            progress_cb(f"下載完成：新增 {added:,} 筆")
        return added

    def contribute(self, progress_cb=None) -> int:
        if progress_cb:
            progress_cb("計算可貢獻筆數中...")
        try:
            data = self._fetch_url(f"{COMMUNITY_RAW_BASE}/data/javdb_community.json")
            community: dict = json.loads(data)
        except Exception as e:
            if progress_cb:
                progress_cb(f"[ERROR] 無法下載社群資料庫：{e}")
            return 0

        local = self._load_local()
        new_entries = {
            code: entry["title"]
            for code, entry in local.items()
            if code not in community
            and not entry.get("partial", False)
            and entry.get("actresses")
        }

        if not new_entries:
            if progress_cb:
                progress_cb("沒有可貢獻的新番號")
            return 0

        total = len(new_entries)
        if progress_cb:
            progress_cb(f"共 {total:,} 筆可貢獻，開始送出...")

        sent = 0
        codes = list(new_entries.items())
        for batch_start in range(0, total, CHUNK_SIZE):
            chunk = dict(codes[batch_start:batch_start + CHUNK_SIZE])
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            title = f"[community-db] batch +{len(chunk)} entries {ts}"
            body = json.dumps(
                {"source": "av-code-rename", "version": 1, "entries": chunk},
                ensure_ascii=False,
            )
            try:
                self._create_issue(title, body)
                sent += len(chunk)
                if progress_cb:
                    progress_cb(f"已送出 {sent:,} / {total:,} 筆")
                time.sleep(2)
            except Exception as e:
                if progress_cb:
                    progress_cb(f"[ERROR] 送出失敗：{e}")
                break

        if progress_cb:
            progress_cb(f"貢獻完成：送出 {sent:,} 筆，等待 GitHub Action 驗證後合併")
        return sent

    def _create_issue(self, title: str, body: str):
        payload = json.dumps({"title": title, "body": body}).encode("utf-8")
        req = urllib.request.Request(
            f"{COMMUNITY_API_BASE}/issues",
            data=payload,
            headers={
                "Authorization": f"Bearer {COMMUNITY_TOKEN}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "av-code-rename",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"HTTP {resp.status}")
