import assert from 'node:assert/strict';
import { test } from 'node:test';
import { takeEvents } from './src/sse.ts';

test('joins multi-line data with newlines and keeps the unfinished tail', () => {
  const { events, rest } = takeEvents(
    'event: message\r\ndata: Перший.\r\ndata: Другий.\r\n\r\n: ping\r\n\r\nevent: err',
  );
  assert.deepEqual(events, [{ event: 'message', data: 'Перший.\nДругий.' }]);
  assert.equal(rest, 'event: err');
});

test('reports error events with their message', () => {
  const { events } = takeEvents('event: error\r\ndata: Ліміт\r\n\r\n');
  assert.deepEqual(events, [{ event: 'error', data: 'Ліміт' }]);
});
