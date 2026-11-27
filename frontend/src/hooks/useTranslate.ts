import { useRef, useState } from 'react';
import { apiFetch, errorMessage } from '../api';
import { translateDirect, type PreparedCall } from '../direct';
import { takeEvents } from '../sse';

// Довше за тайм-аут gateway (120 с), щоб помилку повідомив сервер.
const TRANSLATE_TIMEOUT_MS = 150_000;

export function useTranslate() {
  const [output, setOutput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Повідомлення про вичерпаний ліміт; тоді пропонується прямий виклик
  const [limit, setLimit] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const clearOutput = () => {
    setOutput('');
    setError(null);
    setNotice(null);
    setLimit(null);
  };

  // Спільна обгортка: скасування попереднього запиту, тайм-аут, помилки.
  const run = async (work: (signal: AbortSignal) => Promise<void>) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setIsLoading(true);
    clearOutput();

    const timeoutId = setTimeout(() => {
      controller.abort();
      setError('The request timed out. Try again in a minute.');
    }, TRANSLATE_TIMEOUT_MS);

    try {
      await work(controller.signal);
    } catch (err: unknown) {
      if (!controller.signal.aborted) setError(errorMessage(err));
    } finally {
      clearTimeout(timeoutId);
      if (controllerRef.current === controller) setIsLoading(false);
    }
  };

  const post = (path: string, text: string, sourceLang: string, targetLang: string, signal: AbortSignal) =>
    apiFetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, source_lang: sourceLang, target_lang: targetLang }),
      signal,
    });

  const translate = (text: string, sourceLang: string, targetLang: string) =>
    run(async (signal) => {
      const response = await post('/translate/stream', text, sourceLang, targetLang, signal);
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const parsed = takeEvents(buffer + decoder.decode(value, { stream: true }));
        buffer = parsed.rest;

        for (const { event, data } of parsed.events) {
          if (event === 'message') setOutput(data);
          if (event === 'notice') setNotice(data);
          if (event === 'limit') setLimit(data);
          if (event === 'error') {
            setError(data === 'Translation failed' ? 'Translation failed. Try again.' : data);
          }
        }
      }
    });

  // Лише після згоди відвідувача: його браузер звертається до Hugging Face.
  const translateAsVisitor = (text: string, sourceLang: string, targetLang: string) =>
    run(async (signal) => {
      const response = await post('/translate/direct', text, sourceLang, targetLang, signal);
      const prepared = (await response.json()) as PreparedCall;
      setOutput(await translateDirect(prepared, signal));
    });

  return { translate, translateAsVisitor, output, isLoading, error, notice, limit, clearOutput };
}
