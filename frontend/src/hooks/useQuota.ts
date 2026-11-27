import { useEffect, useState } from 'react';
import { apiFetch } from '../api';
import type { Quota } from '../quota';

// null, якщо gateway не може прочитати ліміт: тоді лічильник ховається.
export function useQuota(pollInterval: number, refreshKey: unknown): Quota | null {
  const [quota, setQuota] = useState<Quota | null>(null);

  useEffect(() => {
    let active = true;

    const check = async () => {
      let next: Quota | null = null;
      try {
        const response = await apiFetch('/quota', { signal: AbortSignal.timeout(5000) });
        next = ((await response.json()) as { quota: Quota | null }).quota;
      } catch {
        // лічильник не обов'язковий
      }
      if (active) setQuota(next);
    };

    void check();
    const timer = window.setInterval(() => void check(), pollInterval);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [pollInterval, refreshKey]);

  return quota;
}
