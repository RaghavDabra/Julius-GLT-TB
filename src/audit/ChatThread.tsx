import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ArrowUp, Sparkles, Cpu, FileText } from 'lucide-react';
import type { PipelineResult } from './types';
import { askChat } from './api';
import { pct, money } from './format';
import ReconTable from './views/ReconTable';
import QualityRadar from './views/QualityRadar';
import DuplicatesPanel from './views/DuplicatesPanel';
import FlowSankey from './views/FlowSankey';
import KpiCards from './views/KpiCards';

type Kind = 'text' | 'recon' | 'radar' | 'dupes' | 'sankey' | 'kpis';
type Source = 'gemini' | 'openai' | 'fallback';
interface Msg { id: number; role: 'user' | 'assistant'; kind: Kind; text?: string; source?: Source; }

let _id = 0;
const nid = () => ++_id;

const QUICK: { label: string; kind?: Kind; q?: string; lead?: string }[] = [
  { label: 'Overview', kind: 'kpis', lead: 'Here are the headline figures for this engagement:' },
  { label: 'Reconciliation breaks', kind: 'recon', lead: 'These accounts did not reconcile against the trial balance:' },
  { label: 'Data-quality radar', kind: 'radar', lead: 'Data quality across the six assurance dimensions:' },
  { label: 'Duplicate findings', kind: 'dupes', lead: 'Potential duplicate postings flagged for review:' },
  { label: 'Transaction flow', kind: 'sankey', lead: 'How postings flow from the ledger to reconciliation status:' },
  { label: 'How was the data cleaned?', q: 'How was the data ingested and cleaned — which headers were mapped, what values were standardised/replaced, and which rows were affected?' },
  { label: 'Documentation coverage', q: 'What is the supporting-documentation coverage, and which undocumented journals touch a reconciliation break?' },
  { label: 'Explain the largest break', q: 'Explain the largest reconciliation break, its variance and the most likely root cause.' },
  { label: 'Summarise the key risks', q: 'Summarise the key audit risks for this engagement as concise bullet points.' },
];

function welcome(result: PipelineResult): string {
  const k = result.kpis;
  return [
    `**${result.client_name}** is loaded. I ran the full deterministic pipeline — ingestion, cleaning, validation, deduplication and GL↔TB reconciliation — and every figure below traces back through the audit trail.`,
    '',
    `- **${k.gl_rows.toLocaleString()}** GL transactions across **${k.journals}** journals, reconciled to **${k.tb_accounts}** TB accounts`,
    `- **${pct(k.reconciled_pct)}** of accounts reconciled · **${k.material_breaks}** material break(s), **${k.immaterial_breaks}** immaterial`,
    `- **${k.dupes_flagged}** duplicate group(s) flagged · overall data quality **${pct(k.dq_overall)}** · materiality ${money(k.materiality)}`,
    '',
    'Ask me anything about the data, or use a shortcut below.',
  ].join('\n');
}

const SourceBadge: React.FC<{ source?: Source }> = ({ source }) =>
  source === 'gemini' || source === 'openai' ? (
    <span className="inline-flex items-center gap-1 text-[10px] text-radioactive-600 font-medium">
      <Sparkles size={11} /> {source === 'gemini' ? 'Gemini' : 'GPT-4o'}
    </span>
  ) : source === 'fallback' ? (
    <span className="inline-flex items-center gap-1 text-[10px] text-[var(--faint)] font-medium">
      <Cpu size={11} /> Deterministic
    </span>
  ) : null;

const Inline: React.FC<{ kind: Kind; result: PipelineResult }> = ({ kind, result }) => {
  if (kind === 'recon') return <ReconTable result={result} compact />;
  if (kind === 'radar') return <QualityRadar result={result} />;
  if (kind === 'dupes') return <DuplicatesPanel result={result} compact />;
  if (kind === 'sankey') return <FlowSankey result={result} />;
  if (kind === 'kpis') return <KpiCards result={result} />;
  return null;
};

