import TextTranslator from './components/TextTranslator';
import InferenceStatusBadge from './components/InferenceStatusBadge';
import QuotaBadge from './components/QuotaBadge';
import { useHealth } from './hooks/useHealth';
import { useQuota } from './hooks/useQuota';
import { useTranslate } from './hooks/useTranslate';

export default function App() {
  const translator = useTranslate();
  const inferenceStatus = useHealth(8000);
  // Оновлюється також після кожного перекладу тексту
  const quota = useQuota(30_000, translator.isLoading);

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
      {/* Навігація */}
      <nav className="max-w-6xl mx-auto px-6 py-8 flex flex-wrap gap-3 justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center shadow-lg">
            <span className="text-white font-black text-xl">B</span>
          </div>
          <span className="text-xl font-bold tracking-tight text-slate-800">BalkanTranslate</span>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          {quota && <QuotaBadge quota={quota} />}
          <InferenceStatusBadge status={inferenceStatus} />
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 pb-20">
        <TextTranslator {...translator} inferenceStatus={inferenceStatus} />
      </main>
    </div>
  );
}
