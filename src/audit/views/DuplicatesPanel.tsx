import React from 'react';
import { CopyX } from 'lucide-react';
import type { PipelineResult } from '../types';
import { Card, Pill } from '../ui';
import { money } from '../format';

const DuplicatesPanel: React.FC<{ result: PipelineResult; compact?: boolean }> = ({ result, compact }) => {
  const dups = result.duplicates;
  return (
    <Card title="Duplicate transactions"
      subtitle="Exact & near-duplicate postings — flagged for review, never auto-removed">
      {dups.length === 0 ? (
        <div className="text-sm text-[var(--muted)] py-6 text-center">No duplicate transactions detected ✓</div>
      ) : (
        <div className="space-y-2.5" style={{ maxHeight: compact ? 280 : undefined, overflow: 'auto' }}>
          {dups.map((d) => {
            const r0 = d.rows[0];
            return (
              <div key={d.group_id} className="rounded-lg border border-[var(--border)] p-3 bg-[var(--canvas)]">
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    <CopyX size={14} className="text-status-immaterial" />
                    <span className="font-medium text-[13px]">Group {d.group_id}</span>
                    <Pill tone={d.kind === 'exact' ? 'dark' : 'plain'}>{d.kind}</Pill>
                  </div>
                  <span className="text-[11px] text-[var(--faint)]">similarity {Math.round(d.score * 100)}% · {d.rows.length} rows</span>
                </div>
                <div className="text-[12px] text-[var(--muted)] grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-0.5">
                  <span>acct <b className="text-ink font-mono">{r0.account_code}</b></span>
                  <span>amount <b className="text-ink">{typeof r0.amount === 'number' ? money(r0.amount) : r0.amount}</b></span>
                  <span className="col-span-2 truncate">“{r0.description || r0.transaction_id}”</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
};

export default DuplicatesPanel;
