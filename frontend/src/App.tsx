import TextTranslator from './components/TextTranslator';
import InferenceStatusBadge from './components/InferenceStatusBadge';
import { useHealth } from './hooks/useHealth';
import { useTranslate } from './hooks/useTranslate';

export default function App() {
  const translator = useTranslate();
  const inferenceStatus = useHealth(8000);

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
      {/* Навігація */}
      <nav className="max-w-6xl mx-auto px-6 py-8 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-indigo-600 rounded-xl flex items-center justify-center shadow-lg">
            <span className="text-white font-black text-xl">B</span>
          </div>
          <span className="text-xl font-bold tracking-tight text-slate-800">BalkanTranslate</span>
        </div>
        <InferenceStatusBadge status={inferenceStatus} />
      </nav>

      <main className="max-w-6xl mx-auto px-6 pb-20">
        <TextTranslator {...translator} inferenceStatus={inferenceStatus} />
      </main>
    </div>
  );
}
