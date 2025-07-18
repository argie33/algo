import React, { useState, useEffect } from 'react';
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
  IconButton,
  Divider,
  Collapse
} from '@mui/material';
import { useAuth } from '../../contexts/AuthContext';
import BiometricAuth from './BiometricAuth';
import MFASetupModal from './MFASetupModal';

function LoginForm({ onSwitchToRegister, onSwitchToForgotPassword }) {
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState('');
  const [showMFASetup, setShowMFASetup] = useState(false);
  const [showBiometric, setShowBiometric] = useState(false);
  const [loginSuccess, setLoginSuccess] = useState(false);

  const { login, isLoading, error, clearError, user } = useAuth();

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

  // Check for user authentication success and show MFA setup
  useEffect(() => {
    if (user && !loginSuccess) {
      setLoginSuccess(true);
      // Check if user should set up MFA (could check user attributes)
      const shouldSetupMFA = !user.mfaEnabled; // This would come from user attributes
      if (shouldSetupMFA) {
        setShowMFASetup(true);
      }
      setShowBiometric(true);
    }
  }, [user, loginSuccess]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError('');

    if (!formData.username || !formData.password) {
      setLocalError('Please enter both username and password');
      return;
    }

    const result = await login(formData.username, formData.password);
    
    if (!result.success && result.error) {
      setLocalError(result.error);
    }
  };

  const handleBiometricAuth = async (authResult) => {
    console.log('Biometric authentication successful: [REDACTED]');
    // In production, you would validate this with your backend
    setLocalError('');
  };

  const handleBiometricSetup = (credentialData) => {
    console.log('Biometric setup completed: [REDACTED]');
  };

  const handleBiometricError = (error) => {
    console.error('Biometric error:', error);
  };

  const handleMFASetupComplete = (method) => {
    console.log('MFA setup completed with method:', method);
    setShowMFASetup(false);
  };

  const displayError = error || localError;

  return (
    <div className="bg-white shadow-md rounded-lg" sx={{ maxWidth: 400, mx: 'auto', mt: 4 }}>
      <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 4 }}>
        <div  display="flex" alignItems="center" justifyContent="center" mb={3}>
          <LoginIcon sx={{ mr: 1, color: 'primary.main' }} />
          <div  variant="h4" component="h1" color="primary">
            Sign In
          </div>
        </div>

        <div  variant="body1" color="text.secondary" align="center" mb={3}>
          Access your Financial Dashboard
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
            value={formData.username}
            onChange={handleChange}
            margin="normal"
            required
            autoComplete="username"
            autoFocus
            disabled={isLoading}
          />

          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            fullWidth
            id="password"
            name="password"
            label="Password"
            type={showPassword ? 'text' : 'password'}
            value={formData.password}
            onChange={handleChange}
            margin="normal"
            required
            autoComplete="current-password"
            disabled={isLoading}
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

          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={isLoading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} /> : <LoginIcon />}
          >
            {isLoading ? 'Signing In...' : 'Sign In'}
          </button>

          <div  display="flex" justifyContent="space-between" alignItems="center" mt={2}>
            <Link
              component="button"
              type="button"
              variant="body2"
              onClick={onSwitchToForgotPassword}
              disabled={isLoading}
            >
              Forgot password?
            </Link>
          </div>

          <hr className="border-gray-200" sx={{ my: 2 }} />

          {/* Biometric Authentication Section */}
          <Collapse in={showBiometric && user}>
            <div  sx={{ mt: 2 }}>
              <div  variant="subtitle2" sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Security fontSize="small" />
                Enhanced Security
              </div>
              <BiometricAuth
                userId={user?.userId}
                username={user?.username}
                onAuthSuccess={handleBiometricAuth}
                onSetupComplete={handleBiometricSetup}
                onError={handleBiometricError}
                compact={true}
              />
            </div>
          </Collapse>

          <div  textAlign="center">
            <div  variant="body2" color="text.secondary">
              Don't have an account?{' '}
              <Link
                component="button"
                type="button"
                variant="body2"
                onClick={onSwitchToRegister}
                disabled={isLoading}
                sx={{ fontWeight: 'medium' }}
              >
                Sign up here
              </Link>
            </div>
          </div>
        </div>

        {/* MFA Setup Modal */}
        <MFASetupModal
          open={showMFASetup}
          onClose={() => setShowMFASetup(false)}
          onSetupComplete={handleMFASetupComplete}
          userPhoneNumber={user?.phoneNumber}
        />
      </div>
    </div>
  );
}

export default LoginForm;