import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Avatar,
  IconButton,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction,
  Divider,
  Alert,
  Grid,
  Paper
} from '@mui/material';
import {
  Security,
  DeviceUnknown,
  Smartphone,
  Computer,
  Shield,
  Warning,
  CheckCircle,
  Block,
  Refresh,
  Visibility,
  LocationOn,
  Schedule,
  Fingerprint,
  VpnKey,
  Delete,
  Info
} from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import { useSession } from '../auth/SessionManager';
import BiometricAuth from './BiometricAuth';
import MFASetupModal from './MFASetupModal';

// Mock security data - in production this would come from your backend
const mockSecurityData = {
  loginHistory: [
    {
      id: 1,
      timestamp: '2024-01-16T10:30:00Z',
      location: 'New York, NY',
      device: 'Chrome on Windows',
      ip: '192.168.1.100',
      status: 'success',
      method: 'password'
    },
    {
      id: 2,
      timestamp: '2024-01-16T08:15:00Z',
      location: 'New York, NY',
      device: 'Safari on iPhone',
      ip: '192.168.1.101',
      status: 'success',
      method: 'biometric'
    },
    {
      id: 3,
      timestamp: '2024-01-15T18:45:00Z',
      location: 'Los Angeles, CA',
      ip: '10.0.0.50',
      device: 'Chrome on Mac',
      status: 'failed',
      method: 'password'
    }
  ],
  devices: [
    {
      id: 1,
      name: 'MacBook Pro',
      type: 'computer',
      browser: 'Chrome 120.0',
      lastSeen: '2024-01-16T10:30:00Z',
      location: 'New York, NY',
      isCurrent: true,
      trusted: true
    },
    {
      id: 2,
      name: 'iPhone 15 Pro',
      type: 'mobile',
      browser: 'Safari',
      lastSeen: '2024-01-16T08:15:00Z',
      location: 'New York, NY',
      isCurrent: false,
      trusted: true
    }
  ],
  securitySettings: {
    mfaEnabled: true,
    biometricEnabled: false,
    passwordStrength: 'strong',
    lastPasswordChange: '2024-01-01T00:00:00Z',
    accountLocked: false,
    failedLoginAttempts: 0
  }
};

