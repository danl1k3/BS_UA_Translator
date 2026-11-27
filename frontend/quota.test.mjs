import assert from 'node:assert/strict';
import { test } from 'node:test';
import { describeQuota } from './src/quota.ts';

test('shows remaining and total GPU time', () => {
  assert.equal(
    describeQuota({ remaining_seconds: 205, total_seconds: 300, resets_at: null }),
    'Ліміт GPU: залишилось 3 хв 25 с з 5 хв',
  );
});

test('handles less than a minute and an empty quota', () => {
  assert.equal(
    describeQuota({ remaining_seconds: 0, total_seconds: 210, resets_at: null }),
    'Ліміт GPU: залишилось 0 с з 3 хв 30 с',
  );
});
