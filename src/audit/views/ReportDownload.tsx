import React from 'react';
import { FileDown, Braces } from 'lucide-react';
import { reportPdfUrl, reportJsonUrl } from '../api';

const ReportDownload: React.FC<{ clientId: string }> = ({ clientId }) => (
  <div className="flex items-center gap-2">
    <a href={reportPdfUrl(clientId)} target="_blank" rel="noreferrer"
      className="flex items-center gap-1.5 text-[12px] font-medium px-3 py-1.5 rounded-lg text-white"
      style={{ background: 'var(--coral-black)' }}>
      <FileDown size={14} /> Report PDF
    </a>
    <a href={reportJsonUrl(clientId)} target="_blank" rel="noreferrer"
      className="flex items-center gap-1.5 text-[12px] font-medium px-3 py-1.5 rounded-lg border border-[var(--border)] text-[var(--muted)] hover:bg-white">
      <Braces size={14} /> Audit JSON
    </a>
  </div>
);

export default ReportDownload;
