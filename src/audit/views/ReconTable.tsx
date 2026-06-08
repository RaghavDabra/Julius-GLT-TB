import React, { useState } from 'react';
import type { PipelineResult } from '../types';
import { Card, StatusChip } from '../ui';
import { money } from '../format';

const ReconTable: React.FC<{ result: PipelineResult; compact?: boolean }> = ({ result, compact }) => {
  const [onlyBreaks, setOnlyBreaks] = useState(true);
  const rows = result.reconciliation
    .filter((r) => (onlyBreaks ? r.status !== 'reconciled' : true))
    .sort((a, b) => b.abs_variance - a.abs_variance);

  const body = (
    <div className="overflow-auto" style={{ maxHeight: compact ? 280 : 520 }}>
      <table className="w-full text-[13px]">
        <thead className="sticky top-0 bg-white">
          <tr className="text-left text-[var(--faint)] text-[11px] uppercase tracking-wide border-b border-[var(--border)]">
            <th className="py-2 pr-3 font-semibold">Account</th>
            <th className="py-2 pr-3 font-semibold">Name</th>
            <th className="py-2 pr-3 font-semibold text-right">GL balance</th>
            <th className="py-2 pr-3 font-semibold text-right">TB balance</th>
            <th className="py-2 pr-3 font-semibold text-right">Variance</th>
            <th className="py-2 font-semibold">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.account_code} className="border-b border-[var(--border)] hover:bg-[var(--canvas)]">
              <td className="py-2 pr-3 font-mono text-[12px]">{r.account_code}</td>
              <td className="py-2 pr-3">{r.account_name}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{money(r.gl_balance)}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{money(r.tb_balance)}</td>
              <td className="py-2 pr-3 text-right tabular-nums font-medium"
                style={{ color: r.status === 'reconciled' ? 'var(--muted)' : 'var(--status-material)' }}>
                {r.variance === 0 ? '—' : money(r.variance)}
              </td>
              <td className="py-2"><StatusChip status={r.status} /></td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr><td colSpan={6} className="py-6 text-center text-[var(--muted)]">All accounts reconcile within tolerance ✓</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );

  return (
    <Card
      title="Reconciliation findings"
      subtitle="GL-derived balance vs Trial Balance, per account"
      right={
        <button
          onClick={() => setOnlyBreaks((v) => !v)}
          className="text-[12px] px-2.5 py-1 rounded-full border border-[var(--border)] text-[var(--muted)] hover:bg-[var(--canvas)]"
        >
          {onlyBreaks ? 'Show all accounts' : 'Breaks only'}
        </button>
      }
    >
      {body}
    </Card>
  );
};

export default ReconTable;
