import json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

CODE_REGEX     = re.compile(r'^[A-Z]+-\d+$')
DB_PATH        = Path('data/javdb_community.json')
STATS_PATH     = Path('data/community_stats.json')
MAX_BODY_BYTES = 100_000   # GitHub issue body cap is ~65KB; 100KB is defense-in-depth
MAX_ENTRIES    = 1_000
MAX_TITLE_LEN  = 200


def validate_payload(body_str):
    """Returns (payload, error_msg). error_msg is None on success."""
    if len(body_str.encode('utf-8')) > MAX_BODY_BYTES:
        return None, "❌ 拒絕：請求內容過大"
    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        return None, "❌ 解析失敗：JSON 格式錯誤"
    if payload.get('source') != 'av-code-rename' or payload.get('version') != 1:
        return None, "❌ 驗證失敗：source 或 version 不符"
    entries = payload.get('entries', {})
    if not isinstance(entries, dict) or not (1 <= len(entries) <= MAX_ENTRIES):
        count = len(entries) if isinstance(entries, dict) else 'N/A'
        return None, f"❌ 驗證失敗：entries 筆數須介於 1–{MAX_ENTRIES}（收到 {count} 筆）"
    return payload, None


def filter_entries(entries, community):
    """Returns (valid_dict, skipped_count)."""
    valid = {}
    skipped = 0
    for code, title in entries.items():
        if not CODE_REGEX.match(str(code)):
            skipped += 1
            continue
        if not isinstance(title, str) or not title.strip():
            skipped += 1
            continue
        if len(title) > MAX_TITLE_LEN:
            skipped += 1
            continue
        if code in community:
            skipped += 1
            continue
        valid[code] = title
    return valid, skipped


if __name__ == '__main__':
    issue_number = os.environ['ISSUE_NUMBER']
    body         = os.environ['ISSUE_BODY']

    def close_issue(comment):
        comment_escaped = comment.replace('"', '\\"').replace('\n', '\\n')
        os.system(f'gh issue comment {issue_number} --body "{comment_escaped}"')
        os.system(f'gh issue close {issue_number}')
        sys.exit(0)

    payload, err = validate_payload(body)
    if err:
        close_issue(err)

    community = json.loads(DB_PATH.read_text(encoding='utf-8')) if DB_PATH.exists() else {}
    entries   = payload['entries']

    valid_entries, skipped = filter_entries(entries, community)
    added = len(valid_entries)

    if added == 0:
        close_issue(f"ℹ️ 無新增（跳過 {skipped} 筆，已存在或格式不符）")

    community.update(valid_entries)

    DB_PATH.write_text(json.dumps(community, ensure_ascii=False, indent=2), encoding='utf-8')

    stats = {
        'count': len(community),
        'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    }
    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')

    subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
    subprocess.run(['git', 'config', 'user.email',
                    'github-actions[bot]@users.noreply.github.com'], check=True)
    subprocess.run(['git', 'add', 'data/javdb_community.json', 'data/community_stats.json'], check=True)
    subprocess.run(['git', 'commit', '-m',
                    f'community: +{added} entries (issue #{issue_number})'], check=True)
    subprocess.run(['git', 'push'], check=True)

    close_issue(f"✓ 已合併 {added:,} 筆新番號（跳過 {skipped} 筆）")
