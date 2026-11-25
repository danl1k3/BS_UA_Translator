import { useState, useRef } from 'react';
import TextTranslator from './components/TextTranslator';
import InferenceStatusBadge from './components/InferenceStatusBadge';
import { useHealth } from './hooks/useHealth';
import type { InferenceStatus } from './hooks/useHealth';
import { API_BASE } from './config';

// --- ТИПІЗАЦІЯ ---
export interface TranslatorProps {
  setPage: (page: string) => void;
  translate: (text: string, sourceLang: string, targetLang: string) => Promise<void>;
  output: string;
  isLoading: boolean;
  error: string | null;
  clearOutput: () => void;
  inferenceStatus: InferenceStatus;
}

// --- Timeout for inference requests (ms) ---
const TRANSLATE_TIMEOUT_MS = 55_000; // Heroku 55s idle limit

// --- ХУК ДЛЯ ПЕРЕКЛАДУ (SSE) ---
const useTranslate = () => {
  const [output, setOutput] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const translate = async (text: string, sourceLang: string, targetLang: string) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    abortControllerRef.current = new AbortController();
    setIsLoading(true);
    setOutput("");
    setError(null);

    // Set a timeout to abort if inference takes too long
    const timeoutId = setTimeout(() => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        setError("Час очікування вичерпано. Модель може прокидатися — спробуйте ще раз через хвилину.");
        setIsLoading(false);
      }
    }, TRANSLATE_TIMEOUT_MS);

    try {
      const response = await fetch(`${API_BASE}/translate/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          source_lang: sourceLang,
          target_lang: targetLang,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (response.status === 429) {
        const data = await response.json().catch(() => null);
        setError(data?.detail || "Занадто багато запитів. Зачекайте трохи.");
        setIsLoading(false);
        clearTimeout(timeoutId);
        return;
      }

      if (!response.ok) throw new Error("Помилка з'єднання з сервером");

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) return;

      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        
        // Останній елемент може бути незавершеним рядком, залишаємо його в буфері
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine) continue;

          if (trimmedLine.startsWith("event: error")) {
            // Next data line will contain the error
            continue;
          }

          if (trimmedLine.startsWith("data: ")) {
            const content = trimmedLine.replace("data: ", "").trim();
            if (content === "[DONE]") {
              setIsLoading(false);
              continue;
            }
            if (content === "Translation failed") {
              setError("Переклад не вдався. Спробуйте ще раз.");
              setIsLoading(false);
              continue;
            }
            // Додаємо частину перекладу
            setOutput((prev) => prev + content);
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        // If error was already set by the timeout handler, don't overwrite
        if (!error) {
          // User cancelled
        }
      } else {
        setError(err instanceof Error ? err.message : "Невідома помилка");
      }
    } finally {
      clearTimeout(timeoutId);
      setIsLoading(false);
    }
  };

  return { translate, output, isLoading, error, setOutput };
};

// --- ОСНОВНИЙ КОМПОНЕНТ ---
export default function App() {
  const [currentPage, setCurrentPage] = useState<string>('translator');
  const { translate, output, isLoading, error, setOutput } = useTranslate();
  const { stats, inferenceStatus } = useHealth(8000);

  const commonProps: TranslatorProps = {
    setPage: setCurrentPage,
    translate,
    output,
    isLoading,
    error,
    clearOutput: () => setOutput(""),
    inferenceStatus,
  };

  const renderContent = () => {
    switch (currentPage) {
      case 'translator':
        return <TextTranslator {...commonProps} />;
      
      case 'dashboard':
        return (
          <div className="p-10 text-center bg-white rounded-3xl border border-slate-200 shadow-sm">
            <h1 className="text-2xl font-bold mb-4">API Dashboard</h1>
            <button 
              onClick={() => setCurrentPage('translator')} 
              className="text-indigo-600 underline"
            >
              Повернутися до перекладу
            </button>
          </div>
        );

      default:
        return <div className="p-10 text-center">Сторінку не знайдено</div>;
    }
  };

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
        <InferenceStatusBadge status={inferenceStatus} eta={stats?.eta_seconds} />
      </nav>

      <main className="max-w-6xl mx-auto px-6 pb-20">
        {renderContent()}
      </main>
    </div>
  );
}
