import { Loader2, Wifi, WifiOff, Coffee } from 'lucide-react';
import type { InferenceStatus } from '../hooks/useHealth';

interface Props {
  status: InferenceStatus;
  eta?: number;
}

const statusConfig: Record<InferenceStatus, {
  label: string;
  icon: React.ReactNode;
  className: string;
  description: string;
}> = {
  ready: {
    label: 'Готово до роботи',
    icon: <Wifi className="w-3.5 h-3.5" />,
    className: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    description: 'Модель завантажена і готова',
  },
  waking_up: {
    label: 'Прокидається...',
    icon: <Coffee className="w-3.5 h-3.5 animate-pulse" />,
    className: 'bg-amber-50 text-amber-700 border-amber-200',
    description: 'Модель завантажується, зачекайте 30-60 сек.',
  },
  unavailable: {
    label: 'Недоступно',
    icon: <WifiOff className="w-3.5 h-3.5" />,
    className: 'bg-rose-50 text-rose-700 border-rose-200',
    description: 'Сервіс тимчасово недоступний',
  },
  unknown: {
    label: 'Перевірка...',
    icon: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
    className: 'bg-slate-50 text-slate-500 border-slate-200',
    description: 'Визначаємо статус сервісу',
  },
};

export default function InferenceStatusBadge({ status, eta }: Props) {
  const config = statusConfig[status];
  return (
    <div className="flex items-center gap-2">
      <div
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold border ${config.className}`}
        title={config.description}
      >
        {config.icon}
        {config.label}
      </div>
      {status === 'waking_up' && eta !== undefined && (
        <span className="text-[10px] text-amber-600 font-mono">
          ~{Math.ceil(eta)}с
        </span>
      )}
    </div>
  );
}
