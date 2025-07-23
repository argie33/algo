/**
 * MFA Challenge Component
 * Handles MFA verification during the login process
 */

import React, { useState } from 'react';
import {
  Box,
  Typography,
  TextField,
  Button,
  Alert,
  Paper,
  InputAdornment,
  CircularProgress
} from '@mui/material';
import {
  Security as SecurityIcon,
  Sms as SmsIcon,
  PhoneAndroid as PhoneAndroidIcon
} from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';

const MFAChallenge = ({ challengeType, message, onSuccess, onCancel }) => {
  const { confirmMFA, isLoading } = useAuth();
  const [verificationCode, setVerificationCode] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!verificationCode || verificationCode.length !== 6) {
      setError('Please enter a valid 6-digit verification code.');
      return;
    }

    try {
      const result = await confirmMFA(verificationCode);
      if (result.success) {
        console.log('✅ MFA verification successful');
        onSuccess?.();
      } else {
        setError(result.message || 'Verification failed. Please try again.');
      }
    } catch (error) {
      console.error('❌ MFA verification error:', error);
      setError('Verification failed. Please check your code and try again.');
    }
  };

  const handleCodeChange = (e) => {
    const value = e.target.value.replace(/\D/g, '').slice(0, 6);
    setVerificationCode(value);
    if (error) setError('');
  };

  const getIcon = () => {
    switch (challengeType) {
      case 'SMS_MFA':
        return <SmsIcon color="primary" />;
      case 'TOTP_MFA':
        return <PhoneAndroidIcon color="primary" />;
      default:
        return <SecurityIcon color="primary" />;
    }
  };

  const getTitle = () => {
    switch (challengeType) {
      case 'SMS_MFA':
        return 'SMS Verification';
      case 'TOTP_MFA':
        return 'Authenticator App';
      default:
        return 'Multi-Factor Authentication';
    }
  };

  const getPlaceholder = () => {
    switch (challengeType) {
      case 'SMS_MFA':
        return 'Enter SMS code';
      case 'TOTP_MFA':
        return 'Enter app code';
      default:
        return 'Enter code';
    }
  };

  return (
    <Paper
      elevation={3}
      sx={{
        p: 4,
        maxWidth: 400,
        mx: 'auto',
        mt: 4,
        borderRadius: 2
      }}
    >
      <Box display="flex" flexDirection="column" alignItems="center" gap={3}>
        {/* Header */}
        <Box display="flex" alignItems="center" gap={1}>
          {getIcon()}
          <Typography variant="h5" component="h1" fontWeight="bold">
            {getTitle()}
          </Typography>
        </Box>

        {/* Message */}
        <Typography 
          variant="body1" 
          color="text.secondary" 
          textAlign="center"
          sx={{ mb: 1 }}
        >
          {message}
        </Typography>

        {/* Error Alert */}
        {error && (
          <Alert severity="error" sx={{ width: '100%' }}>
            {error}
          </Alert>
        )}

        {/* Form */}
        <Box 
          component="form" 
          onSubmit={handleSubmit}
          sx={{ width: '100%' }}
        >
          <TextField
            fullWidth
            label="Verification Code"
            placeholder={getPlaceholder()}
            value={verificationCode}
            onChange={handleCodeChange}
            disabled={isLoading}
            inputProps={{
              maxLength: 6,
              style: { 
                textAlign: 'center', 
                fontSize: '1.5rem',
                letterSpacing: '0.5rem'
              }
            }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SecurityIcon color="action" />
                </InputAdornment>
              )
            }}
            sx={{ mb: 3 }}
            autoFocus
            autoComplete="one-time-code"
          />

          {/* Action Buttons */}
          <Box display="flex" gap={2} flexDirection="column">
            <Button
              type="submit"
              variant="contained"
              fullWidth
              disabled={isLoading || verificationCode.length !== 6}
              startIcon={isLoading ? <CircularProgress size={20} /> : null}
              sx={{ py: 1.5 }}
            >
              {isLoading ? 'Verifying...' : 'Verify Code'}
            </Button>

            <Button
              variant="text"
              fullWidth
              onClick={onCancel}
              disabled={isLoading}
              color="secondary"
            >
              Cancel
            </Button>
          </Box>
        </Box>

        {/* Help Text */}
        <Typography 
          variant="caption" 
          color="text.secondary" 
          textAlign="center"
          sx={{ mt: 2 }}
        >
          {challengeType === 'SMS_MFA' 
            ? "Didn't receive the code? Check your messages or wait a moment and try again."
            : "Make sure to enter the current code from your authenticator app."
          }
        </Typography>
      </Box>
    </Paper>
  );
};

export default MFAChallenge;