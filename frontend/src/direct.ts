// Переклад напряму з браузера відвідувача до Space, за його власним анонімним лімітом.
// Жодних cookie чи токенів: gateway лише готує текст.
import { takeEvents } from './sse.ts';

export interface PreparedCall {
  url: string;
  direction: string;
  batches: string[];
  layout: number[]; // кількість сегментів у кожному рядку
}

const FAILED = 'Hugging Face could not translate the text. Try again later.';
const QUOTA_USED = 'Your own free limit on Hugging Face is used up too. Try again tomorrow.';

type Send = typeof fetch;

async function callSpace(
  call: PreparedCall,
  batch: string,
  signal: AbortSignal | undefined,
  send: Send,
): Promise<string[]> {
  const endpoint = `${call.url}/gradio_api/call/translate`;
  const submitted = await send(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data: [batch, call.direction] }),
    credentials: 'omit',
    signal,
  });
  if (!submitted.ok) throw new Error(FAILED);
  const { event_id: id } = (await submitted.json()) as { event_id: string };

  const response = await send(`${endpoint}/${id}`, { method: 'GET', credentials: 'omit', signal });
  if (!response.ok) throw new Error(FAILED);
  for (const { event, data } of takeEvents(await response.text()).events) {
    if (event === 'error') throw new Error(/quota/i.test(data) ? QUOTA_USED : FAILED);
    if (event === 'complete') return (JSON.parse(data) as [string])[0].split('\n');
  }
  throw new Error(FAILED);
}

export async function translateDirect(
  call: PreparedCall,
  signal?: AbortSignal,
  send: Send = (input, init) => fetch(input, init),
): Promise<string> {
  const segments: string[] = [];
  for (const batch of call.batches) {
    const lines = await callSpace(call, batch, signal, send);
    if (lines.length !== batch.split('\n').length) throw new Error(FAILED);
    segments.push(...lines.map((line) => line.trim()));
  }
  let next = 0;
  return call.layout.map((count) => segments.slice(next, (next += count)).join(' ')).join('\n');
}
