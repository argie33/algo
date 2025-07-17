import { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api from '../services/api';

/**
 * Hook to manage user onboarding state
 */
export const useOnboarding = () => {
  const [onboardingState, setOnboardingState] = useState({
    isComplete: false,
    hasApiKeys: false,
    hasPreferences: false,
    showOnboarding: false,
    loading: true
  });
  
  const { user, isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated && user) {
      checkOnboardingStatus();
    } else {
      setOnboardingState(prev => ({ ...prev, loading: false }));
    }
  }, [isAuthenticated, user]);

  const checkOnboardingStatus = async () => {
    try {
      setOnboardingState(prev => ({ ...prev, loading: true }));
      
      // Check if onboarding is marked as complete
      const onboardingResponse = await api.get('/api/settings/onboarding-status');
      const isComplete = onboardingResponse.data?.isComplete || false;
      
      // Check if user has API keys
      const apiKeysResponse = await api.get('/api/settings/api-keys');
      const hasApiKeys = apiKeysResponse.data?.keys?.length > 0 || false;
      
      // Check if user has set preferences
      const preferencesResponse = await api.get('/api/settings/preferences');
      const hasPreferences = preferencesResponse.data?.riskTolerance ? true : false;
      
      // Determine if we should show onboarding
      const shouldShowOnboarding = !isComplete && (!hasApiKeys || !hasPreferences);
      
      setOnboardingState({
        isComplete,
        hasApiKeys,
        hasPreferences,
        showOnboarding: shouldShowOnboarding,
        loading: false
      });
      
    } catch (error) {
      console.error('Failed to check onboarding status:', error);
      
      // If this is a new user (no settings yet), show onboarding
      if (error.response?.status === 404) {
        setOnboardingState({
          isComplete: false,
          hasApiKeys: false,
          hasPreferences: false,
          showOnboarding: true,
          loading: false
        });
      } else {
        setOnboardingState(prev => ({
          ...prev,
          loading: false,
          showOnboarding: false
        }));
      }
    }
  };

  const completeOnboarding = () => {
    setOnboardingState(prev => ({
      ...prev,
      isComplete: true,
      showOnboarding: false
    }));
  };

  const skipOnboarding = async () => {
    try {
      await api.post('/api/settings/onboarding-complete');
      completeOnboarding();
    } catch (error) {
      console.error('Failed to skip onboarding:', error);
      // Still mark as complete locally
      completeOnboarding();
    }
  };

  const reopenOnboarding = () => {
    setOnboardingState(prev => ({
      ...prev,
      showOnboarding: true
    }));
  };

  return {
    ...onboardingState,
    completeOnboarding,
    skipOnboarding,
    reopenOnboarding,
    checkOnboardingStatus
  };
};