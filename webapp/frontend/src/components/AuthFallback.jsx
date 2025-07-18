import React, { useState } from 'react';
import {
  Box, Card, CardContent, Typography, Button, Alert, 
  TextField, Stack, Divider, Chip
} from '@mui/material';

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
    <div  sx={{ 
      minHeight: '100vh', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      p: 2
    }}>
      <div className="bg-white shadow-md rounded-lg" sx={{ maxWidth: 500, width: '100%' }}>
        <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 4 }}>
          <div className="flex flex-col space-y-2" spacing={3} alignItems="center">
            <Warning sx={{ fontSize: 60, color: 'warning.main' }} />
            
            <div  variant="h4" textAlign="center" gutterBottom>
              Authentication Unavailable
            </div>
            
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning" sx={{ width: '100%' }}>
              <div  variant="body2">
                <strong>Production Issue:</strong> Cognito configuration is using fallback values. 
                Real authentication is not available.
              </div>
            </div>

            <div className="flex flex-col space-y-2" spacing={1} sx={{ width: '100%' }}>
              <div  variant="body2" color="text.secondary">
                <strong>Technical Details:</strong>
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="USER_POOL_ID: us-east-1_MISSING" size="small" color="error" />
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="CLIENT_ID: missing-client-id" size="small" color="error" />
              <div  variant="caption" color="text.secondary">
                CloudFormation deployment must extract real Cognito values
              </div>
            </div>

            <hr className="border-gray-200" sx={{ width: '100%' }} />

            <div  variant="h6" color="primary.main">
              Development Mode Access
            </div>

            <div className="flex flex-col space-y-2" spacing={2} sx={{ width: '100%' }}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                fullWidth
                size="small"
                InputProps={{
                  startAdornment: <Email sx={{ mr: 1, color: 'text.secondary' }} />
                }}
              />
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                fullWidth
                size="small"
                InputProps={{
                  startAdornment: <Person sx={{ mr: 1, color: 'text.secondary' }} />
                }}
              />
            </div>

            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="contained"
              onClick={handleDemoLogin}
              startIcon={<Login />}
              size="large"
              fullWidth
              sx={{ py: 1.5 }}
            >
              Continue with Demo Mode
            </button>

            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ width: '100%' }}>
              <div  variant="caption">
                This creates a temporary demo session. No real authentication is performed.
                All data will be mock/demo data until the backend database is connected.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuthFallback;