import React from 'react';
import { CogIcon } from '@heroicons/react/24/outline';
import { useAuth } from '../contexts/AuthContext';
import { PageLayout } from '../components/ui/layout';
import { LoadingFallback } from '../components/fallbacks/DataNotAvailable';
import SettingsManager from '../components/SettingsManager';
import RequiresApiKeys from '../components/RequiresApiKeys';

const Settings = () => {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading) {
    return (
      <PageLayout title="Settings">
        <LoadingFallback message="Loading settings..." />
      </PageLayout>
    );
  }

  return (
    <PageLayout 
      title="Settings" 
      subtitle="Manage your account, API keys, and trading preferences"
    >
      <div className="space-y-6">
        <SettingsManager />
      </div>
    </PageLayout>
  );
};

export default Settings;