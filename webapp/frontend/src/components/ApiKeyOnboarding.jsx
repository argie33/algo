/**
 * API Key Onboarding - Step-by-step API key setup
 */
import { useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  TextField,
  Typography,
  Alert,
  CircularProgress,
  Link
} from '@mui/material';
import { useApiKeys } from './ApiKeyProvider';

const steps = [
  {
    label: 'Welcome',
    description: 'Set up your API keys to access real market data'
  },
  {
    label: 'Alpaca Trading',
    description: 'Configure your Alpaca API for trading and portfolio data'
  },
  {
    label: 'Market Data',
    description: 'Add Polygon or Finnhub for enhanced market data'
  },
  {
    label: 'Validation',
    description: 'Test your API key connections'
  },
  {
    label: 'Complete',
    description: 'Your API keys are configured and ready'
  }
];

const ApiKeyOnboarding = ({ onComplete }) => {
  const [activeStep, setActiveStep] = useState(0);
  const [apiKeyInputs, setApiKeyInputs] = useState({
    alpaca: '',
    polygon: '',
    finnhub: ''
  });
  const [validating, setValidating] = useState(false);
  const [errors, setErrors] = useState({});

  const { setApiKey, validateApiKeys } = useApiKeys();

  const handleNext = () => {
    setActiveStep((prevActiveStep) => prevActiveStep + 1);
  };

  const handleBack = () => {
    setActiveStep((prevActiveStep) => prevActiveStep - 1);
  };

  const handleApiKeyChange = (provider, value) => {
    setApiKeyInputs(prev => ({ ...prev, [provider]: value }));
    // Clear error when user starts typing
    if (errors[provider]) {
      setErrors(prev => ({ ...prev, [provider]: null }));
    }
  };

  const validateAndSave = async (provider) => {
    const key = apiKeyInputs[provider];
    if (!key || key.trim().length === 0) {
      setErrors(prev => ({ ...prev, [provider]: 'API key is required' }));
      return false;
    }

    try {
      const success = await setApiKey(provider, key.trim());
      if (success) {
        setErrors(prev => ({ ...prev, [provider]: null }));
        return true;
      } else {
        setErrors(prev => ({ ...prev, [provider]: 'Failed to save API key' }));
        return false;
      }
    } catch (error) {
      setErrors(prev => ({ ...prev, [provider]: error.message }));
      return false;
    }
  };

  const handleValidateAll = async () => {
    setValidating(true);
    try {
      const result = await validateApiKeys();
      if (result.success) {
        handleNext(); // Move to complete step
      } else {
        setErrors({ general: result.error || 'Validation failed' });
      }
    } catch (error) {
      setErrors({ general: error.message });
    } finally {
      setValidating(false);
    }
  };

  const renderStepContent = (step) => {
    switch (step) {
      case 0:
        return (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body1" gutterBottom>
              Welcome to the API Key Setup Wizard! To access real-time market data and trading features, 
              you&rsquo;ll need to configure API keys from supported providers.
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              This process will take just a few minutes and will unlock all the advanced features of the platform.
            </Typography>
            <Button
              variant="contained"
              onClick={handleNext}
              sx={{ mt: 2 }}
            >
              Get Started
            </Button>
          </Box>
        );

      case 1:
        return (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" gutterBottom>
              Alpaca provides trading capabilities and portfolio data. 
              <Link href="https://alpaca.markets/docs/api-references/" target="_blank" rel="noopener">
                Get your Alpaca API key
              </Link>
            </Typography>
            <TextField
              fullWidth
              label="Alpaca API Key"
              type="password"
              value={apiKeyInputs.alpaca}
              onChange={(e) => handleApiKeyChange('alpaca', e.target.value)}
              error={!!errors.alpaca}
              helperText={errors.alpaca}
              sx={{ mt: 2, mb: 2 }}
            />
            <Box sx={{ mb: 1 }}>
              <Button
                variant="contained"
                onClick={async () => {
                  const success = await validateAndSave('alpaca');
                  if (success) handleNext();
                }}
                sx={{ mt: 1, mr: 1 }}
              >
                Continue
              </Button>
              <Button onClick={handleNext} sx={{ mt: 1, mr: 1 }}>
                Skip for now
              </Button>
              <Button onClick={handleBack} sx={{ mt: 1, mr: 1 }}>
                Back
              </Button>
            </Box>
          </Box>
        );

      case 2:
        return (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" gutterBottom>
              Add market data providers for enhanced real-time quotes and historical data.
            </Typography>
            
            <TextField
              fullWidth
              label="Polygon API Key (Optional)"
              type="password"
              value={apiKeyInputs.polygon}
              onChange={(e) => handleApiKeyChange('polygon', e.target.value)}
              error={!!errors.polygon}
              helperText={errors.polygon}
              sx={{ mt: 2, mb: 2 }}
            />
            
            <TextField
              fullWidth
              label="Finnhub API Key (Optional)"
              type="password"
              value={apiKeyInputs.finnhub}
              onChange={(e) => handleApiKeyChange('finnhub', e.target.value)}
              error={!!errors.finnhub}
              helperText={errors.finnhub}
              sx={{ mb: 2 }}
            />
            
            <Box sx={{ mb: 1 }}>
              <Button
                variant="contained"
                onClick={async () => {
                  // Save any filled keys
                  if (apiKeyInputs.polygon) await validateAndSave('polygon');
                  if (apiKeyInputs.finnhub) await validateAndSave('finnhub');
                  handleNext();
                }}
                sx={{ mt: 1, mr: 1 }}
              >
                Continue
              </Button>
              <Button onClick={handleNext} sx={{ mt: 1, mr: 1 }}>
                Skip
              </Button>
              <Button onClick={handleBack} sx={{ mt: 1, mr: 1 }}>
                Back
              </Button>
            </Box>
          </Box>
        );

      case 3:
        return (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body2" gutterBottom>
              Let&rsquo;s validate your API key connections to ensure everything is working correctly.
            </Typography>
            
            {errors.general && (
              <Alert severity="error" sx={{ mt: 2, mb: 2 }}>
                {errors.general}
              </Alert>
            )}
            
            <Box sx={{ mb: 1 }}>
              <Button
                variant="contained"
                onClick={handleValidateAll}
                disabled={validating}
                sx={{ mt: 1, mr: 1 }}
                startIcon={validating ? <CircularProgress size={20} /> : null}
              >
                {validating ? 'Validating...' : 'Validate Connections'}
              </Button>
              <Button onClick={handleNext} sx={{ mt: 1, mr: 1 }}>
                Skip Validation
              </Button>
              <Button onClick={handleBack} sx={{ mt: 1, mr: 1 }}>
                Back
              </Button>
            </Box>
          </Box>
        );

      case 4:
        return (
          <Box sx={{ mt: 2 }}>
            <Typography variant="body1" gutterBottom color="success.main">
              🎉 Setup Complete!
            </Typography>
            <Typography variant="body2" gutterBottom>
              Your API keys have been configured. You can now access all the platform features.
              You can always update your API keys later in the Settings page.
            </Typography>
            <Button
              variant="contained"
              onClick={onComplete}
              sx={{ mt: 2 }}
            >
              Start Using the Platform
            </Button>
          </Box>
        );

      default:
        return null;
    }
  };

  return (
    <Card sx={{ maxWidth: 600, mx: 'auto', mt: 4 }}>
      <CardContent>
        <Typography variant="h5" component="h1" gutterBottom>
          API Key Setup
        </Typography>
        
        <Stepper activeStep={activeStep} orientation="vertical">
          {steps.map((step, index) => (
            <Step key={step.label}>
              <StepLabel>
                <Typography variant="h6">{step.label}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {step.description}
                </Typography>
              </StepLabel>
              <StepContent>
                {renderStepContent(index)}
              </StepContent>
            </Step>
          ))}
        </Stepper>
      </CardContent>
    </Card>
  );
};

export default ApiKeyOnboarding;