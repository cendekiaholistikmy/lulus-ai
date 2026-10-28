import { json } from '@sveltejs/kit';
import { ask } from '$lib/server/ollama.js';

export async function POST({ request }) {
  const { question, missing = [], values = {}, errors = {}, context = '' } = (await request.json().catch(() => ({})));
  if (!question?.trim()) return json({ error: 'Ask a question first.' }, { status: 400 });
  try {
    const answer = await ask([
      { role: 'system', content: 'You are lulus.ai, a concise Malaysian SSM filing assistant. Use only the supplied context (form values, validation errors, source document text). Help users understand missing fields and validation errors, and say where in the document a value may be found. If the context does not contain the answer, say so. Never promise acceptance by SSM.' },
      { role: 'user', content: `Missing fields: ${JSON.stringify(missing.slice(0, 60))}\nFilled values: ${JSON.stringify(values).slice(0, 4000)}\nValidation errors: ${JSON.stringify(errors).slice(0, 2000)}\nDocument text (excerpt):\n${String(context).slice(0, 3000)}\n\nQuestion: ${question.slice(0, 1000)}` }
    ]);
    return json({ answer });
  } catch (error) { return json({ error: error.name === 'TimeoutError' ? 'The model took too long to answer.' : `Assistant unavailable: ${error.message}` }, { status: 502 }); }
}
