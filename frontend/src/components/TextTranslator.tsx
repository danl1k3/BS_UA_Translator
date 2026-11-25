import { useState } from 'react';
import { ArrowLeftRight, Copy, Check, Loader2, AlertTriangle } from 'lucide-react';
import type { TranslatorProps } from '../App';
import FileUploader from './FileUploader';

export default function TextTranslator({ translate, output, isLoading, error: propError, clearOutput, inferenceStatus }: TranslatorProps) {
  const [sourceText, setSourceText] = useState('');
  const [copied, setCopied] = useState(false);
  const [direction, setDirection] = useState('balkan_to_ua');
  const [localError, setLocalError] = useState<string | null>(null);
  
  const MAX_CHARS = 2000;

  const isWakingUp = inferenceStatus === 'waking_up';
  const isUnavailable = inferenceStatus === 'unavailable';

  // Викликає функцію перекладу, що приходить з пропсів
  const handleTranslate = async () => {
    if (!sourceText.trim()) return;
    setLocalError(null);

    if (isUnavailable) {
      setLocalError('Сервіс тимчасово недоступний. Зачекайте або спробуйте пізніше.');
      return;
    }

    const isBalkanSource = direction === 'balkan_to_ua';
    const sourceLang = isBalkanSource ? 'bos_Latn' : 'ukr_Cyrl';
    const targetLang = isBalkanSource ? 'ukr_Cyrl' : 'bos_Latn';

    try {
      clearOutput();
      await translate(sourceText, sourceLang, targetLang);
    } catch (err: unknown) {
      setLocalError(err instanceof Error ? err.message : 'Невідома помилка');
    }
  };

  const handleSwap = () => {
    setDirection(prev => prev === 'balkan_to_ua' ? 'ua_to_balkan' : 'balkan_to_ua');
    setSourceText(output || '');
  };

  const handleCopy = () => {
    if (!output) return;
    navigator.clipboard.writeText(output).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isBalkanSource = direction === 'balkan_to_ua';
  const sourceLabel = isBalkanSource ? 'SR / ME / BS' : 'Ukrainian (UA)';
  const targetLabel = isBalkanSource ? 'Ukrainian (UA)' : 'SR / ME / BS';

  const sourceLangCode = isBalkanSource ? 'bos_Latn' : 'ukr_Cyrl';
  const targetLangCode = isBalkanSource ? 'ukr_Cyrl' : 'bos_Latn';

  const displayError = propError ?? localError;

  return (
    <div className="max-w-5xl mx-auto p-4 lg:p-8">
      <div className="bg-white rounded-3xl shadow-xl border border-slate-200 flex flex-col overflow-hidden min-h-[600px]">
        {/* Header */}
        <div className="flex border-b border-slate-100 p-4 bg-slate-50/50 justify-between items-center">
          <div className="flex gap-2 items-center">
            <div className="px-4 py-1.5 bg-white border border-slate-200 rounded-lg text-sm font-bold text-slate-700">
              {sourceLabel}
            </div>
            
            <button onClick={handleSwap} className="p-2 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-full transition-all">
              <ArrowLeftRight className="w-4 h-4" />
            </button>
            
            <div className="px-4 py-1.5 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-lg text-sm font-bold">
              {targetLabel}
            </div>
          </div>
          <span className="hidden sm:block text-[10px] font-mono text-slate-400 uppercase tracking-[0.2em]">Neural Engine v1.0</span>
        </div>

        {/* Waking up banner */}
        {isWakingUp && (
          <div className="flex items-center gap-2 px-4 py-2.5 bg-amber-50 border-b border-amber-100 text-amber-700 text-sm">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            <span>
              Модель прокидається після сну. Перший запит може зайняти 30–60 секунд.
            </span>
          </div>
        )}

        {/* Content Area */}
        <div className="flex flex-col lg:flex-row flex-grow divide-y lg:divide-y-0 lg:divide-x divide-slate-100">
          {/* Input Section */}
          <div className="w-full lg:w-1/2 flex flex-col relative">
            <textarea
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value.slice(0, MAX_CHARS))}
              placeholder={isBalkanSource ? "Введіть текст..." : "Введіть український текст..."}
              className="w-full h-64 lg:h-full resize-none border-none focus:ring-0 p-6 text-xl text-slate-700 placeholder-slate-300 outline-none bg-transparent"
            />
            <div className="p-4 flex justify-between items-center text-xs text-slate-400 font-mono">
              <span>{sourceText.length} / {MAX_CHARS}</span>
              {displayError && (
                <span className="text-rose-500 font-sans flex items-center gap-1 max-w-[60%] text-right">
                  <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                  {displayError}
                </span>
              )}
            </div>
          </div>
          
          {/* Output Section */}
          <div className="w-full lg:w-1/2 p-6 bg-slate-50/30 flex flex-col min-h-[250px]">
            {output || isLoading ? (
              <div className="text-xl text-slate-800 leading-relaxed font-normal">
                {/* Вже перекладений текст */}
                {output && (
                  <span className="animate-in fade-in duration-500 whitespace-pre-wrap">
                    {output}
                  </span>
                )}
                
                {/* Заблюрений "фантомний" текст для візуалізації обсягу, що залишився */}
                {isLoading && (
                  <span className="text-slate-300 blur-[3px] select-none animate-pulse transition-all duration-700 whitespace-pre-wrap">
                    {sourceText.slice(Math.min(sourceText.length, output.length)) || "..."}
                  </span>
                )}

                {/* Курсор, що блимає під час перекладу */}
                {isLoading && (
                  <span className="inline-block w-1.5 h-6 bg-indigo-500/40 animate-pulse ml-1 align-middle rounded-full" />
                )}
              </div>
            ) : (
              <p className="text-xl text-slate-300 italic">Тут з'явиться переклад...</p>
            )}
          </div>
        </div>

        {/* Action Footer */}
        <div className="p-4 border-t border-slate-100 bg-white flex flex-wrap gap-4 justify-between items-center">
          <div className="flex gap-1">
            <button onClick={handleCopy} disabled={!output} className="p-3 text-slate-500 hover:bg-slate-100 rounded-xl transition-colors disabled:opacity-30">
              {copied ? <Check className="w-6 h-6 text-emerald-600" /> : <Copy className="w-6 h-6" />}
            </button>
          </div>
          
          <button
            onClick={handleTranslate}
            disabled={!sourceText.trim() || isLoading || isUnavailable}
            className="w-full sm:w-auto px-8 py-4 bg-indigo-600 hover:bg-indigo-700 text-white rounded-2xl font-bold text-lg shadow-lg shadow-indigo-100 transition-all active:scale-95 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                {isWakingUp ? 'Прокидається...' : 'Перекладає...'}
              </>
            ) : isUnavailable ? (
              'Сервіс недоступний'
            ) : (
              "Перекласти зараз"
            )}
          </button>
        </div>
      </div>
        <FileUploader sourceLang={sourceLangCode} targetLang={targetLangCode} inferenceStatus={inferenceStatus} />
      </div>
  );
}
