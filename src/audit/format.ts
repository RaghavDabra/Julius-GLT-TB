import type { ReconStatus } from './types';

export const money = (v: number | null | undefined) =>
  v === null || v === undefined
    ? '—'
    : v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const pct = (v: number) => `${Math.round(v * 100)}%`;

export const STATUS_LABEL: Record<ReconStatus, string> = {
  reconciled: 'Reconciled',
  immaterial_break: 'Immaterial break',
  material_break: 'Material break',
  gl_only: 'GL only',
  tb_only: 'TB only',
};

export const STATUS_COLOR: Record<ReconStatus, string> = {
  reconciled: 'var(--status-ok)',
  immaterial_break: 'var(--status-immaterial)',
  material_break: 'var(--status-material)',
  gl_only: 'var(--status-orphan)',
  tb_only: 'var(--status-orphan)',
};

// soft background tint for status chips / cells
export const STATUS_TINT: Record<ReconStatus, string> = {
  reconciled: 'rgba(95,162,60,0.12)',
  immaterial_break: 'rgba(201,154,30,0.14)',
  material_break: 'rgba(200,71,58,0.13)',
  gl_only: 'rgba(181,116,60,0.14)',
  tb_only: 'rgba(181,116,60,0.14)',
};

export const scoreColor = (s: number) =>
  s >= 0.9 ? 'var(--status-ok)' : s >= 0.7 ? 'var(--status-immaterial)' : 'var(--status-material)';

export const DIMENSIONS = [
  'completeness',
  'validity',
  'consistency',
  'uniqueness',
  'accuracy',
  'timeliness',
] as const;
