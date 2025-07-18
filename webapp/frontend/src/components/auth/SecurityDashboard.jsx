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
    <div  sx={{ p: 3 }}>
      <div  variant="h4" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Security color="primary" />
        Security Dashboard
      </div>

      <div className="grid" container spacing={3}>
        {/* Security Overview Cards */}
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <Shield color="primary" />
                <div  variant="h6">Account Security</div>
              </div>
              
              <div  sx={{ mb: 1 }}>
                <div  variant="body2" color="text.secondary">
                  Multi-Factor Authentication
                </div>
                <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    label={securityData.securitySettings.mfaEnabled ? "Enabled" : "Disabled"}
                    color={securityData.securitySettings.mfaEnabled ? "success" : "warning"}
                    size="small"
                    icon={securityData.securitySettings.mfaEnabled ? <CheckCircle /> : <Warning />}
                  />
                  {!securityData.securitySettings.mfaEnabled && (
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" size="small" onClick={() => setShowMFASetup(true)}>
                      Setup
                    </button>
                  )}
                </div>
              </div>

              <div  sx={{ mb: 1 }}>
                <div  variant="body2" color="text.secondary">
                  Biometric Authentication
                </div>
                <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    label={securityData.securitySettings.biometricEnabled ? "Enabled" : "Available"}
                    color={securityData.securitySettings.biometricEnabled ? "success" : "info"}
                    size="small"
                    icon={<Fingerprint />}
                  />
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" size="small" onClick={() => setShowBiometricSetup(true)}>
                    {securityData.securitySettings.biometricEnabled ? "Manage" : "Setup"}
                  </button>
                </div>
              </div>

              <div>
                <div  variant="body2" color="text.secondary">
                  Password Strength
                </div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label={securityData.securitySettings.passwordStrength}
                  color="success"
                  size="small"
                  icon={<VpnKey />}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Current Session Info */}
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                <Schedule color="primary" />
                <div  variant="h6">Current Session</div>
              </div>
              
              {sessionInfo && (
                <>
                  <div  variant="body2" color="text.secondary" gutterBottom>
                    Started: {formatTimestamp(sessionInfo.sessionStarted)}
                  </div>
                  <div  variant="body2" color="text.secondary" gutterBottom>
                    User: {sessionInfo.email}
                  </div>
                  <div  variant="body2" color="text.secondary" gutterBottom>
                    Refreshed: {sessionInfo.refreshCount} times
                  </div>
                  <div  sx={{ mt: 2 }}>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      label="Active"
                      color="success"
                      size="small"
                      icon={<CheckCircle />}
                    />
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Quick Actions
              </div>
              
              <div  sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
                  startIcon={<VpnKey />}
                  size="small"
                >
                  Change Password
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
                  startIcon={<Refresh />}
                  size="small"
                >
                  Review Active Sessions
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
                  startIcon={<Block />}
                  color="error"
                  size="small"
                >
                  Lock Account
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Login History */}
        <div className="grid" item xs={12} md={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Recent Login Activity
              </div>
              
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Date & Time</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Location</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Device</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Method</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
                    </tr>
                  </thead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                    {securityData.loginHistory.map((login) => (
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={login.id}>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{formatTimestamp(login.timestamp)}</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                            <LocationOn fontSize="small" color="action" />
                            {login.location}
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{login.device}</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                            label={login.method}
                            size="small"
                            variant="outlined"
                          />
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                            label={login.status}
                            color={getStatusColor(login.status)}
                            size="small"
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        {/* Trusted Devices */}
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Trusted Devices
              </div>
              
              <List dense>
                {securityData.devices.map((device) => (
                  <ListItem key={device.id}>
                    <ListItemIcon>
                      {getDeviceIcon(device.type)}
                    </ListItemIcon>
                    <ListItemText
                      primary={device.name}
                      secondary={
                        <div>
                          <div  variant="caption" display="block">
                            {device.browser}
                          </div>
                          <div  variant="caption" color="text.secondary">
                            Last seen: {formatTimestamp(device.lastSeen)}
                          </div>
                          {device.isCurrent && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Current" size="small" color="primary" sx={{ ml: 1 }} />
                          )}
                        </div>
                      }
                    />
                    <ListItemSecondaryAction>
                      <button className="p-2 rounded-full hover:bg-gray-100" 
                        edge="end" 
                        size="small"
                        onClick={() => {
                          setSelectedDevice(device);
                          setShowDeviceDialog(true);
                        }}
                      >
                        <Visibility />
                      </button>
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
              </List>
            </div>
          </div>
        </div>
      </div>

      {/* Device Details Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={showDeviceDialog} onClose={() => setShowDeviceDialog(false)}>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Device Details</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          {selectedDevice && (
            <div>
              <div  variant="h6" gutterBottom>
                {selectedDevice.name}
              </div>
              <div  variant="body2" color="text.secondary" gutterBottom>
                Browser: {selectedDevice.browser}
              </div>
              <div  variant="body2" color="text.secondary" gutterBottom>
                Last Location: {selectedDevice.location}
              </div>
              <div  variant="body2" color="text.secondary" gutterBottom>
                Last Seen: {formatTimestamp(selectedDevice.lastSeen)}
              </div>
              
              {selectedDevice.isCurrent && (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mt: 2 }}>
                  This is your current device
                </div>
              )}
            </div>
          )}
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setShowDeviceDialog(false)}>
            Close
          </button>
          {selectedDevice && !selectedDevice.isCurrent && (
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              color="error" 
              onClick={() => handleRemoveDevice(selectedDevice.id)}
              startIcon={<Delete />}
            >
              Remove Device
            </button>
          )}
        </div>
      </div>

      {/* MFA Setup Modal */}
      <MFASetupModal
        open={showMFASetup}
        onClose={() => setShowMFASetup(false)}
        onSetupComplete={handleMFASetupComplete}
        userPhoneNumber={user?.phoneNumber}
      />

      {/* Biometric Setup Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
        open={showBiometricSetup} 
        onClose={() => setShowBiometricSetup(false)}
        maxWidth="sm"
        fullWidth
      >
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Biometric Authentication</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
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
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setShowBiometricSetup(false)}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default SecurityDashboard;