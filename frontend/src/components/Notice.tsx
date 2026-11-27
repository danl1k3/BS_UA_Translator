import { Info } from 'lucide-react';

export default function Notice({ message }: { message: string }) {
  return (
    <div role="status" className="flex items-center gap-2 px-4 py-2.5 bg-sky-50 border border-sky-100 rounded-2xl text-sky-800 text-sm font-semibold">
      <Info className="w-4 h-4 flex-shrink-0" />
      {message}
    </div>
  );
}
