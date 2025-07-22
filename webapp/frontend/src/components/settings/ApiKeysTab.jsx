import React from 'react';
import {
  Grid,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  FormControlLabel,
  Switch,
  Alert,
  Chip,
  Box,
  InputAdornment,
  IconButton
} from '@mui/material';
import {
  AccountBalance,
  Assessment,
  Visibility,
  VisibilityOff
} from '@mui/icons-material';

const ApiKeysTab = ({
  settings,
  updateSettings,
  showPasswords,
  setShowPasswords,
  saveApiKeyLocal,
  testConnection,
  testingConnection,
  connectionResults
}) => {
  return (
    <Grid container spacing={3}>
      {/* Alpaca */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <AccountBalance sx={{ mr: 1 }} />
              <Typography variant="h6">Alpaca Trading</Typography>
              <Chip 
                label={settings?.apiKeys?.alpaca?.enabled ? 'Connected' : 'Disconnected'} 
                color={settings?.apiKeys?.alpaca?.enabled ? 'success' : 'default'}
                size="small"
                sx={{ ml: 2 }}
              />
            </Box>
            
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="API Key ID"
                  type={showPasswords.alpacaKey ? 'text' : 'password'}
                  value={settings?.apiKeys?.alpaca?.keyId || ''}
                  onChange={(e) => updateSettings('apiKeys', 'alpaca', {
                    ...settings.apiKeys.alpaca,
                    keyId: e.target.value
                  })}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          onClick={() => setShowPasswords(prev => ({
                            ...prev,
                            alpacaKey: !prev.alpacaKey
                          }))}
                        >
                          {showPasswords.alpacaKey ? <VisibilityOff /> : <Visibility />}
                        </IconButton>
                      </InputAdornment>
                    )
                  }}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Secret Key"
                  type={showPasswords.alpacaSecret ? 'text' : 'password'}
                  value={settings?.apiKeys?.alpaca?.secretKey || ''}
                  onChange={(e) => updateSettings('apiKeys', 'alpaca', {
                    ...settings.apiKeys.alpaca,
                    secretKey: e.target.value
                  })}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          onClick={() => setShowPasswords(prev => ({
                            ...prev,
                            alpacaSecret: !prev.alpacaSecret
                          }))}
                        >
                          {showPasswords.alpacaSecret ? <VisibilityOff /> : <Visibility />}
                        </IconButton>
                      </InputAdornment>
                    )
                  }}
                />
              </Grid>
              <Grid item xs={12}>
                <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={settings?.apiKeys?.alpaca?.paperTrading || false}
                        onChange={(e) => updateSettings('apiKeys', 'alpaca', {
                          ...settings.apiKeys.alpaca,
                          paperTrading: e.target.checked
                        })}
                      />
                    }
                    label="Paper Trading"
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={settings?.apiKeys?.alpaca?.enabled || false}
                        onChange={(e) => updateSettings('apiKeys', 'alpaca', {
                          ...settings.apiKeys.alpaca,
                          enabled: e.target.checked
                        })}
                      />
                    }
                    label="Enabled"
                  />
                  <Button
                    variant="contained"
                    onClick={() => saveApiKeyLocal('alpaca', settings.apiKeys.alpaca)}
                    disabled={!settings?.apiKeys?.alpaca?.keyId || !settings?.apiKeys?.alpaca?.secretKey}
                    sx={{ mr: 1 }}
                  >
                    Save API Key
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={() => testConnection('alpaca')}
                    disabled={testingConnection || !settings?.apiKeys?.alpaca?.id}
                  >
                    Test Connection
                  </Button>
                </Box>
              </Grid>
            </Grid>
            
            {connectionResults?.alpaca && (
              <Alert severity={connectionResults.alpaca.status} sx={{ mt: 2 }}>
                {connectionResults.alpaca.message}
              </Alert>
            )}
          </CardContent>
        </Card>
      </Grid>

      {/* Polygon */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Assessment sx={{ mr: 1 }} />
              <Typography variant="h6">Polygon Market Data</Typography>
              <Chip 
                label={settings?.apiKeys?.polygon?.enabled ? 'Connected' : 'Disconnected'} 
                color={settings?.apiKeys?.polygon?.enabled ? 'success' : 'default'}
                size="small"
                sx={{ ml: 2 }}
              />
            </Box>
            
            <Grid container spacing={2}>
              <Grid item xs={12} md={8}>
                <TextField
                  fullWidth
                  label="API Key"
                  type={showPasswords.polygonKey ? 'text' : 'password'}
                  value={settings?.apiKeys?.polygon?.apiKey || ''}
                  onChange={(e) => updateSettings('apiKeys', 'polygon', {
                    ...settings.apiKeys.polygon,
                    apiKey: e.target.value
                  })}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          onClick={() => setShowPasswords(prev => ({
                            ...prev,
                            polygonKey: !prev.polygonKey
                          }))}
                        >
                          {showPasswords.polygonKey ? <VisibilityOff /> : <Visibility />}
                        </IconButton>
                      </InputAdornment>
                    )
                  }}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={settings?.apiKeys?.polygon?.enabled || false}
                        onChange={(e) => updateSettings('apiKeys', 'polygon', {
                          ...settings.apiKeys.polygon,
                          enabled: e.target.checked
                        })}
                      />
                    }
                    label="Enabled"
                  />
                  <Button
                    variant="contained"
                    onClick={() => saveApiKeyLocal('polygon', settings.apiKeys.polygon)}
                    disabled={!settings?.apiKeys?.polygon?.apiKey}
                    sx={{ mr: 1 }}
                  >
                    Save API Key
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={() => testConnection('polygon')}
                    disabled={testingConnection || !settings?.apiKeys?.polygon?.id}
                  >
                    Test Connection
                  </Button>
                </Box>
              </Grid>
            </Grid>
            
            {connectionResults?.polygon && (
              <Alert severity={connectionResults.polygon.status} sx={{ mt: 2 }}>
                {connectionResults.polygon.message}
              </Alert>
            )}
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
};

export default ApiKeysTab;