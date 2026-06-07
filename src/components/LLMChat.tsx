import React, { useState } from 'react';
import {
  Box,
  Typography,
  TextField,
  Button,
  Alert,
  Paper,
  Avatar,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';
import PersonIcon from '@mui/icons-material/Person';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import { useMutation } from 'react-query';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface LLMChatProps {
  processedSummary: string;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

const LLMChat: React.FC<LLMChatProps> = ({ processedSummary }) => {
  const [userQuery, setUserQuery] = useState('');
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);

  const llmMutation = useMutation(
    async () => {
      const response = await axios.post('http://localhost:8080/api/llm', {
        prompt: userQuery,
        chat_history: chatHistory,
        processed_summary: processedSummary,
      });
      return response.data;
    },
    {
      onSuccess: (data) => {
        // Create a user message and assistant message
        const userMsg: ChatMessage = { role: 'user', content: userQuery };
        const assistantMsg: ChatMessage = {
          role: 'assistant',
          content: data.response,
        };

        // Append them to the chat history
        setChatHistory((prev) => [...prev, userMsg, assistantMsg]);
        setUserQuery(''); // Clear the input field
      },
      onError: (error: any) => {
        console.error('LLM Error:', error.response?.data || error.message);
      },
    }
  );

  // --- MUI table components for Markdown tables ---
  const muiTableComponents = {
    table: ({ node, ...props }: any) => (
      <TableContainer
        component="div"
        sx={{ my: 2, overflowX: 'auto', maxWidth: '100%' }}
      >
        <Table
          size="small"
          sx={{ border: '1px solid #ccc', width: 'max-content' }}
        >
          {props.children}
        </Table>
      </TableContainer>
    ),
    thead: ({ node, ...props }: any) => <TableHead>{props.children}</TableHead>,
    tbody: ({ node, ...props }: any) => <TableBody>{props.children}</TableBody>,
    tr: ({ node, ...props }: any) => <TableRow>{props.children}</TableRow>,
    th: ({ node, ...props }: any) => (
      <TableCell
        variant="head"
        sx={{ border: '1px solid #ccc', fontWeight: 'bold' }}
      >
        {props.children}
      </TableCell>
    ),
    td: ({ node, ...props }: any) => (
      <TableCell variant="body" sx={{ border: '1px solid #ccc' }}>
        {props.children}
      </TableCell>
    ),
  };

  // --- Group the chat history into [user, assistant] pairs ---
  const pairedMessages: [ChatMessage, ChatMessage | null][] = [];
  for (let i = 0; i < chatHistory.length; i += 2) {
    const userMsg = chatHistory[i];
    const assistantMsg = i + 1 < chatHistory.length ? chatHistory[i + 1] : null;
    pairedMessages.push([userMsg, assistantMsg]);
  }

  // Reverse the array of pairs so the newest pair appears at the top
  const reversedPairs = pairedMessages.slice().reverse();

  // --- Render the UI ---
  return (
    <Box sx={{ mt: 3 }}>
      <Typography variant="h6" gutterBottom>
        LLM Business Insights &amp; Predictions
      </Typography>

      <TextField
        fullWidth
        label="Enter your question"
        value={userQuery}
        onChange={(e) => setUserQuery(e.target.value)}
        sx={{ my: 2 }}
      />

      {llmMutation.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Error:{' '}
          {(llmMutation.error as any).response?.data?.error ||
            (llmMutation.error as Error).message}
        </Alert>
      )}

      <Button
        variant="contained"
        onClick={() => llmMutation.mutate()}
        disabled={llmMutation.isLoading || userQuery.trim() === ''}
        sx={{
          backgroundColor: '#00AF40',
          '&:hover': {
            backgroundColor: '#009836', // slightly darker green on hover
          },
        }}
      >
        {llmMutation.isLoading ? 'Sending...' : 'Send Query'}
      </Button>

      <Box sx={{ mt: 3 }}>
        <Typography variant="subtitle1" gutterBottom>
          Chat History:
        </Typography>

        {chatHistory.length === 0 ? (
          <Typography variant="body2">No conversation yet.</Typography>
        ) : (
          reversedPairs.map((pair, index) => {
            const [userMsg, assistantMsg] = pair;

            return (
              <React.Fragment key={index}>
                {/* -- User message (always first in each pair) -- */}
                {userMsg && (
                  <Paper
                    sx={{
                      p: 2,
                      my: 1,
                      display: 'flex',
                      gap: 2,
                      alignItems: 'flex-start',
                      backgroundColor: '#e3f2fd', // user color
                    }}
                  >
                    <Avatar sx={{ bgcolor: 'primary.main', mt: 0.5 }}>
                      <PersonIcon />
                    </Avatar>
                    <Box>
                      <Typography variant="caption" display="block" gutterBottom>
                        You:
                      </Typography>

                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          ...muiTableComponents,
                          h1: ({ node, ...props }) => (
                            <Typography variant="h5" sx={{ mt: 2 }} {...props} />
                          ),
                          h2: ({ node, ...props }) => (
                            <Typography variant="h6" sx={{ mt: 2 }} {...props} />
                          ),
                          h3: ({ node, ...props }) => (
                            <Typography
                              variant="subtitle1"
                              sx={{ mt: 2 }}
                              {...props}
                            />
                          ),
                          p: ({ node, ...props }) => (
                            <Typography variant="body1" paragraph {...props} />
                          ),
                          li: ({ node, ordered, ...props }) => (
                            <li style={{ marginBottom: '0.5em' }} {...props} />
                          ),
                        }}
                      >
                        {userMsg.content}
                      </ReactMarkdown>
                    </Box>
                  </Paper>
                )}

                {/* -- Assistant message (second in each pair) -- */}
                {assistantMsg && (
                  <Paper
                    sx={{
                      p: 2,
                      my: 1,
                      display: 'flex',
                      gap: 2,
                      alignItems: 'flex-start',
                      backgroundColor: '#f1f8e9', // assistant color
                    }}
                  >
                    <Avatar sx={{ bgcolor: 'secondary.main', mt: 0.5 }}>
                      <SmartToyIcon />
                    </Avatar>
                    <Box>
                      <Typography variant="caption" display="block" gutterBottom>
                        Assistant:
                      </Typography>

                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          ...muiTableComponents,
                          h1: ({ node, ...props }) => (
                            <Typography variant="h5" sx={{ mt: 2 }} {...props} />
                          ),
                          h2: ({ node, ...props }) => (
                            <Typography variant="h6" sx={{ mt: 2 }} {...props} />
                          ),
                          h3: ({ node, ...props }) => (
                            <Typography
                              variant="subtitle1"
                              sx={{ mt: 2 }}
                              {...props}
                            />
                          ),
                          p: ({ node, ...props }) => (
                            <Typography variant="body1" paragraph {...props} />
                          ),
                          li: ({ node, ordered, ...props }) => (
                            <li style={{ marginBottom: '0.5em' }} {...props} />
                          ),
                        }}
                      >
                        {assistantMsg.content}
                      </ReactMarkdown>
                    </Box>
                  </Paper>
                )}
              </React.Fragment>
            );
          })
        )}
      </Box>
    </Box>
  );
};

export default LLMChat;
