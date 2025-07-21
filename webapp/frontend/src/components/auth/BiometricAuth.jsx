import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Typography,
  Alert,
  CircularProgress,
  Card,
  CardContent,
  IconButton,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions
} from '@mui/material';
import {
  Fingerprint,
  Face,
  Security,
  CheckCircle,
  Warning,
  Settings,
  Close
} from '@mui/icons-material';

// Biometric authentication capabilities detection and management
class BiometricService {
  constructor() {
    this.isSupported = this.checkSupport();
    this.availableMethods = this.detectAvailableMethods();
  }

  checkSupport() {
    // Check for Web Authentication API support
    return !!(navigator.credentials && navigator.credentials.create && navigator.credentials.get && 
             window.PublicKeyCredential && window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable);
  }

  async detectAvailableMethods() {
    if (!this.isSupported) {
      return { touchId: false, faceId: false, windowsHello: false, platformAuthenticator: false };
    }

    try {
      // Check for platform authenticator availability (Touch ID, Face ID, Windows Hello)
      const platformAuthenticatorAvailable = 
        window.PublicKeyCredential 
          ? await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable()
          : false;
      
      // Detect specific biometric types based on user agent and platform
      const userAgent = navigator.userAgent.toLowerCase();
      const platform = navigator.platform.toLowerCase();
      
      const touchId = (userAgent.includes('mac') || userAgent.includes('iphone') || userAgent.includes('ipad')) && platformAuthenticatorAvailable;
      const faceId = (userAgent.includes('iphone') || userAgent.includes('ipad')) && platformAuthenticatorAvailable;
      const windowsHello = (userAgent.includes('windows') || platform.includes('win')) && platformAuthenticatorAvailable;
      
      return {
        touchId,
        faceId,
        windowsHello,
        platformAuthenticator: platformAuthenticatorAvailable,
        crossPlatform: true // Most devices support some form of biometric auth
      };
    } catch (error) {
      console.error('Error detecting biometric capabilities:', error);
      return { touchId: false, faceId: false, windowsHello: false, platformAuthenticator: false };
    }
  }

  async createCredentials(userId, username) {
    if (!this.isSupported) {
      throw new Error('Biometric authentication is not supported on this device');
    }

    const challenge = new Uint8Array(32);
    crypto.getRandomValues(challenge);

    const publicKeyCredentialCreationOptions = {
      challenge,
      rp: {
        name: "Financial Platform",
        id: window.location.hostname,
      },
      user: {
        id: new TextEncoder().encode(userId),
        name: username,
        displayName: username,
      },
      pubKeyCredParams: [
        { alg: -7, type: "public-key" }, // ES256
        { alg: -257, type: "public-key" }, // RS256
      ],
      authenticatorSelection: {
        authenticatorAttachment: "platform", // Built-in authenticators only
        userVerification: "required", // Require biometric verification
        requireResidentKey: true // Store credential on device
      },
      timeout: 60000,
      attestation: "direct"
    };

    try {
      const credential = await navigator.credentials.create({
        publicKey: publicKeyCredentialCreationOptions
      });

      // Store credential information
      const credentialData = {
        id: credential.id,
        rawId: Array.from(new Uint8Array(credential.rawId)),
        type: credential.type,
        response: {
          attestationObject: Array.from(new Uint8Array(credential.response.attestationObject)),
          clientDataJSON: Array.from(new Uint8Array(credential.response.clientDataJSON))
        },
        createdAt: new Date().toISOString(),
        lastUsed: new Date().toISOString()
      };

      // Store in local storage for this demo (in production, store on server)
      localStorage.setItem(`biometric_credential_${userId}`, JSON.stringify(credentialData));
      
      return credentialData;
    } catch (error) {
      console.error('Biometric credential creation failed:', error);
      throw new Error(`Failed to create biometric credentials: ${error.message}`);
    }
  }

