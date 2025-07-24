import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  Box,
  IconButton,
  Typography,
  Alert,
  Fade,
  Slide,
  CircularProgress
} from '@mui/material';
import { Close, CheckCircle } from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import LoginForm from './LoginForm';
import RegisterForm from './RegisterForm';
import ConfirmationForm from './ConfirmationForm';
import ForgotPasswordForm from './ForgotPasswordForm';
import ResetPasswordForm from './ResetPasswordForm';

const AUTH_MODES = {
  LOGIN: 'login',
  REGISTER: 'register',
  CONFIRM: 'confirm',
  FORGOT_PASSWORD: 'forgot_password',
  RESET_PASSWORD: 'reset_password'
};

function AuthModal({ open, onClose, initialMode = AUTH_MODES.LOGIN }) {
  const { isAuthenticated, user } = useAuth();
  const [mode, setMode] = useState(initialMode);
  const [username, setUsername] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [showSuccess, setShowSuccess] = useState(false);
  const [isClosing, setIsClosing] = useState(false);

  // Auto-dismiss modal on successful authentication
  useEffect(() => {
    if (isAuthenticated && user && open) {
      setShowSuccess(true);
      setSuccessMessage(`Welcome back, ${user.username || user.email}!`);
      
      // Start success animation and auto-close sequence
      const successTimer = setTimeout(() => {
        setIsClosing(true);
      }, 1500);

      const closeTimer = setTimeout(() => {
        handleClose();
      }, 2000);

      return () => {
        clearTimeout(successTimer);
        clearTimeout(closeTimer);
      };
    }
  }, [isAuthenticated, user, open]);

  const handleRegistrationSuccess = (registeredUsername, nextStep) => {
    setUsername(registeredUsername);
    setSuccessMessage('Registration successful! Please check your email for a verification code.');
    setMode(AUTH_MODES.CONFIRM);
  };

  const handleConfirmationSuccess = () => {
    setSuccessMessage('Account confirmed! You can now sign in.');
    setMode(AUTH_MODES.LOGIN);
  };

  const handleForgotPasswordSuccess = (resetUsername) => {
    setUsername(resetUsername);
    setSuccessMessage('Password reset code sent! Please check your email.');
    setMode(AUTH_MODES.RESET_PASSWORD);
  };

  const handlePasswordResetSuccess = () => {
    setSuccessMessage('Password reset successful! You can now sign in with your new password.');
    setMode(AUTH_MODES.LOGIN);
  };

  const handleClose = () => {
    setMode(initialMode);
    setUsername('');
    setSuccessMessage('');
    setShowSuccess(false);
    setIsClosing(false);
    onClose();
  };

  const getTitle = () => {
    switch (mode) {
      case AUTH_MODES.LOGIN:
        return 'Sign In';
      case AUTH_MODES.REGISTER:
        return 'Create Account';
      case AUTH_MODES.CONFIRM:
        return 'Verify Account';
      case AUTH_MODES.FORGOT_PASSWORD:
        return 'Reset Password';
      case AUTH_MODES.RESET_PASSWORD:
        return 'Set New Password';
      default:
        return 'Authentication';
    }
  };

  // Show success animation overlay
  if (showSuccess) {
    return (
      <Dialog
        open={open}
        onClose={() => {}} // Prevent manual close during success
        maxWidth="sm"
        fullWidth
        PaperProps={{
          sx: { 
            borderRadius: 3,
            background: 'linear-gradient(135deg, #4CAF50 0%, #45A049 100%)',
            color: 'white'
          }
        }}
      >
        <DialogContent sx={{ p: 4, textAlign: 'center' }}>
          <Fade in={showSuccess} timeout={500}>
            <Box>
              <Slide direction="down" in={showSuccess} timeout={600}>
                <CheckCircle sx={{ fontSize: 64, mb: 2 }} />
              </Slide>
              <Typography variant="h5" fontWeight="bold" mb={1}>
                Login Successful!
              </Typography>
              <Typography variant="body1" sx={{ opacity: 0.9 }}>
                {successMessage}
              </Typography>
              {isClosing && (
                <Box mt={2}>
                  <CircularProgress size={24} sx={{ color: 'white' }} />
                </Box>
              )}
            </Box>
          </Fade>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: { 
          borderRadius: 3,
          background: 'rgba(255, 255, 255, 0.95)',
          backdropFilter: 'blur(10px)',
          boxShadow: '0 24px 48px rgba(0, 0, 0, 0.2)'
        }
      }}
      sx={{
        '& .MuiBackdrop-root': {
          background: 'rgba(0, 0, 0, 0.7)',
          backdropFilter: 'blur(5px)'
        }
      }}
    >
      <Slide direction="down" in={open} mountOnEnter unmountOnExit>
        <Box>
          <Box
            display="flex"
            justifyContent="space-between"
            alignItems="center"
            p={3}
            borderBottom={1}
            borderColor="divider"
          >
            <Typography variant="h5" component="h2" fontWeight="bold">
              {getTitle()}
            </Typography>
            <IconButton
              onClick={handleClose}
              size="small"
              aria-label="close"
              sx={{
                '&:hover': {
                  backgroundColor: 'rgba(0, 0, 0, 0.1)'
                }
              }}
            >
              <Close />
            </IconButton>
          </Box>

          <DialogContent sx={{ p: 0 }}>
            {successMessage && !showSuccess && (
              <Alert severity="success" sx={{ m: 3, mb: 0, borderRadius: 2 }}>
                {successMessage}
              </Alert>
            )}

        {mode === AUTH_MODES.LOGIN && (
          <LoginForm
            onSwitchToRegister={() => {
              setSuccessMessage('');
              setMode(AUTH_MODES.REGISTER);
            }}
            onSwitchToForgotPassword={() => {
              setSuccessMessage('');
              setMode(AUTH_MODES.FORGOT_PASSWORD);
            }}
          />
        )}

        {mode === AUTH_MODES.REGISTER && (
          <RegisterForm
            onSwitchToLogin={() => {
              setSuccessMessage('');
              setMode(AUTH_MODES.LOGIN);
            }}
            onRegistrationSuccess={handleRegistrationSuccess}
          />
        )}

        {mode === AUTH_MODES.CONFIRM && (
          <ConfirmationForm
            username={username}
            onConfirmationSuccess={handleConfirmationSuccess}
            onSwitchToLogin={() => {
              setSuccessMessage('');
              setMode(AUTH_MODES.LOGIN);
            }}
          />
        )}

        {mode === AUTH_MODES.FORGOT_PASSWORD && (
          <ForgotPasswordForm
            onForgotPasswordSuccess={handleForgotPasswordSuccess}
            onSwitchToLogin={() => {
              setSuccessMessage('');
              setMode(AUTH_MODES.LOGIN);
            }}
          />
        )}

        {mode === AUTH_MODES.RESET_PASSWORD && (
          <ResetPasswordForm
            username={username}
            onPasswordResetSuccess={handlePasswordResetSuccess}
            onSwitchToLogin={() => {
              setSuccessMessage('');
              setMode(AUTH_MODES.LOGIN);
            }}
          />
        )}
          </DialogContent>
        </Box>
      </Slide>
    </Dialog>
  );
}

export default AuthModal;