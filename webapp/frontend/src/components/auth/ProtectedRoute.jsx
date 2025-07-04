import React from 'react';
import { Box, CircularProgress, Typography, Button } from '@mui/material';
import { Lock } from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';

function ProtectedRoute({ children, requireAuth = false, fallback = null }) {
  // Authentication disabled - all routes are now public
  return children;
}

export default ProtectedRoute;