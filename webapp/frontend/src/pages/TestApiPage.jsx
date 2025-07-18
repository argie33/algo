import React, { useState, useEffect } from 'react';
import { getPortfolioPerformance, getPortfolioAnalytics } from '../services/api';

const TestApiPage = () => {
  const [results, setResults] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const testApi = async () => {
    setLoading(true);
    setError(null);
    const testResults = {};

    try {
      console.log('🧪 Testing API endpoints...');
      
      // Test portfolio performance
      console.log('Testing getPortfolioPerformance...');
      const perfResult = await getPortfolioPerformance('1Y');
      testResults.performance = {
        success: true,
        data: perfResult,
        dataLength: perfResult?.data?.performance?.length || 0
      };
      console.log('✅ Portfolio Performance success:', perfResult);

      // Test portfolio analytics
      console.log('Testing getPortfolioAnalytics...');
      const analyticsResult = await getPortfolioAnalytics('1Y');
      testResults.analytics = {
        success: true,
        data: analyticsResult,
        holdingsCount: analyticsResult?.data?.holdings?.length || 0
      };
      console.log('✅ Portfolio Analytics success:', analyticsResult);

    } catch (err) {
      console.error('❌ API Test failed:', err);
      setError(err.message);
      testResults.error = err.message;
    }

    setResults(testResults);
    setLoading(false);
  };

  useEffect(() => {
    testApi();
  }, []);

  return (
    <div className="container mx-auto" maxWidth="md">
      <div  sx={{ mt: 4 }}>
        <div  variant="h4" gutterBottom>
          API Test Page
        </div>
        <div  variant="body1" sx={{ mb: 3 }}>
          This page tests the API endpoints used by the Portfolio Performance page.
        </div>

        {error && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }}>
            Error: {error}
          </div>
        )}

        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
          variant="contained" 
          onClick={testApi} 
          disabled={loading}
          sx={{ mb: 3 }}
        >
          {loading ? 'Testing...' : 'Test API Endpoints'}
        </button>

        {Object.keys(results).length > 0 && (
          <div>
            <div  variant="h6" gutterBottom>
              Test Results:
            </div>
            
            {results.performance && (
              <div className="bg-white shadow-md rounded-lg" sx={{ mb: 2 }}>
                <div className="bg-white shadow-md rounded-lg"Content>
                  <div  variant="h6" color="success.main">
                    ✅ Portfolio Performance API
                  </div>
                  <div  variant="body2">
                    Data points: {results.performance.dataLength}
                  </div>
                  <div  variant="body2">
                    Status: {results.performance.success ? 'SUCCESS' : 'FAILED'}
                  </div>
                </div>
              </div>
            )}

            {results.analytics && (
              <div className="bg-white shadow-md rounded-lg" sx={{ mb: 2 }}>
                <div className="bg-white shadow-md rounded-lg"Content>
                  <div  variant="h6" color="success.main">
                    ✅ Portfolio Analytics API
                  </div>
                  <div  variant="body2">
                    Holdings count: {results.analytics.holdingsCount}
                  </div>
                  <div  variant="body2">
                    Status: {results.analytics.success ? 'SUCCESS' : 'FAILED'}
                  </div>
                </div>
              </div>
            )}

            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="h6" gutterBottom>
                  Raw Results:
                </div>
                <div  component="pre" sx={{ fontSize: '0.75rem', overflow: 'auto', maxHeight: 300 }}>
                  {JSON.stringify(results, null, 2)}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TestApiPage;