function SecurityDashboard() {
  const { user } = useAuth();
  const { sessionInfo } = useSession();
  const [securityData, setSecurityData] = useState(mockSecurityData);
  const [showDeviceDialog, setShowDeviceDialog] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [showMFASetup, setShowMFASetup] = useState(false);
  const [showBiometricSetup, setShowBiometricSetup] = useState(false);

  const getDeviceIcon = (type) => {
    switch (type) {
      case 'mobile':
        return <Smartphone />;
      case 'computer':
        return <Computer />;
      default:
        return <DeviceUnknown />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'success':
        return 'success';
      case 'failed':
        return 'error';
      default:
        return 'default';
    }
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  const handleRemoveDevice = (deviceId) => {
    setSecurityData(prev => ({
      ...prev,
      devices: prev.devices.filter(device => device.id !== deviceId)
    }));
    setShowDeviceDialog(false);
  };

  const handleMFASetupComplete = (method) => {
    setSecurityData(prev => ({
      ...prev,
      securitySettings: {
        ...prev.securitySettings,
        mfaEnabled: true
      }
    }));
    setShowMFASetup(false);
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Security color="primary" />
        Security Dashboard
      </Typography>

      <Grid container spacing={3}>
        {/* Security Overview Cards */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <Shield color="primary" />
                <Typography variant="h6">Account Security</Typography>
              </Box>
              
              <Box sx={{ mb: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  Multi-Factor Authentication
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip 
                    label={securityData.securitySettings.mfaEnabled ? "Enabled" : "Disabled"}
                    color={securityData.securitySettings.mfaEnabled ? "success" : "warning"}
                    size="small"
                    icon={securityData.securitySettings.mfaEnabled ? <CheckCircle /> : <Warning />}
                  />
                  {!securityData.securitySettings.mfaEnabled && (
                    <Button size="small" onClick={() => setShowMFASetup(true)}>
                      Setup
                    </Button>
                  )}
                </Box>
              </Box>

              <Box sx={{ mb: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  Biometric Authentication
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip 
                    label={securityData.securitySettings.biometricEnabled ? "Enabled" : "Available"}
                    color={securityData.securitySettings.biometricEnabled ? "success" : "info"}
                    size="small"
                    icon={<Fingerprint />}
                  />
                  <Button size="small" onClick={() => setShowBiometricSetup(true)}>
                    {securityData.securitySettings.biometricEnabled ? "Manage" : "Setup"}
                  </Button>
                </Box>
              </Box>

              <Box>
                <Typography variant="body2" color="text.secondary">
                  Password Strength
                </Typography>
                <Chip 
                  label={securityData.securitySettings.passwordStrength}
                  color="success"
                  size="small"
                  icon={<VpnKey />}
                />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Current Session Info */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <Schedule color="primary" />
                <Typography variant="h6">Current Session</Typography>
              </Box>
              
              {sessionInfo && (
                <>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Started: {formatTimestamp(sessionInfo.sessionStarted)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    User: {sessionInfo.email}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Refreshed: {sessionInfo.refreshCount} times
                  </Typography>
                  <Box sx={{ mt: 2 }}>
                    <Chip 
                      label="Active"
                      color="success"
                      size="small"
                      icon={<CheckCircle />}
                    />
                  </Box>
                </>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Quick Actions */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Quick Actions
              </Typography>
              
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Button 
                  variant="outlined" 
                  startIcon={<VpnKey />}
                  size="small"
                >
                  Change Password
                </Button>
                <Button 
                  variant="outlined" 
                  startIcon={<Refresh />}
                  size="small"
                >
                  Review Active Sessions
                </Button>
                <Button 
                  variant="outlined" 
                  startIcon={<Block />}
                  color="error"
                  size="small"
                >
                  Lock Account
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Login History */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Recent Login Activity
              </Typography>
              
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Date & Time</TableCell>
                      <TableCell>Location</TableCell>
                      <TableCell>Device</TableCell>
                      <TableCell>Method</TableCell>
                      <TableCell>Status</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {securityData.loginHistory.map((login) => (
                      <TableRow key={login.id}>
                        <TableCell>{formatTimestamp(login.timestamp)}</TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                            <LocationOn fontSize="small" color="action" />
                            {login.location}
                          </Box>
                        </TableCell>
                        <TableCell>{login.device}</TableCell>
                        <TableCell>
                          <Chip 
                            label={login.method}
                            size="small"
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell>
                          <Chip 
                            label={login.status}
                            color={getStatusColor(login.status)}
                            size="small"
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Trusted Devices */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Trusted Devices
              </Typography>
              
              <List dense>
                {securityData.devices.map((device) => (
                  <ListItem key={device.id}>
                    <ListItemIcon>
                      {getDeviceIcon(device.type)}
                    </ListItemIcon>
                    <ListItemText
                      primary={device.name}
                      secondary={
                        <Box>
                          <Typography variant="caption" display="block">
                            {device.browser}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            Last seen: {formatTimestamp(device.lastSeen)}
                          </Typography>
                          {device.isCurrent && (
                            <Chip label="Current" size="small" color="primary" sx={{ ml: 1 }} />
                          )}
                        </Box>
                      }
                    />
                    <ListItemSecondaryAction>
                      <IconButton 
                        edge="end" 
                        size="small"
                        onClick={() => {
                          setSelectedDevice(device);
                          setShowDeviceDialog(true);
                        }}
                      >
                        <Visibility />
                      </IconButton>
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Device Details Dialog */}
      <Dialog open={showDeviceDialog} onClose={() => setShowDeviceDialog(false)}>
        <DialogTitle>Device Details</DialogTitle>
        <DialogContent>
          {selectedDevice && (
            <Box>
              <Typography variant="h6" gutterBottom>
                {selectedDevice.name}
              </Typography>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Browser: {selectedDevice.browser}
              </Typography>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Last Location: {selectedDevice.location}
              </Typography>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Last Seen: {formatTimestamp(selectedDevice.lastSeen)}
              </Typography>
              
              {selectedDevice.isCurrent && (
                <Alert severity="info" sx={{ mt: 2 }}>
                  This is your current device
                </Alert>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowDeviceDialog(false)}>
            Close
          </Button>
          {selectedDevice && !selectedDevice.isCurrent && (
            <Button 
              color="error" 
              onClick={() => handleRemoveDevice(selectedDevice.id)}
              startIcon={<Delete />}
            >
              Remove Device
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* MFA Setup Modal */}
      <MFASetupModal
        open={showMFASetup}
        onClose={() => setShowMFASetup(false)}
        onSetupComplete={handleMFASetupComplete}
        userPhoneNumber={user?.phoneNumber}
      />

      {/* Biometric Setup Dialog */}
      <Dialog 
        open={showBiometricSetup} 
        onClose={() => setShowBiometricSetup(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Biometric Authentication</DialogTitle>
        <DialogContent>
          <BiometricAuth
            userId={user?.userId}
            username={user?.username}
            onAuthSuccess={(result) => {
              console.log('Biometric auth success:', result);
            }}
            onSetupComplete={(credentials) => {
              console.log('Biometric setup complete:', credentials);
              setSecurityData(prev => ({
                ...prev,
                securitySettings: {
                  ...prev.securitySettings,
                  biometricEnabled: true
                }
              }));
            }}
            onError={(error) => {
              console.error('Biometric error:', error);
            }}
            showSetup={true}
            compact={false}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowBiometricSetup(false)}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default SecurityDashboard;