import React, { useState, useEffect } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { getApiKeys } from '../../services/api';
import ApiKeySetupWizard from '../ApiKeySetupWizard';

function ProtectedRoute({ 
  children, 
  requireAuth = false, 
  requireApiKeys = false, 
  fallback = null 
}) {
  const { user, isAuthenticated, isLoading } = useAuth();
  const [apiKeys, setApiKeys] = useState([]);
  const [loadingApiKeys, setLoadingApiKeys] = useState(false);
  const [showSetupWizard, setShowSetupWizard] = useState(false);
  const navigate = useNavigate();

  // Check for API keys when component mounts
  useEffect(() => {
    if (requireApiKeys && isAuthenticated && user) {
      checkApiKeys();
    }
  }, [requireApiKeys, isAuthenticated, user]);

  const checkApiKeys = async () => {
    setLoadingApiKeys(true);
    try {
      const response = await getApiKeys();
      const keys = response?.apiKeys || [];
      setApiKeys(keys);
    } catch (error) {
      console.error('Error checking API keys:', error);
      setApiKeys([]);
    } finally {
      setLoadingApiKeys(false);
    }
  };

  const handleApiKeySetup = async (formData) => {
    // This would be called from the wizard
    await checkApiKeys(); // Refresh API keys after setup
    setShowSetupWizard(false);
  };

  // Show loading spinner while checking authentication
  if (isLoading || loadingApiKeys) {
    return (
      <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
      </div>
    );
  }

  // Show fallback if provided and not authenticated
  if (requireAuth && !isAuthenticated && fallback) {
    return fallback;
  }

  // Show auth required message
  if (requireAuth && !isAuthenticated) {
    return (
      <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <div className="bg-white shadow-md rounded-lg" sx={{ maxWidth: 400, textAlign: 'center' }}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <Lock sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
            <div  variant="h6" gutterBottom>
              Authentication Required
            </div>
            <div  variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Please sign in to access this page.
            </div>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="contained"
              onClick={() => navigate('/login')}
            >
              Sign In
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Show API key setup required message
  if (requireApiKeys && isAuthenticated && apiKeys.length === 0) {
    return (
      <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <div className="bg-white shadow-md rounded-lg" sx={{ maxWidth: 500, textAlign: 'center' }}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <Key sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
            <div  variant="h6" gutterBottom>
              API Key Setup Required
            </div>
            <div  variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              This page requires connection to your brokerage account to display live data. 
              Set up your API keys to get started.
            </div>
            
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 3, textAlign: 'left' }}>
              <div  variant="body2">
                <strong>Why do I need API keys?</strong><br />
                API keys allow us to securely connect to your brokerage account to:
                <br />• Import your real portfolio holdings
                <br />• Display live market data
                <br />• Execute trades (if enabled)
                <br />• Provide real-time analytics
              </div>
            </div>

            <div  sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="contained"
                startIcon={<Key />}
                onClick={() => setShowSetupWizard(true)}
              >
                Set Up API Keys
              </button>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                startIcon={<Settings />}
                onClick={() => navigate('/settings')}
              >
                Go to Settings
              </button>
            </div>
          </div>
        </div>

        <ApiKeySetupWizard
          open={showSetupWizard}
          onClose={() => setShowSetupWizard(false)}
          onComplete={handleApiKeySetup}
        />
      </div>
    );
  }

  return children;
}

export default ProtectedRoute;