import React from 'react';
import { FileCheck2, FileWarning, Sparkles } from 'lucide-react';
import type { PipelineResult } from '../types';
import { Card, Pill } from '../ui';
import { pct, scoreColor } from '../format';

const DocumentationCard: React.FC<{ result: PipelineResult }> = ({ result }) => {
  const s = result.support;
  if (!s) {
    return (
      <Card title="Supporting documentation" subtitle="Journal vouchers / approvals (PDF)">
        <div className="text-sm text-[var(--muted)] py-4">
          No supporting documentation was provided. Add journal PDFs in <b>New ingest</b> to assess
          evidence coverage.
        </div>
      </Card>
    );
  }
  const cov = s.coverage_pct;
  return (
    <Card title="Supporting documentation"
      subtitle={`${s.documents} PDF · ${s.pages} pages · read via ${s.method}`}
      right={s.method !== 'text-match'
        ? <span className="flex items-center gap-1 text-[11px] text-radioactive-600"><Sparkles size={12} /> AI-extracted</span>
        : undefined}>
      <div className="flex items-center gap-5">
        <div className="shrink-0 flex flex-col items-center justify-center w-24 h-24 rounded-full"
          style={{ background: `conic-gradient(${scoreColor(cov)} ${cov * 360}deg, rgba(15,11,11,0.07) 0deg)` }}>
          <div className="w-[78px] h-[78px] rounded-full bg-white flex flex-col items-center justify-center">
            <span className="font-display text-[20px] font-semibold" style={{ color: scoreColor(cov) }}>{pct(cov)}</span>
            <span className="text-[9px] text-[var(--faint)] uppercase tracking-wide">coverage</span>
          </div>
        </div>
        <div className="flex-1 space-y-1.5 text-[13px]">
          <div className="flex items-center gap-2">
            <FileCheck2 size={15} className="text-status-ok" />
            <span><b>{s.supported_count}</b> of {s.total_journals} journals evidenced</span>
          </div>
          <div className="flex items-center gap-2">
            <FileWarning size={15} className="text-status-immaterial" />
            <span><b>{s.unsupported_count}</b> journals lack documentation</span>
          </div>
          {s.unsupported_risky_journals.length > 0 && (
            <div className="pt-1">
              <div className="text-[11px] uppercase tracking-wide text-[var(--faint)] font-semibold mb-1">
                Undocumented + touching a break (priority)
              </div>
              <div className="flex flex-wrap gap-1">
                {s.unsupported_risky_journals.slice(0, 14).map((j) => (
                  <span key={j} className="px-1.5 py-0.5 rounded text-[11px] font-mono"
                    style={{ background: 'rgba(200,71,58,0.12)', color: 'var(--status-material)' }}>{j}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {s.vouchers && s.vouchers.length > 0 && (
        <div className="mt-4">
          <div className="text-[11px] uppercase tracking-wide text-[var(--faint)] font-semibold mb-1.5">
            Extracted vouchers <Pill tone="green">{s.vouchers.length}</Pill>
          </div>
          <div className="overflow-auto" style={{ maxHeight: 180 }}>
            <table className="w-full text-[12px]">
              <thead className="text-left text-[var(--faint)] text-[10.5px] uppercase">
                <tr><th className="py-1 pr-2">Journal</th><th className="py-1 pr-2">Date</th><th className="py-1 pr-2 text-right">Amount</th><th className="py-1">Approver</th></tr>
              </thead>
              <tbody>
                {s.vouchers.slice(0, 25).map((v, i) => (
                  <tr key={i} className="border-t border-[var(--border)]">
                    <td className="py-1 pr-2 font-mono">{v.journal_id || '—'}</td>
                    <td className="py-1 pr-2">{v.date || '—'}</td>
                    <td className="py-1 pr-2 text-right tabular-nums">{v.amount || '—'}</td>
                    <td className="py-1 truncate">{v.approver || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
};

export default DocumentationCard;
