// Shared types mirroring the backend PipelineResult (api/pipeline/runner.py).

export interface ScoreCard {
  completeness: number;
  validity: number;
  consistency: number;
  uniqueness: number;
  accuracy: number;
  timeliness: number;
  overall: number;
}

export type ReconStatus =
  | 'reconciled'
  | 'immaterial_break'
  | 'material_break'
  | 'gl_only'
  | 'tb_only';

export interface ReconRow {
  account_code: string;
  account_name: string;
  category: string;
  gl_balance: number | null;
  tb_balance: number | null;
  variance: number;
  abs_variance: number;
  status: ReconStatus;
}

export interface DuplicateGroup {
  group_id: string;
  kind: 'exact' | 'near';
  score: number;
  rows: Record<string, any>[];
}

export interface MappingDecision {
  raw: string;
  canonical: string | null;
  method: string;
  confidence: number;
  ai_used: boolean;
  needs_review: boolean;
}

export interface Kpis {
  gl_rows: number;
  tb_accounts: number;
  journals: number;
  reconciled_pct: number;
  material_breaks: number;
  immaterial_breaks: number;
  dupes_flagged: number;
  dq_overall: number;
  materiality: number;
  doc_coverage?: number | null;
  unsupported_journals?: number | null;
}

export interface VoucherRef {
  journal_id?: string;
  date?: string;
  amount?: string;
  description?: string;
  approver?: string;
}

export interface SupportInfo {
  documents: number;
  document_names: string[];
  pages: number;
  method: string;
  vouchers: VoucherRef[];
  total_journals: number;
  coverage_pct: number;
  supported_count: number;
  unsupported_count: number;
  unsupported_journals: string[];
  unsupported_risky_journals: string[];
}

export interface SankeyData {
  nodes: { name: string }[];
  links: { source: number; target: number; value: number }[];
}

export interface HeatmapCell {
  account_code: string;
  account_name: string;
  category: string;
  status: ReconStatus;
  intensity: number;
  variance: number;
}

export interface AuditEntry {
  seq: number;
  timestamp: string;
  stage: string;
  action: string;
  rows_affected: number;
  ai_used: boolean;
  details: string;
}

export interface PipelineResult {
  client_id: string;
  client_name: string;
  mapping: {
    gl: Record<string, string>;
    tb: Record<string, string>;
    gl_decisions: MappingDecision[];
    tb_decisions: MappingDecision[];
    gl_unmatched: string[];
    tb_unmatched: string[];
  };
  summary: Record<string, any>;
  scorecard: ScoreCard;
  validation: {
    double_entry: { journals: number; unbalanced: any[]; unbalanced_count: number };
    missing_fields: Record<string, any>;
    referential_integrity: { gl_only_accounts: string[]; tb_only_accounts: string[] };
    validity: Record<string, number>;
  };
  duplicates: DuplicateGroup[];
  reconciliation: ReconRow[];
  support?: SupportInfo | null;
  sankey: SankeyData;
  heatmap: { materiality: number; cells: HeatmapCell[] };
  kpis: Kpis;
  ai: { available: boolean; explanations: any[]; narrative?: { text: string; source: string } };
  trail: AuditEntry[];
}

export interface ClientSummary {
  client_id: string;
  client_name: string;
  dq_overall: number;
  reconciled_pct: number;
  material_breaks: number;
  dupes_flagged: number;
  gl_rows: number;
}
