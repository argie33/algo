import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Paper,
  Typography,
  TextField,
  Button,
  Alert,
  CircularProgress,
  Divider,
  alpha,
  useTheme,
  Fade,
  Slide,
  InputAdornment,
  IconButton
} from '@mui/material';
import {
  Login as LoginIcon,
  Visibility,
  VisibilityOff,
  TrendingUp,
  ArrowBack,
  CheckCircle
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import LoadingTransition from '../components/LoadingTransition';
import MFAChallenge from '../components/auth/MFAChallenge';

const LoginPage = ({ onSuccess }) => {
  const theme = useTheme();
  const navigate = useNavigate();
  const { login, isAuthenticated, user, isLoading, error, clearError, mfaChallenge } = useAuth();
  
  const [formData, setFormData] = useState({
    username: '',
    password: ''
  });
  const [showPassword, setShowPassword] = useState(false);
  const [localError, setLocalError] = useState('');
  const [loginSuccess, setLoginSuccess] = useState(false);
  const [showSuccessAnimation, setShowSuccessAnimation] = useState(false);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated && user && !loginSuccess) {
      setLoginSuccess(true);
      setShowSuccessAnimation(true);
      
      // Show success animation then redirect
      const timer = setTimeout(() => {
        onSuccess?.();
        navigate('/dashboard');
      }, 2000);
      
      return () => clearTimeout(timer);
    }
  }, [isAuthenticated, user, navigate, onSuccess, loginSuccess]);

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

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError('');

    if (!formData.username || !formData.password) {
      setLocalError('Please enter both username and password');
      return;
    }

    const result = await login(formData.username, formData.password);
    
    if (!result.success && result.nextStep !== 'MFA_CHALLENGE') {
      if (result.message) {
        setLocalError(result.message);
      }
    }
  };

  const handleMFASuccess = () => {
    console.log('✅ MFA challenge completed successfully');
    // Success will be handled by the useEffect above
  };

  const handleMFACancel = () => {
    setFormData({ username: '', password: '' });
    setLocalError('');
  };

  // Show success animation
  if (showSuccessAnimation) {
    return (
      <Box
        sx={{
          minHeight: '100vh',
          background: `linear-gradient(135deg, 
            ${alpha(theme.palette.success.main, 0.1)} 0%, 
            ${alpha(theme.palette.primary.main, 0.05)} 100%)`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        <Fade in={showSuccessAnimation} timeout={500}>
          <Paper
            elevation={12}
            sx={{
              p: 6,
              borderRadius: 4,
              textAlign: 'center',
              background: alpha(theme.palette.background.paper, 0.98),
              backdropFilter: 'blur(10px)',
              border: `2px solid ${theme.palette.success.main}`,
              maxWidth: 400
            }}
          >
            <Slide direction="down" in={showSuccessAnimation} timeout={600}>
              <CheckCircle sx={{ fontSize: 80, mb: 2, color: theme.palette.success.main }} />
            </Slide>
            <Typography variant="h4" fontWeight="bold" mb={2} color="text.primary">
              Welcome Back!
            </Typography>
            <Typography variant="h6" sx={{ mb: 2, color: theme.palette.text.secondary }}>
              {user?.username || user?.email}
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Redirecting to your dashboard...
            </Typography>
            <Box mt={3}>
              <CircularProgress size={32} sx={{ color: theme.palette.primary.main }} />
            </Box>
          </Paper>
        </Fade>
      </Box>
    );
  }

  // Show loading state
  if (isLoading && !mfaChallenge) {
    return (
      <LoadingTransition 
        message="Signing you in..."
        submessage="Verifying your credentials and preparing your dashboard"
        type="auth"
      />
    );
  }

  const displayError = error || localError;

  // Show MFA challenge if active
  if (mfaChallenge) {
    return (
      <Box
        sx={{
          minHeight: '100vh',
          background: `linear-gradient(135deg, 
            ${alpha(theme.palette.primary.main, 0.05)} 0%, 
            ${alpha(theme.palette.secondary.main, 0.02)} 100%)`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        <Container maxWidth="sm">
          <Paper elevation={12} sx={{ borderRadius: 4, overflow: 'hidden' }}>
            <Box sx={{ p: 4 }}>
              <Button
                startIcon={<ArrowBack />}
                onClick={handleMFACancel}
                sx={{ mb: 2 }}
                color="inherit"
              >
                Back to Login
              </Button>
              <MFAChallenge
                challengeType={mfaChallenge.challenge}
                message={mfaChallenge.challenge === 'SMS_MFA' 
                  ? `Enter the verification code sent to ${mfaChallenge.destination}.`
                  : 'Enter the code from your authenticator app.'
                }
                onSuccess={handleMFASuccess}
                onCancel={handleMFACancel}
              />
            </Box>
          </Paper>
        </Container>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: `linear-gradient(135deg, 
          ${alpha(theme.palette.primary.main, 0.05)} 0%, 
          ${alpha(theme.palette.secondary.main, 0.02)} 100%)`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative'
      }}
    >
      {/* Background Pattern */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          opacity: 0.1,
          background: `url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23${theme.palette.primary.main.replace('#', '')}' fill-opacity='0.3'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")`,
        }}
      />

      <Container maxWidth="sm" sx={{ position: 'relative', zIndex: 1 }}>
        <Fade in={true} timeout={800}>
          <Paper
            elevation={12}
            sx={{
              borderRadius: 4,
              overflow: 'hidden',
              background: alpha(theme.palette.background.paper, 0.95),
              backdropFilter: 'blur(10px)'
            }}
          >
            {/* Header */}
            <Box
              sx={{
                background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
                color: 'white',
                p: 4,
                textAlign: 'center',
                position: 'relative'
              }}
            >
              <Button
                startIcon={<ArrowBack />}
                onClick={() => navigate('/')}
                sx={{ 
                  position: 'absolute',
                  left: 16,
                  top: 16,
                  color: 'white',
                  '&:hover': {
                    backgroundColor: alpha(theme.palette.common.white, 0.1)
                  }
                }}
              >
                Back to Markets
              </Button>
              
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 2 }}>
                <TrendingUp sx={{ fontSize: 40, mr: 1 }} />
                <Typography variant="h4" fontWeight="bold">
                  Financial Platform
                </Typography>
              </Box>
              <Typography variant="h6" sx={{ opacity: 0.9 }}>
                Sign in to your account
              </Typography>
            </Box>

            {/* Form */}
            <Box sx={{ p: 4 }}>
              {displayError && (
                <Slide direction="down" in={!!displayError} timeout={300}>
                  <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>
                    {displayError}
                  </Alert>
                </Slide>
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
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 2,
                    }
                  }}
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
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: 2,
                    }
                  }}
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
                  size="large"
                  disabled={isLoading}
                  startIcon={isLoading ? <CircularProgress size={20} /> : <LoginIcon />}
                  sx={{
                    mt: 4,
                    mb: 2,
                    py: 1.5,
                    borderRadius: 2,
                    fontSize: '1.1rem',
                    fontWeight: 600,
                    background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
                    '&:hover': {
                      background: `linear-gradient(135deg, ${theme.palette.primary.dark} 0%, ${theme.palette.secondary.dark} 100%)`,
                      transform: 'translateY(-1px)',
                      boxShadow: theme.shadows[8]
                    },
                    '&:disabled': {
                      background: theme.palette.action.disabledBackground
                    },
                    transition: 'all 0.3s ease'
                  }}
                >
                  {isLoading ? 'Signing In...' : 'Sign In to Dashboard'}
                </Button>

                <Divider sx={{ my: 3 }}>
                  <Typography variant="body2" color="text.secondary">
                    Need help?
                  </Typography>
                </Divider>

                <Box textAlign="center">
                  <Button
                    variant="text"
                    onClick={() => navigate('/forgot-password')}
                    disabled={isLoading}
                    sx={{ mr: 2 }}
                  >
                    Forgot Password?
                  </Button>
                  <Button
                    variant="text"
                    onClick={() => navigate('/register')}
                    disabled={isLoading}
                  >
                    Create Account
                  </Button>
                </Box>
              </Box>
            </Box>
          </Paper>
        </Fade>
      </Container>
    </Box>
  );
};

export default LoginPage;