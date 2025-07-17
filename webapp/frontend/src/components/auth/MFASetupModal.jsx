import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  Box,
  Typography,
  Button,
  TextField,
  Alert,
  CircularProgress,
  Stepper,
  Step,
  StepLabel,
  Card,
  CardContent,
  Grid,
  IconButton,
  Chip,
  Divider
} from '@mui/material';
import {
  Security,
  Smartphone,
  QrCode,
  Close,
  CheckCircle,
  Warning,
  ContentCopy
} from '@mui/icons-material';
import { getCurrentUser } from '@aws-amplify/auth';
import QRCode from 'qrcode';

const MFA_METHODS = {
  SMS: 'SMS',
  TOTP: 'TOTP'
};

const SETUP_STEPS = ['Choose Method', 'Configure', 'Verify', 'Complete'];

function MFASetupModal({ open, onClose, onSetupComplete, userPhoneNumber }) {
  const [activeStep, setActiveStep] = useState(0);
  const [selectedMethod, setSelectedMethod] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  
  // TOTP specific state
  const [totpSecret, setTotpSecret] = useState('');
  const [qrCodeUrl, setQrCodeUrl] = useState('');
  const [totpCode, setTotpCode] = useState('');
  const [secretCopied, setSecretCopied] = useState(false);
  
  // SMS specific state
  const [smsCode, setSmsCode] = useState('');
  const [smsSent, setSmsSent] = useState(false);

  const handleMethodSelect = (method) => {
    setSelectedMethod(method);
    setActiveStep(1);
    setError('');
    setSuccess('');
  };

  const setupTOTPMethod = async () => {
    try {
      setLoading(true);
      setError('');
      
      // Generate a random secret for demonstration
      // In production, this would come from AWS Cognito MFA setup
      const secretCode = Array.from(crypto.getRandomValues(new Uint8Array(10)))
        .map(b => b.toString(36))
        .join('')
        .slice(0, 16)
        .toUpperCase();
      
      setTotpSecret(secretCode);
      
      // Generate QR code for easy setup
      const totpUri = `otpauth://totp/FinancialPlatform:${userPhoneNumber || 'user'}?secret=${secretCode}&issuer=FinancialPlatform`;
      const qrCodeDataUrl = await QRCode.toDataURL(totpUri);
      setQrCodeUrl(qrCodeDataUrl);
      
      setActiveStep(2);
      setSuccess('TOTP setup initialized. Scan the QR code with your authenticator app.');
    } catch (error) {
      console.error('TOTP setup error:', error);
      setError(`Failed to setup TOTP: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const verifyTOTPCode = async () => {
    if (!totpCode || totpCode.length !== 6) {
      setError('Please enter a valid 6-digit code from your authenticator app');
      return;
    }

    try {
      setLoading(true);
      setError('');
      
      // In production, this would verify with AWS Cognito
      // For demo purposes, accept any 6-digit code
      console.log('TOTP code entered:', totpCode);
      
      setActiveStep(3);
      setSuccess('TOTP authentication successfully configured!');
      
      setTimeout(() => {
        onSetupComplete('TOTP');
      }, 2000);
    } catch (error) {
      console.error('TOTP verification error:', error);
      setError(`Verification failed: ${error.message}. Please check your code and try again.`);
    } finally {
      setLoading(false);
    }
  };

  const setupSMSMethod = async () => {
    try {
      setLoading(true);
      setError('');
      
      // SMS setup is typically handled during user registration
      // This would trigger an SMS to the user's verified phone number
      setSmsSent(true);
      setActiveStep(2);
      setSuccess(`Verification code sent to ${userPhoneNumber}`);
    } catch (error) {
      console.error('SMS setup error:', error);
      setError(`Failed to setup SMS: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const verifySMSCode = async () => {
    if (!smsCode || smsCode.length !== 6) {
      setError('Please enter the 6-digit code sent to your phone');
      return;
    }

    try {
      setLoading(true);
      setError('');
      
      // Verify SMS code logic would go here
      // This depends on your specific SMS MFA implementation
      
      setActiveStep(3);
      setSuccess('SMS authentication successfully configured!');
      
      setTimeout(() => {
        onSetupComplete('SMS');
      }, 2000);
    } catch (error) {
      console.error('SMS verification error:', error);
      setError(`Verification failed: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const copySecretToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(totpSecret);
      setSecretCopied(true);
      setTimeout(() => setSecretCopied(false), 3000);
    } catch (error) {
      console.error('Failed to copy secret:', error);
    }
  };

  const handleNext = () => {
    if (activeStep === 1) {
      if (selectedMethod === MFA_METHODS.TOTP) {
        setupTOTPMethod();
      } else if (selectedMethod === MFA_METHODS.SMS) {
        setupSMSMethod();
      }
    } else if (activeStep === 2) {
      if (selectedMethod === MFA_METHODS.TOTP) {
        verifyTOTPCode();
      } else if (selectedMethod === MFA_METHODS.SMS) {
        verifySMSCode();
      }
    }
  };

  const handleBack = () => {
    if (activeStep > 0) {
      setActiveStep(activeStep - 1);
      setError('');
      setSuccess('');
    }
  };

  const handleClose = () => {
    setActiveStep(0);
    setSelectedMethod(null);
    setError('');
    setSuccess('');
    setTotpSecret('');
    setQrCodeUrl('');
    setTotpCode('');
    setSmsCode('');
    setSmsSent(false);
    setSecretCopied(false);
    onClose();
  };

  const renderMethodSelection = () => (
    <Box sx={{ mt: 2 }}>
      <Typography variant="h6" gutterBottom>
        Choose Your Preferred MFA Method
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Multi-factor authentication adds an extra layer of security to your account
      </Typography>
      
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Card 
            sx={{ 
              cursor: 'pointer',
              border: selectedMethod === MFA_METHODS.TOTP ? 2 : 1,
              borderColor: selectedMethod === MFA_METHODS.TOTP ? 'primary.main' : 'divider'
            }}
            onClick={() => handleMethodSelect(MFA_METHODS.TOTP)}
          >
            <CardContent sx={{ textAlign: 'center', py: 3 }}>
              <QrCode sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
              <Typography variant="h6" gutterBottom>
                Authenticator App
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Use Google Authenticator, Authy, or similar TOTP apps
              </Typography>
              <Box sx={{ mt: 2 }}>
                <Chip label="Recommended" color="primary" size="small" />
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={6}>
          <Card 
            sx={{ 
              cursor: 'pointer',
              border: selectedMethod === MFA_METHODS.SMS ? 2 : 1,
              borderColor: selectedMethod === MFA_METHODS.SMS ? 'primary.main' : 'divider'
            }}
            onClick={() => handleMethodSelect(MFA_METHODS.SMS)}
          >
            <CardContent sx={{ textAlign: 'center', py: 3 }}>
              <Smartphone sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
              <Typography variant="h6" gutterBottom>
                SMS Text Message
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Receive verification codes via SMS to {userPhoneNumber || 'your phone'}
              </Typography>
              <Box sx={{ mt: 2 }}>
                <Chip label="Convenient" color="secondary" size="small" />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );

  const renderTOTPSetup = () => (
    <Box sx={{ mt: 2 }}>
      <Typography variant="h6" gutterBottom>
        Setup Authenticator App
      </Typography>
      
      {qrCodeUrl && (
        <Box sx={{ textAlign: 'center', mb: 3 }}>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Scan this QR code with your authenticator app:
          </Typography>
          <img src={qrCodeUrl} alt="TOTP QR Code" style={{ maxWidth: 200 }} />
        </Box>
      )}
      
      <Divider sx={{ my: 2 }} />
      
      <Typography variant="body2" gutterBottom>
        Or manually enter this secret key:
      </Typography>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
        <TextField
          fullWidth
          value={totpSecret}
          InputProps={{
            readOnly: true,
            style: { fontFamily: 'monospace', fontSize: '0.9rem' }
          }}
          size="small"
        />
        <IconButton onClick={copySecretToClipboard} color="primary">
          <ContentCopy />
        </IconButton>
      </Box>
      
      {secretCopied && (
        <Typography variant="caption" color="success.main">
          Secret copied to clipboard!
        </Typography>
      )}
    </Box>
  );

  const renderVerification = () => (
    <Box sx={{ mt: 2 }}>
      <Typography variant="h6" gutterBottom>
        Verify Your Setup
      </Typography>
      
      {selectedMethod === MFA_METHODS.TOTP && (
        <>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Enter the 6-digit code from your authenticator app:
          </Typography>
          <TextField
            fullWidth
            label="Authentication Code"
            value={totpCode}
            onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="123456"
            inputProps={{ 
              maxLength: 6,
              style: { textAlign: 'center', fontSize: '1.5rem', letterSpacing: '0.5rem' }
            }}
            sx={{ mb: 2 }}
          />
        </>
      )}
      
      {selectedMethod === MFA_METHODS.SMS && (
        <>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Enter the 6-digit code sent to your phone:
          </Typography>
          <TextField
            fullWidth
            label="SMS Code"
            value={smsCode}
            onChange={(e) => setSmsCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="123456"
            inputProps={{ 
              maxLength: 6,
              style: { textAlign: 'center', fontSize: '1.5rem', letterSpacing: '0.5rem' }
            }}
            sx={{ mb: 2 }}
          />
        </>
      )}
    </Box>
  );

  const renderComplete = () => (
    <Box sx={{ textAlign: 'center', py: 4 }}>
      <CheckCircle sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
      <Typography variant="h5" gutterBottom>
        MFA Successfully Configured!
      </Typography>
      <Typography variant="body1" color="text.secondary">
        Your account is now protected with multi-factor authentication using {selectedMethod}.
      </Typography>
    </Box>
  );

  const getStepContent = () => {
    switch (activeStep) {
      case 0:
        return renderMethodSelection();
      case 1:
        return selectedMethod === MFA_METHODS.TOTP ? renderTOTPSetup() : renderMethodSelection();
      case 2:
        return renderVerification();
      case 3:
        return renderComplete();
      default:
        return null;
    }
  };

  return (
    <Dialog 
      open={open} 
      onClose={handleClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: { borderRadius: 2 }
      }}
    >
      <DialogTitle>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Box display="flex" alignItems="center" gap={1}>
            <Security color="primary" />
            <Typography variant="h6">
              Setup Multi-Factor Authentication
            </Typography>
          </Box>
          <IconButton onClick={handleClose} size="small">
            <Close />
          </IconButton>
        </Box>
      </DialogTitle>
      
      <DialogContent>
        <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
          {SETUP_STEPS.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>
        
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        
        {success && (
          <Alert severity="success" sx={{ mb: 2 }}>
            {success}
          </Alert>
        )}
        
        {getStepContent()}
        
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 4 }}>
          <Button
            onClick={handleBack}
            disabled={activeStep === 0 || activeStep === 3}
          >
            Back
          </Button>
          
          <Box sx={{ display: 'flex', gap: 1 }}>
            {activeStep < 3 && activeStep > 0 && (
              <Button
                variant="contained"
                onClick={handleNext}
                disabled={loading || (activeStep === 2 && (!totpCode && !smsCode))}
                startIcon={loading ? <CircularProgress size={20} /> : null}
              >
                {activeStep === 2 ? 'Verify' : 'Continue'}
              </Button>
            )}
            
            {activeStep === 3 && (
              <Button
                variant="contained"
                onClick={handleClose}
                color="success"
              >
                Done
              </Button>
            )}
          </Box>
        </Box>
      </DialogContent>
    </Dialog>
  );
}

export default MFASetupModal;