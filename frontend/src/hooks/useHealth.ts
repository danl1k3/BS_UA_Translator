import { useEffect, useState } from 'react';
import { API_BASE } from '../config';

type HealthStats = { status: string; device?: 'cuda' | 'cpu' } | null;

export function useHealth(pollInterval = 5000) {
  const [stats, setStats] = useState<HealthStats>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const fetchHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const j = (await res.json()) as { status?: string; device?: 'cuda' | 'cpu' };
        if (active) {
          setStats({ status: j.status || 'unknown', device: j.device });
          setError(null);
        }
      } catch (err: unknown) {
        if (active) {
          setError(err instanceof Error ? err.message : 'health check failed');
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
  }, [pollInterval]);

  return { stats, error } as const;
}

export default useHealth;
