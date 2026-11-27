import { describeQuota, type Quota } from '../quota';

export default function QuotaBadge({ quota }: { quota: Quota }) {
  const reset = quota.resets_at
    ? `Оновиться ${new Date(quota.resets_at).toLocaleString('uk-UA')}`
    : 'Спільний добовий ліміт для всіх відвідувачів';
  return (
    <div
      className={`px-2.5 py-1 rounded-lg text-xs font-semibold border ${
        quota.remaining_seconds > 0
          ? 'bg-slate-50 text-slate-600 border-slate-200'
          : 'bg-rose-50 text-rose-700 border-rose-200'
      }`}
      title={reset}
    >
      {describeQuota(quota)}
    </div>
  );
}