  async authenticate(userId) {
    if (!this.isSupported) {
      throw new Error('Biometric authentication is not supported on this device');
    }

    // Retrieve stored credential
    const storedCredentialData = localStorage.getItem(`biometric_credential_${userId}`);
    if (!storedCredentialData) {
      throw new Error('No biometric credentials found for this user');
    }

    const credentialData = JSON.parse(storedCredentialData);
    const challenge = new Uint8Array(32);
    crypto.getRandomValues(challenge);

    const publicKeyCredentialRequestOptions = {
      challenge,
      allowCredentials: [{
        id: new Uint8Array(credentialData.rawId),
        type: 'public-key',
        transports: ['internal'] // Platform authenticator
      }],
      userVerification: "required",
      timeout: 60000,
    };

    try {
      const assertion = await navigator.credentials.get({
        publicKey: publicKeyCredentialRequestOptions
      });

      // Update last used timestamp
      credentialData.lastUsed = new Date().toISOString();
      localStorage.setItem(`biometric_credential_${userId}`, JSON.stringify(credentialData));

      return {
        id: assertion.id,
        response: {
          authenticatorData: Array.from(new Uint8Array(assertion.response.authenticatorData)),
          clientDataJSON: Array.from(new Uint8Array(assertion.response.clientDataJSON)),
          signature: Array.from(new Uint8Array(assertion.response.signature)),
          userHandle: assertion.response.userHandle
        },
        authenticatedAt: new Date().toISOString()
      };
    } catch (error) {
      console.error('Biometric authentication failed:', error);
      throw new Error(`Biometric authentication failed: ${error.message}`);
    }
  }

  hasCredentials(userId) {
    return !!localStorage.getItem(`biometric_credential_${userId}`);
  }

  removeCredentials(userId) {
    localStorage.removeItem(`biometric_credential_${userId}`);
  }
}

