import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Box, Container } from '@mui/material';
import AuthModal from '../components/auth/AuthModal';
import { useAuth } from '../contexts/AuthContext';

/**
 * Dedicated login page
 * Displays authentication modal centered on the page
 * Redirects to intended route after successful login
 */
function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, user } = useAuth();
  const [authModalOpen, setAuthModalOpen] = useState(true);

  // Get the intended destination from query params, default to /app/portfolio
  const from = new URLSearchParams(location.search).get('from') || '/app/portfolio';

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated && user) {
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, user, navigate, from]);

  const handleAuthModalClose = () => {
    setAuthModalOpen(false);
    // Redirect to home if user closes modal without logging in
    navigate('/', { replace: true });
  };

  const handleAuthSuccess = () => {
    setAuthModalOpen(false);
    // Will be redirected by the useEffect above when isAuthenticated changes
  };

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        backgroundColor: '#f5f5f5',
      }}
    >
      <Container maxWidth="sm">
        <Box sx={{ p: 2 }}>
          <AuthModal
            open={authModalOpen}
            onClose={handleAuthModalClose}
            initialMode="login"
            onSuccess={handleAuthSuccess}
          />
        </Box>
      </Container>
    </Box>
  );
}

export default LoginPage;
