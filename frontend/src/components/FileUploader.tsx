import { useRef, useState } from 'react';
import { Loader2, UploadCloud, FileText, CheckCircle2, AlertTriangle } from 'lucide-react';
import { apiFetch, errorMessage } from '../api';
import type { InferenceStatus } from '../hooks/useHealth';
import Notice from './Notice';

interface Props {
  sourceLang: string;
  targetLang: string;
  inferenceStatus: InferenceStatus;
}

interface JobStatus {
  status: 'pending' | 'running' | 'complete' | 'failed';
  progress_current: number;
  progress_total: number;
  filename: string;
  error: string | null;
}

// Ті самі ліміти, що й у gateway.
const MAX_FILE_BYTES = 3 * 1024 * 1024;
const POLL_INTERVAL_MS = 2000;
const DUPLICATE_NOTICES = {
  processing: 'Цей файл уже перекладається. Показуємо прогрес.',
  complete: 'Цей файл уже перекладено. Можна завантажити результат.',
};

interface Submitted {
  job_id: string;
  duplicate: keyof typeof DUPLICATE_NOTICES | null;
}

export default function FileUploader({ sourceLang, targetLang, inferenceStatus }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<(JobStatus & { id: string }) | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const isUnavailable = inferenceStatus === 'unavailable';

  const selectFile = (next: File | undefined) => {
    if (!next || busy) return;
    setJob(null);
    setNotice(null);
    setError(next.size > MAX_FILE_BYTES ? 'Файл завеликий (ліміт 3 МБ).' : null);
    setFile(next.size > MAX_FILE_BYTES ? null : next);
  };

  // Ставить файл у чергу та опитує статус, доки завдання не завершиться.
  const handleUpload = async () => {
    if (!file) return;
    const controller = new AbortController();
    const { signal } = controller;
    controllerRef.current = controller;
    setBusy(true);
    setError(null);
    setNotice(null);
    setJob(null);

    try {
      const form = new FormData();
      form.append('upload_file', file, file.name);
      const query = new URLSearchParams({ source_lang: sourceLang, target_lang: targetLang });
      // Без signal: потрібен job_id, щоб скасувати вже прийняте завдання.
      const submitted = await apiFetch(`/translate/file/submit?${query}`, {
        method: 'POST',
        body: form,
      });
      const { job_id: id, duplicate } = (await submitted.json()) as Submitted;
      if (duplicate) setNotice(DUPLICATE_NOTICES[duplicate]);

      while (!signal.aborted) {
        const response = await apiFetch(`/translate/file/status?job_id=${id}`);
        const status = (await response.json()) as JobStatus;
        if (signal.aborted) break;
        setJob({ ...status, id });
        if (status.status === 'failed') throw new Error(status.error ?? 'Переклад не вдався.');
        if (status.status === 'complete') return;
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }
      await apiFetch(`/translate/file/job?job_id=${id}`, { method: 'DELETE' });
    } catch (err: unknown) {
      if (!signal.aborted) setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const handleDownload = async (id: string, filename: string) => {
    try {
      const response = await apiFetch(`/translate/file/result?job_id=${id}`);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err: unknown) {
      setError(errorMessage(err));
    }
  };

  const percent = job?.progress_total
    ? Math.round((job.progress_current / job.progress_total) * 100)
    : 0;

  return (
    <div className="max-w-5xl mx-auto p-4 lg:p-8">
      <div
        onDrop={(e) => {
          e.preventDefault();
          selectFile(e.dataTransfer.files[0]);
        }}
        onDragOver={(e) => e.preventDefault()}
        className={`mt-6 p-8 border-2 border-dashed rounded-3xl text-center transition-all duration-300 ${
          file ? 'border-indigo-300 bg-indigo-50/30' : 'border-slate-200 bg-white'
        } ${isUnavailable ? 'opacity-60' : ''}`}
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
              {file
                ? `${Math.round(file.size / 1024)} KB`
                : 'Підтримується: .txt, .docx, .html — до 3 МБ та 20 000 символів'}
            </div>
          </div>

          <div className="flex flex-col w-full max-w-md gap-4 mt-2">
            {busy && (
              <div className="w-full">
                <div className="flex justify-between mb-2 px-1 text-sm font-bold text-indigo-600">
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {job?.status === 'running' ? 'Перекладаємо...' : 'У черзі...'}
                  </span>
                  <span className="font-black">{percent}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-3 overflow-hidden shadow-inner">
                  <div
                    className="bg-indigo-600 h-full rounded-full transition-all duration-500"
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>
            )}

            <div className="flex flex-wrap justify-center gap-3 mt-2">
              {busy ? (
                <button
                  onClick={() => controllerRef.current?.abort()}
                  className="px-6 py-2.5 bg-rose-50 text-rose-700 border border-rose-100 rounded-xl font-bold hover:bg-rose-100 transition-colors"
                >
                  Скасувати
                </button>
              ) : (
                <>
                  <button
                    onClick={() => inputRef.current?.click()}
                    className="px-6 py-2.5 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold hover:bg-slate-50 transition-colors shadow-sm"
                  >
                    Вибрати файл
                  </button>
                  <button
                    onClick={handleUpload}
                    className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl font-bold hover:bg-indigo-700 transition-all shadow-lg shadow-indigo-100 disabled:opacity-50 disabled:shadow-none"
                    disabled={!file || isUnavailable}
                  >
                    {isUnavailable ? 'Сервіс недоступний' : 'Перекласти'}
                  </button>
                </>
              )}

              {!busy && job?.status === 'complete' && (
                <button
                  onClick={() => handleDownload(job.id, job.filename)}
                  className="px-6 py-2.5 bg-emerald-600 text-white rounded-xl font-bold hover:bg-emerald-700 transition-all shadow-lg shadow-emerald-100 flex items-center gap-2"
                >
                  <CheckCircle2 className="w-5 h-5" />
                  Завантажити результат
                </button>
              )}
            </div>
          </div>

          <input
            ref={inputRef}
            type="file"
            onChange={(e) => selectFile(e.target.files?.[0])}
            className="hidden"
            accept=".txt,.docx,.html,.htm"
          />
        </div>
      </div>

      {notice && (
        <div className="mt-6">
          <Notice message={notice} />
        </div>
      )}

      {error && (
        <div className="mt-6 flex items-center gap-2 bg-rose-50 p-4 rounded-2xl border border-rose-100 text-rose-700 text-sm font-semibold">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}
    </div>
  );
}
