import React from 'react';
import { Sparkles } from 'lucide-react';
import type { PipelineResult } from '../types';
import { Card } from '../ui';

const STAGE_COLOR: Record<string, string> = {
  ingest: '#6B7BB5', clean: '#86BC24', validate: '#C99A1E',
  dedupe: '#B5743C', reconcile: '#C8473A',
};

const AuditTrailView: React.FC<{ result: PipelineResult }> = ({ result }) => (
  <Card title="Audit trail" subtitle="Append-only lineage from raw upload to reconciled output">
    <ol className="relative border-l border-[var(--border)] ml-2">
      {result.trail.map((t) => (
        <li key={t.seq} className="ml-4 pb-3 last:pb-0">
          <span className="absolute -left-[5px] w-2.5 h-2.5 rounded-full"
            style={{ background: STAGE_COLOR[t.stage] || 'var(--muted)' }} />
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[11px] font-semibold uppercase tracking-wide"
              style={{ color: STAGE_COLOR[t.stage] || 'var(--muted)' }}>{t.stage}</span>
            <span className="text-[13px] font-medium text-ink">{t.action}</span>
            {t.ai_used && <Sparkles size={12} className="text-radioactive-600" />}
            <span className="text-[11px] text-[var(--faint)]">· {t.rows_affected} rows</span>
          </div>
          {t.details && <div className="text-[12px] text-[var(--muted)] mt-0.5">{t.details}</div>}
        </li>
      ))}
    </ol>
  </Card>
);

export default AuditTrailView;
