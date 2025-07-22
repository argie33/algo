import { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Alert,
  CircularProgress,
  Link
} from '@mui/material';
import { LockReset as ResetIcon } from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';

function ForgotPasswordForm({ onForgotPasswordSuccess, onSwitchToLogin }) {
  const [username, setUsername] = useState('');
  const [localError, setLocalError] = useState('');

  const { forgotPassword, isLoading, error, clearError } = useAuth();

  const handleChange = (e) => {
    setUsername(e.target.value);
    // Clear errors when user starts typing
    if (error) clearError();
    if (localError) setLocalError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError('');

    if (!username) {
      setLocalError('Please enter your username or email');
      return;
    }

    const result = await forgotPassword(username);
    
    if (result.success) {
      onForgotPasswordSuccess?.(username);
    } else if (result.error) {
      setLocalError(result.error);
    }
  };

  const displayError = error || localError;

  return (
    <Card sx={{ maxWidth: 400, mx: 'auto', mt: 4 }}>
      <CardContent sx={{ p: 4 }}>
        <Box display="flex" alignItems="center" justifyContent="center" mb={3}>
          <ResetIcon sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="h4" component="h1" color="primary">
            Reset Password
          </Typography>
        </Box>

        <Typography variant="body1" color="text.secondary" align="center" mb={3}>
          Enter your username or email address and we&apos;ll send you a reset code
        </Typography>

        {displayError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {displayError}
          </Alert>
        )}

        <Box component="form" onSubmit={handleSubmit} noValidate>
          <TextField
            fullWidth
            id="username"
            name="username"
            label="Username or Email"
            type="text"
            value={username}
            onChange={handleChange}
            margin="normal"
            required
            autoFocus
            disabled={isLoading}
            autoComplete="username"
          />

          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={isLoading ? <CircularProgress size={20} /> : <ResetIcon />}
          >
            {isLoading ? 'Sending...' : 'Send Reset Code'}
          </Button>

          <Box textAlign="center" mt={2}>
            <Typography variant="body2" color="text.secondary">
              Remember your password?{' '}
              <Link
                component="button"
                type="button"
                variant="body2"
                onClick={onSwitchToLogin}
                disabled={isLoading}
                sx={{ fontWeight: 'medium' }}
              >
                Back to Sign In
              </Link>
            </Typography>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

export default ForgotPasswordForm;