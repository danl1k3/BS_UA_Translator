import React, { useState, useRef } from 'react';
import TextTranslator from './components/TextTranslator';

// --- ТИПІЗАЦІЯ ---
export interface TranslatorProps {
  setPage: (page: string) => void;
  translate: (text: string, sourceLang: string, targetLang: string) => Promise<void>;
  output: string;
  isLoading: boolean;
  error: string | null;
  clearOutput: () => void;
}

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

    try {
      const apiBaseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const response = await fetch(`${apiBaseUrl}/translate/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          source_lang: sourceLang,
          target_lang: targetLang,
        }),
        signal: abortControllerRef.current.signal,
      });

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

          if (trimmedLine.startsWith("data: ")) {
            const content = trimmedLine.replace("data: ", "").trim();
            if (content === "[DONE]") {
              setIsLoading(false);
              continue;
            }
            // Додаємо частину перекладу
            setOutput((prev) => prev + content);
          }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setError(err instanceof Error ? err.message : "Невідома помилка");
        setIsLoading(false);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return { translate, output, isLoading, error, setOutput };
};

// --- ОСНОВНИЙ КОМПОНЕНТ ---
export default function App() {
  const [currentPage, setCurrentPage] = useState<string>('translator');
  const { translate, output, isLoading, error, setOutput } = useTranslate();

  const commonProps: TranslatorProps = {
    setPage: setCurrentPage,
    translate,
    output,
    isLoading,
    error,
    clearOutput: () => setOutput("")
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
      </nav>

      <main className="max-w-6xl mx-auto px-6 pb-20">
        {renderContent()}
      </main>
    </div>
  );
}