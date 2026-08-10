import { useEffect, useState, useRef } from 'react';

type HealthStats = { status: 'idle' | 'busy' | 'unknown'; device?: 'cuda' | 'cpu' } | null;

export function useHealth(pollInterval = 5000) {
  const [stats, setStats] = useState<HealthStats>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const fetchHealth = async () => {
    try {
      const res = await fetch('/health');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const j = await res.json();
      // Expecting { status: 'idle'|'busy', device: 'cuda'|'cpu' }
      setStats({ status: j.status || 'unknown', device: j.device });
      setError(null);
    } catch (err: any) {
      setError(err.message || 'health check failed');
      setStats(null);
    }
  };

  useEffect(() => {
    fetchHealth();
    timerRef.current = window.setInterval(fetchHealth, pollInterval);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [pollInterval]);

  return { stats, error } as const;
}

export default useHealth;
