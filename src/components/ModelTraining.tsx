import React, { useState } from 'react';
import { Box, Typography, FormControl, InputLabel, Select, MenuItem, Button, Alert } from '@mui/material';
import { useMutation } from 'react-query';
import axios from 'axios';

interface ModelTrainingProps {
  preprocessedData: any;
  onComplete: (results: any) => void;
}

const ModelTraining: React.FC<ModelTrainingProps> = ({ preprocessedData, onComplete }) => {
  const [targetColumn, setTargetColumn] = useState('');
  const [trainingResult, setTrainingResult] = useState<any>(null);

  const trainingMutation = useMutation(async () => {
    const response = await axios.post('http://localhost:8080/api/train', {
      data: preprocessedData.data,
      target_column: targetColumn
    });
    return response.data;
  }, {
    onSuccess: (data) => { 
      setTrainingResult(data);
      onComplete(data);
    },
    onError: (error: any) => { 
      console.error("Training error:", error.response?.data || error.message);
    }
  });

  return (
    <Box>
      <Typography variant="h6">Model Training </Typography>
      <FormControl fullWidth sx={{ mb: 2 }}>
        <InputLabel>Select Target Column</InputLabel>
        <Select
          value={targetColumn}
          label="Select Target Column"
          onChange={(e) => setTargetColumn(e.target.value as string)}
        >
          {preprocessedData?.columns?.numeric?.map((col: string) => (
            <MenuItem key={col} value={col}>{col}</MenuItem>
          ))}
        </Select>
      </FormControl>

      {trainingMutation.isError && (
        <Alert severity="error">
          Error: {(trainingMutation.error as any).response?.data?.error || (trainingMutation.error as Error).message}
        </Alert>
      )}

      <Button
        variant="contained"
        onClick={() => trainingMutation.mutate()}
        disabled={!targetColumn || trainingMutation.isLoading}
        sx={{
          backgroundColor: '#00AF40',
          '&:hover': {
            backgroundColor: '#009836', // Slightly darker shade of green on hover
          },
        }}
      >
        {trainingMutation.isLoading ? 'Training...' : 'Train Model'}
      </Button>

      {trainingResult && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle1">
            Chosen Model: {trainingResult.best_model} (Accuracy: {(trainingResult.best_score * 100).toFixed(2)}%)
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default ModelTraining;
