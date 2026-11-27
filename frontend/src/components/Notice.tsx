import { Info } from 'lucide-react';

export default function Notice({ message }: { message: string }) {
  return (
    <div role="status" className="flex items-center gap-2 px-4 py-3 bg-note border-l-4 border-sun text-ink">
      <Info className="w-4 h-4 flex-shrink-0" />
      {message}
    </div>
  );
}
