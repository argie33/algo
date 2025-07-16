import React from 'react';
import { Container, Typography, Box } from '@mui/material';
import { Settings as SettingsIcon } from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import SettingsManager from '../components/SettingsManager';
import RequiresApiKeys from '../components/RequiresApiKeys';

const Settings = () => {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <Typography>Loading...</Typography>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <SettingsIcon /> Settings
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          Manage your account, API keys, and trading preferences
        </Typography>
      </Box>
      
      <SettingsManager />
    </Container>
  );
};

export default Settings;