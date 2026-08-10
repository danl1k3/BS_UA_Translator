import React, { useState, useRef } from 'react';
import { Loader2, UploadCloud, FileText, CheckCircle2, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

interface Props {
  sourceLang: string;
  targetLang: string;
}

export default function FileUploader({ sourceLang, targetLang }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [messages, setMessages] = useState<string[]>([]);
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null);
  
  // Toggle this constant in code to enable debug view (show raw JSON payloads).
  const DEBUG = false; 
  const [jobId, setJobId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const onBrowse = () => inputRef.current?.click();

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) setFile(e.target.files[0]);
  };

  const appendMsg = (m: string) => setMessages((s) => [...s, m].slice(-100));

  const downloadBlob = (data: Blob | string, filename: string, contentType?: string) => {
    const blob = typeof data === 'string' ? new Blob([data], { type: contentType || 'text/plain' }) : data;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setMessages([]);
    setProgress(null);
    setJobId(null);

    const form = new FormData();
    form.append('upload_file', file, file.name);

    try {
      const apiBaseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const backendUrl = `${apiBaseUrl}/translate/file/stream?source_lang=${encodeURIComponent(sourceLang)}&target_lang=${encodeURIComponent(targetLang)}&debug=${DEBUG}`;
      const controller = new AbortController();
      abortRef.current = controller;
      const resp = await fetch(backendUrl, {
        method: 'POST',
        body: form,
        signal: controller.signal,
      });

      if (!resp.ok || !resp.body) {
        const txt = await resp.text();
        appendMsg('Server error: ' + txt);
        setUploading(false);
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        let parts = buf.split(/\r?\n\r?\n/);
        buf = parts.pop() || '';

        for (const rawMsg of parts) {
          const lines = rawMsg.split('\n');
          let event = 'message';
          let data = '';
          for (const line of lines) {
            if (line.startsWith('event:')) event = line.replace('event:', '').trim();
            if (line.startsWith('data:')) {
              let piece = line.slice(5);
              if (piece.startsWith(' ')) piece = piece.slice(1);
              data += piece;
              data += '\n';
            }
          }
          if (data.endsWith('\n')) data = data.slice(0, -1);

          if (event === 'progress') {
            try {
              const cleanedData = data.trim();
              const p = JSON.parse(cleanedData);
              
              if (typeof p.current === 'number' && typeof p.total === 'number') {
                setProgress({ current: p.current, total: p.total });
              } else if (typeof p.percent === 'number') {
                setProgress({ current: p.percent, total: 100 });
              }

              if (p.data && typeof p.data === 'string' && DEBUG) {
                appendMsg(p.data);
              }
              
              if (p.status === 'done' && !DEBUG) {
                // Optional: log only when a chunk is fully done to keep logs clean
                // appendMsg(`Оброблено чанк ${p.paragraph}:${p.chunk}`);
              }
            } catch (e) {
              // Regex fallback for non-JSON or malformed data
              const match = data.match(/(\d+)\s*\/\s*(\d+)/);
              if (match) {
                setProgress({ current: parseInt(match[1]), total: parseInt(match[2]) });
              }
              appendMsg(data);
            }
          } else if (event === 'processing') {
            appendMsg(data);
            // If data contains "done" or similar, we might want to set progress to 100
          } else if (event === 'complete') {
            setProgress({ current: 100, total: 100 });
            appendMsg('Збірка файлу завершена!');
            if (DEBUG) {
              let payload = null;
              try {
                const candidate = data.trimStart();
                payload = (candidate.startsWith('{') || candidate.startsWith('[')) ? JSON.parse(candidate) : data;
              } catch {
                payload = data;
              }

              if (payload && typeof payload === 'object' && payload.content_type && payload.data) {
                if (payload.content_type.includes('word') || (payload.filename && payload.filename.toLowerCase().endsWith('.docx'))) {
                  const bin = atob(payload.data);
                  const arr = new Uint8Array(bin.length);
                  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
                  const blob = new Blob([arr], { type: payload.content_type });
                  downloadBlob(blob, payload.filename || ('translated_' + file.name), payload.content_type);
                  appendMsg('Download ready: ' + (payload.filename || file.name));
                } else {
                  downloadBlob(payload.data, payload.filename || ('translated_' + file.name), payload.content_type);
                  appendMsg('Download ready: ' + (payload.filename || file.name));
                }
              } else if (typeof payload === 'string') {
                downloadBlob(payload, 'translated_' + file.name);
                appendMsg('Download ready');
              } else if (payload && typeof payload === 'object' && payload.job_id) {
                setJobId(payload.job_id);
                appendMsg('Translation complete');
              }
            } else {
              try {
                const obj = JSON.parse(data);
                if (obj && obj.job_id) {
                  setJobId(obj.job_id);
                  appendMsg('Translation complete');
                }
              } catch (e) {
                appendMsg('Complete');
              }
            }
            setUploading(false);
          } else if (event === 'error') {
            appendMsg('Error: ' + data);
            setUploading(false);
          }
        }
      }
      if (buf.trim()) appendMsg(buf.trim());
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        appendMsg('Upload failed: ' + (e.message || String(e)));
      }
    } finally {
      setUploading(false);
      abortRef.current = null;
    }
  };

  const fetchResultAndDownload = async (id: string) => {
    try {
      const apiBaseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
      const url = `${apiBaseUrl}/translate/file/result?job_id=${encodeURIComponent(id)}`;
      const res = await fetch(url);
      if (!res.ok) {
        const t = await res.text();
        appendMsg('Fetch failed: ' + t);
        return;
      }
      const cd = res.headers.get('Content-Disposition') || '';
      let filename = 'translated_file';
      const m = cd.match(/filename="?([^";]+)"?/);
      if (m) filename = m[1];
      const blob = await res.blob();
      downloadBlob(blob, filename, res.headers.get('Content-Type') || undefined);
      appendMsg('Downloaded: ' + filename);
    } catch (e: any) {
      appendMsg('Download failed: ' + (e.message || String(e)));
    }
  };

  const progressPercent = progress ? Math.round((progress.current / progress.total) * 100) : 0;

  return (
    <div className="max-w-5xl mx-auto p-4 lg:p-8">
      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        className={`mt-6 p-8 border-2 border-dashed rounded-3xl text-center transition-all duration-300 ${
          file ? 'border-indigo-300 bg-indigo-50/30' : 'border-slate-200 bg-white'
        }`}
      >
        <div className="flex flex-col items-center gap-4">
          <div className={`p-4 rounded-2xl ${file ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-400'}`}>
            {file ? <FileText className="w-10 h-10" /> : <UploadCloud className="w-10 h-10" />}
          </div>
          
          <div>
            <div className="text-xl font-bold text-slate-800">
              {file ? file.name : 'Завантажити файл для пакетного перекладу'}
            </div>
            <div className="text-sm text-slate-500 mt-1">
              {file ? `${Math.round(file.size/1024)} KB` : 'Підтримується: .txt, .docx — до 50MB'}
            </div>
          </div>

          <div className="flex flex-col w-full max-w-md gap-4 mt-2">
            <AnimatePresence>
              {uploading && (
                <motion.div 
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="w-full"
                >
                  <div className="flex justify-between mb-2 px-1">
                    <span className="text-sm font-bold text-indigo-600 flex items-center gap-2">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      {progress ? (progress.total === 100 ? `Переклад: ${progress.current}%` : `Оброблено: ${progress.current} / ${progress.total}`) : 'Підготовка...'}
                    </span>
                    <span className="text-sm font-black text-indigo-600">{progressPercent}%</span>
                  </div>
                  <div className="w-full bg-slate-200 rounded-full h-3 overflow-hidden shadow-inner">
                    <motion.div 
                      className="bg-indigo-600 h-full rounded-full shadow-[0_0_10px_rgba(79,70,229,0.4)]"
                      initial={{ width: 0 }}
                      animate={{ width: `${progressPercent}%` }}
                      transition={{ type: "spring", stiffness: 50, damping: 15 }}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="flex flex-wrap justify-center gap-3 mt-2">
              {!uploading ? (
                <>
                  <button onClick={onBrowse} className="px-6 py-2.5 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold hover:bg-slate-50 transition-colors shadow-sm">
                    Вибрати файл
                  </button>
                  <button 
                    onClick={handleUpload} 
                    className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl font-bold hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-100 disabled:opacity-50 disabled:shadow-none"
                    disabled={!file}
                  >
                    Перекласти
                  </button>
                </>
              ) : (
                <button 
                  onClick={() => { if (abortRef.current) abortRef.current.abort(); setUploading(false); }} 
                  className="px-6 py-2.5 bg-rose-50 text-rose-700 border border-rose-100 rounded-xl font-bold hover:bg-rose-100 transition-colors"
                >
                  Скасувати
                </button>
              )}

              {jobId && !uploading && (
                <motion.button 
                  initial={{ scale: 0.9, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  onClick={() => fetchResultAndDownload(jobId)} 
                  className="px-6 py-2.5 bg-emerald-600 text-white rounded-xl font-bold hover:bg-emerald-700 transition-all shadow-lg shadow-emerald-100 flex items-center gap-2"
                >
                  <CheckCircle2 className="w-5 h-5" />
                  Завантажити результат
                </motion.button>
              )}
            </div>
          </div>

          <input ref={inputRef} type="file" onChange={onFileChange} className="hidden" accept=".txt,.docx" />
        </div>
      </div>

      {(DEBUG || messages.some(m => m.startsWith('Error:'))) && (
        <div className="mt-6 bg-white p-5 rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
          <div className="flex items-center gap-2 mb-3 text-slate-800 font-bold">
            <AlertCircle className="w-4 h-4 text-amber-500" />
            Логи обробки
          </div>
          <div className="text-sm font-mono text-slate-600 max-h-40 overflow-auto bg-slate-50 p-4 rounded-xl leading-relaxed">
            {messages.length === 0 && <div className="text-slate-400 italic">Очікування подій...</div>}
            {messages.map((m, i) => (
              <div key={i} className={`mb-1 ${m.startsWith('Error') ? 'text-rose-600 font-bold' : ''}`}>{m}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
