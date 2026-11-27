import assert from 'node:assert/strict';
import { test } from 'node:test';
import { describeQuota } from './src/quota.ts';

test('shows remaining and total GPU time', () => {
  assert.equal(
    describeQuota({ remaining_seconds: 205, total_seconds: 300, resets_at: null }),
    'GPU time left: 3 min 25 s of 5 min',
  );
});

test('handles less than a minute and an empty quota', () => {
  assert.equal(
    describeQuota({ remaining_seconds: 0, total_seconds: 210, resets_at: null }),
    'GPU time left: 0 s of 3 min 30 s',
  );
});
