import React, { useState } from 'react';
import { Search, Plus, ShieldCheck, Sparkles, Cpu, Trash2 } from 'lucide-react';
import type { ClientSummary } from './types';

const dqColor = (s: number) =>
  s >= 0.95 ? '#86BC24' : s >= 0.85 ? '#C99A1E' : '#C8473A';

const Sidebar: React.FC<{
  clients: ClientSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (c: ClientSummary) => void;
  aiAvailable: boolean;
  aiProvider?: string | null;
}> = ({ clients, selected, onSelect, onNew, onDelete, aiAvailable, aiProvider }) => {
  const [q, setQ] = useState('');
  const filtered = clients.filter((c) => c.client_name.toLowerCase().includes(q.toLowerCase()));

  return (
    <aside className="dark-scroll flex flex-col h-full w-[264px] shrink-0"
      style={{ background: 'var(--coral-black)', color: 'var(--sidebar-fg)' }}>
      {/* brand */}
      <div className="px-4 pt-5 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'var(--green)' }}>
            <ShieldCheck size={18} className="text-coral-black" />
          </div>
          <div>
            <div className="font-display text-[17px] font-bold leading-none">
              Ledger<span style={{ color: 'var(--green)' }}>Lens</span>
            </div>
            <div className="text-[10px] tracking-wide" style={{ color: 'var(--sidebar-muted)' }}>
              Assurance Data Pipeline
            </div>
          </div>
        </div>
      </div>

      <div className="px-3">
        <button onClick={onNew}
          className="w-full flex items-center justify-center gap-2 py-2 rounded-lg text-[13px] font-medium transition-colors"
          style={{ background: 'var(--green)', color: 'var(--coral-black)' }}>
          <Plus size={15} /> New ingest
        </button>
      </div>

      {/* search */}
      <div className="px-3 mt-3">
        <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg" style={{ background: 'var(--coral-800)' }}>
          <Search size={14} style={{ color: 'var(--sidebar-muted)' }} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search engagements"
            className="bg-transparent outline-none text-[13px] w-full placeholder:text-[var(--sidebar-muted)]"
            style={{ color: 'var(--sidebar-fg)' }} />
        </div>
      </div>

      <div className="px-4 mt-3.5 mb-1 text-[10px] uppercase tracking-wider font-semibold"
        style={{ color: 'var(--sidebar-muted)' }}>
        Engagements · {filtered.length}
      </div>

      <nav className="flex-1 overflow-auto px-2 pb-2">
        {filtered.map((c) => {
          const active = c.client_id === selected;
          return (
            <div key={c.client_id}
              className={`group relative rounded-lg mb-0.5 transition-colors ${active ? '' : 'hover:bg-coral-900'}`}
              style={active ? { background: 'var(--coral-700)' } : undefined}>
              <button onClick={() => onSelect(c.client_id)} className="w-full text-left px-2.5 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium truncate flex items-center gap-2">
                    {active && <span className="w-1 h-3.5 rounded-full" style={{ background: 'var(--green)' }} />}
                    {c.client_name}
                  </span>
                  <span className="text-[11px] font-semibold tabular-nums shrink-0 transition-opacity group-hover:opacity-0"
                    style={{ color: dqColor(c.dq_overall) }}>
                    {Math.round(c.dq_overall * 100)}%
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-0.5 text-[10.5px]" style={{ color: 'var(--sidebar-muted)' }}>
                  <span>{c.gl_rows} txns</span>
                  {c.material_breaks > 0 && (
                    <span style={{ color: '#E0826F' }}>· {c.material_breaks} material</span>
                  )}
                  {c.dupes_flagged > 0 && <span>· {c.dupes_flagged} dupes</span>}
                </div>
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(c); }}
                title={`Delete ${c.client_name}`}
                className="absolute right-1.5 top-2 p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity hover:bg-coral-700">
                <Trash2 size={13} style={{ color: '#E0826F' }} />
              </button>
            </div>
          );
        })}
      </nav>

      {/* footer status */}
      <div className="px-4 py-3 border-t" style={{ borderColor: 'var(--coral-800)' }}>
        <div className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--sidebar-muted)' }}>
          {aiAvailable
            ? <><Sparkles size={12} style={{ color: 'var(--green)' }} /> {aiProvider === 'openai' ? 'GPT-4o' : 'Gemini'} reasoning active</>
            : <><Cpu size={12} /> Deterministic mode (no AI key)</>}
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
