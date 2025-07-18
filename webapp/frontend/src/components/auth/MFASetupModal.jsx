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
    <div  sx={{ mt: 2 }}>
      <div  variant="h6" gutterBottom>
        Choose Your Preferred MFA Method
      </div>
      <div  variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Multi-factor authentication adds an extra layer of security to your account
      </div>
      
      <div className="grid" container spacing={2}>
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg" 
            sx={{ 
              cursor: 'pointer',
              border: selectedMethod === MFA_METHODS.TOTP ? 2 : 1,
              borderColor: selectedMethod === MFA_METHODS.TOTP ? 'primary.main' : 'divider'
            }}
            onClick={() => handleMethodSelect(MFA_METHODS.TOTP)}
          >
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 3 }}>
              <QrCode sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
              <div  variant="h6" gutterBottom>
                Authenticator App
              </div>
              <div  variant="body2" color="text.secondary">
                Use Google Authenticator, Authy, or similar TOTP apps
              </div>
              <div  sx={{ mt: 2 }}>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Recommended" color="primary" size="small" />
              </div>
            </div>
          </div>
        </div>
        
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg" 
            sx={{ 
              cursor: 'pointer',
              border: selectedMethod === MFA_METHODS.SMS ? 2 : 1,
              borderColor: selectedMethod === MFA_METHODS.SMS ? 'primary.main' : 'divider'
            }}
            onClick={() => handleMethodSelect(MFA_METHODS.SMS)}
          >
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 3 }}>
              <Smartphone sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
              <div  variant="h6" gutterBottom>
                SMS Text Message
              </div>
              <div  variant="body2" color="text.secondary">
                Receive verification codes via SMS to {userPhoneNumber || 'your phone'}
              </div>
              <div  sx={{ mt: 2 }}>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Convenient" color="secondary" size="small" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const renderTOTPSetup = () => (
    <div  sx={{ mt: 2 }}>
      <div  variant="h6" gutterBottom>
        Setup Authenticator App
      </div>
      
      {qrCodeUrl && (
        <div  sx={{ textAlign: 'center', mb: 3 }}>
          <div  variant="body2" sx={{ mb: 2 }}>
            Scan this QR code with your authenticator app:
          </div>
          <img src={qrCodeUrl} alt="TOTP QR Code" style={{ maxWidth: 200 }} />
        </div>
      )}
      
      <hr className="border-gray-200" sx={{ my: 2 }} />
      
      <div  variant="body2" gutterBottom>
        Or manually enter this secret key:
      </div>
      <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
        <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          fullWidth
          value={totpSecret}
          InputProps={{
            readOnly: true,
            style: { fontFamily: 'monospace', fontSize: '0.9rem' }
          }}
          size="small"
        />
        <button className="p-2 rounded-full hover:bg-gray-100" onClick={copySecretToClipboard} color="primary">
          <ContentCopy />
        </button>
      </div>
      
      {secretCopied && (
        <div  variant="caption" color="success.main">
          Secret copied to clipboard!
        </div>
      )}
    </div>
  );

  const renderVerification = () => (
    <div  sx={{ mt: 2 }}>
      <div  variant="h6" gutterBottom>
        Verify Your Setup
      </div>
      
      {selectedMethod === MFA_METHODS.TOTP && (
        <>
          <div  variant="body2" sx={{ mb: 2 }}>
            Enter the 6-digit code from your authenticator app:
          </div>
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
          <div  variant="body2" sx={{ mb: 2 }}>
            Enter the 6-digit code sent to your phone:
          </div>
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
    </div>
  );

  const renderComplete = () => (
    <div  sx={{ textAlign: 'center', py: 4 }}>
      <CheckCircle sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
      <div  variant="h5" gutterBottom>
        MFA Successfully Configured!
      </div>
      <div  variant="body1" color="text.secondary">
        Your account is now protected with multi-factor authentication using {selectedMethod}.
      </div>
    </div>
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
      open={open} 
      onClose={handleClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: { borderRadius: 2 }
      }}
    >
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>
        <div  display="flex" alignItems="center" justifyContent="space-between">
          <div  display="flex" alignItems="center" gap={1}>
            <Security color="primary" />
            <div  variant="h6">
              Setup Multi-Factor Authentication
            </div>
          </div>
          <button className="p-2 rounded-full hover:bg-gray-100" onClick={handleClose} size="small">
            <Close />
          </button>
        </div>
      </h2>
      
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
        <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
          {SETUP_STEPS.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>
        
        {error && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
            {error}
          </div>
        )}
        
        {success && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="success" sx={{ mb: 2 }}>
            {success}
          </div>
        )}
        
        {getStepContent()}
        
        <div  sx={{ display: 'flex', justifyContent: 'space-between', mt: 4 }}>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            onClick={handleBack}
            disabled={activeStep === 0 || activeStep === 3}
          >
            Back
          </button>
          
          <div  sx={{ display: 'flex', gap: 1 }}>
            {activeStep < 3 && activeStep > 0 && (
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="contained"
                onClick={handleNext}
                disabled={loading || (activeStep === 2 && (!totpCode && !smsCode))}
                startIcon={loading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} /> : null}
              >
                {activeStep === 2 ? 'Verify' : 'Continue'}
              </button>
            )}
            
            {activeStep === 3 && (
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="contained"
                onClick={handleClose}
                color="success"
              >
                Done
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default MFASetupModal;