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
  });
  const [mappingTb, setMappingTb] = useState({
    account_code: '',
    balance: '',
  });
  const [tolerance, setTolerance] = useState<string>('0.01');

  const [result, setResult] = useState<any>(null);

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
        const glResp = await axios.post<IngestResponse>('http://localhost:8080/api/ingest', glFd);
        setRunId(glResp.data.run_id);
        setGlIngest(glResp.data);

        const tbFd = new FormData();
        tbFd.append('file', tbFile);
        tbFd.append('dataset_type', 'tb');
        tbFd.append('run_id', glResp.data.run_id);
        const tbResp = await axios.post<IngestResponse>('http://localhost:8080/api/ingest', tbFd);
        setTbIngest(tbResp.data);

        const glMapResp = await axios.post<SuggestMappingResponse>('http://localhost:8080/api/suggest-mapping', {
          run_id: glResp.data.run_id,
          dataset_type: 'gl',
        });
        setMappingGl((prev) => ({ ...prev, ...glMapResp.data.proposed_mapping }));

        const tbMapResp = await axios.post<SuggestMappingResponse>('http://localhost:8080/api/suggest-mapping', {
          run_id: glResp.data.run_id,
          dataset_type: 'tb',
        });
        setMappingTb((prev) => ({ ...prev, ...tbMapResp.data.proposed_mapping }));
      } catch (e: any) {
        setError(e?.response?.data?.error || e?.message || 'Ingestion failed.');
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
      const resp = await axios.post('http://localhost:8080/api/reconcile', {
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

  const handleDownloadExceptionsCsv = async () => {
    setError('');
    try {
      const url = `http://localhost:8080/api/reconcile/export?run_id=${encodeURIComponent(
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
