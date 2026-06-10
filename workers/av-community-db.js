--fbd1df4f89b71d2935b5623f1c219875dabbdaccd1edf0caa063eecc93fb
Content-Disposition: form-data; name="worker.js"


  export default {
    async fetch(request, env) {

      // åªæ¥å POST
      if (request.method !== 'POST') {
        return json({ ok: false, error: 'Method not allowed' }, 405);
      }

      // è§£æ body
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ ok: false, error: 'Invalid JSON' }, 400);
      }

      // åºæ¬é©è­
      const entries = body?.entries;
      if (!entries || typeof entries !== 'object' || Object.keys(entries).length === 0) {
        return json({ ok: false, error: 'Missing or empty entries' }, 400);
      }

      const count = Object.keys(entries).length;
      const ts    = new Date().toISOString().slice(0, 19).replace('T', '_');
      const title = `[community-db] batch +${count} entries ${ts}`;
      const issueBody = JSON.stringify({
        source:  'av-code-rename',
        version: 1,
        entries: entries,
      });

      // å»º GitHub Issue
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
    }
  };

  function json(data, status = 200) {
    return new Response(JSON.stringify(data), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  }

--fbd1df4f89b71d2935b5623f1c219875dabbdaccd1edf0caa063eecc93fb--

