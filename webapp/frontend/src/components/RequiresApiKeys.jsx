/**
 * RequiresApiKeys - Enhanced wrapper component with graceful degradation
 * Provides comprehensive API key protection with fallback strategies
 * Updated with production-grade error handling and demo mode support
 */

import React, { useState } from 'react';
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
    apiKeys, 
    isLoading, 
    hasApiKeys, 
    needsOnboarding, 
    error,
    markOnboardingComplete,
    hasValidProvider 
  } = useApiKeys();
  
  const navigate = useNavigate();
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [onboardingOpen, setOnboardingOpen] = useState(false);

  // Show loading state
  if (isLoading) {
    return (
      <div  sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
      </div>
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
    console.log('🎉 API key onboarding completed');
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
    <div  sx={{ p: 3 }}>
      <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
        severity="warning" 
        sx={{ mb: 2 }}
        action={
          <div  sx={{ display: 'flex', gap: 1 }}>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              color="inherit" 
              size="small"
              onClick={handleStartOnboarding}
              startIcon={<VpnKey />}
            >
              Setup API Keys
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              color="inherit" 
              size="small"
              onClick={handleGoToSettings}
              startIcon={<Settings />}
            >
              Go to Settings
            </button>
          </div>
        }
      >
        {message || defaultMessage}
      </div>

      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
          Error loading API keys: {error}
        </div>
      )}

      {/* Show basic info about what's missing */}
      <div  sx={{ mt: 2 }}>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
          <strong>Required for this page:</strong>
          <ul style={{ margin: '8px 0', paddingLeft: '20px' }}>
            {requiredProviders.map(provider => (
              <li key={provider}>
                {provider.charAt(0).toUpperCase() + provider.slice(1)} API
                {hasValidProvider(provider) ? ' ✅' : ' ❌'}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Show limited content if skip is allowed */}
      {allowSkip && (
        <div  sx={{ mt: 3 }}>
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 2 }}>
            You can continue with limited functionality using demo data.
          </div>
          {children}
        </div>
      )}

      {/* API Key Onboarding Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
        open={onboardingOpen} 
        onClose={() => setOnboardingOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <ApiKeyOnboarding 
          onComplete={handleOnboardingComplete}
          onSkip={handleSkipOnboarding}
        />
      </div>
    </div>
  );
};

export default RequiresApiKeys;