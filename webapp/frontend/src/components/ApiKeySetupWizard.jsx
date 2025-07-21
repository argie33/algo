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
          <Box>
            <Typography variant="h6" gutterBottom>
              Choose Your Broker
            </Typography>
            <Typography color="text.secondary" sx={{ mb: 3 }}>
              Select your broker to connect your trading account and access live market data.
            </Typography>
            
            <Grid container spacing={2}>
              {providers.map((provider) => (
                <Grid item xs={12} key={provider.id}>
                  <Card
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
                      <Chip
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
                    
                    <CardContent>
                      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
                        <Box sx={{ color: provider.color, mt: 0.5 }}>
                          {provider.icon}
                        </Box>
                        
                        <Box sx={{ flex: 1 }}>
                          <Typography variant="h6" gutterBottom>
                            {provider.name}
                          </Typography>
                          
                          <Typography color="text.secondary" sx={{ mb: 2 }}>
                            {provider.description}
                          </Typography>
                          
                          <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
                            {provider.features.map((feature) => (
                              <Chip 
                                key={feature} 
                                label={feature} 
                                size="small" 
                                variant="outlined" 
                              />
                            ))}
                          </Box>
                          
                          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                            <Chip 
                              label={`Setup: ${provider.setupTime}`} 
                              size="small" 
                              color="info" 
                            />
                            <Chip 
                              label={provider.difficulty} 
                              size="small" 
                              color={provider.difficulty === 'Easy' ? 'success' : 'warning'} 
                            />
                          </Box>
                        </Box>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
            
            {errors.provider && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {errors.provider}
              </Alert>
            )}
          </Box>
        );

      case 1: {
        const selectedProvider = getSelectedProvider();
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              Security & Risk Information
            </Typography>
            
            <Alert severity="info" sx={{ mb: 3 }}>
              <Typography variant="body2">
                Your API keys are encrypted using AES-256-GCM encryption before storage. 
                We never store your credentials in plain text.
              </Typography>
            </Alert>

            <Card sx={{ mb: 3 }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                  <Shield color="primary" />
                  <Typography variant="subtitle1" fontWeight="bold">
                    How Your Data is Protected
                  </Typography>
                </Box>
                
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
              </CardContent>
            </Card>

            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                  <Warning color="warning" />
                  <Typography variant="subtitle1" fontWeight="bold">
                    Important Considerations
                  </Typography>
                </Box>
                
                <Typography variant="body2" sx={{ mb: 2 }}>
                  Please read and understand the following before proceeding:
                </Typography>
                
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
              </CardContent>
            </Card>

            <Box sx={{ mt: 3 }}>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={formData.agreedToTerms}
                    onChange={(e) => setFormData({ ...formData, agreedToTerms: e.target.checked })}
                  />
                }
                label={
                  <Typography variant="body2">
                    I agree to the{' '}
                    <Link href="#" onClick={(e) => e.preventDefault()}>
                      Terms of Service
                    </Link>
                    {' '}and{' '}
                    <Link href="#" onClick={(e) => e.preventDefault()}>
                      Privacy Policy
                    </Link>
                  </Typography>
                }
              />
              
              <FormControlLabel
                control={
                  <Checkbox
                    checked={formData.understoodRisks}
                    onChange={(e) => setFormData({ ...formData, understoodRisks: e.target.checked })}
                  />
                }
                label={
                  <Typography variant="body2">
                    I understand the security implications and risks of API key integration
                  </Typography>
                }
              />
            </Box>

            {(errors.agreedToTerms || errors.understoodRisks) && (
              <Alert severity="error" sx={{ mt: 2 }}>
                Please review and accept all terms before proceeding.
              </Alert>
            )}
          </Box>
        );
      }

      case 2: {
        const provider = getSelectedProvider();
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              Configure API Access
            </Typography>
            
            <Alert severity="info" sx={{ mb: 3 }}>
              <Typography variant="body2">
                You&apos;ll need to create API keys in your {provider?.name} account first.{' '}
                <Link 
                  href={provider?.docsUrl} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}
                >
                  View Setup Guide <Launch fontSize="small" />
                </Link>
              </Typography>
            </Alert>

            <Box sx={{ mb: 3 }}>
              <TextField
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
              
              <TextField
                fullWidth
                label="API Secret (if required)"
                value={formData.apiSecret}
                onChange={(e) => setFormData({ ...formData, apiSecret: e.target.value })}
                placeholder="Enter your API secret (optional)"
                type="password"
                helperText="Some providers require both API key and secret"
                sx={{ mb: 2 }}
              />
              
              <TextField
                fullWidth
                label="Description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="e.g., Main trading account"
                helperText="Optional description to help you identify this API key"
                sx={{ mb: 2 }}
              />
              
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.isSandbox}
                    onChange={(e) => setFormData({ ...formData, isSandbox: e.target.checked })}
                  />
                }
                label="Paper Trading Environment"
              />
              <Typography variant="caption" color="text.secondary" display="block">
                Start with paper trading to test safely. You can switch to live trading later.
              </Typography>
            </Box>
          </Box>
        );
      }

      case 3:
        return (
          <Box>
            <Typography variant="h6" gutterBottom>
              Review & Confirm
            </Typography>
            
            <Card>
              <CardContent>
                <Typography variant="subtitle1" gutterBottom>
                  Configuration Summary
                </Typography>
                
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
              </CardContent>
            </Card>

            <Alert severity="success" sx={{ mt: 2 }}>
              <Typography variant="body2">
                Ready to connect! Your API keys will be securely encrypted and stored.
              </Typography>
            </Alert>

            {errors.submit && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {errors.submit}
              </Alert>
            )}
          </Box>
        );

      default:
        return null;
    }
  };

  return (
    <Dialog 
      open={open} 
      onClose={onClose} 
      maxWidth="md" 
      fullWidth
      PaperProps={{
        sx: { minHeight: 600 }
      }}
    >
      <DialogTitle>
        <Typography variant="h5">Set Up API Keys</Typography>
        <Typography color="text.secondary">
          Connect your broker account for live trading data
        </Typography>
      </DialogTitle>

      <DialogContent>
        <Box sx={{ mb: 3 }}>
          <Stepper activeStep={activeStep} alternativeLabel>
            {steps.map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>
        </Box>

        {renderStepContent(activeStep)}
      </DialogContent>

      <DialogActions sx={{ p: 3, pt: 0 }}>
        <Button onClick={onClose}>
          Cancel
        </Button>
        
        <Box sx={{ flex: 1 }} />
        
        {activeStep > 0 && (
          <Button onClick={handleBack}>
            Back
          </Button>
        )}
        
        {activeStep < steps.length - 1 ? (
          <Button 
            variant="contained" 
            onClick={handleNext}
            disabled={activeStep === 0 && !formData.provider}
          >
            Next
          </Button>
        ) : (
          <Button 
            variant="contained" 
            onClick={handleSubmit}
            disabled={isSubmitting}
            startIcon={isSubmitting ? <CircularProgress size={20} /> : null}
          >
            {isSubmitting ? 'Setting Up...' : 'Complete Setup'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default ApiKeySetupWizard;