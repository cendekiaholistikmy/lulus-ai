import { json } from '@sveltejs/kit';
import { runPy } from '$lib/server/py.js';

const CMDS = new Set(['entries', 'form', 'extract', 'validate']);

export async function POST({ request }) {
  const body = await request.json().catch(() => null);
  if (!body || !CMDS.has(body.cmd)) return json({ error: 'Unknown command.' }, { status: 400 });
  if (body.cmd !== 'entries' && !/^[A-Za-z0-9_-]{1,40}$/.test(body.entry ?? '')) return json({ error: 'Invalid entry point.' }, { status: 400 });
  try {
    const result = await runPy('bridge.py', { input: JSON.stringify(body), timeout: body.cmd === 'form' || body.cmd === 'entries' ? 300_000 : 900_000 });
    if (result.error) return json({ error: result.error }, { status: 422 });
    return json(result);
  } catch (error) { return json({ error: error.message }, { status: 502 }); }
}
