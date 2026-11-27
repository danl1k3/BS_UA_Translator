export interface Quota {
  remaining_seconds: number;
  total_seconds: number;
  resets_at: string | null;
}

function duration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (!minutes) return `${rest} s`;
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}

export function describeQuota(quota: Quota): string {
  const { remaining_seconds: left, total_seconds: total } = quota;
  return `GPU time left: ${duration(left)} of ${duration(total)}`;
}
