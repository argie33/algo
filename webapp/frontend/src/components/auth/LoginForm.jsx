import { useState, useEffect } from 'react';
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
import { Visibility, VisibilityOff, Login as LoginIcon, Security } from '@mui/icons-material';
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
    // Biometric authentication successful
    // In production, you would validate this with your backend
    setLocalError('');
  };

  const handleBiometricSetup = (credentialData) => {
    // Biometric setup completed
  };

  const handleBiometricError = (error) => {
    // Biometric error handled
  };

  const handleMFASetupComplete = (method) => {
    // MFA setup completed
    setShowMFASetup(false);
  };

  const displayError = error || localError;

  return (
    <Card sx={{ maxWidth: 400, mx: 'auto', mt: 4 }}>
      <CardContent sx={{ p: 4 }}>
        <Box display="flex" alignItems="center" justifyContent="center" mb={3}>
          <LoginIcon sx={{ mr: 1, color: 'primary.main' }} />
          <Typography variant="h4" component="h1" color="primary">
            Sign In
          </Typography>
        </Box>

        <Typography variant="body1" color="text.secondary" align="center" mb={3}>
          Access your Financial Dashboard
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
            value={formData.username}
            onChange={handleChange}
            margin="normal"
            required
            autoComplete="username"
            autoFocus
            disabled={isLoading}
          />

          <TextField
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
                  <IconButton
                    aria-label="toggle password visibility"
                    onClick={() => setShowPassword(!showPassword)}
                    edge="end"
                    disabled={isLoading}
                  >
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              )
            }}
          />

          <Button
            type="submit"
            fullWidth
            variant="contained"
            sx={{ mt: 3, mb: 2, py: 1.5 }}
            disabled={isLoading}
            startIcon={isLoading ? <CircularProgress size={20} /> : <LoginIcon />}
          >
            {isLoading ? 'Signing In...' : 'Sign In'}
          </Button>

          <Box display="flex" justifyContent="space-between" alignItems="center" mt={2}>
            <Link
              component="button"
              type="button"
              variant="body2"
              onClick={onSwitchToForgotPassword}
              disabled={isLoading}
            >
              Forgot password?
            </Link>
          </Box>

          <Divider sx={{ my: 2 }} />

          {/* Biometric Authentication Section */}
          <Collapse in={showBiometric && user}>
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle2" sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Security fontSize="small" />
                Enhanced Security
              </Typography>
              <BiometricAuth
                userId={user?.userId}
                username={user?.username}
                onAuthSuccess={handleBiometricAuth}
                onSetupComplete={handleBiometricSetup}
                onError={handleBiometricError}
                compact={true}
              />
            </Box>
          </Collapse>

          <Box textAlign="center">
            <Typography variant="body2" color="text.secondary">
              Don&apos;t have an account?{' '}
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
            </Typography>
          </Box>
        </Box>

        {/* MFA Setup Modal */}
        <MFASetupModal
          open={showMFASetup}
          onClose={() => setShowMFASetup(false)}
          onSetupComplete={handleMFASetupComplete}
          userPhoneNumber={user?.phoneNumber}
        />
      </CardContent>
    </Card>
  );
}

export default LoginForm;