import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getApiConfig } from '../services/api';
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

const LiveDataTailwind = () => {
  const { user, isAuthenticated } = useAuth();
  const { apiUrl } = getApiConfig();
  
  // State management
  const [isStreaming, setIsStreaming] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [isAdminMode, setIsAdminMode] = useState(false);
  const [adminMetrics, setAdminMetrics] = useState(null);
  const [activeFeeds, setActiveFeeds] = useState([]);
  
  // Check if user is admin
  const isUserAdmin = () => {
    return user?.role === 'admin' || user?.userId === 'admin';
  };
  
  // Load admin data
  const loadAdminData = async () => {
    try {
      const token = localStorage.getItem('authToken');
      const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      };
      
      const metricsResponse = await fetch(`${apiUrl}/live-data/admin/metrics`, { headers });
      if (metricsResponse.ok) {
        const metricsData = await metricsResponse.json();
        setAdminMetrics(metricsData.success ? metricsData.data : metricsData);
      }
    } catch (error) {
      console.error('Failed to load admin data:', error);
    }
  };
  
  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'bg-green-100 text-green-800';
      case 'connecting': return 'bg-yellow-100 text-yellow-800';
      case 'error': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <ApiKeyStatusIndicator 
          showSetupDialog={true}
          requiredProviders={['alpaca']}
        />
      </div>
      
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Live Market Data - No MUI</h1>
          <p className="text-gray-600">TailwindCSS version to avoid MUI createPalette errors</p>
        </div>
        
        {isUserAdmin() && (
          <div className="flex items-center space-x-2">
            <span className="text-sm font-medium text-gray-700">Admin Mode</span>
            <button
              onClick={() => setIsAdminMode(!isAdminMode)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                isAdminMode ? 'bg-blue-600' : 'bg-gray-200'
              }`}
            >
              <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                isAdminMode ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </button>
          </div>
        )}
      </div>
      
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-lg font-semibold">Connection Status</h2>
            <div className="flex items-center space-x-2 mt-2">
              <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusColor(connectionStatus)}`}>
                {connectionStatus.toUpperCase()}
              </span>
            </div>
          </div>
          
          <button
            onClick={() => setIsStreaming(!isStreaming)}
            className={`px-4 py-2 rounded-md font-medium ${
              isStreaming 
                ? 'bg-red-600 text-gray-100 hover:bg-red-700' 
                : 'bg-green-600 text-gray-100 hover:bg-green-700'
            }`}
          >
            {isStreaming ? 'Disconnect' : 'Connect WebSocket'}
          </button>
        </div>
      </div>
      
      {!isStreaming && (
        <div className="mt-6 bg-white rounded-lg shadow p-12 text-center">
          <h3 className="text-lg font-semibold text-gray-900 mb-2">WebSocket Disconnected</h3>
          <p className="text-gray-600 mb-4">This version uses TailwindCSS instead of MUI to avoid createPalette errors</p>
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 max-w-2xl mx-auto">
            <p className="text-sm text-blue-800">
              TailwindCSS implementation of the LiveData component without any MUI dependencies.
              This should eliminate the createPalette.js TypeError completely.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

export default LiveDataTailwind;