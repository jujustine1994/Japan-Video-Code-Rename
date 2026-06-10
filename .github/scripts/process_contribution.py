import json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

CODE_REGEX = re.compile(r'^[A-Z]+-\d+$')
DB_PATH    = Path('data/javdb_community.json')
STATS_PATH = Path('data/community_stats.json')

issue_number = os.environ['ISSUE_NUMBER']
body         = os.environ['ISSUE_BODY']


def close_issue(comment):
    comment_escaped = comment.replace('"', '\\"').replace('\n', '\\n')
    os.system(f'gh issue comment {issue_number} --body "{comment_escaped}"')
    os.system(f'gh issue close {issue_number}')
    sys.exit(0)


try:
    payload = json.loads(body)
except json.JSONDecodeError:
    close_issue("❌ 解析失敗：JSON 格式錯誤")

if payload.get('source') != 'av-code-rename' or payload.get('version') != 1:
    close_issue("❌ 驗證失敗：source 或 version 不符")

community = json.loads(DB_PATH.read_text(encoding='utf-8')) if DB_PATH.exists() else {}
entries   = payload.get('entries', {})

added = skipped = 0
for code, title in entries.items():
    if not CODE_REGEX.match(str(code)):
        skipped += 1
        continue
    if not isinstance(title, str) or not title.strip():
        skipped += 1
        continue
    if code in community:
        skipped += 1
        continue
    community[code] = title
    added += 1

if added == 0:
    close_issue(f"ℹ️ 無新增（跳過 {skipped} 筆，已存在或格式不符）")

DB_PATH.write_text(json.dumps(community, ensure_ascii=False, indent=2), encoding='utf-8')

stats = {
    'count': len(community),
    'last_updated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
}
STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')

subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
subprocess.run(['git', 'config', 'user.email',
                'github-actions[bot]@users.noreply.github.com'], check=True)
subprocess.run(['git', 'add', 'javdb_community.json', 'community_stats.json'], check=True)
subprocess.run(['git', 'commit', '-m',
                f'community: +{added} entries (issue #{issue_number})'], check=True)
subprocess.run(['git', 'push'], check=True)

close_issue(f"✓ 已合併 {added:,} 筆新番號（跳過 {skipped} 筆）")
