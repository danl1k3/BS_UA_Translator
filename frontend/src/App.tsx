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
    <div className="min-h-screen">
      <header className="bg-blue text-white border-b-4 border-sun">
        <div className="max-w-5xl mx-auto px-4 py-4 flex flex-wrap gap-x-8 gap-y-3 justify-between items-center">
          <h1 className="text-2xl font-bold">BalkanTranslate</h1>
          <div className="flex flex-wrap gap-x-8 gap-y-2 items-center">
            {quota && <QuotaBadge quota={quota} />}
            <InferenceStatusBadge status={inferenceStatus} />
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-8">
        <TextTranslator {...translator} inferenceStatus={inferenceStatus} />
      </main>
    </div>
  );
}
