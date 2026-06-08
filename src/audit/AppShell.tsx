import React, { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from 'react-query';
import { Loader2, ServerCrash } from 'lucide-react';
import Sidebar from './Sidebar';
import WorkCanvas from './WorkCanvas';
import UploadPanel from './UploadPanel';
import { fetchClients, fetchResult, deleteClient } from './api';
import type { PipelineResult, ClientSummary } from './types';

const AppShell: React.FC = () => {
  const qc = useQueryClient();
  const deepLink = new URLSearchParams(window.location.search).get('client');
  const [selected, setSelected] = useState<string | null>(deepLink);
  const [showUpload, setShowUpload] = useState(false);

  const clientsQ = useQuery('clients', fetchClients, { refetchOnWindowFocus: false });
  const clients = clientsQ.data?.clients ?? [];
  const aiAvailable = clientsQ.data?.ai_available ?? false;
  const aiProvider = clientsQ.data?.ai_provider ?? null;

  useEffect(() => {
    if (!selected && clients.length) setSelected(clients[0].client_id);
  }, [clients, selected]);

  const resultQ = useQuery(['result', selected], () => fetchResult(selected as string), {
    enabled: !!selected,
    refetchOnWindowFocus: false,
  });

  // Seed the freshly-computed result straight into the cache so a new ingest
  // displays immediately and reliably (no dependency on a follow-up refetch).
  const onDone = (result: PipelineResult) => {
    setShowUpload(false);
    qc.setQueryData(['result', result.client_id], result);
    setSelected(result.client_id);
    qc.invalidateQueries('clients');
  };

  const onDelete = async (c: ClientSummary) => {
    if (!window.confirm(`Remove "${c.client_name}" from the workspace?\n\n(Synthetic/pinned engagements reload on the next API restart.)`))
      return;
    if (selected === c.client_id) setSelected(null);
    await deleteClient(c.client_id);
    qc.removeQueries(['result', c.client_id]);
    await qc.invalidateQueries('clients');
  };

  const body = useMemo(() => {
    if (clientsQ.isLoading)
      return <Center><Loader2 className="animate-spin text-radioactive-600" /> Loading engagements…</Center>;
    if (clientsQ.isError)
      return <Center><ServerCrash className="text-status-material" /> Backend unreachable — is the API running on :8080?</Center>;
    if (!clients.length)
      return <Center>No engagements yet. Run <code className="mx-1">scripts/generate_dataset.py</code> or use “New ingest”.</Center>;
    if (resultQ.isLoading || !resultQ.data)
      return <Center><Loader2 className="animate-spin text-radioactive-600" /> Running pipeline…</Center>;
    return <WorkCanvas result={resultQ.data} />;
  }, [clientsQ.isLoading, clientsQ.isError, clients.length, resultQ.isLoading, resultQ.data]);

  return (
    <div className="flex h-full">
      <Sidebar clients={clients} selected={selected} onSelect={setSelected}
        onNew={() => setShowUpload(true)} onDelete={onDelete}
        aiAvailable={aiAvailable} aiProvider={aiProvider} />
      {body}
      {showUpload && (
        <UploadPanel onClose={() => setShowUpload(false)} onDone={onDone} aiAvailable={aiAvailable} />
      )}
    </div>
  );
};

const Center: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="flex-1 flex items-center justify-center">
    <div className="flex items-center gap-2 text-[14px] text-[var(--muted)]">{children}</div>
  </div>
);

export default AppShell;
