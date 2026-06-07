import React, { useRef, useState } from 'react';
import { Box, Button, Paper, Typography } from '@mui/material';

interface FinancialDataUploadProps {
  onComplete: (files: { glFile: File; tbFile: File }) => void;
}

const FinancialDataUpload: React.FC<FinancialDataUploadProps> = ({ onComplete }) => {
  const glInputRef = useRef<HTMLInputElement | null>(null);
  const tbInputRef = useRef<HTMLInputElement | null>(null);
  const [glFile, setGlFile] = useState<File | null>(null);
  const [tbFile, setTbFile] = useState<File | null>(null);

  const ready = Boolean(glFile && tbFile);

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Upload General Ledger and Trial Balance
      </Typography>

      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" gutterBottom>
            General Ledger (GL) CSV
          </Typography>
          <input
            ref={glInputRef}
            type="file"
            accept=".csv"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              setGlFile(f);
            }}
          />
          <Button
            variant="outlined"
            onClick={() => glInputRef.current?.click()}
            sx={{ borderColor: '#00AF40', color: '#00AF40' }}
          >
            Choose GL File
          </Button>
          <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary' }}>
            {glFile ? glFile.name : 'No file selected'}
          </Typography>
        </Paper>

        <Paper sx={{ p: 2 }}>
          <Typography variant="subtitle1" gutterBottom>
            Trial Balance (TB) CSV
          </Typography>
          <input
            ref={tbInputRef}
            type="file"
            accept=".csv"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0] || null;
              setTbFile(f);
            }}
          />
          <Button
            variant="outlined"
            onClick={() => tbInputRef.current?.click()}
            sx={{ borderColor: '#00AF40', color: '#00AF40' }}
          >
            Choose TB File
          </Button>
          <Typography variant="body2" sx={{ mt: 1, color: 'text.secondary' }}>
            {tbFile ? tbFile.name : 'No file selected'}
          </Typography>
        </Paper>
      </Box>

      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
        <Button
          variant="contained"
          disabled={!ready}
          onClick={() => {
            if (!glFile || !tbFile) return;
            onComplete({ glFile, tbFile });
          }}
          sx={{
            backgroundColor: '#00AF40',
            '&:hover': { backgroundColor: '#009836' },
          }}
        >
          Continue
        </Button>
      </Box>
    </Box>
  );
};

export default FinancialDataUpload;
