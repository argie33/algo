import React, { useState, useEffect } from 'react';
import { 
  Box, 
  Card, 
  CardContent, 
  Typography, 
  Button, 
  Alert,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { getApiConfig, getCurrentBaseURL } from '../services/api';
import axios from 'axios';

function ApiDebugger() {
  const [results, setResults] = useState({});
  const [testing, setTesting] = useState(false);
  const [config, setConfig] = useState(null);

  useEffect(() => {
    setConfig(getApiConfig());
  }, []);

  const testEndpoint = async (name, url) => {
    const startTime = Date.now();
    try {
      console.log(`Testing ${name}: ${url}`);
      const response = await axios.get(url, { 
        timeout: 10000,
        headers: {
          'Content-Type': 'application/json'
        }
      });
      const duration = Date.now() - startTime;
      return {
        success: true,
        status: response.status,
        statusText: response.statusText,
        duration: `${duration}ms`,
        data: response.data,
        headers: response.headers
      };
    } catch (error) {
      const duration = Date.now() - startTime;
      return {
        success: false,
        status: error.response?.status || 'No Response',
        statusText: error.response?.statusText || error.message,
        duration: `${duration}ms`,
        error: error.message,
        code: error.code,
        data: error.response?.data
      };
    }
  };

  const runTests = async () => {
    setTesting(true);
    setResults({});
    
    const baseUrl = getCurrentBaseURL();
    const endpoints = [
      { name: 'Health Check', url: `${baseUrl}/health` },
      { name: 'API Info', url: `${baseUrl}/api` },
      { name: 'Market Overview', url: `${baseUrl}/api/market/overview` },
      { name: 'Market Overview (Alt)', url: `${baseUrl}/market/overview` },
      { name: 'Stocks', url: `${baseUrl}/api/stocks?limit=5` },
      { name: 'Stocks (Alt)', url: `${baseUrl}/stocks?limit=5` },
      { name: 'Technical Daily', url: `${baseUrl}/api/technical/daily?limit=5` },
      { name: 'Technical (Alt)', url: `${baseUrl}/technical/daily?limit=5` },
      { name: 'Market Ping', url: `${baseUrl}/api/market/ping` },
      { name: 'Stocks Ping', url: `${baseUrl}/api/stocks/ping` },
      { name: 'Technical Ping', url: `${baseUrl}/api/technical/ping` }
    ];

    const newResults = {};
    
    for (const endpoint of endpoints) {
      console.log(`Testing: ${endpoint.name}`);
      newResults[endpoint.name] = await testEndpoint(endpoint.name, endpoint.url);
      setResults({ ...newResults });
      // Small delay between requests
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    setTesting(false);
  };

  const getStatusColor = (result) => {
    if (!result) return 'default';
    if (result.success && result.status === 200) return 'success';
    if (result.success) return 'warning';
    return 'error';
  };

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          API Connection Debugger
        </Typography>
        
        {config && (
          <Alert severity="info" sx={{ mb: 2 }}>
            <Typography variant="body2">
              <strong>Current Configuration:</strong><br/>
              Base URL: {config.baseURL}<br/>
              Environment: {config.environment}<br/>
              Is Serverless: {config.isServerless ? 'Yes' : 'No'}<br/>
              Is Configured: {config.isConfigured ? 'Yes' : 'No'}
            </Typography>
          </Alert>
        )}

        <Button 
          variant="contained" 
          onClick={runTests} 
          disabled={testing}
          sx={{ mb: 2 }}
        >
          {testing ? <CircularProgress size={20} sx={{ mr: 1 }} /> : null}
          {testing ? 'Testing...' : 'Test API Endpoints'}
        </Button>

        {Object.entries(results).map(([name, result]) => (
          <Accordion key={name}>
            <AccordionSummary
              expandIcon={<ExpandMoreIcon />}
              sx={{ 
                backgroundColor: getStatusColor(result) === 'success' ? 'success.light' :
                               getStatusColor(result) === 'error' ? 'error.light' :
                               getStatusColor(result) === 'warning' ? 'warning.light' : 'grey.light'
              }}
            >
              <Typography>
                {name} - {result?.success ? '✅' : '❌'} ({result?.status}) - {result?.duration}
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Box>
                <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(result, null, 2)}
                </Typography>
              </Box>
            </AccordionDetails>
          </Accordion>
        ))}
      </CardContent>
    </Card>
  );
}

export default ApiDebugger;
