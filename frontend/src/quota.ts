export interface Quota {
  remaining_seconds: number;
  total_seconds: number;
  resets_at: string | null;
}

function duration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (!minutes) return `${rest} с`;
  return rest ? `${minutes} хв ${rest} с` : `${minutes} хв`;
}

export function describeQuota(quota: Quota): string {
  const { remaining_seconds: left, total_seconds: total } = quota;
  return `Ліміт GPU: залишилось ${duration(left)} з ${duration(total)}`;
}
