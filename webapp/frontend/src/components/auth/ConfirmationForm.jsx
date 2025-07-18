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

function ConfirmationForm({ username, onConfirmationSuccess, onSwitchToLogin }) {
  const [confirmationCode, setConfirmationCode] = useState('');
  const [localError, setLocalError] = useState('');

  const { confirmRegistration, isLoading, error, clearError } = useAuth();

  const handleChange = (e) => {
    setConfirmationCode(e.target.value);
    // Clear errors when user starts typing
    if (error) clearError();
    if (localError) setLocalError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError('');

    if (!confirmationCode) {
      setLocalError('Please enter the confirmation code');
      return;
    }

    const result = await confirmRegistration(username, confirmationCode);
    
    if (result.success) {
      onConfirmationSuccess?.();
    } else if (result.error) {
      setLocalError(result.error);
    }
  };

  const displayError = error || localError;

  return (
    <div className="bg-white shadow-md rounded-lg" sx={{ maxWidth: 400, mx: 'auto', mt: 4 }}>
      <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 4 }}>
        <div  display="flex" alignItems="center" justifyContent="center" mb={3}>
          <ConfirmIcon sx={{ mr: 1, color: 'primary.main' }} />
          <div  variant="h4" component="h1" color="primary">
            Verify Account
          </div>
        </div>

        <div  variant="body1" color="text.secondary" align="center" mb={3}>
          Enter the verification code sent to your email address
        </div>

        {displayError && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
            {displayError}
          </div>
        )}

        <div  component="form" onSubmit={handleSubmit} noValidate>
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            fullWidth
            id="confirmationCode"
            name="confirmationCode"
            label="Verification Code"
            type="text"
            value={confirmationCode}
            onChange={handleChange}
            margin="normal"
            required
            autoFocus
            disabled={isLoading}
            placeholder="Enter 6-digit code"
            inputProps={{ maxLength: 6 }}
          />

          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={isLoading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} /> : <ConfirmIcon />}
          >
            {isLoading ? 'Verifying...' : 'Verify Account'}
          </button>

          <div  textAlign="center" mt={2}>
            <div  variant="body2" color="text.secondary">
              Didn't receive the code?{' '}
              <Link
                component="button"
                type="button"
                variant="body2"
                onClick={() => {
                  // TODO: Implement resend code functionality
                  console.log('Resend code for:', username);
                }}
                disabled={isLoading}
                sx={{ fontWeight: 'medium' }}
              >
                Resend
              </Link>
            </div>
            
            <div  variant="body2" color="text.secondary" mt={1}>
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

export default ConfirmationForm;