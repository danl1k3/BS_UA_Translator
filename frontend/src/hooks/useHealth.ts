import { useEffect, useState, useCallback } from 'react';
import { API_BASE } from '../config';

export type InferenceStatus = 'ready' | 'waking_up' | 'unavailable' | 'unknown';

export interface HealthStats {
  status: string;
  device?: 'cuda' | 'cpu' | 'remote';
  inference?: {
    status?: string;
    reachable?: boolean;
    device?: string;
  };
  queue_size?: number;
  eta_seconds?: number;
}

export function useHealth(pollInterval = 5000) {
  const [stats, setStats] = useState<HealthStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inferenceStatus, setInferenceStatus] = useState<InferenceStatus>('unknown');

  const deriveInferenceStatus = useCallback((data: HealthStats): InferenceStatus => {
    // Check if inference is reachable via the nested inference field
    if (data.inference) {
      if (data.inference.reachable === false) {
        const status = (data.inference.status || '').toLowerCase();
        if (status.includes('waking') || status.includes('starting') || status.includes('loading')) {
          return 'waking_up';
        }
        return 'unavailable';
      }
      return 'ready';
    }
    // Fallback: check top-level status
    const topStatus = (data.status || '').toLowerCase();
    if (topStatus === 'waking up' || topStatus === 'waking_up') return 'waking_up';
    if (topStatus === 'normal' || topStatus === 'ready') return 'ready';
    return 'unknown';
  }, []);

  useEffect(() => {
    let active = true;

    const fetchHealth = async () => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        const res = await fetch(`${API_BASE}/health`, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = (await res.json()) as HealthStats;

        if (active) {
          setStats(data);
          setInferenceStatus(deriveInferenceStatus(data));
          setError(null);
        }
      } catch (err: unknown) {
        if (active) {
          if (err instanceof Error && err.name === 'AbortError') {
            setError('Gateway timeout');
            setInferenceStatus('unavailable');
          } else {
            setError(err instanceof Error ? err.message : 'health check failed');
            setInferenceStatus('unavailable');
          }
          setStats(null);
        }
      }
    };

    void fetchHealth();
    const timer = window.setInterval(() => {
      void fetchHealth();
    }, pollInterval);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [pollInterval, deriveInferenceStatus]);

  return { stats, error, inferenceStatus } as const;
}

export default useHealth;
