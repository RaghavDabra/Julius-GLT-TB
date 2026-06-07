import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import axios from 'axios';

type DatasetType = 'gl' | 'tb';

interface IngestResponse {
  run_id: string;
  dataset_type: DatasetType;
  summary: { shape: [number, number]; columns: string[] };
  checksum_sha256: string;
  filename: string;
}

interface SuggestMappingResponse {
  proposed_mapping: Record<string, string>;
  columns: string[];
}

interface FinancialReconciliationProps {
  glFile: File;
  tbFile: File;
  onComplete: (payload: { runId: string; result: any; processedSummary: string }) => void;
}

const FinancialReconciliation: React.FC<FinancialReconciliationProps> = ({
  glFile,
  tbFile,
  onComplete,
}) => {
  const [runId, setRunId] = useState<string>('');
  const [glIngest, setGlIngest] = useState<IngestResponse | null>(null);
  const [tbIngest, setTbIngest] = useState<IngestResponse | null>(null);
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);

  const [mappingGl, setMappingGl] = useState({
    account_code: '',
    amount: '',
    debit: '',
    credit: '',
    transaction_date: '',
    description: '',
  });
  const [mappingTb, setMappingTb] = useState({
    account_code: '',
    balance: '',
  });
  const [tolerance, setTolerance] = useState<string>('0.01');

  const [result, setResult] = useState<any>(null);
  const [validation, setValidation] = useState<any>(null);
  const [validationLoading, setValidationLoading] = useState<boolean>(false);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfLoading, setPdfLoading] = useState<boolean>(false);
  const [pdfAnalyses, setPdfAnalyses] = useState<any[]>([]);

  const glColumns = glIngest?.summary?.columns || [];
  const tbColumns = tbIngest?.summary?.columns || [];

  const canReconcile = useMemo(() => {
    if (!runId) return false;
    if (!mappingGl.account_code) return false;
    const glAmountOk = Boolean(mappingGl.amount) || (Boolean(mappingGl.debit) && Boolean(mappingGl.credit));
    if (!glAmountOk) return false;
    if (!mappingTb.account_code || !mappingTb.balance) return false;
    if (Number.isNaN(Number(tolerance))) return false;
    return true;
  }, [mappingGl, mappingTb, runId, tolerance]);

  useEffect(() => {
    const ingest = async () => {
      setError('');
      setLoading(true);
      try {
        const glFd = new FormData();
        glFd.append('file', glFile);
        glFd.append('dataset_type', 'gl');
        const glResp = await axios.post<IngestResponse>('/api/ingest', glFd);
        setRunId(glResp.data.run_id);
        setGlIngest(glResp.data);

        const tbFd = new FormData();
        tbFd.append('file', tbFile);
        tbFd.append('dataset_type', 'tb');
        tbFd.append('run_id', glResp.data.run_id);
        const tbResp = await axios.post<IngestResponse>('/api/ingest', tbFd);
        setTbIngest(tbResp.data);

        const glMapResp = await axios.post<SuggestMappingResponse>('/api/suggest-mapping', {
          run_id: glResp.data.run_id,
          dataset_type: 'gl',
        });
        setMappingGl((prev) => ({
          ...prev,
          ...glMapResp.data.proposed_mapping,
          transaction_date: (glMapResp.data.proposed_mapping as any).posting_date || '',
        }));

        const tbMapResp = await axios.post<SuggestMappingResponse>('/api/suggest-mapping', {
          run_id: glResp.data.run_id,
          dataset_type: 'tb',
        });
        setMappingTb((prev) => ({ ...prev, ...tbMapResp.data.proposed_mapping }));
      } catch (e: any) {
        const msg = e?.response?.data?.error || e?.message || 'Ingestion failed.';
        if (msg === 'Network Error') {
          setError('Network Error: backend not reachable. Start the API (python3 api/app.py) on port 8080.');
        } else {
          setError(msg);
        }
      } finally {
        setLoading(false);
      }
    };

    ingest();
  }, [glFile, tbFile]);

  const handleReconcile = async () => {
    setError('');
    setLoading(true);
    try {
      const resp = await axios.post('/api/reconcile', {
        run_id: runId,
        mapping_gl: mappingGl,
        mapping_tb: mappingTb,
        tolerance: Number(tolerance),
        normalize_account_codes: true,
      });
      setResult(resp.data);

      const summary = resp.data?.summary || {};
      const topExceptions = (resp.data?.exceptions || []).slice(0, 10);
      const processedSummary = [
        `**Reconciliation Summary**`,
        `- Run ID: ${runId}`,
        `- Tolerance: ${summary.tolerance}`,
        `- GL Total Sum: ${summary.gl_total_sum}`,
        `- TB Total Sum: ${summary.tb_total_sum}`,
        `- Exceptions: ${summary.exceptions_count}`,
        ``,
        `**Top Exceptions (first 10)**`,
        ...topExceptions.map((x: any) => `- ${x.AccountCode}: GL=${x.GLTotal}, TB=${x.TBTotal}, Diff=${x.Difference}`),
      ].join('\n');

      onComplete({ runId, result: resp.data, processedSummary });
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || 'Reconciliation failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleValidate = async () => {
    setError('');
    setValidationLoading(true);
    try {
      const resp = await axios.post('/api/validate', {
        run_id: runId,
        dataset_type: 'gl',
        mapping_gl: mappingGl,
        normalize_account_codes: true,
      });
      setValidation(resp.data);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || 'Validation failed.');
    } finally {
      setValidationLoading(false);
    }
  };

  const handleUploadAndAnalyzePdf = async () => {
    setError('');
    if (!runId || !pdfFile) return;
    setPdfLoading(true);
    try {
      const fd = new FormData();
      fd.append('file', pdfFile);
      fd.append('run_id', runId);
      const uploadResp = await axios.post('/api/pdf/upload', fd);
      const pdfId = uploadResp.data?.pdf_id;
      const analysisResp = await axios.post('/api/pdf/analyze', { run_id: runId, pdf_id: pdfId });
      setPdfAnalyses((prev) => [analysisResp.data?.result, ...prev].filter(Boolean));
      setPdfFile(null);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || 'PDF analysis failed.');
    } finally {
      setPdfLoading(false);
    }
  };

  const handleDownloadExceptionsCsv = async () => {
    setError('');
    try {
      const url = `/api/reconcile/export?run_id=${encodeURIComponent(
        runId
      )}&dataset=exceptions`;
      const resp = await axios.get(url, { responseType: 'blob' });
      const blobUrl = window.URL.createObjectURL(resp.data);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `${runId}_exceptions.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(blobUrl);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || 'Download failed.');
    }
  };

  const exceptions = result?.exceptions || [];
  const validationReport = validation?.report;
  const duplicateRecords = validation?.duplicate_records || [];

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Validate & Reconcile (GL vs TB)
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Paper sx={{ p: 2, mb: 2 }}>
        <Typography variant="subtitle1" gutterBottom>
          Ingestion Summary
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {glIngest ? `GL: ${glIngest.filename} (sha256: ${glIngest.checksum_sha256.slice(0, 12)}…)` : 'GL: ingesting…'}
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {tbIngest ? `TB: ${tbIngest.filename} (sha256: ${tbIngest.checksum_sha256.slice(0, 12)}…)` : 'TB: ingesting…'}
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {runId ? `Run ID: ${runId}` : 'Run ID: pending…'}
        </Typography>
      </Paper>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" gutterBottom>
            GL Mapping
          </Typography>

          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Account Code</InputLabel>
            <Select
              value={mappingGl.account_code}
              label="Account Code"
              onChange={(e) => setMappingGl((p) => ({ ...p, account_code: e.target.value as string }))}
            >
              {glColumns.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Signed Amount (optional)</InputLabel>
            <Select
              value={mappingGl.amount}
              label="Signed Amount (optional)"
              onChange={(e) => setMappingGl((p) => ({ ...p, amount: e.target.value as string }))}
            >
              <MenuItem value="">(not used)</MenuItem>
              {glColumns.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Date (for validation/duplicates)</InputLabel>
            <Select
              value={mappingGl.transaction_date}
              label="Date (for validation/duplicates)"
              onChange={(e) =>
                setMappingGl((p) => ({ ...p, transaction_date: e.target.value as string }))
              }
            >
              <MenuItem value="">(not used)</MenuItem>
              {glColumns.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Description (for duplicates)</InputLabel>
            <Select
              value={mappingGl.description}
              label="Description (for duplicates)"
              onChange={(e) =>
                setMappingGl((p) => ({ ...p, description: e.target.value as string }))
              }
            >
              <MenuItem value="">(not used)</MenuItem>
              {glColumns.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2 }}>
            <FormControl fullWidth>
              <InputLabel>Debit (optional)</InputLabel>
              <Select
                value={mappingGl.debit}
                label="Debit (optional)"
                onChange={(e) => setMappingGl((p) => ({ ...p, debit: e.target.value as string }))}
              >
                <MenuItem value="">(not used)</MenuItem>
                {glColumns.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl fullWidth>
              <InputLabel>Credit (optional)</InputLabel>
              <Select
                value={mappingGl.credit}
                label="Credit (optional)"
                onChange={(e) => setMappingGl((p) => ({ ...p, credit: e.target.value as string }))}
              >
                <MenuItem value="">(not used)</MenuItem>
                {glColumns.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>

          <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary' }}>
            Provide either Signed Amount, or both Debit and Credit.
          </Typography>
        </Paper>

        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" gutterBottom>
            TB Mapping
          </Typography>

          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Account Code</InputLabel>
            <Select
              value={mappingTb.account_code}
              label="Account Code"
              onChange={(e) => setMappingTb((p) => ({ ...p, account_code: e.target.value as string }))}
            >
              {tbColumns.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl fullWidth sx={{ mb: 2 }}>
            <InputLabel>Balance</InputLabel>
            <Select
              value={mappingTb.balance}
              label="Balance"
              onChange={(e) => setMappingTb((p) => ({ ...p, balance: e.target.value as string }))}
            >
              {tbColumns.map((c) => (
                <MenuItem key={c} value={c}>
                  {c}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <TextField
            label="Tolerance"
            value={tolerance}
            onChange={(e) => setTolerance(e.target.value)}
            fullWidth
            inputProps={{ inputMode: 'decimal' }}
          />
        </Paper>
      </Box>

      <Box sx={{ mt: 3 }}>
        <Typography variant="subtitle1" gutterBottom>
          Journal PDF Analysis
        </Typography>
        <Paper sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
            <Button
              variant="outlined"
              component="label"
              sx={{ borderColor: '#00AF40', color: '#00AF40' }}
            >
              Choose PDF
              <input
                type="file"
                accept="application/pdf"
                hidden
                onChange={(e) => setPdfFile(e.target.files?.[0] || null)}
              />
            </Button>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              {pdfFile ? pdfFile.name : 'No PDF selected'}
            </Typography>
            <Button
              variant="contained"
              disabled={!runId || !pdfFile || pdfLoading}
              onClick={handleUploadAndAnalyzePdf}
              sx={{ backgroundColor: '#00AF40', '&:hover': { backgroundColor: '#009836' } }}
            >
              {pdfLoading ? 'Analyzing…' : 'Upload & Analyze'}
            </Button>
          </Box>

          {pdfAnalyses.length > 0 && (
            <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
              {pdfAnalyses.slice(0, 5).map((a: any, idx: number) => (
                <Paper key={idx} sx={{ p: 2, backgroundColor: '#f7fdf9' }} variant="outlined">
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    Journal Reference: {a?.journalReference || 'N/A'}
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                    Prepared By: {a?.preparedBy || 'N/A'} | Approved By: {a?.approvedBy || 'N/A'}
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    Summary: {a?.summary || 'N/A'}
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    Possible Issues: {Array.isArray(a?.possibleIssues) ? a.possibleIssues.join(', ') : a?.possibleIssues || 'N/A'}
                  </Typography>
                </Paper>
              ))}
            </Box>
          )}
        </Paper>
      </Box>

      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 2, gap: 2 }}>
        <Button
          variant="outlined"
          disabled={!result || !runId}
          onClick={handleDownloadExceptionsCsv}
          sx={{ borderColor: '#00AF40', color: '#00AF40' }}
        >
          Download Exceptions CSV
        </Button>
        <Button
          variant="outlined"
          disabled={!runId || validationLoading}
          onClick={handleValidate}
          sx={{ borderColor: '#00AF40', color: '#00AF40' }}
        >
          {validationLoading ? 'Validating…' : 'Run Validation'}
        </Button>
        <Button
          variant="contained"
          disabled={!canReconcile || loading}
          onClick={handleReconcile}
          sx={{
            backgroundColor: '#00AF40',
            '&:hover': { backgroundColor: '#009836' },
          }}
        >
          {loading ? 'Working…' : 'Run Reconciliation'}
        </Button>
      </Box>

      {validationReport && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle1" gutterBottom>
            Validation Report
          </Typography>
          <Paper sx={{ p: 2, mb: 2 }}>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Validation Score: {Number(validationReport.validation_score_pct || 0).toFixed(2)}%
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Double Entry: {validationReport.double_entry?.status} (Diff: {validationReport.double_entry?.difference ?? 'N/A'})
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Duplicate Count: {validationReport.duplicate_count}
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Missing Values: account={validationReport.missing_values?.missing_account_codes}, date={validationReport.missing_values?.missing_dates}, amount={validationReport.missing_values?.missing_amounts}
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Invalid Records: account={validationReport.invalid_records?.invalid_account_codes}, date={validationReport.invalid_records?.invalid_dates}, amount={validationReport.invalid_records?.invalid_amounts}
            </Typography>
          </Paper>

          {duplicateRecords.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                Duplicate Records (sample)
              </Typography>
              <Paper sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>duplicate_hash</TableCell>
                      <TableCell>account_code</TableCell>
                      <TableCell>date</TableCell>
                      <TableCell>amount</TableCell>
                      <TableCell>description</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {duplicateRecords.slice(0, 20).map((row: any, idx: number) => (
                      <TableRow key={`${row.duplicate_hash}-${idx}`}>
                        <TableCell>{row.duplicate_hash}</TableCell>
                        <TableCell>{mappingGl.account_code ? row[mappingGl.account_code] : ''}</TableCell>
                        <TableCell>{mappingGl.transaction_date ? row[mappingGl.transaction_date] : ''}</TableCell>
                        <TableCell>{mappingGl.amount ? row[mappingGl.amount] : ''}</TableCell>
                        <TableCell>{mappingGl.description ? row[mappingGl.description] : ''}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Paper>
            </Box>
          )}
        </Box>
      )}

      {result && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle1" gutterBottom>
            Exceptions ({exceptions.length})
          </Typography>
          <Paper sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Account</TableCell>
                  <TableCell align="right">GL Total</TableCell>
                  <TableCell align="right">TB Total</TableCell>
                  <TableCell align="right">Difference</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {exceptions.slice(0, 200).map((row: any, idx: number) => (
                  <TableRow key={`${row.AccountCode}-${idx}`}>
                    <TableCell>{row.AccountCode}</TableCell>
                    <TableCell align="right">{row.GLTotal}</TableCell>
                    <TableCell align="right">{row.TBTotal}</TableCell>
                    <TableCell align="right">{row.Difference}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        </Box>
      )}
    </Box>
  );
};

export default FinancialReconciliation;
