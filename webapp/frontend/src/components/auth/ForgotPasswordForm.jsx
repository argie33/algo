import React, { useState } from 'react';
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
    <div className="bg-white shadow-md rounded-lg" sx={{ maxWidth: 400, mx: 'auto', mt: 4 }}>
      <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 4 }}>
        <div  display="flex" alignItems="center" justifyContent="center" mb={3}>
          <ResetIcon sx={{ mr: 1, color: 'primary.main' }} />
          <div  variant="h4" component="h1" color="primary">
            Reset Password
          </div>
        </div>

        <div  variant="body1" color="text.secondary" align="center" mb={3}>
          Enter your username or email address and we'll send you a reset code
        </div>

        {displayError && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
            {displayError}
          </div>
        )}

        <div  component="form" onSubmit={handleSubmit} noValidate>
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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

          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={isLoading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} /> : <ResetIcon />}
          >
            {isLoading ? 'Sending...' : 'Send Reset Code'}
          </button>

          <div  textAlign="center" mt={2}>
            <div  variant="body2" color="text.secondary">
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
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ForgotPasswordForm;