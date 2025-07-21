/**
 * ApiKeyOnboarding - Comprehensive guided setup for API keys
 * Step-by-step process supporting Alpaca and TD Ameritrade
 * Production-grade with validation, error handling, and progress tracking
 */

import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Stepper,
  Step,
  StepLabel,
  Alert,
  Link,
  CircularProgress,
  Chip,
  Divider,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem
} from '@mui/material';
import {
  TrendingUp,
  VpnKey,
  CheckCircle,
  Error,
  ArrowForward,
  ArrowBack,
  OpenInNew
} from '@mui/icons-material';
import { useApiKeys } from './ApiKeyProvider';

const ApiKeyOnboarding = ({ onComplete, onSkip }) => {
  const { saveApiKey, validateApiKey } = useApiKeys();
  const [activeStep, setActiveStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedProvider, setSelectedProvider] = useState('alpaca');
  const [apiKeyData, setApiKeyData] = useState({
    alpaca: { keyId: '', secretKey: '' },
    td_ameritrade: { keyId: '' }
  });

  const steps = [
    'Welcome',
    'Choose Provider',
    'Configure API Keys',
    'Validation',
    'Complete'
  ];

  const providerInfo = {
    alpaca: {
      name: 'Alpaca Trading',
      description: 'Commission-free trading platform with comprehensive API',
      requirements: ['Key ID (20 characters)', 'Secret Key (40 characters)'],
      setupUrl: 'https://app.alpaca.markets/paper/dashboard/overview',
      features: ['Paper Trading', 'Live Trading', 'Portfolio Management', 'Real-time Data']
    },
    td_ameritrade: {
      name: 'TD Ameritrade',
      description: 'Full-service broker with powerful trading tools',
      requirements: ['Consumer Key (App Key)'],
      setupUrl: 'https://developer.tdameritrade.com/user/me/apps',
      features: ['Market Data', 'Account Information', 'Options Trading', 'Research Tools']
    }
  };

  const handleNext = async () => {
    if (activeStep === 2) {
      // Validate API keys before proceeding
      await handleValidateKeys();
    } else if (activeStep === 3) {
      // Save validated keys
      await handleSaveKeys();
    } else {
      setActiveStep((prevStep) => prevStep + 1);
    }
  };

  const handleBack = () => {
    setActiveStep((prevStep) => prevStep - 1);
    setError(null);
  };

  const handleProviderChange = (provider) => {
    setSelectedProvider(provider);
    setError(null);
  };

  const handleKeyChange = (field, value) => {
    setApiKeyData(prev => ({
      ...prev,
      [selectedProvider]: {
        ...prev[selectedProvider],
        [field]: value
      }
    }));
    setError(null);
  };

  const handleValidateKeys = async () => {
    setLoading(true);
    setError(null);

    try {
      const keys = apiKeyData[selectedProvider];
      const validation = validateApiKey(selectedProvider, keys.keyId, keys.secretKey);
      
      if (!validation.valid) {
        throw new Error(validation.error);
      }

      console.log(`✅ API key validation passed for ${selectedProvider}`);
      setActiveStep(3);
    } catch (error) {
      console.error('❌ API key validation failed:', error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveKeys = async () => {
    setLoading(true);
    setError(null);

    try {
      const keys = apiKeyData[selectedProvider];
      await saveApiKey(selectedProvider, keys.keyId, keys.secretKey);
      
      console.log(`✅ API key saved for ${selectedProvider}`);
      setActiveStep(4);
    } catch (error) {
      console.error('❌ Failed to save API key:', error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleComplete = () => {
    const savedKeys = { [selectedProvider]: apiKeyData[selectedProvider] };
    onComplete(savedKeys);
  };

  const renderStepContent = () => {
    switch (activeStep) {
      case 0:
        return (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <TrendingUp sx={{ fontSize: 64, color: 'primary.main', mb: 2 }} />
            <Typography variant="h4" gutterBottom>
              Welcome to API Key Setup
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ mb: 3, maxWidth: 600, mx: 'auto' }}>
              To provide you with real-time market data and trading capabilities, 
              we need to connect to your broker&apos;s API. This process is secure and 
              your credentials are encrypted.
            </Typography>
            <Alert severity="info" sx={{ mb: 2, textAlign: 'left' }}>
              <Typography variant="subtitle2" gutterBottom>
                What you&apos;ll need:
              </Typography>
              <ul style={{ margin: 0, paddingLeft: '20px' }}>
                <li>An account with a supported broker (Alpaca or TD Ameritrade)</li>
                <li>API credentials from your broker&apos;s developer portal</li>
                <li>5-10 minutes to complete the setup</li>
              </ul>
            </Alert>
          </Box>
        );

      case 1:
        return (
          <Box sx={{ py: 2 }}>
            <Typography variant="h5" gutterBottom>
              Choose Your Broker
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Select your broker to configure API access. You can add multiple brokers later.
            </Typography>
            
            <Grid container spacing={2}>
              {Object.entries(providerInfo).map(([provider, info]) => (
                <Grid item xs={12} md={6} key={provider}>
                  <Card 
                    sx={{ 
                      cursor: 'pointer',
                      border: selectedProvider === provider ? 2 : 1,
                      borderColor: selectedProvider === provider ? 'primary.main' : 'grey.300'
                    }}
                    onClick={() => handleProviderChange(provider)}
                  >
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                        <VpnKey sx={{ mr: 1, color: 'primary.main' }} />
                        <Typography variant="h6">{info.name}</Typography>
                        {selectedProvider === provider && (
                          <CheckCircle sx={{ ml: 'auto', color: 'success.main' }} />
                        )}
                      </Box>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        {info.description}
                      </Typography>
                      <Box sx={{ mb: 2 }}>
                        {info.features.map((feature, index) => (
                          <Chip key={index} label={feature} size="small" sx={{ mr: 0.5, mb: 0.5 }} />
                        ))}
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </Box>
        );

      case 2: {
        const provider = providerInfo[selectedProvider];
        const keys = apiKeyData[selectedProvider];
        
        return (
          <Box sx={{ py: 2 }}>
            <Typography variant="h5" gutterBottom>
              Configure {provider.name} API
            </Typography>
            
            <Alert severity="info" sx={{ mb: 3 }}>
              <Typography variant="subtitle2" gutterBottom>
                Get your API credentials:
              </Typography>
              <Link 
                href={provider.setupUrl} 
                target="_blank" 
                rel="noopener"
                sx={{ display: 'flex', alignItems: 'center', mt: 1 }}
              >
                Open {provider.name} Developer Portal
                <OpenInNew sx={{ ml: 0.5, fontSize: 16 }} />
              </Link>
            </Alert>

            <Box sx={{ mb: 3 }}>
              <Typography variant="subtitle1" gutterBottom>
                Required Information:
              </Typography>
              <ul>
                {provider.requirements.map((req, index) => (
                  <li key={index}>{req}</li>
                ))}
              </ul>
            </Box>

            <Box sx={{ mb: 2 }}>
              <TextField
                fullWidth
                label={selectedProvider === 'alpaca' ? 'API Key ID' : 'Consumer Key'}
                value={keys.keyId}
                onChange={(e) => handleKeyChange('keyId', e.target.value)}
                placeholder={selectedProvider === 'alpaca' ? 'PKXXXXXXXXXXXXXXXXXXX' : 'XXXXXXXXXXXXXXXXXXXXXXXX@AMER.OAUTHAP'}
                sx={{ mb: 2 }}
              />
              
              {selectedProvider === 'alpaca' && (
                <TextField
                  fullWidth
                  label="Secret Key"
                  type="password"
                  value={keys.secretKey}
                  onChange={(e) => handleKeyChange('secretKey', e.target.value)}
                  placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                />
              )}
            </Box>

            {error && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {error}
              </Alert>
            )}
          </Box>
        );
      }

      case 3:
        return (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CheckCircle sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
            <Typography variant="h5" gutterBottom>
              API Keys Validated Successfully
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
              Your {providerInfo[selectedProvider].name} API credentials have been validated 
              and are ready to use.
            </Typography>
            
            <Card sx={{ maxWidth: 400, mx: 'auto', textAlign: 'left' }}>
              <CardContent>
                <Typography variant="subtitle1" gutterBottom>
                  Configuration Summary:
                </Typography>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="body2">Provider:</Typography>
                  <Chip label={providerInfo[selectedProvider].name} size="small" color="primary" />
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="body2">Key Status:</Typography>
                  <Chip label="Valid" size="small" color="success" />
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2">Encryption:</Typography>
                  <Chip label="AES-256-GCM" size="small" />
                </Box>
              </CardContent>
            </Card>
          </Box>
        );

      case 4:
        return (
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <CheckCircle sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
            <Typography variant="h4" gutterBottom>
              Setup Complete!
            </Typography>
            <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
              Your API keys have been securely saved and encrypted. You can now access 
              real-time market data and trading features.
            </Typography>
            
            <Alert severity="success" sx={{ mb: 3, textAlign: 'left' }}>
              <Typography variant="subtitle2" gutterBottom>
                What&apos;s Next:
              </Typography>
              <ul style={{ margin: 0, paddingLeft: '20px' }}>
                <li>Access your portfolio and real-time data</li>
                <li>Configure additional API providers in Settings</li>
                <li>Explore trading features and analytics</li>
              </ul>
            </Alert>
          </Box>
        );

      default:
        return null;
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
        {steps.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      <Box sx={{ minHeight: 400 }}>
        {renderStepContent()}
      </Box>

      <Divider sx={{ my: 3 }} />

      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button
          disabled={activeStep === 0}
          onClick={handleBack}
          startIcon={<ArrowBack />}
        >
          Back
        </Button>

        <Box>
          {onSkip && activeStep < 4 && (
            <Button onClick={onSkip} sx={{ mr: 1 }}>
              Skip for Now
            </Button>
          )}
          
          {activeStep < 4 ? (
            <Button
              variant="contained"
              onClick={handleNext}
              disabled={loading || (activeStep === 2 && (!apiKeyData[selectedProvider].keyId || (selectedProvider === 'alpaca' && !apiKeyData[selectedProvider].secretKey)))}
              endIcon={loading ? <CircularProgress size={20} /> : <ArrowForward />}
            >
              {activeStep === 2 ? 'Validate' : activeStep === 3 ? 'Save & Continue' : 'Next'}
            </Button>
          ) : (
            <Button
              variant="contained"
              onClick={handleComplete}
              color="success"
            >
              Complete Setup
            </Button>
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default ApiKeyOnboarding;