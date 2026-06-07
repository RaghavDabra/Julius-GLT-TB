import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  FormGroup,
  FormControlLabel,
  Checkbox,
  Button,
  Alert,
  Paper,
  Divider,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
} from '@mui/material';
import { useMutation } from 'react-query';
import axios from 'axios';

interface DataPreprocessingProps {
  file: File;
  onComplete: (data: any) => void;
}

const DataPreprocessing: React.FC<DataPreprocessingProps> = ({ file, onComplete }) => {
  const [options, setOptions] = useState({
    dropMissing: true,
    dropEmpty: true,
    fillMissing: false,
    scaleNumeric: true,
    encodeCategorical: true,
    formatDates: true,
    performPCA: false,
    showCorrelation: false,
  });

  const [columnHeaders, setColumnHeaders] = useState<string[]>([]);
  const [columnTypes, setColumnTypes] = useState<{ [key: string]: string }>({});

  // Automatically read the file on mount to detect column headers and types
  useEffect(() => {
    const reader = new FileReader();
    reader.onload = async (event) => {
      const text = event.target?.result;
      if (typeof text === 'string') {
        // Extract headers from the first line of the CSV file
        const lines = text.split('\n');
        if (lines.length > 0) {
          const headers = lines[0].split(',').map((h) => h.trim());
          setColumnHeaders(headers);

          // Initialize all column types as empty for now
          const initialTypes: { [key: string]: string } = {};
          headers.forEach((header) => {
            initialTypes[header] = '';
          });
          setColumnTypes(initialTypes);

          // Immediately call backend to auto-detect column types
          const formData = new FormData();
          formData.append('file', file);
          formData.append('options', JSON.stringify({ detectOnly: true }));
          formData.append('columnTypes', JSON.stringify(initialTypes));

          try {
            const response = await axios.post('http://localhost:8080/api/preprocess', formData);
            console.log('Auto-detect response:', response.data);
            if (response.data?.detected_column_types) {
              setColumnTypes(response.data.detected_column_types);
            }
          } catch (error) {
            console.error('Error detecting column types', error);
          }
        }
      }
    };
    reader.readAsText(file);
  }, [file]);

  const handleColumnTypeChange = (column: string, type: string) => {
    setColumnTypes((prev) => ({ ...prev, [column]: type }));
  };

  const preprocessMutation = useMutation(
    async () => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('options', JSON.stringify(options));
      formData.append('columnTypes', JSON.stringify(columnTypes));

      const response = await axios.post('http://localhost:8080/api/preprocess', formData);
      console.log('Process response:', response.data);
      return response.data;
    },
    {
      onSuccess: (data) => {
        // Validate that the response has a summary with shape before using it
        if (!data || !data.summary || !data.summary.shape) {
          console.error('Unexpected response format:', data);
          return;
        }
        // If the backend updated detected_column_types, apply them
        if (data.detected_column_types) {
          setColumnTypes(data.detected_column_types);
        }
        // Notify parent component
        onComplete(data);
      },
    }
  );

  // Custom style for checkboxes and button
  const customColor = '#00AF40';
  const customHoverColor = '#009836';

  return (
    <Box>
      <Typography variant="h6" gutterBottom>
        Data Preprocessing Options
      </Typography>

      {/* Two-column layout for checkboxes */}
      <Paper sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2}>
          {/* Left Column */}
          <Grid item xs={12} sm={6}>
            <FormGroup>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={options.dropMissing}
                    onChange={(e) =>
                      setOptions({ ...options, dropMissing: e.target.checked })
                    }
                    sx={{
                      color: customColor,
                      '&.Mui-checked': { color: customColor },
                    }}
                  />
                }
                label="Drop Rows with Missing Values"
              />
              <Divider sx={{ my: 1 }} />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={options.dropEmpty}
                    onChange={(e) =>
                      setOptions({ ...options, dropEmpty: e.target.checked })
                    }
                    sx={{
                      color: customColor,
                      '&.Mui-checked': { color: customColor },
                    }}
                  />
                }
                label="Drop Empty Columns"
              />
              <Divider sx={{ my: 1 }} />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={options.fillMissing}
                    onChange={(e) =>
                      setOptions({ ...options, fillMissing: e.target.checked })
                    }
                    sx={{
                      color: customColor,
                      '&.Mui-checked': { color: customColor },
                    }}
                  />
                }
                label="Fill Missing Values"
              />
              <Divider sx={{ my: 1 }} />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={options.scaleNumeric}
                    onChange={(e) =>
                      setOptions({ ...options, scaleNumeric: e.target.checked })
                    }
                    sx={{
                      color: customColor,
                      '&.Mui-checked': { color: customColor },
                    }}
                  />
                }
                label="Scale Numeric Data"
              />
            </FormGroup>
          </Grid>

          {/* Right Column */}
          <Grid item xs={12} sm={6}>
            <FormGroup>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={options.encodeCategorical}
                    onChange={(e) =>
                      setOptions({
                        ...options,
                        encodeCategorical: e.target.checked,
                      })
                    }
                    sx={{
                      color: customColor,
                      '&.Mui-checked': { color: customColor },
                    }}
                  />
                }
                label="Encode Categorical Data"
              />
              <Divider sx={{ my: 1 }} />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={options.formatDates}
                    onChange={(e) =>
                      setOptions({ ...options, formatDates: e.target.checked })
                    }
                    sx={{
                      color: customColor,
                      '&.Mui-checked': { color: customColor },
                    }}
                  />
                }
                label="Format Date Columns"
              />
              <Divider sx={{ my: 1 }} />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={options.performPCA}
                    onChange={(e) =>
                      setOptions({ ...options, performPCA: e.target.checked })
                    }
                    sx={{
                      color: customColor,
                      '&.Mui-checked': { color: customColor },
                    }}
                  />
                }
                label="Perform PCA"
              />
              <Divider sx={{ my: 1 }} />

              <FormControlLabel
                control={
                  <Checkbox
                    checked={options.showCorrelation}
                    onChange={(e) =>
                      setOptions({
                        ...options,
                        showCorrelation: e.target.checked,
                      })
                    }
                    sx={{
                      color: customColor,
                      '&.Mui-checked': { color: customColor },
                    }}
                  />
                }
                label="Show Correlation Matrix"
              />
            </FormGroup>
          </Grid>
        </Grid>
      </Paper>

      {columnHeaders.length > 0 && (
        <Paper sx={{ p: 2, mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            Manual Column Type Selection
          </Typography>
          <Grid container spacing={2}>
            {columnHeaders.map((header) => (
              <Grid item xs={12} sm={6} md={4} lg={3} key={header}>
                <Box>
                  <Typography variant="body1" sx={{ mb: 1 }}>
                    {header}
                  </Typography>
                  <FormControl fullWidth>
                    <InputLabel id={`select-${header}`}>Type</InputLabel>
                    <Select
                      labelId={`select-${header}`}
                      value={columnTypes[header] || ''}
                      label="Type"
                      onChange={(e) =>
                        handleColumnTypeChange(header, e.target.value as string)
                      }
                    >
                      <MenuItem value="numeric">Numeric</MenuItem>
                      <MenuItem value="categorical">Categorical</MenuItem>
                      <MenuItem value="date">Date</MenuItem>
                      <MenuItem value="exclude">Exclude</MenuItem>
                    </Select>
                  </FormControl>
                </Box>
              </Grid>
            ))}
          </Grid>
        </Paper>
      )}

      {preprocessMutation.isError && (
        <Alert severity="error">
          Error: {(preprocessMutation.error as Error)?.message || 'Unknown error'}
        </Alert>
      )}

      <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button
          variant="contained"
          onClick={() => preprocessMutation.mutate()}
          disabled={preprocessMutation.isLoading}
          sx={{
            backgroundColor: customColor,
            '&:hover': { backgroundColor: customHoverColor },
          }}
        >
          {preprocessMutation.isLoading ? 'Processing...' : 'Process Data'}
        </Button>
      </Box>
    </Box>
  );
};

export default DataPreprocessing;
