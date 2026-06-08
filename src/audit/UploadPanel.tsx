import React, { useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { X, UploadCloud, FileSpreadsheet, FileText, Loader2 } from 'lucide-react';
import { runUpload } from './api';
import type { PipelineResult } from './types';

const DocsDrop: React.FC<{ files: File[]; onFiles: (f: File[]) => void }> = ({ files, onFiles }) => {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    multiple: true,
    accept: { 'application/pdf': ['.pdf'] },
    onDrop: (f) => onFiles([...files, ...f]),
  });
  return (
    <div {...getRootProps()}
      className="border-2 border-dashed rounded-xl px-4 py-5 text-center cursor-pointer transition-colors"
      style={{ borderColor: isDragActive ? 'var(--green)' : 'var(--border)', background: isDragActive ? 'var(--green-100)' : 'transparent' }}>
      <input {...getInputProps()} />
      {files.length ? (
        <div className="space-y-1">
          {files.map((f, i) => (
            <div key={i} className="flex items-center justify-center gap-2 text-[13px] text-ink">
              <FileText size={15} className="text-radioactive-600" /> {f.name}
            </div>
          ))}
          <div className="text-[11px] text-[var(--faint)]">click to add more</div>
        </div>
      ) : (
        <div className="text-[13px] text-[var(--muted)]">
          <UploadCloud size={20} className="mx-auto mb-1 text-[var(--faint)]" />
          Drop supporting journal documentation <span className="text-[var(--faint)]">(PDF, optional)</span>
        </div>
      )}
    </div>
  );
};

const Drop: React.FC<{ label: string; file: File | null; onFile: (f: File) => void }> = ({ label, file, onFile }) => {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    multiple: false,
    accept: { 'text/csv': ['.csv'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] },
    onDrop: (f) => f[0] && onFile(f[0]),
  });
  return (
    <div {...getRootProps()}
      className="border-2 border-dashed rounded-xl px-4 py-6 text-center cursor-pointer transition-colors"
      style={{ borderColor: isDragActive ? 'var(--green)' : 'var(--border)', background: isDragActive ? 'var(--green-100)' : 'transparent' }}>
      <input {...getInputProps()} />
      {file ? (
        <div className="flex items-center justify-center gap-2 text-[13px] text-ink">
          <FileSpreadsheet size={16} className="text-radioactive-600" /> {file.name}
        </div>
      ) : (
        <div className="text-[13px] text-[var(--muted)]">
          <UploadCloud size={20} className="mx-auto mb-1 text-[var(--faint)]" />
          {label} <span className="text-[var(--faint)]">(CSV or XLSX)</span>
        </div>
      )}
    </div>
  );
};

const UploadPanel: React.FC<{ onClose: () => void; onDone: (result: PipelineResult) => void; aiAvailable: boolean }> =
  ({ onClose, onDone, aiAvailable }) => {
    const [gl, setGl] = useState<File | null>(null);
    const [tb, setTb] = useState<File | null>(null);
    const [docs, setDocs] = useState<File[]>([]);
    const [name, setName] = useState('');
    const [useAi, setUseAi] = useState(aiAvailable);
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState('');

    async function submit() {
      if (!gl) { setErr('A General Ledger file is required.'); return; }
      setBusy(true); setErr('');
      try {
        const res = await runUpload(gl, tb, docs, name || gl.name.replace(/\.[^.]+$/, ''), useAi);
        onDone(res);
      } catch (e: any) {
        setErr(e?.response?.data?.error || 'Pipeline run failed.');
      } finally { setBusy(false); }
    }

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(15,11,11,0.45)' }}>
        <div className="bg-white rounded-xl2 shadow-lift w-full max-w-[480px] p-5 ll-fade-up">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display text-[17px] font-semibold">New engagement</h3>
            <button onClick={onClose} className="text-[var(--faint)] hover:text-ink"><X size={18} /></button>
          </div>

          <label className="text-[12px] font-medium text-[var(--muted)]">Engagement name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Northwind Traders — FY2026"
            className="w-full mt-1 mb-3 px-3 py-2 rounded-lg border border-[var(--border)] outline-none text-[13px] focus:border-radioactive-300" />

          <div className="space-y-2.5">
            <div>
              <label className="text-[12px] font-medium text-[var(--muted)] mb-1 block">General Ledger *</label>
              <Drop label="Drop the GL export" file={gl} onFile={setGl} />
            </div>
            <div>
              <label className="text-[12px] font-medium text-[var(--muted)] mb-1 block">Trial Balance (optional)</label>
              <Drop label="Drop the TB export" file={tb} onFile={setTb} />
            </div>
            <div>
              <label className="text-[12px] font-medium text-[var(--muted)] mb-1 block">Supporting documents (optional)</label>
              <DocsDrop files={docs} onFiles={setDocs} />
            </div>
          </div>

          <label className="flex items-center gap-2 mt-3 text-[13px] text-[var(--muted)]"
            style={{ opacity: aiAvailable ? 1 : 0.5 }}>
            <input type="checkbox" checked={useAi && aiAvailable} disabled={!aiAvailable}
              onChange={(e) => setUseAi(e.target.checked)} className="accent-[var(--green)]" />
            Generate AI narratives & extract vouchers{!aiAvailable && ' — no key configured'}
          </label>

          {err && <p className="text-[12px] text-status-material mt-2">{err}</p>}

          <div className="flex justify-end gap-2 mt-4">
            <button onClick={onClose} className="px-3.5 py-2 rounded-lg text-[13px] text-[var(--muted)] hover:bg-canvas">Cancel</button>
            <button onClick={submit} disabled={busy}
              className="px-4 py-2 rounded-lg text-[13px] font-medium text-white flex items-center gap-2 disabled:opacity-60"
              style={{ background: 'var(--coral-black)' }}>
              {busy && <Loader2 size={14} className="animate-spin" />} Run pipeline
            </button>
          </div>
        </div>
      </div>
    );
  };

export default UploadPanel;
