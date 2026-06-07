import React, { useEffect, useState } from 'react';
import { Alert, Box, Button, Paper, Typography } from '@mui/material';
import axios from 'axios';
import { Download } from 'lucide-react';

interface AuditEvent {
  id: string;
  timestamp: string;
  eventType: string;
  step: string;
  details: any;
  runId: string;
}

interface AuditTrailProps {
  runId: string;
}

const AuditTrail: React.FC<AuditTrailProps> = ({ runId }) => {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    const fetchEvents = async () => {
      setError('');
      setLoading(true);
      try {
        const resp = await axios.get('/api/audit', {
          params: { run_id: runId },
        });
        setEvents(resp.data?.events || []);
      } catch (e: any) {
        setError(e?.response?.data?.error || e?.message || 'Failed to load audit events.');
      } finally {
        setLoading(false);
      }
    };

    if (runId) fetchEvents();
  }, [runId]);

  const handleExportJson = async () => {
    setError('');
    try {
      const url = `/api/audit/export?run_id=${encodeURIComponent(runId)}`;
      const resp = await axios.get(url, { responseType: 'blob' });
      const blobUrl = window.URL.createObjectURL(resp.data);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `${runId}_audit_events.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(blobUrl);
    } catch (e: any) {
      setError(e?.response?.data?.error || e?.message || 'Export failed.');
    }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Box>
          <Typography variant="h6">Audit Trail</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            Run ID: {runId}
          </Typography>
        </Box>
        <Button
          variant="outlined"
          onClick={handleExportJson}
          disabled={!runId}
          sx={{ borderColor: '#00AF40', color: '#00AF40', display: 'flex', gap: 1 }}
        >
          <Download size={16} />
          Export JSON
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <Paper sx={{ p: 2 }}>
        <Typography variant="subtitle1" gutterBottom>
          Timeline
        </Typography>

        {loading ? (
          <Typography variant="body2">Loading…</Typography>
        ) : events.length === 0 ? (
          <Typography variant="body2">No events yet.</Typography>
        ) : (
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {events
              .slice()
              .sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1))
              .map((e) => (
                <Box
                  key={e.id}
                  sx={{
                    borderLeft: '3px solid #00AF40',
                    pl: 2,
                    py: 1,
                    borderRadius: 1,
                    backgroundColor: '#f7fdf9',
                  }}
                >
                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                    {e.timestamp}
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {e.eventType}
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                    {e.step}
                  </Typography>
                  {e.details && (
                    <pre
                      style={{
                        marginTop: 8,
                        marginBottom: 0,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                        fontSize: 12,
                        background: 'white',
                        padding: 8,
                        borderRadius: 6,
                        border: '1px solid #e5e7eb',
                      }}
                    >
                      {JSON.stringify(e.details, null, 2)}
                    </pre>
                  )}
                </Box>
              ))}
          </Box>
        )}
      </Paper>
    </Box>
  );
};

export default AuditTrail;
