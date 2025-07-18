import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  Container,
  Typography,
  CircularProgress,
  Alert,
  Card,
  CardContent,
  Button,
  Box,
  Paper
} from '@mui/material';
import { getPortfolioPerformance, getPortfolioAnalytics } from '../services/api';
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

const PortfolioPerformanceDebug = () => {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [performanceData, setPerformanceData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [debugInfo, setDebugInfo] = useState([]);

  const addDebugInfo = (message) => {
    const timestamp = new Date().toLocaleTimeString();
    const logMessage = `${timestamp}: ${message}`;
    console.log('🐛 DEBUG:', logMessage);
    setDebugInfo(prev => [...prev, logMessage]);
  };

  useEffect(() => {
    addDebugInfo('Component mounted');
    addDebugInfo(`Auth loading: ${authLoading}, Authenticated: ${isAuthenticated}, User: ${user ? user.username : 'none'}`);
  }, []);

  useEffect(() => {
    addDebugInfo(`Auth state changed - Loading: ${authLoading}, Authenticated: ${isAuthenticated}`);
    
    // Only fetch data when auth is not loading
    if (!authLoading) {
      addDebugInfo('Auth loading complete, attempting to fetch data');
      fetchData();
    }
  }, [authLoading, isAuthenticated]);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      addDebugInfo('Starting data fetch...');

      // Check auth state from useAuth
      addDebugInfo(`User authenticated: ${isAuthenticated}, User object: ${!!user}`);

      // Test 1: Portfolio Performance
      addDebugInfo('Calling getPortfolioPerformance API...');
      try {
        const perfResponse = await getPortfolioPerformance('1Y');
        addDebugInfo(`Performance API success: ${JSON.stringify(perfResponse?.success || 'unknown')}`);
        setPerformanceData(perfResponse);
      } catch (perfError) {
        addDebugInfo(`Performance API failed: ${perfError.message}`);
        throw perfError;
      }

      // Test 2: Portfolio Analytics
      addDebugInfo('Calling getPortfolioAnalytics API...');
      try {
        const analyticsResponse = await getPortfolioAnalytics('1Y');
        addDebugInfo(`Analytics API success: ${JSON.stringify(analyticsResponse?.success || 'unknown')}`);
        setAnalyticsData(analyticsResponse);
      } catch (analyticsError) {
        addDebugInfo(`Analytics API failed: ${analyticsError.message}`);
        // Don't throw here, as analytics failure shouldn't block performance data
      }

      addDebugInfo('All API calls completed');
    } catch (err) {
      addDebugInfo(`Error in fetchData: ${err.message}`);
      console.error('❌ Fetch Error:', err);
      setError(`Failed to fetch data: ${err.message}`);
    } finally {
      setLoading(false);
      addDebugInfo('Data fetch completed, loading set to false');
    }
  };

  const retryFetch = () => {
    addDebugInfo('Manual retry initiated');
    fetchData();
  };

  const clearDebugInfo = () => {
    setDebugInfo([]);
  };

  return (
    <div className="container mx-auto" maxWidth="xl">
      {/* API Key Status */}
      <div  sx={{ mb: 3 }}>
        <ApiKeyStatusIndicator 
          compact={true}
          showSetupDialog={true}
          onStatusChange={(status) => {
            console.log('Portfolio Performance Debug - API Key Status:', status);
          }}
        />
      </div>

      <div  variant="h4" gutterBottom>
        Portfolio Performance (Debug Version)
      </div>
      
      <div  sx={{ mb: 3 }}>
        <div  variant="h6" gutterBottom>
          Authentication Status:
        </div>
        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, bgcolor: 'grey.50' }}>
          <div>Auth Loading: {authLoading ? '⏳ Yes' : '✅ No'}</div>
          <div>Authenticated: {isAuthenticated ? '✅ Yes' : '❌ No'}</div>
          <div>User: {user ? `✅ ${user.username}` : '❌ None'}</div>
          <div>Auth Context: {isAuthenticated ? '✅ Authenticated' : '❌ Not Authenticated'}</div>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }}>
          {error}
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={retryFetch} sx={{ ml: 2 }}>
            Retry
          </button>
        </div>
      )}

      {(loading || authLoading) && (
        <div  sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
          <div>
            {authLoading ? 'Initializing authentication...' : 'Loading portfolio data...'}
          </div>
        </div>
      )}

      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Data Status
          </div>
          
          <div  sx={{ mb: 2 }}>
            <div  variant="subtitle1">Performance Data:</div>
            {performanceData ? (
              <div  color="success.main">
                ✅ Loaded ({performanceData.data?.performance?.length || 0} data points)
              </div>
            ) : (
              <div  color="error.main">❌ Not loaded</div>
            )}
          </div>

          <div  sx={{ mb: 2 }}>
            <div  variant="subtitle1">Analytics Data:</div>
            {analyticsData ? (
              <div  color="success.main">
                ✅ Loaded ({analyticsData.data?.holdings?.length || 0} holdings)
              </div>
            ) : (
              <div  color="error.main">❌ Not loaded</div>
            )}
          </div>

          <div  sx={{ display: 'flex', gap: 2 }}>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={retryFetch} variant="outlined">
              Reload Data
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={clearDebugInfo} variant="outlined">
              Clear Debug Log
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Debug Log ({debugInfo.length} entries):
          </div>
          <div  sx={{ maxHeight: 400, overflow: 'auto', bgcolor: 'grey.50', p: 1 }}>
            {debugInfo.map((info, index) => (
              <div  
                key={index} 
                variant="body2" 
                sx={{ 
                  fontFamily: 'monospace', 
                  marginBottom: '2px',
                  fontSize: '0.75rem'
                }}
              >
                {info}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default PortfolioPerformanceDebug;