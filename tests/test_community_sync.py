# tests/test_community_sync.py
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
from community_sync import CommunitySync

SAMPLE_LOCAL = {
    "SSIS-001": {"title": "タイトルA", "actresses": ["女優A"], "partial": False},
    "IPX-001":  {"title": "タイトルB", "actresses": ["女優B"], "partial": False},
    "NEW-001":  {"title": "タイトルC", "actresses": [],         "partial": True},
    "OLD-001":  {"title": "タイトルD", "actresses": [],         "partial": False},
}
SAMPLE_COMMUNITY = {"SSIS-001": "タイトルA", "OLD-001": "タイトルD"}
SAMPLE_STATS = {"count": 2, "last_updated": "2026-06-10T00:00:00Z"}


def _make_sync(tmp_path):
    p = tmp_path / "javdb_lookup.json"
    p.write_text(json.dumps(SAMPLE_LOCAL), encoding="utf-8")
    return CommunitySync(p)


def test_get_community_stats_success(tmp_path):
    sync = _make_sync(tmp_path)
    with patch.object(sync, "_fetch_url", return_value=json.dumps(SAMPLE_STATS).encode()):
        result = sync.get_community_stats()
    assert result["count"] == 2
    assert result["last_updated"] == "2026-06-10T00:00:00Z"


def test_get_community_stats_error(tmp_path):
    sync = _make_sync(tmp_path)
    with patch.object(sync, "_fetch_url", side_effect=Exception("network error")):
        result = sync.get_community_stats()
    assert result["count"] == 0
    assert result["last_updated"] == "無法取得"


def test_get_contribute_count(tmp_path):
    sync = _make_sync(tmp_path)
    # SSIS-001 already in community → skip
    # IPX-001 not in community + partial=False + actresses → count
    # NEW-001 partial=True → skip
    # OLD-001 not partial but actresses=[] → skip
    with patch.object(sync, "_fetch_url", return_value=json.dumps(SAMPLE_COMMUNITY).encode()):
        count = sync.get_contribute_count()
    assert count == 1  # only IPX-001


def test_get_contribute_count_network_error(tmp_path):
    sync = _make_sync(tmp_path)
    with patch.object(sync, "_fetch_url", side_effect=Exception("timeout")):
        count = sync.get_contribute_count()
    assert count == 0


def test_download_merges_new_entries(tmp_path):
    sync = _make_sync(tmp_path)
    backup_dir = tmp_path / "backups"

    def fake_fetch(url):
        return json.dumps({"SSIS-001": "タイトルA", "BRAND_NEW-001": "新タイトル"}).encode()

    with patch.object(sync, "_fetch_url", side_effect=fake_fetch):
        added = sync.download(backup_dir)

    assert added == 1
    result = json.loads(sync.local_lookup_path.read_text(encoding="utf-8"))
    assert "BRAND_NEW-001" in result
    assert result["BRAND_NEW-001"]["partial"] is True
    assert result["BRAND_NEW-001"]["actresses"] == []
    # 原有資料不被覆蓋
    assert result["SSIS-001"]["actresses"] == ["女優A"]


def test_download_creates_backup(tmp_path):
    sync = _make_sync(tmp_path)
    backup_dir = tmp_path / "backups"

    with patch.object(sync, "_fetch_url", return_value=b"{}"):
        sync.download(backup_dir)

    backups = list(backup_dir.glob("javdb_lookup_*.json"))
    assert len(backups) == 1


def test_download_keeps_max_backups(tmp_path):
    sync = _make_sync(tmp_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    # 預先放 3 個舊備份
    for i in range(3):
        (backup_dir / f"javdb_lookup_2026010{i}_000000.json").write_text("{}")

    with patch.object(sync, "_fetch_url", return_value=b"{}"):
        sync.download(backup_dir)

    backups = list(backup_dir.glob("javdb_lookup_*.json"))
    assert len(backups) == 3  # 最舊的被刪，維持 3 份


def test_download_network_error_returns_zero(tmp_path):
    sync = _make_sync(tmp_path)
    with patch.object(sync, "_fetch_url", side_effect=Exception("timeout")):
        added = sync.download(tmp_path / "backups")
    assert added == 0


def test_contribute_sends_only_complete_entries(tmp_path):
    sync = _make_sync(tmp_path)
    issues_created = []

    def fake_fetch(url):
        return json.dumps(SAMPLE_COMMUNITY).encode()

    def fake_create_issue(entries):
        issues_created.append(entries)

    with patch.object(sync, "_fetch_url", side_effect=fake_fetch), \
         patch.object(sync, "_create_issue", side_effect=fake_create_issue):
        sent = sync.contribute()

    # IPX-001 only (SSIS-001 already in community; NEW-001 partial; OLD-001 no actresses)
    assert sent == 1
    assert len(issues_created) == 1
    assert "IPX-001" in issues_created[0]
    assert "NEW-001" not in issues_created[0]


def test_contribute_chunks_large_dataset(tmp_path):
    # 2500 entries → 3 Issues (ceil(2500/1000))
    large_local = {
        f"CODE-{i:04d}": {"title": f"タイトル{i}", "actresses": ["女優"], "partial": False}
        for i in range(2500)
    }
    p = tmp_path / "javdb_lookup.json"
    p.write_text(json.dumps(large_local), encoding="utf-8")
    sync = CommunitySync(p)

    issues_created = []
    with patch.object(sync, "_fetch_url", return_value=b"{}"), \
         patch.object(sync, "_create_issue", side_effect=lambda e: issues_created.append(e)), \
         patch("time.sleep"):
        sent = sync.contribute()

    assert sent == 2500
    assert len(issues_created) == 3


def test_contribute_nothing_to_send(tmp_path):
    sync = _make_sync(tmp_path)
    full_community = {
        "SSIS-001": "A", "IPX-001": "B", "OLD-001": "D"
    }
    with patch.object(sync, "_fetch_url", return_value=json.dumps(full_community).encode()), \
         patch.object(sync, "_create_issue") as mock_issue:
        sent = sync.contribute()
    assert sent == 0
    mock_issue.assert_not_called()
