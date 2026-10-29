import { json } from '@sveltejs/kit';
import { writeFile, mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { runPy } from '$lib/server/py.js';

const MAX_BYTES = 25 * 1024 * 1024;

export async function POST({ request }) {
  const file = (await request.formData().catch(() => new FormData())).get('file');
  if (!(file instanceof File) || !file.size) return json({ error: 'PDF required.' }, { status: 400 });
  if (file.size > MAX_BYTES) return json({ error: 'PDF is larger than 25 MB.' }, { status: 413 });
  const buffer = Buffer.from(await file.arrayBuffer());
  if (buffer.subarray(0, 5).toString() !== '%PDF-') return json({ error: 'That file is not a PDF.' }, { status: 400 });
  const dir = await mkdtemp(join(tmpdir(), 'lulus-'));
  try {
    const path = join(dir, 'upload.pdf');
    await writeFile(path, buffer);
    const { pages = [], device } = await runPy('ocr.py', { args: [path], timeout: 900_000 });
    return json({ text: pages.map((p) => p.text).join('\n\n'), pageData: pages, pages: pages.length, device });
  } catch (error) { return json({ error: error.message }, { status: 502 }); }
  finally { await rm(dir, { recursive: true, force: true }); }
}
