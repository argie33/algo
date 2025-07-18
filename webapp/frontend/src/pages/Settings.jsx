import React from 'react';
import { useAuth } from '../contexts/AuthContext';
import SettingsManager from '../components/SettingsManager';
import RequiresApiKeys from '../components/RequiresApiKeys';

const Settings = () => {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading) {
    return (
      <div className="container mx-auto" maxWidth="lg" sx={{ py: 4 }}>
        <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <div>Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="lg" sx={{ py: 4 }}>
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" component="h1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <SettingsIcon /> Settings
        </div>
        <div  variant="subtitle1" color="text.secondary">
          Manage your account, API keys, and trading preferences
        </div>
      </div>
      
      <SettingsManager />
    </div>
  );
};

export default Settings;