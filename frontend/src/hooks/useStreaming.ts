import { useState, useRef, useCallback } from 'react';
import { API_BASE } from '../config';

type Device = 'cuda' | 'cpu' | 'unknown';

export function useStreaming() {
  const [chunks, setChunks] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [device, setDevice] = useState<Device>('unknown');

  const controllerRef = useRef<AbortController | null>(null);

  const startStreaming = useCallback(async (text: string, sourceLang: string, targetLang: string) => {
    if (!text) return;
    if (controllerRef.current) controllerRef.current.abort();

    controllerRef.current = new AbortController();
    setChunks([]);
    setIsStreaming(true);
    setDevice('unknown');

    try {
      const resp = await fetch(`${API_BASE}/translate/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, source_lang: sourceLang, target_lang: targetLang }),
        signal: controllerRef.current.signal,
      });

      if (!resp.ok) {
        throw new Error(`Stream error: ${resp.status}`);
      }

      const reader = resp.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('No stream reader');

      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const line = part.trim();
          if (!line) continue;
          if (line.startsWith('data:')) {
            const payload = line.replace(/^data:\s*/, '');
            if (payload === '[DONE]') {
              setIsStreaming(false);
              continue;
            }
            try {
              const p = JSON.parse(payload) as { text?: string; device?: string };
              if (p.text) {
                setChunks((c) => [...c, p.text!]);
              }
              if (p.device) setDevice(p.device === 'cuda' ? 'cuda' : 'cpu');
            } catch {
              setChunks((c) => [...c, payload]);
            }
          } else {
            setChunks((c) => [...c, line]);
          }
        }
      }

      if (buffer) setChunks((c) => [...c, buffer]);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        // aborted by user
      } else {
        console.error('Streaming error', err);
      }
    } finally {
      setIsStreaming(false);
      controllerRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    if (controllerRef.current) controllerRef.current.abort();
    setChunks([]);
    setIsStreaming(false);
    setDevice('unknown');
    controllerRef.current = null;
  }, []);

  return { chunks, isStreaming, device, startStreaming, reset } as const;
}

export default useStreaming;
