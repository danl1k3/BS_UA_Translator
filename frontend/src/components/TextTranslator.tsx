import { useState } from 'react';
import { ArrowLeftRight, Copy, Check, Loader2 } from 'lucide-react';
import type { useTranslate } from '../hooks/useTranslate';
import type { InferenceStatus } from '../hooks/useHealth';
import { errorMessage } from '../api';
import ErrorMessage from './ErrorMessage';
import DirectOffer from './DirectOffer';
import FileUploader from './FileUploader';
import Notice from './Notice';

type Props = ReturnType<typeof useTranslate> & { inferenceStatus: InferenceStatus };

const MAX_CHARS = 2000;
const BOSNIAN = { name: 'Bosnian', code: 'bos_Latn', htmlLang: 'bs' };
const UKRAINIAN = { name: 'Ukrainian', code: 'ukr_Cyrl', htmlLang: 'uk' };

export default function TextTranslator({ translate, translateAsVisitor, output, isLoading, error: propError, notice, limit, clearOutput, inferenceStatus }: Props) {
  const [sourceText, setSourceText] = useState('');
  const [copied, setCopied] = useState(false);
  const [fromBosnian, setFromBosnian] = useState(true);
  const [localError, setLocalError] = useState<string | null>(null);

  const [source, target] = fromBosnian ? [BOSNIAN, UKRAINIAN] : [UKRAINIAN, BOSNIAN];
  const isWakingUp = inferenceStatus === 'waking_up';
  const isUnavailable = inferenceStatus === 'unavailable';

  // Викликає функцію перекладу, що приходить з пропсів
  const handleTranslate = async () => {
    if (!sourceText.trim()) return;
    setLocalError(null);

    if (isUnavailable) {
      setLocalError('The service is unavailable. Try again later.');
      return;
    }

    try {
      await translate(sourceText, source.code, target.code);
    } catch (err: unknown) {
      setLocalError(errorMessage(err));
    }
  };

  // Переклад стає оригіналом; без перекладу введений текст лишається
  const handleSwap = () => {
    setFromBosnian((prev) => !prev);
    setSourceText((output || sourceText).slice(0, MAX_CHARS));
    clearOutput();
  };

  const handleCopy = () => {
    if (!output) return;
    navigator.clipboard.writeText(output).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const displayError = propError ?? localError;

  return (
    <>
      <section className="bg-white border border-line rounded-lg overflow-hidden">
        {/* Languages */}
        <div className="grid grid-cols-[1fr_auto_1fr] items-stretch border-b border-line">
          <h2 className="py-3 px-4 text-center text-lg font-semibold">{source.name}</h2>
          <button
            onClick={handleSwap}
            disabled={isLoading}
            aria-label="Swap languages"
            title="Swap languages"
            className="px-5 border-x border-line text-blue hover:bg-ground disabled:opacity-40"
          >
            <ArrowLeftRight className="w-5 h-5" />
          </button>
          <h2 className="py-3 px-4 text-center text-lg font-semibold text-blue">{target.name}</h2>
        </div>

        {isWakingUp && (
          <p className="px-4 py-3 bg-note border-b border-line">
            The model is waking up. The first translation can take 30 to 60 seconds.
          </p>
        )}

        <div className="grid lg:grid-cols-2 divide-y lg:divide-y-0 lg:divide-x divide-line">
          {/* Input */}
          <div className="flex flex-col">
            <textarea
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value.slice(0, MAX_CHARS))}
              aria-label={`Text in ${source.name}`}
              lang={source.htmlLang}
              placeholder="Type or paste text"
              className="w-full flex-grow min-h-[16rem] lg:min-h-[22rem] resize-none p-5 font-serif text-xl leading-relaxed placeholder:text-muted bg-transparent focus-visible:outline-offset-[-3px]"
            />
            <div className="px-5 py-3 text-sm text-muted text-right tabular-nums">
              {sourceText.length} / {MAX_CHARS}
            </div>
          </div>

          {/* Output */}
          <div className="flex flex-col bg-ground/50">
            <div className="flex-grow min-h-[12rem] p-5 font-serif text-xl leading-relaxed" aria-live="polite" aria-busy={isLoading}>
              {output ? (
                <p lang={target.htmlLang} className="whitespace-pre-wrap break-words">{output}</p>
              ) : (
                <p className="text-muted">{isLoading ? 'Translating…' : 'The translation appears here'}</p>
              )}
            </div>
            <div className="px-3 py-1.5 flex justify-end">
              <button
                onClick={handleCopy}
                disabled={!output}
                className="flex items-center gap-2 px-3 py-1.5 rounded text-blue font-semibold hover:bg-white disabled:opacity-40"
              >
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>
        </div>

        {notice && <Notice message={notice} />}
        {displayError && <ErrorMessage message={displayError} />}
        {limit && (
          <DirectOffer
            reason={limit}
            disabled={!sourceText.trim() || isLoading}
            onAccept={() => void translateAsVisitor(sourceText, source.code, target.code)}
          />
        )}

        <div className="p-4 border-t border-line flex justify-center">
          <button
            onClick={handleTranslate}
            disabled={!sourceText.trim() || isLoading || isUnavailable}
            className="btn btn-primary w-full sm:w-96 py-3.5 text-lg"
          >
            {isLoading && <Loader2 className="w-5 h-5 animate-spin" />}
            {isLoading ? 'Translating…' : isUnavailable ? 'Service unavailable' : 'Translate'}
          </button>
        </div>
      </section>

      <FileUploader sourceLang={source.code} targetLang={target.code} direction={`${source.name} to ${target.name}`} inferenceStatus={inferenceStatus} />
    </>
  );
}
