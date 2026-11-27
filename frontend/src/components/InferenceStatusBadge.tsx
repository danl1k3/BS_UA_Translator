import type { InferenceStatus } from '../hooks/useHealth';

const statusConfig: Record<InferenceStatus, { label: string; dot: string; description: string }> = {
  ready: {
    label: 'Ready',
    dot: 'bg-emerald-400',
    description: 'The translation service is available',
  },
  waking_up: {
    label: 'Waking up',
    dot: 'bg-sun',
    description: 'The model is loading. This takes 30 to 60 seconds.',
  },
  unavailable: {
    label: 'Unavailable',
    dot: 'bg-red-400',
    description: 'The translation service is not responding',
  },
  unknown: {
    label: 'Checking',
    dot: 'bg-white/50',
    description: 'Checking the translation service',
  },
};

export default function InferenceStatusBadge({ status }: { status: InferenceStatus }) {
  const config = statusConfig[status];
  return (
    <div className="flex items-center gap-2 text-sm" title={config.description}>
      <span className={`w-2.5 h-2.5 rounded-full ${config.dot}`} aria-hidden="true" />
      {config.label}
    </div>
  );
}
