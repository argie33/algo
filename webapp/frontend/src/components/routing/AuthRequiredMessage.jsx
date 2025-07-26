import React from 'react';
import {
  Box,
  Paper,
  Typography,
  Button,
  Container,
  useTheme
} from '@mui/material';
import {
  Login as LoginIcon,
  Security as SecurityIcon
} from '@mui/icons-material';

/**
 * AuthRequiredMessage - Consistent message for protected routes
 * 
 * Shows when users try to access protected content without authentication.
 * Replaces multiple different auth requirement messages.
 */
const AuthRequiredMessage = ({ requiredFor, onSignInClick }) => {
  const theme = useTheme();

  const getFeatureName = (path) => {
    const featureMap = {
      '/dashboard': 'Dashboard',
      '/portfolio': 'Portfolio Management',
      '/settings': 'Settings',
      '/trading': 'Trading Signals',
      '/backtest': 'Backtesting Tools',
      '/hft-trading': 'High-Frequency Trading',
      '/neural-hft': 'Neural HFT Command Center',
      '/options': 'Options Analytics',
      '/sentiment': 'Sentiment Analysis',
      '/stocks/patterns': 'Pattern Recognition',
      '/tools/ai': 'AI Assistant'
    };
    
    return featureMap[path] || 'this feature';
  };

  return (
    <Container maxWidth="sm" sx={{ mt: 8 }}>
      <Paper
        elevation={3}
        sx={{
          p: 4,
          textAlign: 'center',
          backgroundColor: theme.palette.background.paper,
          border: `1px solid ${theme.palette.divider}`
        }}
      >
        <SecurityIcon 
          sx={{ 
            fontSize: 64, 
            color: theme.palette.primary.main,
            mb: 2
          }} 
        />
        
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 600 }}>
          Authentication Required
        </Typography>
        
        <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
          Please sign in to access {getFeatureName(requiredFor)}. 
          This feature requires authentication to protect your data and provide personalized insights.
        </Typography>
        
        <Button
          variant="contained"
          size="large"
          startIcon={<LoginIcon />}
          onClick={onSignInClick}
          sx={{ 
            mt: 2,
            px: 4,
            py: 1.5,
            fontSize: '1.1rem'
          }}
        >
          Sign In to Continue
        </Button>
        
        <Box sx={{ mt: 3, p: 2, backgroundColor: theme.palette.grey[50], borderRadius: 1 }}>
          <Typography variant="body2" color="text.secondary">
            💡 <strong>Why sign in?</strong><br />
            Authentication ensures your portfolios, settings, and trading data remain secure and private.
          </Typography>
        </Box>
      </Paper>
    </Container>
  );
};

export default AuthRequiredMessage;