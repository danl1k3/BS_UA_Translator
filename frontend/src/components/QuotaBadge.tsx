import { describeQuota, type Quota } from '../quota';

export default function QuotaBadge({ quota }: { quota: Quota }) {
  const reset = quota.resets_at
    ? `Resets ${new Date(quota.resets_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}`
    : 'A daily limit shared by all visitors';
  const share = quota.total_seconds
    ? Math.min(100, (quota.remaining_seconds / quota.total_seconds) * 100)
    : 0;
  return (
    <div title={reset} className="text-sm">
      <div className="tabular-nums">{describeQuota(quota)}</div>
      <div className="mt-1 h-1 bg-white/25" aria-hidden="true">
        <div className="h-full bg-sun" style={{ width: `${share}%` }} />
      </div>
    </div>
  );
}
