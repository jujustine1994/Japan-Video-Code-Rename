const CODE_RE     = /^[A-Z]+-\d+$/;
const MAX_ENTRIES = 1_000;
const MAX_TITLE   = 200;

export default {
  async fetch(request, env) {
    const { success } = await env.RATE_LIMITER.limit({ key: request.headers.get('CF-Connecting-IP') ?? 'unknown' });
    if (!success) {
      return json({ ok: false, error: 'Rate limit exceeded' }, 429);
    }

    if (request.method !== 'POST') {
      return json({ ok: false, error: 'Method not allowed' }, 405);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: 'Invalid JSON' }, 400);
    }

    const entries = body?.entries;
    if (!entries || typeof entries !== 'object' || Array.isArray(entries)) {
      return json({ ok: false, error: 'entries must be an object' }, 400);
    }

    const count = Object.keys(entries).length;
    if (count < 1 || count > MAX_ENTRIES) {
      return json({ ok: false, error: `entries count must be 1-${MAX_ENTRIES} (got ${count})` }, 400);
    }

    for (const [key, title] of Object.entries(entries)) {
      if (!CODE_RE.test(key)) {
        return json({ ok: false, error: `invalid code format: ${key}` }, 400);
      }
      if (typeof title !== 'string' || title.length === 0 || title.length > MAX_TITLE) {
        return json({ ok: false, error: `invalid title for ${key}` }, 400);
      }
    }

    const ts        = new Date().toISOString().slice(0, 19).replace('T', '_');
    const title     = `[community-db] batch +${count} entries ${ts}`;
    const issueBody = JSON.stringify({ source: 'av-code-rename', version: 1, entries });

    const resp = await fetch(
      `https://api.github.com/repos/${env.GITHUB_REPO}/issues`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${env.GITHUB_TOKEN}`,
          'Accept':        'application/vnd.github+json',
          'Content-Type':  'application/json',
          'User-Agent':    'av-community-worker',
        },
        body: JSON.stringify({ title, body: issueBody }),
      }
    );

    if (!resp.ok) {
      const err = await resp.text();
      return json({ ok: false, error: err }, 500);
    }

    return json({ ok: true, submitted: count });
  },
};

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
