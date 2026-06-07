import React from 'react';
import { Box, AppBar, Toolbar, Typography, Container } from '@mui/material';
import { Database } from 'lucide-react';

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="sticky" elevation={0}>
        <Toolbar sx={{ py: 1.5 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
              p: 1,
              borderRadius: 2,
            }}
          >
            <Database size={24} color="#ffffff" />
          </Box>
          <Box sx={{ ml: 2 }}>
            <Typography
              variant="h6"
              component="div"
              sx={{ 
                color: 'text.primary',
                fontWeight: 700,
                letterSpacing: '-0.01em',
              }}
            >
              Data Analysis Platform
            </Typography>
            <Typography
              variant="subtitle2"
              sx={{
                color: 'text.secondary',
                fontSize: '0.875rem',
                mt: 0.5,
              }}
            >
              Intelligent Insights & Predictions
            </Typography>
          </Box>
        </Toolbar>
      </AppBar>
      <Container 
        maxWidth="xl" 
        sx={{ 
          mt: 4, 
          mb: 4, 
          flex: 1,
          px: {
            xs: 2,
            sm: 3,
            md: 4,
          },
        }}
      >
        {children}
      </Container>
    </Box>
  );
};

export default Layout;