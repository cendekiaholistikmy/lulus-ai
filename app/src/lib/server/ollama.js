import { env } from '$env/dynamic/private';
export const model = () => env.OLLAMA_MODEL ?? 'gemma3:4b';
// OLLAMA_URL matches the Python side; OLLAMA_HOST kept for backwards compatibility.
const base = () => (env.OLLAMA_URL ?? env.OLLAMA_HOST ?? 'http://localhost:11434').replace(/\/$/, '');
export async function ask(messages) {
  const response = await fetch(`${base()}/api/chat`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ model: model(), stream: false, options: { temperature: 0.2 }, messages }),
    signal: AbortSignal.timeout(180_000)
  });
  if (!response.ok) throw new Error(`Ollama returned ${response.status} (is ${model()} pulled?)`);
  return (await response.json()).message?.content ?? '';
}
