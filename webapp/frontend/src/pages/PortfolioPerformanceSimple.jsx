import React, { useState, useEffect } from 'react';
import { getPortfolioPerformance, getPortfolioAnalytics } from '../services/api';
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

const PortfolioPerformanceSimple = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [performanceData, setPerformanceData] = useState(null);
  const [analyticsData, setAnalyticsData] = useState(null);
  const [debugInfo, setDebugInfo] = useState([]);

  const addDebugInfo = (message) => {
    console.log('🐛 DEBUG:', message);
    setDebugInfo(prev => [...prev, `${new Date().toLocaleTimeString()}: ${message}`]);
  };

  useEffect(() => {
    addDebugInfo('Component mounted, starting data fetch...');
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      addDebugInfo('Setting loading to true, clearing error');

      // Test 1: Portfolio Performance
      addDebugInfo('Calling getPortfolioPerformance...');
      const perfResponse = await getPortfolioPerformance('1Y');
      addDebugInfo(`Performance API response: ${JSON.stringify(perfResponse, null, 2).substring(0, 200)}...`);
      setPerformanceData(perfResponse);

      // Test 2: Portfolio Analytics
      addDebugInfo('Calling getPortfolioAnalytics...');
      const analyticsResponse = await getPortfolioAnalytics('1Y');
      addDebugInfo(`Analytics API response: ${JSON.stringify(analyticsResponse, null, 2).substring(0, 200)}...`);
      setAnalyticsData(analyticsResponse);

      addDebugInfo('All API calls completed successfully');
    } catch (err) {
      addDebugInfo(`Error occurred: ${err.message}`);
      console.error('❌ API Error:', err);
      setError(`Failed to fetch data: ${err.message}`);
    } finally {
      setLoading(false);
      addDebugInfo('Setting loading to false');
    }
  };

  const retryFetch = () => {
    addDebugInfo('Manual retry initiated');
    fetchData();
  };

  if (loading) {
    return (
      <div className="container mx-auto" maxWidth="md">
        <div  variant="h4" gutterBottom>
          Portfolio Performance (Simple Debug Version)
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '20px' }}>
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
          <div>Loading portfolio data...</div>
        </div>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6">Debug Information:</div>
            {debugInfo.map((info, index) => (
              <div  key={index} variant="body2" style={{ fontFamily: 'monospace', marginBottom: '4px' }}>
                {info}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="md">
      {/* API Key Status */}
      <div  sx={{ mb: 3 }}>
        <ApiKeyStatusIndicator 
          compact={true}
          showSetupDialog={true}
          onStatusChange={(status) => {
            console.log('Portfolio Performance Simple - API Key Status:', status);
          }}
        />
      </div>

      <div  variant="h4" gutterBottom>
        Portfolio Performance (Simple Debug Version)
      </div>

      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }}>
          {error}
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={retryFetch} sx={{ ml: 2 }}>
            Retry
          </button>
        </div>
      )}

      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Performance Data Status
          </div>
          {performanceData ? (
            <div>
              <div  color="success.main">✅ Performance data loaded successfully</div>
              <div>
                Data points: {performanceData.data?.performance?.length || 0}
              </div>
              <div>
                Success: {performanceData.success ? 'true' : 'false'}
              </div>
            </div>
          ) : (
            <div  color="error.main">❌ No performance data</div>
          )}
        </div>
      </div>

      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Analytics Data Status
          </div>
          {analyticsData ? (
            <div>
              <div  color="success.main">✅ Analytics data loaded successfully</div>
              <div>
                Holdings: {analyticsData.data?.holdings?.length || 0}
              </div>
              <div>
                Success: {analyticsData.success ? 'true' : 'false'}
              </div>
            </div>
          ) : (
            <div  color="error.main">❌ No analytics data</div>
          )}
        </div>
      </div>

      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Debug Information:
          </div>
          {debugInfo.map((info, index) => (
            <div  key={index} variant="body2" style={{ fontFamily: 'monospace', marginBottom: '4px' }}>
              {info}
            </div>
          ))}
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={retryFetch} variant="outlined" sx={{ mt: 2 }}>
            Reload Data
          </button>
        </div>
      </div>
    </div>
  );
};

export default PortfolioPerformanceSimple;