/**
 * API Key Onboarding Component
 * Guided process for setting up API keys with validation and testing
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Button,
  Typography,
  TextField,
  Alert,
  Card,
  CardContent,
  FormControlLabel,
  Switch,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Chip,
  Link,
  InputAdornment,
  IconButton
} from '@mui/material';
import {
  ExpandMore,
  CheckCircle,
  Error,
  Info,
  Visibility,
  VisibilityOff,
  Launch,
  Security,
  AccountBalance,
  TrendingUp,
  Warning
} from '@mui/icons-material';
import settingsService from '../services/settingsService';

const ApiKeyOnboarding = ({ onComplete, onSkip }) => {
  const [activeStep, setActiveStep] = useState(0);
  const [apiKeys, setApiKeys] = useState({
    alpaca: { keyId: '', secretKey: '', paperTrading: true },
    polygon: { apiKey: '' },
    finnhub: { apiKey: '' }
  });
  const [showPasswords, setShowPasswords] = useState({});
  const [validationResults, setValidationResults] = useState({});
  const [isValidating, setIsValidating] = useState(false);
  const [errors, setErrors] = useState({});
  const [savedKeys, setSavedKeys] = useState({});

  const steps = [
    {
      label: 'Welcome & Overview',
      description: 'Learn about API keys and their importance'
    },
    {
      label: 'Alpaca Trading API',
      description: 'Set up your trading account connection'
    },
    {
      label: 'Market Data APIs',
      description: 'Configure real-time market data sources'
    },
    {
      label: 'Test & Validate',
      description: 'Verify your API connections'
    },
    {
      label: 'Complete Setup',
      description: 'Finish onboarding and start trading'
    }
  ];

  const togglePasswordVisibility = (field) => {
    setShowPasswords(prev => ({
      ...prev,
      [field]: !prev[field]
    }));
  };

  const updateApiKey = (provider, field, value) => {
    setApiKeys(prev => ({
      ...prev,
      [provider]: {
        ...prev[provider],
        [field]: value
      }
    }));
    
    // Clear errors when user starts typing
    if (errors[`${provider}.${field}`]) {
      setErrors(prev => ({
        ...prev,
        [`${provider}.${field}`]: null
      }));
    }
  };

  const validateApiKeyFormat = (provider, apiKey) => {
    const formats = {
      alpaca: {
        keyId: /^[A-Z0-9]{20}$/,
        secretKey: /^[A-Za-z0-9/+]{40}$/
      },
      polygon: {
        apiKey: /^[A-Za-z0-9_]{32}$/
      },
      finnhub: {
        apiKey: /^[A-Za-z0-9]{20}$/
      }
    };

    if (!formats[provider]) return true;

    for (const [field, pattern] of Object.entries(formats[provider])) {
      if (apiKey[field] && !pattern.test(apiKey[field])) {
        return false;
      }
    }
    return true;
  };

  const saveApiKey = async (provider) => {
    try {
      console.log('💾 Saving API key for provider:', provider);
      
      const apiKey = apiKeys[provider];
      
      // Validate format
      if (!validateApiKeyFormat(provider, apiKey)) {
        setErrors(prev => ({
          ...prev,
          [provider]: 'Invalid API key format'
        }));
        return false;
      }

      const keyData = {
        provider,
        apiKey: apiKey.keyId || apiKey.apiKey,
        apiSecret: apiKey.secretKey || 'not_required',
        isSandbox: apiKey.paperTrading !== undefined ? apiKey.paperTrading : false,
        description: `${provider} API key (onboarding)`
      };

      const result = await settingsService.addApiKey(keyData);
      
      setSavedKeys(prev => ({
        ...prev,
        [provider]: result
      }));

      setErrors(prev => ({
        ...prev,
        [provider]: null
      }));

      return true;
    } catch (error) {
      console.error('❌ Error saving API key:', error);
      setErrors(prev => ({
        ...prev,
        [provider]: error.message || 'Failed to save API key'
      }));
      return false;
    }
  };

  const validateConnection = async (provider) => {
    try {
      setIsValidating(true);
      console.log('🧪 Validating connection for:', provider);

      const savedKey = savedKeys[provider];
      if (!savedKey) {
        throw new Error('Please save the API key first');
      }

      const result = await settingsService.validateApiKey(savedKey.id, provider);
      
      setValidationResults(prev => ({
        ...prev,
        [provider]: result
      }));

      return result.valid;
    } catch (error) {
      console.error('❌ Validation error:', error);
      setValidationResults(prev => ({
        ...prev,
        [provider]: { valid: false, message: error.message }
      }));
      return false;
    } finally {
      setIsValidating(false);
    }
  };

  const handleNext = async () => {
    // Validate current step before proceeding
    if (activeStep === 1) { // Alpaca step
      const alpacaKey = apiKeys.alpaca;
      if (alpacaKey.keyId && alpacaKey.secretKey) {
        const saved = await saveApiKey('alpaca');
        if (!saved) return;
      }
    } else if (activeStep === 2) { // Market data step
      if (apiKeys.polygon.apiKey) {
        await saveApiKey('polygon');
      }
      if (apiKeys.finnhub.apiKey) {
        await saveApiKey('finnhub');
      }
    } else if (activeStep === 3) { // Validation step
      // Validate all configured APIs
      const providers = Object.keys(savedKeys);
      if (providers.length === 0) {
        setErrors({ validation: 'Please configure at least one API key before proceeding' });
        return;
      }
    }

    setActiveStep(prev => prev + 1);
  };

  const handleBack = () => {
    setActiveStep(prev => prev - 1);
  };

  const handleComplete = () => {
    if (onComplete) {
      onComplete(savedKeys);
    }
  };

  const handleSkip = () => {
    if (onSkip) {
      onSkip();
    }
  };

  const renderWelcomeStep = () => (
    <Box>
      <Typography variant="h6" gutterBottom>
        Welcome to Financial Dashboard Setup
      </Typography>
      <Typography paragraph>
        To provide you with real-time trading capabilities and live market data, 
        we need to connect to your broker and data provider APIs.
      </Typography>

      <Alert severity="info" sx={{ mb: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          Why API Keys Are Required:
        </Typography>
        <List dense>
          <ListItem>
            <ListItemIcon><TrendingUp fontSize="small" /></ListItemIcon>
            <ListItemText primary="Real-time portfolio data from your broker" />
          </ListItem>
          <ListItem>
            <ListItemIcon><AccountBalance fontSize="small" /></ListItemIcon>
            <ListItemText primary="Execute trades and manage positions" />
          </ListItem>
          <ListItem>
            <ListItemIcon><Security fontSize="small" /></ListItemIcon>
            <ListItemText primary="Secure, encrypted storage of your credentials" />
          </ListItem>
        </List>
      </Alert>

      <Accordion>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="subtitle2">Security & Privacy</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2">
            Your API keys are encrypted using AES-256-GCM encryption with individual user salts.
            We never store your keys in plain text, and they're only used to communicate with
            your chosen broker APIs. You maintain full control and can revoke access at any time.
          </Typography>
        </AccordionDetails>
      </Accordion>
    </Box>
  );

  const renderAlpacaStep = () => (
    <Box>
      <Typography variant="h6" gutterBottom>
        Alpaca Trading API Setup
      </Typography>
      <Typography paragraph>
        Alpaca provides commission-free trading and real-time portfolio management.
        You'll need to create an account and generate API keys.
      </Typography>

      <Alert severity="warning" sx={{ mb: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          Paper Trading Recommended
        </Typography>
        <Typography variant="body2">
          We recommend starting with paper trading to test the platform without real money.
        </Typography>
      </Alert>

      <Box sx={{ mb: 2 }}>
        <Link 
          href="https://alpaca.markets/signup" 
          target="_blank" 
          rel="noopener noreferrer"
          sx={{ display: 'flex', alignItems: 'center', mb: 1 }}
        >
          Create Alpaca Account <Launch sx={{ ml: 1, fontSize: 16 }} />
        </Link>
        <Link 
          href="https://app.alpaca.markets/paper/dashboard/overview" 
          target="_blank" 
          rel="noopener noreferrer"
          sx={{ display: 'flex', alignItems: 'center' }}
        >
          Get API Keys <Launch sx={{ ml: 1, fontSize: 16 }} />
        </Link>
      </Box>

      <TextField
        fullWidth
        label="API Key ID"
        value={apiKeys.alpaca.keyId}
        onChange={(e) => updateApiKey('alpaca', 'keyId', e.target.value)}
        error={!!errors['alpaca.keyId']}
        helperText={errors['alpaca.keyId'] || 'Format: 20 characters, uppercase letters and numbers'}
        type={showPasswords.alpacaKeyId ? 'text' : 'password'}
        InputProps={{
          endAdornment: (
            <InputAdornment position="end">
              <IconButton onClick={() => togglePasswordVisibility('alpacaKeyId')}>
                {showPasswords.alpacaKeyId ? <VisibilityOff /> : <Visibility />}
              </IconButton>
            </InputAdornment>
          )
        }}
        sx={{ mb: 2 }}
      />

      <TextField
        fullWidth
        label="Secret Key"
        value={apiKeys.alpaca.secretKey}
        onChange={(e) => updateApiKey('alpaca', 'secretKey', e.target.value)}
        error={!!errors['alpaca.secretKey']}
        helperText={errors['alpaca.secretKey'] || 'Format: 40 characters, base64 encoded'}
        type={showPasswords.alpacaSecret ? 'text' : 'password'}
        InputProps={{
          endAdornment: (
            <InputAdornment position="end">
              <IconButton onClick={() => togglePasswordVisibility('alpacaSecret')}>
                {showPasswords.alpacaSecret ? <VisibilityOff /> : <Visibility />}
              </IconButton>
            </InputAdornment>
          )
        }}
        sx={{ mb: 2 }}
      />

      <FormControlLabel
        control={
          <Switch
            checked={apiKeys.alpaca.paperTrading}
            onChange={(e) => updateApiKey('alpaca', 'paperTrading', e.target.checked)}
          />
        }
        label="Paper Trading (Recommended)"
        sx={{ mb: 2 }}
      />

      {errors.alpaca && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errors.alpaca}
        </Alert>
      )}

      {savedKeys.alpaca && (
        <Alert severity="success" sx={{ mb: 2 }}>
          <CheckCircle sx={{ mr: 1 }} />
          Alpaca API key saved successfully
        </Alert>
      )}
    </Box>
  );

  const renderMarketDataStep = () => (
    <Box>
      <Typography variant="h6" gutterBottom>
        Market Data APIs (Optional)
      </Typography>
      <Typography paragraph>
        Configure additional data sources for enhanced market analysis.
        These are optional but provide richer data and analysis capabilities.
      </Typography>

      <Accordion sx={{ mb: 2 }}>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="subtitle2">Polygon.io - Premium Market Data</Typography>
          <Chip 
            label="Optional" 
            size="small" 
            color="default" 
            sx={{ ml: 2 }} 
          />
        </AccordionSummary>
        <AccordionDetails>
          <Box>
            <Typography variant="body2" paragraph>
              Polygon provides real-time and historical market data with high accuracy.
            </Typography>
            <Link 
              href="https://polygon.io/dashboard/signup" 
              target="_blank" 
              rel="noopener noreferrer"
              sx={{ display: 'flex', alignItems: 'center', mb: 2 }}
            >
              Get Polygon API Key <Launch sx={{ ml: 1, fontSize: 16 }} />
            </Link>
            <TextField
              fullWidth
              label="Polygon API Key"
              value={apiKeys.polygon.apiKey}
              onChange={(e) => updateApiKey('polygon', 'apiKey', e.target.value)}
              error={!!errors['polygon.apiKey']}
              helperText={errors['polygon.apiKey'] || 'Format: 32 characters'}
              type={showPasswords.polygonKey ? 'text' : 'password'}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => togglePasswordVisibility('polygonKey')}>
                      {showPasswords.polygonKey ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                )
              }}
            />
          </Box>
        </AccordionDetails>
      </Accordion>

      <Accordion sx={{ mb: 2 }}>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="subtitle2">Finnhub - Financial Data</Typography>
          <Chip 
            label="Optional" 
            size="small" 
            color="default" 
            sx={{ ml: 2 }} 
          />
        </AccordionSummary>
        <AccordionDetails>
          <Box>
            <Typography variant="body2" paragraph>
              Finnhub provides company financials, news, and analyst recommendations.
            </Typography>
            <Link 
              href="https://finnhub.io/register" 
              target="_blank" 
              rel="noopener noreferrer"
              sx={{ display: 'flex', alignItems: 'center', mb: 2 }}
            >
              Get Finnhub API Key <Launch sx={{ ml: 1, fontSize: 16 }} />
            </Link>
            <TextField
              fullWidth
              label="Finnhub API Key"
              value={apiKeys.finnhub.apiKey}
              onChange={(e) => updateApiKey('finnhub', 'apiKey', e.target.value)}
              error={!!errors['finnhub.apiKey']}
              helperText={errors['finnhub.apiKey'] || 'Format: 20 characters'}
              type={showPasswords.finnhubKey ? 'text' : 'password'}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => togglePasswordVisibility('finnhubKey')}>
                      {showPasswords.finnhubKey ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                )
              }}
            />
          </Box>
        </AccordionDetails>
      </Accordion>

      {(errors.polygon || errors.finnhub) && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errors.polygon || errors.finnhub}
        </Alert>
      )}
    </Box>
  );

  const renderValidationStep = () => (
    <Box>
      <Typography variant="h6" gutterBottom>
        Test API Connections
      </Typography>
      <Typography paragraph>
        Let's validate your API keys by testing connections to your configured services.
      </Typography>

      {errors.validation && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errors.validation}
        </Alert>
      )}

      {Object.keys(savedKeys).map(provider => (
        <Card key={provider} sx={{ mb: 2 }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6" sx={{ textTransform: 'capitalize', flexGrow: 1 }}>
                {provider}
              </Typography>
              <Button
                variant="outlined"
                onClick={() => validateConnection(provider)}
                disabled={isValidating}
                startIcon={isValidating ? <CircularProgress size={16} /> : null}
              >
                {isValidating ? 'Testing...' : 'Test Connection'}
              </Button>
            </Box>
            
            {validationResults[provider] && (
              <Alert 
                severity={validationResults[provider].valid ? 'success' : 'error'}
                icon={validationResults[provider].valid ? <CheckCircle /> : <Error />}
              >
                {validationResults[provider].message || 
                 (validationResults[provider].valid ? 'Connection successful' : 'Connection failed')}
              </Alert>
            )}
          </CardContent>
        </Card>
      ))}

      {Object.keys(savedKeys).length === 0 && (
        <Alert severity="warning">
          No API keys configured yet. Please go back and configure at least one API key.
        </Alert>
      )}
    </Box>
  );

  const renderCompleteStep = () => (
    <Box textAlign="center">
      <CheckCircle sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
      <Typography variant="h5" gutterBottom>
        Setup Complete!
      </Typography>
      <Typography paragraph>
        Your API keys have been securely configured and validated. 
        You can now start using the trading platform with real-time data.
      </Typography>

      <Alert severity="success" sx={{ mb: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          What's Next:
        </Typography>
        <List dense>
          <ListItem>
            <ListItemText primary="• View your live portfolio data" />
          </ListItem>
          <ListItem>
            <ListItemText primary="• Set up watchlists and alerts" />
          </ListItem>
          <ListItem>
            <ListItemText primary="• Explore trading strategies" />
          </ListItem>
          <ListItem>
            <ListItemText primary="• Manage risk and analytics" />
          </ListItem>
        </List>
      </Alert>

      <Typography variant="body2" color="text.secondary">
        You can always update your API keys later in the Settings page.
      </Typography>
    </Box>
  );

  const renderStepContent = (stepIndex) => {
    switch (stepIndex) {
      case 0:
        return renderWelcomeStep();
      case 1:
        return renderAlpacaStep();
      case 2:
        return renderMarketDataStep();
      case 3:
        return renderValidationStep();
      case 4:
        return renderCompleteStep();
      default:
        return null;
    }
  };

  return (
    <Box sx={{ maxWidth: 800, mx: 'auto', p: 3 }}>
      <Typography variant="h4" gutterBottom align="center">
        API Key Setup
      </Typography>
      <Typography variant="subtitle1" align="center" color="text.secondary" paragraph>
        Configure your trading and data connections
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
              
              <Box sx={{ mt: 3 }}>
                <Button
                  variant="contained"
                  onClick={index === steps.length - 1 ? handleComplete : handleNext}
                  sx={{ mr: 1 }}
                  disabled={index === 3 && Object.keys(savedKeys).length === 0}
                >
                  {index === steps.length - 1 ? 'Start Trading' : 'Continue'}
                </Button>
                
                {index > 0 && (
                  <Button onClick={handleBack} sx={{ mr: 1 }}>
                    Back
                  </Button>
                )}

                {index === 0 && (
                  <Button onClick={handleSkip} color="secondary">
                    Skip Setup
                  </Button>
                )}
              </Box>
            </StepContent>
          </Step>
        ))}
      </Stepper>
    </Box>
  );
};

export default ApiKeyOnboarding;