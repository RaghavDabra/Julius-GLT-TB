import React from 'react';
import type { PipelineResult, HeatmapCell } from '../types';
import { Card } from '../ui';
import { money, STATUS_LABEL } from '../format';

// Reconciled = green; breaks ramp amber→red by variance/materiality; orphans = orange.
function cellColor(c: HeatmapCell): string {
  if (c.status === 'reconciled') return 'rgba(95,162,60,0.85)';
  if (c.status === 'gl_only' || c.status === 'tb_only') return 'rgba(181,116,60,0.9)';
  const t = Math.min(Math.max(c.intensity, 0.15), 1);
  // interpolate amber (201,154,30) -> red (200,71,58)
  const r = Math.round(201 + (200 - 201) * t);
  const g = Math.round(154 + (71 - 154) * t);
  const b = Math.round(30 + (58 - 30) * t);
  return `rgb(${r},${g},${b})`;
}

const LEGEND = [
  ['reconciled', 'Reconciled'],
  ['immaterial_break', 'Immaterial'],
  ['material_break', 'Material'],
  ['gl_only', 'Orphan'],
] as const;

const ReconHeatmap: React.FC<{ result: PipelineResult }> = ({ result }) => {
  const cells = result.heatmap.cells;
  const cats = Array.from(new Set(cells.map((c) => c.category)));

  return (
    <Card title="Reconciliation heatmap"
      subtitle={`Accounts coloured by status & variance · materiality ${money(result.heatmap.materiality)}`}
      right={
        <div className="flex flex-wrap gap-2.5">
          {LEGEND.map(([s, label]) => (
            <span key={s} className="flex items-center gap-1.5 text-[11px] text-[var(--muted)]">
              <span className="w-3 h-3 rounded-sm" style={{ background: cellColor({ status: s, intensity: 1 } as HeatmapCell) }} />
              {label}
            </span>
          ))}
        </div>
      }
    >
      <div className="space-y-3">
        {cats.map((cat) => (
          <div key={cat}>
            <div className="text-[11px] uppercase tracking-wide text-[var(--faint)] font-semibold mb-1.5">{cat}</div>
            <div className="flex flex-wrap gap-1.5">
              {cells.filter((c) => c.category === cat).map((c) => (
                <div
                  key={c.account_code}
                  title={`${c.account_code} ${c.account_name}\n${STATUS_LABEL[c.status]}\nvariance ${money(c.variance)}`}
                  className="rounded-md flex flex-col items-center justify-center cursor-default transition-transform hover:scale-[1.06]"
                  style={{ width: 62, height: 46, background: cellColor(c), color: '#fff' }}
                >
                  <span className="text-[11px] font-semibold leading-none">{c.account_code}</span>
                  <span className="text-[9px] opacity-90 mt-0.5 leading-none">
                    {c.status === 'reconciled' ? '✓' : money(Math.abs(c.variance))}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};

export default ReconHeatmap;
