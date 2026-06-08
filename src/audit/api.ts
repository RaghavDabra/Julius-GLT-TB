// Typed API client for the LedgerLens backend (Flask, :8080).
import axios from 'axios';
import type { PipelineResult, ClientSummary } from './types';

const BASE = (import.meta as any).env?.VITE_API_BASE || 'http://localhost:8080';

export const api = axios.create({ baseURL: BASE });

export async function fetchClients(): Promise<{ clients: ClientSummary[]; ai_available: boolean; ai_provider?: string | null }> {
  const { data } = await api.get('/api/clients');
  return data;
}

export async function fetchResult(clientId: string): Promise<PipelineResult> {
  const { data } = await api.get(`/api/result/${clientId}`);
  return data;
}

export async function deleteClient(clientId: string): Promise<void> {
  await api.delete(`/api/clients/${clientId}`);
}

export interface ChatReply { text: string; source: 'gemini' | 'openai' | 'fallback' }

export async function askChat(
  clientId: string,
  question: string,
  history: { role: string; content: string }[],
): Promise<ChatReply> {
  const { data } = await api.post('/api/chat', { client_id: clientId, question, history });
  return data;
}

export async function requestExplanations(clientId: string) {
  const { data } = await api.post('/api/ai/explain', { client_id: clientId });
  return data.ai;
}

export async function runUpload(
  gl: File,
  tb: File | null,
  docs: File[],
  clientName: string,
  useAi: boolean,
): Promise<PipelineResult> {
  const form = new FormData();
  form.append('gl', gl);
  if (tb) form.append('tb', tb);
  docs.forEach((d) => form.append('docs', d));
  form.append('client_name', clientName);
  form.append('ai', String(useAi));
  const { data } = await api.post('/api/run', form);
  return data;
}

export function reportPdfUrl(clientId: string) {
  return `${BASE}/api/report/${clientId}.pdf`;
}
export function reportJsonUrl(clientId: string) {
  return `${BASE}/api/report/${clientId}.json`;
}
