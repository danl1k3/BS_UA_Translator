import { useRef, useState } from 'react';
import { apiFetch, errorMessage } from '../api';
import { takeEvents } from '../sse';

// Довше за тайм-аут gateway (120 с), щоб помилку повідомив сервер.
const TRANSLATE_TIMEOUT_MS = 150_000;

export function useTranslate() {
  const [output, setOutput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const translate = async (text: string, sourceLang: string, targetLang: string) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setIsLoading(true);
    setOutput('');
    setError(null);
    setNotice(null);

    const timeoutId = setTimeout(() => {
      controller.abort();
      setError('The request timed out. Try again in a minute.');
    }, TRANSLATE_TIMEOUT_MS);

    try {
      const response = await apiFetch('/translate/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, source_lang: sourceLang, target_lang: targetLang }),
        signal: controller.signal,
      });
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
          if (event === 'error') {
            setError(data === 'Translation failed' ? 'Translation failed. Try again.' : data);
          }
        }
      }
    } catch (err: unknown) {
      if (!controller.signal.aborted) setError(errorMessage(err));
    } finally {
      clearTimeout(timeoutId);
      if (controllerRef.current === controller) setIsLoading(false);
    }
  };

  const clearOutput = () => {
    setOutput('');
    setNotice(null);
  };

  return { translate, output, isLoading, error, notice, clearOutput };
}
