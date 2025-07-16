import React, { useState } from 'react';
import {
  Box, Card, CardContent, Typography, Button, Alert, 
  TextField, Stack, Divider, Chip
} from '@mui/material';
import { Warning, Login, Person, Email } from '@mui/icons-material';

const AuthFallback = ({ onLogin }) => {
  const [email, setEmail] = useState('demo@example.com');
  const [name, setName] = useState('Demo User');

  const handleDemoLogin = () => {
    // Create a mock user object for development
    const mockUser = {
      id: 'demo-user-123',
      email: email,
      name: name,
      attributes: {
        email: email,
        name: name,
        email_verified: 'true'
      },
      signInUserSession: {
        accessToken: {
          jwtToken: 'demo-access-token',
          payload: {
            sub: 'demo-user-123',
            email: email,
            name: name
          }
        },
        idToken: {
          jwtToken: 'demo-id-token',
          payload: {
            sub: 'demo-user-123',
            email: email,
            name: name,
            email_verified: true
          }
        }
      }
    };

    // Store in localStorage for persistence
    localStorage.setItem('demo-user', JSON.stringify(mockUser));
    
    onLogin(mockUser);
  };

  return (
    <Box sx={{ 
      minHeight: '100vh', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      p: 2
    }}>
      <Card sx={{ maxWidth: 500, width: '100%' }}>
        <CardContent sx={{ p: 4 }}>
          <Stack spacing={3} alignItems="center">
            <Warning sx={{ fontSize: 60, color: 'warning.main' }} />
            
            <Typography variant="h4" textAlign="center" gutterBottom>
              Authentication Unavailable
            </Typography>
            
            <Alert severity="warning" sx={{ width: '100%' }}>
              <Typography variant="body2">
                <strong>Production Issue:</strong> Cognito configuration is using fallback values. 
                Real authentication is not available.
              </Typography>
            </Alert>

            <Stack spacing={1} sx={{ width: '100%' }}>
              <Typography variant="body2" color="text.secondary">
                <strong>Technical Details:</strong>
              </Typography>
              <Chip label="USER_POOL_ID: us-east-1_MISSING" size="small" color="error" />
              <Chip label="CLIENT_ID: missing-client-id" size="small" color="error" />
              <Typography variant="caption" color="text.secondary">
                CloudFormation deployment must extract real Cognito values
              </Typography>
            </Stack>

            <Divider sx={{ width: '100%' }} />

            <Typography variant="h6" color="primary.main">
              Development Mode Access
            </Typography>

            <Stack spacing={2} sx={{ width: '100%' }}>
              <TextField
                label="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                fullWidth
                size="small"
                InputProps={{
                  startAdornment: <Email sx={{ mr: 1, color: 'text.secondary' }} />
                }}
              />
              <TextField
                label="Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                fullWidth
                size="small"
                InputProps={{
                  startAdornment: <Person sx={{ mr: 1, color: 'text.secondary' }} />
                }}
              />
            </Stack>

            <Button
              variant="contained"
              onClick={handleDemoLogin}
              startIcon={<Login />}
              size="large"
              fullWidth
              sx={{ py: 1.5 }}
            >
              Continue with Demo Mode
            </Button>

            <Alert severity="info" sx={{ width: '100%' }}>
              <Typography variant="caption">
                This creates a temporary demo session. No real authentication is performed.
                All data will be mock/demo data until the backend database is connected.
              </Typography>
            </Alert>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
};

export default AuthFallback;