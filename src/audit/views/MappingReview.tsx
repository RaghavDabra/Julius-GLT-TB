import React from 'react';
import { ArrowRight, Sparkles, Check } from 'lucide-react';
import type { PipelineResult, MappingDecision } from '../types';
import { Card, Pill } from '../ui';

const METHOD_LABEL: Record<string, string> = {
  exact_synonym: 'Exact synonym',
  fuzzy_difflib: 'Fuzzy match',
  ai_suggested: 'AI suggested',
  unmapped: 'Unmapped',
};

const Row: React.FC<{ d: MappingDecision }> = ({ d }) => (
  <div className="flex items-center justify-between py-1.5 border-b border-[var(--border)] last:border-0 text-[13px]">
    <div className="flex items-center gap-2 min-w-0">
      <code className="font-mono text-[12px] text-[var(--muted)] truncate">{d.raw}</code>
      <ArrowRight size={13} className="text-[var(--faint)] shrink-0" />
      <span className="font-medium text-ink truncate">{d.canonical || '—'}</span>
    </div>
    <div className="flex items-center gap-2 shrink-0">
      {d.ai_used && <Sparkles size={12} className="text-radioactive-600" />}
      <Pill tone={d.method === 'exact_synonym' ? 'green' : 'plain'}>
        {METHOD_LABEL[d.method] || d.method}
      </Pill>
      <span className="text-[11px] text-[var(--faint)] w-9 text-right tabular-nums">
        {Math.round(d.confidence * 100)}%
      </span>
    </div>
  </div>
);

const MappingReview: React.FC<{ result: PipelineResult }> = ({ result }) => {
  const gl = result.mapping.gl_decisions;
  const aiUsed = gl.some((d) => d.ai_used) || result.mapping.tb_decisions.some((d) => d.ai_used);
  return (
    <Card title="Schema mapping"
      subtitle="Heterogeneous client headers → canonical fields"
      right={
        <span className="flex items-center gap-1.5 text-[11px] text-[var(--muted)]">
          <Check size={13} className="text-status-ok" />
          {aiUsed ? 'AI used for unmatched only' : 'Fully deterministic'}
        </span>
      }>
      <div className="text-[11px] uppercase tracking-wide text-[var(--faint)] font-semibold mb-1">General Ledger</div>
      {gl.map((d, i) => <Row key={i} d={d} />)}
      <div className="text-[11px] uppercase tracking-wide text-[var(--faint)] font-semibold mb-1 mt-3">Trial Balance</div>
      {result.mapping.tb_decisions.map((d, i) => <Row key={i} d={d} />)}
    </Card>
  );
};

export default MappingReview;
