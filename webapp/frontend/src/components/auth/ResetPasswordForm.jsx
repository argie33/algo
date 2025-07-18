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
  Link,
  InputAdornment,
  IconButton
} from '@mui/material';
import { useAuth } from '../../contexts/AuthContext';

function ResetPasswordForm({ username, onPasswordResetSuccess, onSwitchToLogin }) {
  const [formData, setFormData] = useState({
    confirmationCode: '',
    newPassword: '',
    confirmPassword: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [localError, setLocalError] = useState('');

  const { confirmForgotPassword, isLoading, error, clearError } = useAuth();

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
    // Clear errors when user starts typing
    if (error) clearError();
    if (localError) setLocalError('');
  };

  const validateForm = () => {
    if (!formData.confirmationCode || !formData.newPassword || !formData.confirmPassword) {
      setLocalError('Please fill in all fields');
      return false;
    }

    if (formData.newPassword !== formData.confirmPassword) {
      setLocalError('Passwords do not match');
      return false;
    }

    if (formData.newPassword.length < 8) {
      setLocalError('Password must be at least 8 characters long');
      return false;
    }

    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError('');

    if (!validateForm()) {
      return;
    }

    const result = await confirmForgotPassword(
      username,
      formData.confirmationCode,
      formData.newPassword
    );
    
    if (result.success) {
      onPasswordResetSuccess?.();
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
            Set New Password
          </div>
        </div>

        <div  variant="body1" color="text.secondary" align="center" mb={3}>
          Enter the code from your email and choose a new password
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
            label="Reset Code"
            type="text"
            value={formData.confirmationCode}
            onChange={handleChange}
            margin="normal"
            required
            autoFocus
            disabled={isLoading}
            placeholder="Enter 6-digit code"
            inputProps={{ maxLength: 6 }}
          />

          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            fullWidth
            id="newPassword"
            name="newPassword"
            label="New Password"
            type={showPassword ? 'text' : 'password'}
            value={formData.newPassword}
            onChange={handleChange}
            margin="normal"
            required
            disabled={isLoading}
            autoComplete="new-password"
            helperText="Must be at least 8 characters long"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <button className="p-2 rounded-full hover:bg-gray-100"
                    aria-label="toggle password visibility"
                    onClick={() => setShowPassword(!showPassword)}
                    edge="end"
                    disabled={isLoading}
                  >
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </button>
                </InputAdornment>
              )
            }}
          />

          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            fullWidth
            id="confirmPassword"
            name="confirmPassword"
            label="Confirm New Password"
            type={showConfirmPassword ? 'text' : 'password'}
            value={formData.confirmPassword}
            onChange={handleChange}
            margin="normal"
            required
            disabled={isLoading}
            autoComplete="new-password"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <button className="p-2 rounded-full hover:bg-gray-100"
                    aria-label="toggle confirm password visibility"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    edge="end"
                    disabled={isLoading}
                  >
                    {showConfirmPassword ? <VisibilityOff /> : <Visibility />}
                  </button>
                </InputAdornment>
              )
            }}
          />

          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={isLoading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} /> : <ResetIcon />}
          >
            {isLoading ? 'Resetting...' : 'Reset Password'}
          </button>

          <div  textAlign="center" mt={2}>
            <div  variant="body2" color="text.secondary">
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

export default ResetPasswordForm;