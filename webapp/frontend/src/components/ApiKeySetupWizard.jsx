import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Stepper,
  Step,
  StepLabel,
  Box,
  Typography,
  Card,
  CardContent,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  Link,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Checkbox,
  Divider,
  CircularProgress,
  Chip,
  Switch,
  FormControlLabel,
  Grid
} from '@mui/material';
import {
  AccountBalance,
  Security,
  CheckCircle,
  Warning,
  Info,
  Launch,
  Key,
  Timeline,
  TrendingUp,
  Speed,
  Shield
} from '@mui/icons-material';

const ApiKeySetupWizard = ({ 
  open, 
  onClose, 
  onComplete,
  initialProvider = null 
}) => {
  const [activeStep, setActiveStep] = useState(0);
  const [formData, setFormData] = useState({
    provider: initialProvider || '',
    apiKey: '',
    apiSecret: '',
    isSandbox: true,
    description: '',
    agreedToTerms: false,
    understoodRisks: false
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState({});

  const steps = [
    'Choose Provider',
    'Security Information',
    'API Configuration',
    'Verification'
  ];

  const providers = [
    {
      id: 'alpaca',
      name: 'Alpaca Markets',
      description: 'Commission-free trading with comprehensive API access',
      features: ['Paper Trading', 'Live Trading', 'Real-time Data', 'Portfolio Import'],
      difficulty: 'Easy',
      setupTime: '5 minutes',
      icon: <AccountBalance />,
      color: '#FFD700',
      docsUrl: 'https://alpaca.markets/docs/api-documentation/',
      signupUrl: 'https://alpaca.markets/',
      recommended: true
    },
    {
      id: 'td_ameritrade',
      name: 'TD Ameritrade',
      description: 'Professional trading platform (Migrating to Schwab)',
      features: ['Advanced Orders', 'Options Trading', 'Real-time Data', 'Research'],
      difficulty: 'Medium',
      setupTime: '10 minutes',
      icon: <TrendingUp />,
      color: '#00C851',
      docsUrl: 'https://developer.tdameritrade.com/',
      signupUrl: 'https://www.tdameritrade.com/',
      recommended: false
    }
  ];

  const validateStep = (step) => {
    const newErrors = {};
    
    switch (step) {
      case 0:
        if (!formData.provider) {
          newErrors.provider = 'Please select a provider';
        }
        break;
      case 1:
        if (!formData.agreedToTerms) {
          newErrors.agreedToTerms = 'You must agree to the terms';
        }
        if (!formData.understoodRisks) {
          newErrors.understoodRisks = 'Please confirm you understand the risks';
        }
        break;
      case 2:
        if (!formData.apiKey) {
          newErrors.apiKey = 'API Key is required';
        }
        if (formData.apiKey && formData.apiKey.length < 10) {
          newErrors.apiKey = 'API Key appears to be too short';
        }
        break;
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleNext = () => {
    if (validateStep(activeStep)) {
      setActiveStep((prevStep) => prevStep + 1);
    }
  };

  const handleBack = () => {
    setActiveStep((prevStep) => prevStep - 1);
  };

  const handleSubmit = async () => {
    if (!validateStep(activeStep)) return;
    
    setIsSubmitting(true);
    try {
      // Call the API to create the API key
      await onComplete(formData);
      onClose();
    } catch (error) {
      setErrors({ submit: error.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const getSelectedProvider = () => {
    return providers.find(p => p.id === formData.provider);
  };

  const renderStepContent = (step) => {
    switch (step) {
      case 0:
        return (
          <div>
            <div  variant="h6" gutterBottom>
              Choose Your Broker
            </div>
            <div  color="text.secondary" sx={{ mb: 3 }}>
              Select your broker to connect your trading account and access live market data.
            </div>
            
            <div className="grid" container spacing={2}>
              {providers.map((provider) => (
                <div className="grid" item xs={12} key={provider.id}>
                  <div className="bg-white shadow-md rounded-lg"
                    sx={{
                      cursor: 'pointer',
                      border: formData.provider === provider.id ? 2 : 1,
                      borderColor: formData.provider === provider.id ? 'primary.main' : 'divider',
                      position: 'relative',
                      '&:hover': {
                        boxShadow: 2
                      }
                    }}
                    onClick={() => setFormData({ ...formData, provider: provider.id })}
                  >
                    {provider.recommended && (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                        label="Recommended"
                        color="primary"
                        size="small"
                        sx={{
                          position: 'absolute',
                          top: 8,
                          right: 8,
                          zIndex: 1
                        }}
                      />
                    )}
                    
                    <div className="bg-white shadow-md rounded-lg"Content>
                      <div  sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
                        <div  sx={{ color: provider.color, mt: 0.5 }}>
                          {provider.icon}
                        </div>
                        
                        <div  sx={{ flex: 1 }}>
                          <div  variant="h6" gutterBottom>
                            {provider.name}
                          </div>
                          
                          <div  color="text.secondary" sx={{ mb: 2 }}>
                            {provider.description}
                          </div>
                          
                          <div  sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
                            {provider.features.map((feature) => (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                key={feature} 
                                label={feature} 
                                size="small" 
                                variant="outlined" 
                              />
                            ))}
                          </div>
                          
                          <div  sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={`Setup: ${provider.setupTime}`} 
                              size="small" 
                              color="info" 
                            />
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                              label={provider.difficulty} 
                              size="small" 
                              color={provider.difficulty === 'Easy' ? 'success' : 'warning'} 
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            
            {errors.provider && (
              <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mt: 2 }}>
                {errors.provider}
              </div>
            )}
          </div>
        );

      case 1:
        const selectedProvider = getSelectedProvider();
        return (
          <div>
            <div  variant="h6" gutterBottom>
              Security & Risk Information
            </div>
            
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 3 }}>
              <div  variant="body2">
                Your API keys are encrypted using AES-256-GCM encryption before storage. 
                We never store your credentials in plain text.
              </div>
            </div>

            <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                  <Shield color="primary" />
                  <div  variant="subtitle1" fontWeight="bold">
                    How Your Data is Protected
                  </div>
                </div>
                
                <List dense>
                  <ListItem>
                    <ListItemIcon>
                      <CheckCircle color="success" />
                    </ListItemIcon>
                    <ListItemText primary="End-to-end encryption with user-specific keys" />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <CheckCircle color="success" />
                    </ListItemIcon>
                    <ListItemText primary="No plain text storage of API credentials" />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <CheckCircle color="success" />
                    </ListItemIcon>
                    <ListItemText primary="Isolated user data - no cross-user access" />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <CheckCircle color="success" />
                    </ListItemIcon>
                    <ListItemText primary="API keys only decrypted for authorized requests" />
                  </ListItem>
                </List>
              </div>
            </div>

            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                  <Warning color="warning" />
                  <div  variant="subtitle1" fontWeight="bold">
                    Important Considerations
                  </div>
                </div>
                
                <div  variant="body2" sx={{ mb: 2 }}>
                  Please read and understand the following before proceeding:
                </div>
                
                <List dense>
                  <ListItem>
                    <ListItemText 
                      primary="Start with paper trading to test safely"
                      secondary="We recommend using sandbox/paper trading initially to verify everything works correctly."
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText 
                      primary="API keys grant access to your trading account"
                      secondary="Only use read-only keys initially. Trading permissions can be added later."
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText 
                      primary="You can revoke access at any time"
                      secondary="API keys can be disabled or deleted from your broker account or from our settings."
                    />
                  </ListItem>
                </List>
              </div>
            </div>

            <div  sx={{ mt: 3 }}>
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="form-checkbox h-4 w-4 text-blue-600"
                    checked={formData.agreedToTerms}
                    onChange={(e) => setFormData({ ...formData, agreedToTerms: e.target.checked })}
                  />
                }
                label={
                  <div  variant="body2">
                    I agree to the{' '}
                    <Link href="#" onClick={(e) => e.preventDefault()}>
                      Terms of Service
                    </Link>
                    {' '}and{' '}
                    <Link href="#" onClick={(e) => e.preventDefault()}>
                      Privacy Policy
                    </Link>
                  </div>
                }
              />
              
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="form-checkbox h-4 w-4 text-blue-600"
                    checked={formData.understoodRisks}
                    onChange={(e) => setFormData({ ...formData, understoodRisks: e.target.checked })}
                  />
                }
                label={
                  <div  variant="body2">
                    I understand the security implications and risks of API key integration
                  </div>
                }
              />
            </div>

            {(errors.agreedToTerms || errors.understoodRisks) && (
              <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mt: 2 }}>
                Please review and accept all terms before proceeding.
              </div>
            )}
          </div>
        );

      case 2:
        const provider = getSelectedProvider();
        return (
          <div>
            <div  variant="h6" gutterBottom>
              Configure API Access
            </div>
            
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 3 }}>
              <div  variant="body2">
                You'll need to create API keys in your {provider?.name} account first.{' '}
                <Link 
                  href={provider?.docsUrl} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}
                >
                  View Setup Guide <Launch fontSize="small" />
                </Link>
              </div>
            </div>

            <div  sx={{ mb: 3 }}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                label="API Key"
                value={formData.apiKey}
                onChange={(e) => setFormData({ ...formData, apiKey: e.target.value })}
                placeholder="Enter your API key"
                type="password"
                error={!!errors.apiKey}
                helperText={errors.apiKey || 'Your API key will be encrypted before storage'}
                sx={{ mb: 2 }}
              />
              
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                label="API Secret (if required)"
                value={formData.apiSecret}
                onChange={(e) => setFormData({ ...formData, apiSecret: e.target.value })}
                placeholder="Enter your API secret (optional)"
                type="password"
                helperText="Some providers require both API key and secret"
                sx={{ mb: 2 }}
              />
              
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                label="Description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="e.g., Main trading account"
                helperText="Optional description to help you identify this API key"
                sx={{ mb: 2 }}
              />
              
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="toggle"
                    checked={formData.isSandbox}
                    onChange={(e) => setFormData({ ...formData, isSandbox: e.target.checked })}
                  />
                }
                label="Paper Trading Environment"
              />
              <div  variant="caption" color="text.secondary" display="block">
                Start with paper trading to test safely. You can switch to live trading later.
              </div>
            </div>
          </div>
        );

      case 3:
        return (
          <div>
            <div  variant="h6" gutterBottom>
              Review & Confirm
            </div>
            
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="subtitle1" gutterBottom>
                  Configuration Summary
                </div>
                
                <List>
                  <ListItem>
                    <ListItemText 
                      primary="Provider" 
                      secondary={getSelectedProvider()?.name} 
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText 
                      primary="Environment" 
                      secondary={formData.isSandbox ? 'Paper Trading (Safe)' : 'Live Trading'}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemText 
                      primary="API Key" 
                      secondary={`${formData.apiKey.substring(0, 8)}...${formData.apiKey.slice(-4)}`}
                    />
                  </ListItem>
                  {formData.description && (
                    <ListItem>
                      <ListItemText 
                        primary="Description" 
                        secondary={formData.description}
                      />
                    </ListItem>
                  )}
                </List>
              </div>
            </div>

            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="success" sx={{ mt: 2 }}>
              <div  variant="body2">
                Ready to connect! Your API keys will be securely encrypted and stored.
              </div>
            </div>

            {errors.submit && (
              <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mt: 2 }}>
                {errors.submit}
              </div>
            )}
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
      open={open} 
      onClose={onClose} 
      maxWidth="md" 
      fullWidth
      PaperProps={{
        sx: { minHeight: 600 }
      }}
    >
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>
        <div  variant="h5">Set Up API Keys</div>
        <div  color="text.secondary">
          Connect your broker account for live trading data
        </div>
      </h2>

      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
        <div  sx={{ mb: 3 }}>
          <Stepper activeStep={activeStep} alternativeLabel>
            {steps.map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>
        </div>

        {renderStepContent(activeStep)}
      </div>

      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions sx={{ p: 3, pt: 0 }}>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={onClose}>
          Cancel
        </button>
        
        <div  sx={{ flex: 1 }} />
        
        {activeStep > 0 && (
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleBack}>
            Back
          </button>
        )}
        
        {activeStep < steps.length - 1 ? (
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
            variant="contained" 
            onClick={handleNext}
            disabled={activeStep === 0 && !formData.provider}
          >
            Next
          </button>
        ) : (
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
            variant="contained" 
            onClick={handleSubmit}
            disabled={isSubmitting}
            startIcon={isSubmitting ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} /> : null}
          >
            {isSubmitting ? 'Setting Up...' : 'Complete Setup'}
          </button>
        )}
      </div>
    </div>
  );
};

export default ApiKeySetupWizard;