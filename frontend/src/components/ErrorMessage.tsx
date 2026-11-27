import { AlertTriangle } from 'lucide-react';

export default function ErrorMessage({ message }: { message: string }) {
  return (
    <div role="alert" className="flex items-center gap-2 px-4 py-3 bg-red-50 border-l-4 border-danger text-danger">
      <AlertTriangle className="w-4 h-4 flex-shrink-0" />
      {message}
    </div>
  );
}
