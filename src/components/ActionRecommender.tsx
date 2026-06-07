import React, { useState } from 'react';
import { Box, Typography, Button, TextField, Alert } from '@mui/material';
import { useMutation } from 'react-query';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';

interface ActionRecommenderProps {
  // Optionally, you can pass an initial model info prop.
  initialModelInfo?: string;
}

const ActionRecommender: React.FC<ActionRecommenderProps> = ({ initialModelInfo = '' }) => {
  const [jsonInput, setJsonInput] = useState<string>(
    `{
  "data": [
    {
      "feature1": 200,
      "feature2": 300
    }
  ]
}`
  );
  const [recommendationOutput, setRecommendationOutput] = useState<string>('');
  const [llmInsight, setLLMInsight] = useState<string>(''); // state for LLM insight
  const [modelInfo, setModelInfo] = useState<string>(initialModelInfo);
  const [errorMessage, setErrorMessage] = useState<string>('');

  const predictMutation = useMutation(
    async (input: any) => {
      const response = await axios.post('http://localhost:8080/api/predict', input);
      return response.data;
    },
    {
      onSuccess: (data) => {
        // Extract model_info, predictions, and llm_insight from the response.
        if (data) {
          if (data.model_info) {
            setModelInfo(data.model_info);
          }
          if (data.predictions) {
            const recs = data.predictions.map((item: any) => item.Recommendation);
            setRecommendationOutput(recs.join('\n'));
          } else {
            setRecommendationOutput("No recommendation available.");
          }
          if (data.llm_insight) {
            setLLMInsight(data.llm_insight);
          }
        }
      },
      onError: (error: any) => {
        if (error.response && error.response.data && error.response.data.error) {
          setErrorMessage(error.response.data.error);
        } else {
          setErrorMessage(error.message);
        }
      }
    }
  );

  const handlePredict = () => {
    setErrorMessage('');
    setRecommendationOutput('');
    setModelInfo('');
    setLLMInsight(''); // Reset LLM insight when a new prediction is triggered
    try {
      const parsedInput = JSON.parse(jsonInput);
      predictMutation.mutate(parsedInput);
    } catch (e) {
      setErrorMessage('Invalid JSON input.');
    }
  };

  return (
    <Box sx={{ mt: 4 }}>
      <Typography variant="h6" gutterBottom>
        Action Recommender
      </Typography>
      {modelInfo && (
        <Typography variant="subtitle1" gutterBottom>
          {modelInfo}
        </Typography>
      )}
      {errorMessage && <Alert severity="error" sx={{ mb: 2 }}>{errorMessage}</Alert>}
      <TextField
        label="JSON Input"
        multiline
        fullWidth
        rows={6}
        value={jsonInput}
        onChange={(e) => setJsonInput(e.target.value)}
        variant="outlined"
        sx={{ mb: 2 }}
      />
      <Button
        variant="contained"
        onClick={handlePredict}
        disabled={predictMutation.isLoading}
        sx={{
          backgroundColor: '#00AF40',
          '&:hover': {
            backgroundColor: '#009836',
          },
        }}
      >
        {predictMutation.isLoading ? 'Predicting...' : 'Predict Target Value'}
      </Button>
      {recommendationOutput && (
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            Recommendation
          </Typography>
          <Typography variant="body1" sx={{ whiteSpace: 'pre-line' }}>
            {recommendationOutput}
          </Typography>
        </Box>
      )}
      {llmInsight && (
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" gutterBottom>
            Insights:
          </Typography>
          <ReactMarkdown>{llmInsight}</ReactMarkdown>
        </Box>
      )}
    </Box>
  );
};

export default ActionRecommender;
