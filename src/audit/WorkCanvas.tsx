import React, { useEffect, useState } from 'react';
import { MessageSquare, LayoutDashboard } from 'lucide-react';
import type { PipelineResult } from './types';
import { pct, scoreColor } from './format';
import ChatThread from './ChatThread';
import DashboardTabs from './views/DashboardTabs';
import ReportDownload from './views/ReportDownload';

const initialView = (): 'chat' | 'dashboard' =>
  new URLSearchParams(window.location.search).get('view') === 'dashboard' ? 'dashboard' : 'chat';

const WorkCanvas: React.FC<{ result: PipelineResult }> = ({ result }) => {
  const [view, setView] = useState<'chat' | 'dashboard'>(initialView);
  useEffect(() => setView(initialView()), [result.client_id]);

  return (
    <main className="flex-1 flex flex-col h-full min-h-0 min-w-0">
      {/* header */}
      <header className="flex items-center justify-between gap-3 px-4 sm:px-8 py-3 border-b border-[var(--border)] bg-canvas">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5">
            <h2 className="font-display text-[17px] font-semibold text-ink truncate">{result.client_name}</h2>
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full"
              style={{ color: scoreColor(result.scorecard.overall), background: 'rgba(15,11,11,0.04)' }}>
              DQ {pct(result.scorecard.overall)}
            </span>
          </div>
          <div className="text-[11.5px] text-[var(--muted)] mt-0.5">
            {result.kpis.gl_rows.toLocaleString()} transactions · {result.kpis.material_breaks} material break(s) · {result.kpis.dupes_flagged} duplicate group(s)
          </div>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <div className="flex p-0.5 rounded-lg" style={{ background: 'rgba(15,11,11,0.05)' }}>
            {([['chat', 'Chat', MessageSquare], ['dashboard', 'Dashboard', LayoutDashboard]] as const).map(
              ([id, label, Icon]) => (
                <button key={id} onClick={() => setView(id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[13px] font-medium transition-colors"
                  style={view === id ? { background: 'white', color: 'var(--ink)', boxShadow: '0 1px 2px rgba(15,11,11,0.06)' } : { color: 'var(--muted)' }}>
                  <Icon size={14} /> {label}
                </button>
              ),
            )}
          </div>
          <div className="hidden md:block"><ReportDownload clientId={result.client_id} /></div>
        </div>
      </header>

      {/* body */}
      {view === 'chat' ? (
        <ChatThread result={result} onOpenDashboard={() => setView('dashboard')} />
      ) : (
        <div className="flex-1 overflow-auto px-4 sm:px-8 py-5">
          <div className="max-w-[1180px] mx-auto">
            <div className="md:hidden mb-4"><ReportDownload clientId={result.client_id} /></div>
            <DashboardTabs result={result} />
          </div>
        </div>
      )}
    </main>
  );
};

export default WorkCanvas;
