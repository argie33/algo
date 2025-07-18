import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';

const AuthTest = () => {
  const auth = useAuth();
  const [debugInfo, setDebugInfo] = useState([]);

  const addDebugInfo = (message) => {
    const timestamp = new Date().toLocaleTimeString();
    const logMessage = `${timestamp}: ${message}`;
    console.log('🔐 AUTH DEBUG:', logMessage);
    setDebugInfo(prev => [...prev, logMessage]);
  };

  useEffect(() => {
    addDebugInfo('AuthTest component mounted');
    addDebugInfo(`Initial auth state: loading=${auth.isLoading}, authenticated=${auth.isAuthenticated}`);
  }, []);

  useEffect(() => {
    addDebugInfo(`Auth state changed: loading=${auth.isLoading}, authenticated=${auth.isAuthenticated}, user=${auth.user?.username || 'none'}`);
  }, [auth.isLoading, auth.isAuthenticated, auth.user]);

  const loginWithTestUser = async () => {
    addDebugInfo('Attempting to login with test user...');
    try {
      const result = await auth.login('testuser', 'testpass');
      addDebugInfo(`Login result: ${JSON.stringify(result)}`);
    } catch (error) {
      addDebugInfo(`Login error: ${error.message}`);
    }
  };

  const logout = async () => {
    addDebugInfo('Attempting to logout...');
    try {
      await auth.logout();
      addDebugInfo('Logout successful');
    } catch (error) {
      addDebugInfo(`Logout error: ${error.message}`);
    }
  };

  const checkAuthState = async () => {
    addDebugInfo('Manually checking auth state...');
    try {
      await auth.checkAuthState();
      addDebugInfo('Auth state check completed');
    } catch (error) {
      addDebugInfo(`Auth state check error: ${error.message}`);
    }
  };

  return (
    <div className="container mx-auto" maxWidth="md">
      <div  variant="h4" gutterBottom>
        Authentication Test Page
      </div>

      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Current Auth State:
          </div>
          <div>Loading: {auth.isLoading ? '⏳ Yes' : '✅ No'}</div>
          <div>Authenticated: {auth.isAuthenticated ? '✅ Yes' : '❌ No'}</div>
          <div>User: {auth.user ? `✅ ${auth.user.username}` : '❌ None'}</div>
          <div>Error: {auth.error || '❌ None'}</div>
          <div>Tokens: {auth.tokens ? '✅ Present' : '❌ None'}</div>
          
          <div  sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={loginWithTestUser} variant="contained" size="small">
              Login Test User
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={logout} variant="outlined" size="small">
              Logout
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={checkAuthState} variant="outlined" size="small">
              Check Auth State
            </button>
          </div>
        </div>
      </div>

      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Local Storage Tokens:
          </div>
          <div>accessToken: {localStorage.getItem('accessToken') ? '✅ Present' : '❌ Missing'}</div>
          <div>authToken: {localStorage.getItem('authToken') ? '✅ Present' : '❌ Missing'}</div>
        </div>
      </div>

      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Debug Log ({debugInfo.length} entries):
          </div>
          <div  sx={{ maxHeight: 300, overflow: 'auto', bgcolor: 'grey.50', p: 1 }}>
            {debugInfo.map((info, index) => (
              <div  
                key={index} 
                variant="body2" 
                sx={{ 
                  fontFamily: 'monospace', 
                  marginBottom: '2px',
                  fontSize: '0.75rem'
                }}
              >
                {info}
              </div>
            ))}
          </div>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
            onClick={() => setDebugInfo([])} 
            variant="outlined" 
            size="small" 
            sx={{ mt: 1 }}
          >
            Clear Log
          </button>
        </div>
      </div>
    </div>
  );
};

export default AuthTest;