const ChatThread: React.FC<{ result: PipelineResult; onOpenDashboard: () => void }> = ({ result, onOpenDashboard }) => {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setMsgs([{ id: nid(), role: 'assistant', kind: 'text', text: welcome(result) }]);
  }, [result.client_id]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [msgs, busy]);

  const history = () =>
    msgs.filter((m) => m.text).map((m) => ({ role: m.role, content: m.text as string }));

  async function sendText(q: string) {
    if (!q.trim() || busy) return;
    setMsgs((m) => [...m, { id: nid(), role: 'user', kind: 'text', text: q }]);
    setInput('');
    setBusy(true);
    try {
      const reply = await askChat(result.client_id, q, history());
      setMsgs((m) => [...m, { id: nid(), role: 'assistant', kind: 'text', text: reply.text, source: reply.source }]);
    } catch {
      setMsgs((m) => [...m, { id: nid(), role: 'assistant', kind: 'text', text: 'Sorry — I could not reach the audit service.', source: 'fallback' }]);
    } finally {
      setBusy(false);
    }
  }

  function quick(item: (typeof QUICK)[number]) {
    if (item.q) return sendText(item.q);
    if (item.kind) {
      setMsgs((m) => [
        ...m,
        { id: nid(), role: 'user', kind: 'text', text: item.label },
        { id: nid(), role: 'assistant', kind: 'text', text: item.lead },
        { id: nid(), role: 'assistant', kind: item.kind!, source: 'fallback' },
      ]);
    }
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div ref={scrollRef} className="flex-1 min-h-0 overflow-auto px-4 sm:px-8 py-6">
        <div className="max-w-[820px] mx-auto space-y-5">
          {msgs.map((m) => (
            <div key={m.id} className={`ll-fade-up flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {m.role === 'user' ? (
                <div className="max-w-[80%] rounded-2xl rounded-br-md px-4 py-2.5 text-[14px] text-white"
                  style={{ background: 'var(--coral-black)' }}>
                  {m.text}
                </div>
              ) : m.kind === 'text' ? (
                <div className="max-w-[88%]">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="w-5 h-5 rounded-md flex items-center justify-center" style={{ background: 'var(--green)' }}>
                      <span className="text-[10px] font-bold text-coral-black">L</span>
                    </div>
                    <span className="text-[12px] font-semibold text-ink">LedgerLens</span>
                    <SourceBadge source={m.source} />
                  </div>
                  <div className="md text-[14px] text-ink pl-7">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text || ''}</ReactMarkdown>
                  </div>
                </div>
              ) : (
                <div className="w-full pl-7"><Inline kind={m.kind} result={result} /></div>
              )}
            </div>
          ))}
          {busy && (
            <div className="flex items-center gap-2 pl-7 text-[var(--muted)]">
              <span className="ll-pulse flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-radioactive-green inline-block" />
                <span className="w-1.5 h-1.5 rounded-full bg-radioactive-green inline-block" />
                <span className="w-1.5 h-1.5 rounded-full bg-radioactive-green inline-block" />
              </span>
              <span className="text-[12px]">analysing the audit results…</span>
            </div>
          )}
        </div>
      </div>

      {/* composer */}
      <div className="border-t border-[var(--border)] bg-canvas px-4 sm:px-8 py-3">
        <div className="max-w-[820px] mx-auto">
          <div className="flex flex-wrap gap-1.5 mb-2.5">
            {QUICK.map((q) => (
              <button key={q.label} onClick={() => quick(q)} disabled={busy}
                className="text-[12px] px-2.5 py-1 rounded-full border border-[var(--border)] bg-white text-[var(--muted)] hover:border-radioactive-300 hover:text-ink transition-colors disabled:opacity-50">
                {q.label}
              </button>
            ))}
            <button onClick={onOpenDashboard}
              className="text-[12px] px-2.5 py-1 rounded-full text-radioactive-600 font-medium hover:underline flex items-center gap-1">
              <FileText size={12} /> Open dashboard
            </button>
          </div>
          <div className="flex items-end gap-2 bg-white rounded-2xl border border-[var(--border)] shadow-card px-3 py-2">
            <textarea
              ref={taRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                if (taRef.current) { taRef.current.style.height = 'auto'; taRef.current.style.height = Math.min(taRef.current.scrollHeight, 150) + 'px'; }
              }}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendText(input); } }}
              rows={1}
              placeholder={`Ask about ${result.client_name}…`}
              className="flex-1 resize-none outline-none text-[14px] bg-transparent py-1.5 max-h-[150px]"
            />
            <button onClick={() => sendText(input)} disabled={busy || !input.trim()}
              className="w-8 h-8 rounded-full flex items-center justify-center text-white disabled:opacity-40 transition-opacity"
              style={{ background: 'var(--coral-black)' }}>
              <ArrowUp size={16} />
            </button>
          </div>
          <p className="text-[10.5px] text-[var(--faint)] text-center mt-2">
            Answers are grounded in the computed pipeline outputs · figures are deterministic and auditable
          </p>
        </div>
      </div>
    </div>
  );
};

export default ChatThread;
