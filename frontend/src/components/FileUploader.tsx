import { useRef, useState } from 'react';
import { Loader2, Download } from 'lucide-react';
import { apiFetch, errorMessage } from '../api';
import type { InferenceStatus } from '../hooks/useHealth';
import ErrorMessage from './ErrorMessage';
import Notice from './Notice';

interface Props {
  sourceLang: string;
  targetLang: string;
  direction: string;
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
  processing: 'This file is already being translated. Showing its progress.',
  complete: 'This file is already translated. You can download it.',
};

interface Submitted {
  job_id: string;
  duplicate: keyof typeof DUPLICATE_NOTICES | null;
}

export default function FileUploader({ sourceLang, targetLang, direction, inferenceStatus }: Props) {
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
    setError(next.size > MAX_FILE_BYTES ? 'The file is too large. The limit is 3 MB.' : null);
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
        if (status.status === 'failed') throw new Error(status.error ?? 'Translation failed.');
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
    <section className="mt-8">
      <div
        onDrop={(e) => {
          e.preventDefault();
          selectFile(e.dataTransfer.files[0]);
        }}
        onDragOver={(e) => e.preventDefault()}
        className={`p-6 bg-white border-2 border-dashed rounded-lg ${
          file ? 'border-blue' : 'border-line'
        } ${isUnavailable ? 'opacity-60' : ''}`}
      >
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-5">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold break-all">
              {file ? file.name : `Translate a file from ${direction}`}
            </h2>
            <p className="text-muted">
              {file
                ? `${Math.max(1, Math.round(file.size / 1024))} KB, ${direction}`
                : 'Drop a .txt, .docx or .html file here. Up to 3 MB and 20,000 characters.'}
            </p>
          </div>

          <div className="flex flex-col sm:flex-row gap-3 flex-shrink-0">
            {busy ? (
              <button onClick={() => controllerRef.current?.abort()} className="btn btn-secondary">
                Cancel
              </button>
            ) : (
              <>
                <button onClick={() => inputRef.current?.click()} className="btn btn-secondary">
                  Choose file
                </button>
                <button
                  onClick={handleUpload}
                  className={`btn sm:min-w-[12rem] ${
                    job?.status === 'complete' ? 'btn-secondary' : 'btn-primary'
                  }`}
                  disabled={!file || isUnavailable}
                >
                  {isUnavailable ? 'Service unavailable' : 'Translate file'}
                </button>
              </>
            )}
          </div>
        </div>

        {busy && (
          <div className="mt-5">
            <div className="flex justify-between mb-2">
              <span className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                {job?.status === 'running' ? 'Translating…' : 'Waiting in the queue…'}
              </span>
              <span className="tabular-nums">{percent}%</span>
            </div>
            <div
              role="progressbar"
              aria-label="File translation"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
              className="h-2 bg-ground"
            >
              <div className="h-full bg-blue transition-all duration-500" style={{ width: `${percent}%` }} />
            </div>
          </div>
        )}

        {!busy && job?.status === 'complete' && (
          <button
            onClick={() => handleDownload(job.id, job.filename)}
            className="btn btn-primary mt-5 w-full"
          >
            <Download className="w-5 h-5" />
            Download translation
          </button>
        )}

        <input
          ref={inputRef}
          type="file"
          onChange={(e) => selectFile(e.target.files?.[0])}
          className="hidden"
          accept=".txt,.docx,.html,.htm"
        />
      </div>

      {notice && (
        <div className="mt-4">
          <Notice message={notice} />
        </div>
      )}

      {error && (
        <div className="mt-4">
          <ErrorMessage message={error} />
        </div>
      )}
    </section>
  );
}
