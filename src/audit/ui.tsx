import React from 'react';
import type { ReconStatus } from './types';
import { STATUS_LABEL, STATUS_COLOR, STATUS_TINT } from './format';

export const Card: React.FC<{ title?: string; subtitle?: string; right?: React.ReactNode; className?: string; children: React.ReactNode }> =
  ({ title, subtitle, right, className = '', children }) => (
    <div className={`bg-white rounded-xl2 shadow-card border border-[var(--border)] ${className}`}>
      {(title || right) && (
        <div className="flex items-start justify-between px-5 pt-4 pb-2">
          <div>
            {title && <h3 className="font-display text-[15px] font-semibold text-ink">{title}</h3>}
            {subtitle && <p className="text-xs text-[var(--muted)] mt-0.5">{subtitle}</p>}
          </div>
          {right}
        </div>
      )}
      <div className="px-5 pb-5 pt-1">{children}</div>
    </div>
  );

export const StatusChip: React.FC<{ status: ReconStatus }> = ({ status }) => (
  <span
    className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium"
    style={{ color: STATUS_COLOR[status], background: STATUS_TINT[status] }}
  >
    <span className="w-1.5 h-1.5 rounded-full" style={{ background: STATUS_COLOR[status] }} />
    {STATUS_LABEL[status]}
  </span>
);

export const Pill: React.FC<{ children: React.ReactNode; tone?: 'green' | 'dark' | 'plain' }> =
  ({ children, tone = 'plain' }) => {
    const styles =
      tone === 'green'
        ? { background: 'var(--green-100)', color: 'var(--green-600)' }
        : tone === 'dark'
        ? { background: 'var(--coral-900)', color: 'var(--sidebar-fg)' }
        : { background: 'rgba(15,11,11,0.05)', color: 'var(--muted)' };
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium" style={styles}>
        {children}
      </span>
    );
  };
