# tests/test_process_contribution.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / '.github' / 'scripts'))
import process_contribution as pc


def _body(entries, source='av-code-rename', version=1):
    return json.dumps({'source': source, 'version': version, 'entries': entries})


# --- validate_payload ---

def test_valid_payload_passes():
    payload, err = pc.validate_payload(_body({'ABC-001': 'タイトル'}))
    assert err is None
    assert payload['entries'] == {'ABC-001': 'タイトル'}


def test_body_too_large_rejected():
    huge = 'x' * (pc.MAX_BODY_BYTES + 1)
    _, err = pc.validate_payload(huge)
    assert err is not None and '過大' in err


def test_invalid_json_rejected():
    _, err = pc.validate_payload('not json')
    assert err is not None and 'JSON' in err


def test_wrong_source_rejected():
    _, err = pc.validate_payload(_body({'ABC-001': 'T'}, source='other'))
    assert err is not None


def test_wrong_version_rejected():
    _, err = pc.validate_payload(_body({'ABC-001': 'T'}, version=2))
    assert err is not None


def test_empty_entries_rejected():
    _, err = pc.validate_payload(_body({}))
    assert err is not None and '筆數' in err


def test_entries_over_limit_rejected():
    entries = {f'AB-{i:04d}': 'x' for i in range(pc.MAX_ENTRIES + 1)}
    _, err = pc.validate_payload(_body(entries))
    assert err is not None


# --- filter_entries ---

def test_valid_entry_accepted():
    valid, skipped = pc.filter_entries({'ABC-001': 'タイトル'}, {})
    assert valid == {'ABC-001': 'タイトル'}
    assert skipped == 0


def test_title_too_long_skipped():
    long_title = 'A' * (pc.MAX_TITLE_LEN + 1)
    valid, skipped = pc.filter_entries({'ABC-001': long_title}, {})
    assert skipped == 1
    assert 'ABC-001' not in valid


def test_title_at_limit_accepted():
    valid, skipped = pc.filter_entries({'ABC-001': 'A' * pc.MAX_TITLE_LEN}, {})
    assert skipped == 0
    assert 'ABC-001' in valid


def test_invalid_code_format_skipped():
    entries = {'abc-001': 'T', 'ABC': 'T', '123-456': 'T'}
    _, skipped = pc.filter_entries(entries, {})
    assert skipped == 3


def test_existing_key_skipped():
    _, skipped = pc.filter_entries({'ABC-001': 'New'}, {'ABC-001': 'Old'})
    assert skipped == 1


def test_empty_title_skipped():
    _, skipped = pc.filter_entries({'ABC-001': '   ', 'ABC-002': ''}, {})
    assert skipped == 2


def test_non_string_title_skipped():
    _, skipped = pc.filter_entries({'ABC-001': 123, 'ABC-002': None}, {})
    assert skipped == 2


def test_mixed_valid_and_invalid():
    entries = {
        'ABC-001': 'タイトルA',           # valid
        'abc-002': 'タイトルB',           # invalid code (lowercase)
        'ABC-003': 'A' * 201,             # title too long
        'ABC-004': 'タイトルD',           # valid
        'ABC-005': 'existing',            # already in community
    }
    community = {'ABC-005': 'existing'}
    valid, skipped = pc.filter_entries(entries, community)
    assert len(valid) == 2
    assert skipped == 3
    assert 'ABC-001' in valid
    assert 'ABC-004' in valid
