import React, { useState } from 'react';
import { LayoutGrid, Scale, CopyX, GitBranch } from 'lucide-react';
import type { PipelineResult } from '../types';
import KpiCards from './KpiCards';
import QualityRadar from './QualityRadar';
import FlowSankey from './FlowSankey';
import ReconHeatmap from './ReconHeatmap';
import ReconTable from './ReconTable';
import DuplicatesPanel from './DuplicatesPanel';
import MappingReview from './MappingReview';
import AuditTrailView from './AuditTrailView';
import DocumentationCard from './DocumentationCard';
import { Card } from '../ui';

const TABS = [
  { id: 'overview', label: 'Overview', icon: LayoutGrid },
  { id: 'reconcile', label: 'Reconciliation', icon: Scale },
  { id: 'duplicates', label: 'Quality & Dupes', icon: CopyX },
  { id: 'lineage', label: 'Lineage', icon: GitBranch },
] as const;

const ValidationCard: React.FC<{ result: PipelineResult }> = ({ result }) => {
  const v = result.validation;
  const items: [string, string][] = [
    ['Unbalanced journals', String(v.double_entry.unbalanced_count)],
    ['GL-only accounts', v.referential_integrity.gl_only_accounts.join(', ') || 'none'],
    ['TB-only accounts', v.referential_integrity.tb_only_accounts.join(', ') || 'none'],
    ['Bad DR/CR values', String(v.validity.bad_dr_cr ?? 0)],
    ['Out-of-period dates', String(v.validity.out_of_period ?? 0)],
  ];
  return (
    <Card title="Validation results" subtitle="Deterministic assurance checks">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
        {items.map(([k, val]) => (
          <div key={k} className="flex items-center justify-between text-[13px] border-b border-[var(--border)] py-1.5">
            <span className="text-[var(--muted)]">{k}</span>
            <span className="font-medium text-ink">{val}</span>
          </div>
        ))}
      </div>
    </Card>
  );
};

const urlTab = (): (typeof TABS)[number]['id'] => {
  const t = new URLSearchParams(window.location.search).get('tab');
  return (TABS.some((x) => x.id === t) ? t : 'overview') as (typeof TABS)[number]['id'];
};

const DashboardTabs: React.FC<{ result: PipelineResult }> = ({ result }) => {
  const [tab, setTab] = useState<(typeof TABS)[number]['id']>(urlTab);

  return (
    <div className="space-y-4">
      <div className="flex gap-1.5">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-[13px] font-medium transition-colors"
              style={active
                ? { background: 'var(--coral-black)', color: 'var(--sidebar-fg)' }
                : { background: 'white', color: 'var(--muted)', border: '1px solid var(--border)' }}>
              <Icon size={14} /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === 'overview' && (
        <div className="space-y-4 ll-fade-up">
          <KpiCards result={result} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <QualityRadar result={result} />
            <MappingReview result={result} />
          </div>
          {result.support && <DocumentationCard result={result} />}
          <FlowSankey result={result} />
        </div>
      )}

      {tab === 'reconcile' && (
        <div className="space-y-4 ll-fade-up">
          <ReconHeatmap result={result} />
          <ReconTable result={result} />
        </div>
      )}

      {tab === 'duplicates' && (
        <div className="space-y-4 ll-fade-up">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <DuplicatesPanel result={result} />
            <ValidationCard result={result} />
          </div>
          {result.support && <DocumentationCard result={result} />}
          <QualityRadar result={result} />
        </div>
      )}

      {tab === 'lineage' && (
        <div className="ll-fade-up"><AuditTrailView result={result} /></div>
      )}
    </div>
  );
};

export default DashboardTabs;
