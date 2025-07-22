/**
 * RequiresApiKeys - Enhanced wrapper component with graceful degradation
 * Provides comprehensive API key protection with fallback strategies
 * Updated with production-grade error handling and demo mode support
 */

import { useState } from 'react';
import { Box, Alert, Button, Dialog, CircularProgress } from '@mui/material';
import { Settings, VpnKey } from '@mui/icons-material';
import { useApiKeys } from './ApiKeyProvider';
import ApiKeyOnboarding from './ApiKeyOnboarding';
import { useNavigate } from 'react-router-dom';

const RequiresApiKeys = ({ 
  children, 
  requiredProviders = ['alpaca'], // Which providers are required for this page
  message, // Custom message to show
  allowSkip = false, // Whether user can skip onboarding
  fallbackContent = null // Content to show when no API keys (instead of onboarding)
}) => {
  const { 
    isLoading, 
    needsOnboarding, 
    error,
    markOnboardingComplete,
    hasValidProvider 
  } = useApiKeys();
  
  const navigate = useNavigate();
  const [onboardingOpen, setOnboardingOpen] = useState(false);

  // Show loading state
  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  // Check if required providers are configured
  const hasRequiredProviders = requiredProviders.every(provider => 
    hasValidProvider(provider)
  );

  // Show children if all required providers are available
  if (!needsOnboarding && hasRequiredProviders) {
    return children;
  }

  // Show fallback content if provided
  if (fallbackContent && !hasRequiredProviders) {
    return fallbackContent;
  }

  // Determine which providers are missing
  const missingProviders = requiredProviders.filter(provider => 
    !hasValidProvider(provider)
  );

  const defaultMessage = `This page requires ${missingProviders.join(' and ')} API keys to display live data. Please configure your API keys to continue.`;

  const handleStartOnboarding = () => {
    setOnboardingOpen(true);
  };

  const handleOnboardingComplete = (savedKeys) => {
    setOnboardingOpen(false);
    markOnboardingComplete(savedKeys);
  };

  const handleSkipOnboarding = () => {
    setOnboardingOpen(false);
    if (allowSkip) {
      // Allow user to continue with limited functionality
      return children;
    }
  };

  const handleGoToSettings = () => {
    navigate('/settings');
  };

  return (
    <Box sx={{ p: 3 }}>
      <Alert 
        severity="warning" 
        sx={{ mb: 2 }}
        action={
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button 
              color="inherit" 
              size="small"
              onClick={handleStartOnboarding}
              startIcon={<VpnKey />}
            >
              Setup API Keys
            </Button>
            <Button 
              color="inherit" 
              size="small"
              onClick={handleGoToSettings}
              startIcon={<Settings />}
            >
              Go to Settings
            </Button>
          </Box>
        }
      >
        {message || defaultMessage}
      </Alert>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Error loading API keys: {error}
        </Alert>
      )}

      {/* Show basic info about what's missing */}
      <Box sx={{ mt: 2 }}>
        <Alert severity="info">
          <strong>Required for this page:</strong>
          <ul style={{ margin: '8px 0', paddingLeft: '20px' }}>
            {requiredProviders.map(provider => (
              <li key={provider}>
                {provider.charAt(0).toUpperCase() + provider.slice(1)} API
                {hasValidProvider(provider) ? ' ✅' : ' ❌'}
              </li>
            ))}
          </ul>
        </Alert>
      </Box>

      {/* Show limited content if skip is allowed */}
      {allowSkip && (
        <Box sx={{ mt: 3 }}>
          <Alert severity="info" sx={{ mb: 2 }}>
            You can continue with limited functionality using demo data.
          </Alert>
          {children}
        </Box>
      )}

      {/* API Key Onboarding Dialog */}
      <Dialog 
        open={onboardingOpen} 
        onClose={() => setOnboardingOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <ApiKeyOnboarding 
          onComplete={handleOnboardingComplete}
          onSkip={handleSkipOnboarding}
        />
      </Dialog>
    </Box>
  );
};

export default RequiresApiKeys;