function BiometricAuth({ 
  userId, 
  username, 
  onAuthSuccess, 
  onSetupComplete, 
  onError,
  showSetup = true,
  compact = false 
}) {
  const [biometricService] = useState(new BiometricService());
  const [capabilities, setCapabilities] = useState(null);
  const [isSupported, setIsSupported] = useState(false);
  const [hasCredentials, setHasCredentials] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showSetupDialog, setShowSetupDialog] = useState(false);

  useEffect(() => {
    initializeBiometrics();
  }, [userId]);

  const initializeBiometrics = async () => {
    setIsSupported(biometricService.isSupported);
    
    if (biometricService.isSupported) {
      const caps = await biometricService.availableMethods;
      setCapabilities(caps);
      
      if (userId) {
        setHasCredentials(biometricService.hasCredentials(userId));
      }
    }
  };

  const handleSetupBiometric = async () => {
    if (!userId || !username) {
      setError('User information is required for biometric setup');
      return;
    }

    try {
      setLoading(true);
      setError('');
      
      const credentialData = await biometricService.createCredentials(userId, username);
      setHasCredentials(true);
      setShowSetupDialog(false);
      
      if (onSetupComplete) {
        onSetupComplete(credentialData);
      }
    } catch (error) {
      console.error('Biometric setup error:', error);
      setError(error.message);
      if (onError) {
        onError(error);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleBiometricAuth = async () => {
    if (!userId) {
      setError('User ID is required for authentication');
      return;
    }

    try {
      setLoading(true);
      setError('');
      
      const authResult = await biometricService.authenticate(userId);
      
      if (onAuthSuccess) {
        onAuthSuccess(authResult);
      }
    } catch (error) {
      console.error('Biometric authentication error:', error);
      setError(error.message);
      if (onError) {
        onError(error);
      }
    } finally {
      setLoading(false);
    }
  };

  const getBiometricIcon = () => {
    if (capabilities?.faceId) return <Face sx={{ fontSize: 40 }} />;
    if (capabilities?.touchId) return <Fingerprint sx={{ fontSize: 40 }} />;
    if (capabilities?.windowsHello) return <Security sx={{ fontSize: 40 }} />;
    return <Fingerprint sx={{ fontSize: 40 }} />;
  };

  const getBiometricLabel = () => {
    if (capabilities?.faceId) return 'Face ID';
    if (capabilities?.touchId) return 'Touch ID';
    if (capabilities?.windowsHello) return 'Windows Hello';
    return 'Biometric Authentication';
  };

  if (!isSupported) {
    return null; // Don't show anything if not supported
  }

  if (compact) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {hasCredentials ? (
          <Button
            variant="outlined"
            size="small"
            startIcon={getBiometricIcon()}
            onClick={handleBiometricAuth}
            disabled={loading}
          >
            {loading ? 'Authenticating...' : getBiometricLabel()}
          </Button>
        ) : showSetup ? (
          <Button
            variant="text"
            size="small"
            startIcon={<Settings />}
            onClick={() => setShowSetupDialog(true)}
          >
            Setup {getBiometricLabel()}
          </Button>
        ) : null}
      </Box>
    );
  }

  return (
    <Box>
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Box display="flex" alignItems="center" gap={1}>
              {getBiometricIcon()}
              <Typography variant="h6">
                {getBiometricLabel()}
              </Typography>
            </Box>
            
            {hasCredentials && (
              <Chip 
                label="Configured" 
                color="success" 
                size="small"
                icon={<CheckCircle />}
              />
            )}
          </Box>
          
          <Typography variant="body2" color="text.secondary" gutterBottom>
            {hasCredentials 
              ? `Use your ${getBiometricLabel().toLowerCase()} for quick and secure authentication`
              : `Setup ${getBiometricLabel().toLowerCase()} for enhanced security and convenience`
            }
          </Typography>
          
          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
          
          <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
            {hasCredentials ? (
              <>
                <Button
                  variant="contained"
                  startIcon={getBiometricIcon()}
                  onClick={handleBiometricAuth}
                  disabled={loading}
                >
                  {loading ? (
                    <>
                      <CircularProgress size={20} sx={{ mr: 1 }} />
                      Authenticating...
                    </>
                  ) : (
                    `Use ${getBiometricLabel()}`
                  )}
                </Button>
                
                <Button
                  variant="outlined"
                  color="error"
                  onClick={() => {
                    biometricService.removeCredentials(userId);
                    setHasCredentials(false);
                  }}
                >
                  Remove
                </Button>
              </>
            ) : showSetup ? (
              <Button
                variant="contained"
                startIcon={<Settings />}
                onClick={() => setShowSetupDialog(true)}
              >
                Setup {getBiometricLabel()}
              </Button>
            ) : null}
          </Box>
        </CardContent>
      </Card>

      {/* Setup Dialog */}
      <Dialog open={showSetupDialog} onClose={() => setShowSetupDialog(false)}>
        <DialogTitle>
          <Box display="flex" alignItems="center" justifyContent="space-between">
            <Box display="flex" alignItems="center" gap={1}>
              {getBiometricIcon()}
              <Typography variant="h6">
                Setup {getBiometricLabel()}
              </Typography>
            </Box>
            <IconButton onClick={() => setShowSetupDialog(false)} size="small">
              <Close />
            </IconButton>
          </Box>
        </DialogTitle>
        
        <DialogContent>
          <Typography variant="body1" gutterBottom>
            {getBiometricLabel()} provides secure and convenient authentication using your device's built-in biometric sensors.
          </Typography>
          
          <Alert severity="info" sx={{ mt: 2 }}>
            Your biometric data is stored securely on your device and never leaves your device.
          </Alert>
          
          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
        </DialogContent>
        
        <DialogActions>
          <Button onClick={() => setShowSetupDialog(false)}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleSetupBiometric}
            disabled={loading}
            startIcon={loading ? <CircularProgress size={20} /> : getBiometricIcon()}
          >
            {loading ? 'Setting up...' : `Setup ${getBiometricLabel()}`}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default BiometricAuth;