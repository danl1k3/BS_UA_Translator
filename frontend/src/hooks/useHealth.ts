import { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export type InferenceStatus = 'ready' | 'waking_up' | 'unavailable' | 'unknown';

interface Health {
  inference: { status: string; reachable: boolean };
}

export function useHealth(pollInterval: number): InferenceStatus {
  const [status, setStatus] = useState<InferenceStatus>('unknown');

  useEffect(() => {
    let active = true;

    const check = async () => {
      let next: InferenceStatus = 'unavailable';
      try {
        const response = await apiFetch('/health', { signal: AbortSignal.timeout(5000) });
        const { inference } = (await response.json()) as Health;
        if (inference.reachable) next = 'ready';
        else if (inference.status === 'Waking up') next = 'waking_up';
      } catch {
        // gateway недоступний
      }
      if (active) setStatus(next);
    };

    void check();
    const timer = window.setInterval(() => void check(), pollInterval);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [pollInterval]);

  return status;
}
