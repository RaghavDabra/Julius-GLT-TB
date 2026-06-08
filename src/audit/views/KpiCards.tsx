import React from 'react';
import { CheckCircle2, AlertTriangle, CopyX, Gauge, FileText, Layers, FileCheck2 } from 'lucide-react';
import type { PipelineResult } from '../types';
import { money, pct, scoreColor } from '../format';

const Stat: React.FC<{
  icon: React.ReactNode; label: string; value: string; sub?: string; accent?: string;
}> = ({ icon, label, value, sub, accent }) => (
  <div className="bg-white rounded-xl2 shadow-card border border-[var(--border)] p-4 flex flex-col gap-2">
    <div className="flex items-center justify-between">
      <span className="text-[11px] uppercase tracking-wide text-[var(--faint)] font-semibold">{label}</span>
      <span style={{ color: accent || 'var(--green-600)' }}>{icon}</span>
    </div>
    <div className="font-display text-[26px] leading-none font-semibold text-ink">{value}</div>
    {sub && <div className="text-xs text-[var(--muted)]">{sub}</div>}
  </div>
);

const KpiCards: React.FC<{ result: PipelineResult }> = ({ result }) => {
  const k = result.kpis;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
      <Stat icon={<Gauge size={17} />} label="Data quality" value={pct(k.dq_overall)}
        sub="weighted across 6 dimensions" accent={scoreColor(k.dq_overall)} />
      <Stat icon={<CheckCircle2 size={17} />} label="Reconciled" value={pct(k.reconciled_pct)}
        sub={`${result.reconciliation.length} accounts`} accent="var(--status-ok)" />
      <Stat icon={<AlertTriangle size={17} />} label="Material breaks" value={String(k.material_breaks)}
        sub={`${k.immaterial_breaks} immaterial`} accent="var(--status-material)" />
      <Stat icon={<CopyX size={17} />} label="Duplicate groups" value={String(k.dupes_flagged)}
        sub="flagged, not dropped" accent="var(--status-immaterial)" />
      <Stat icon={<Layers size={17} />} label="GL transactions" value={k.gl_rows.toLocaleString()}
        sub={`${k.journals} journals`} />
      <Stat icon={<FileText size={17} />} label="Materiality" value={money(k.materiality)}
        sub="max(1% of |TB|, 1,000)" />
      {k.doc_coverage !== null && k.doc_coverage !== undefined && (
        <Stat icon={<FileCheck2 size={17} />} label="Doc coverage" value={pct(k.doc_coverage)}
          sub={`${k.unsupported_journals ?? 0} journals unevidenced`}
          accent={scoreColor(k.doc_coverage)} />
      )}
    </div>
  );
};

export default KpiCards;
