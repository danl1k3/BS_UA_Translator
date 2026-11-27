import assert from 'node:assert/strict';
import { test } from 'node:test';
import { translateDirect } from './src/direct.ts';

const PREPARED = {
  url: 'https://space.example',
  direction: 'bs-ua',
  batches: ['a\nb', 'c'],
  layout: [2, 0, 1],
};

function fakeSpace(...streams) {
  const calls = [];
  const send = async (url, init) => {
    calls.push({ url, init });
    if (init.method === 'POST') return new Response('{"event_id":"e1"}');
    return new Response(streams.shift());
  };
  return { calls, send };
}

const complete = (text) => `event: complete\ndata: ${JSON.stringify([text])}\n\n`;

test('sends every batch to the Space and restores the line breaks', async () => {
  const space = fakeSpace(complete('A\nB'), complete('C'));
  assert.equal(await translateDirect(PREPARED, undefined, space.send), 'A B\n\nC');
  assert.equal(space.calls[0].url, 'https://space.example/gradio_api/call/translate');
  assert.equal(space.calls[0].init.body, '{"data":["a\\nb","bs-ua"]}');
  assert.equal(space.calls[1].url, 'https://space.example/gradio_api/call/translate/e1');
});

test('never sends cookies or a token to the Space', async () => {
  const space = fakeSpace(complete('A\nB'), complete('C'));
  await translateDirect(PREPARED, undefined, space.send);
  for (const { init } of space.calls) {
    assert.equal(init.credentials, 'omit');
    assert.equal(init.headers?.Authorization, undefined);
  }
});

test('explains that the visitor quota is used up', async () => {
  const space = fakeSpace('event: error\ndata: {"error":"You have exceeded your GPU quota"}\n\n');
  await assert.rejects(translateDirect(PREPARED, undefined, space.send), /Your own free limit/);
});

test('reports other failures and incomplete answers', async () => {
  for (const stream of ['event: error\ndata: {"error":null}\n\n', complete('only one line'), '']) {
    const space = fakeSpace(stream);
    await assert.rejects(translateDirect(PREPARED, undefined, space.send), /Hugging Face/);
  }
});
