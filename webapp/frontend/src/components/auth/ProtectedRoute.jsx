import React from 'react';
import { Box, CircularProgress, Typography, Button } from '@mui/material';
import { Lock } from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';

function ProtectedRoute({ children, requireAuth = true, fallback = null }) {
  const { isAuthenticated, isLoading, user } = useAuth();

  // Show loading spinner while checking authentication
  if (isLoading) {
    return (
      <Box
        display=\"flex\"
        flexDirection=\"column\"
        alignItems=\"center\"
        justifyContent=\"center\"
        minHeight=\"50vh\"
        gap={2}
      >
        <CircularProgress size={48} />
        <Typography variant=\"h6\" color=\"text.secondary\">
          Checking authentication...
        </Typography>
      </Box>
    );
  }

  // If authentication is required but user is not authenticated
  if (requireAuth && !isAuthenticated) {
    if (fallback) {
      return fallback;
    }

    return (
      <Box
        display=\"flex\"
        flexDirection=\"column\"
        alignItems=\"center\"
        justifyContent=\"center\"
        minHeight=\"50vh\"
        gap={3}
        p={4}
      >
        <Lock sx={{ fontSize: 64, color: 'text.secondary' }} />
        <Typography variant=\"h4\" color=\"text.primary\" textAlign=\"center\">
          Authentication Required
        </Typography>
        <Typography variant=\"body1\" color=\"text.secondary\" textAlign=\"center\" maxWidth={400}>
          You need to be signed in to access this page. Please sign in to continue using the Financial Dashboard.
        </Typography>
        <Button
          variant=\"contained\"
          size=\"large\"
          onClick={() => window.location.reload()}
          sx={{ mt: 2 }}
        >
          Sign In
        </Button>
      </Box>
    );
  }

  // User is authenticated or authentication is not required
  return children;
}

export default ProtectedRoute;