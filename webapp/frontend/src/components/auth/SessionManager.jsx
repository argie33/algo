import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { 
  Dialog, 
  DialogContent, 
  Typography, 
  Button, 
  Box, 
  LinearProgress,
  Alert,
  IconButton,
  Snackbar
} from '@mui/material';
import { fetchAuthSession } from '@aws-amplify/auth';

// Session management configuration
const SESSION_CONFIG = {
  WARNING_THRESHOLD: 5 * 60 * 1000, // 5 minutes before expiry
  AUTO_REFRESH_THRESHOLD: 10 * 60 * 1000, // 10 minutes before expiry
  CHECK_INTERVAL: 30 * 1000, // Check every 30 seconds
  IDLE_TIMEOUT: 30 * 60 * 1000, // 30 minutes of inactivity
  MAX_REFRESH_ATTEMPTS: 3,
  SESSION_STORAGE_KEY: 'session_info'
};

// Activity tracking for idle timeout
class ActivityTracker {
  constructor(onIdle, idleTimeout = SESSION_CONFIG.IDLE_TIMEOUT) {
    this.onIdle = onIdle;
    this.idleTimeout = idleTimeout;
    this.lastActivity = Date.now();
    this.idleTimer = null;
    
    this.events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'];
    this.init();
  }

  init() {
    this.events.forEach(event => {
      document.addEventListener(event, this.resetTimer.bind(this), true);
    });
    this.resetTimer();
  }

  resetTimer() {
    this.lastActivity = Date.now();
    if (this.idleTimer) {
      clearTimeout(this.idleTimer);
    }
    
    this.idleTimer = setTimeout(() => {
      this.onIdle();
    }, this.idleTimeout);
  }

  destroy() {
    if (this.idleTimer) {
      clearTimeout(this.idleTimer);
    }
    
    this.events.forEach(event => {
      document.removeEventListener(event, this.resetTimer.bind(this), true);
    });
  }

  getIdleTime() {
    return Date.now() - this.lastActivity;
  }
}

// Session context for sharing session state
const SessionContext = createContext();

export const useSession = () => {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return context;
};

function SessionManager({ children }) {
  const { user, tokens, refreshTokens, logout, isAuthenticated } = useAuth();
  const [sessionInfo, setSessionInfo] = useState(null);
  const [timeToExpiry, setTimeToExpiry] = useState(null);
  const [showWarning, setShowWarning] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshAttempts, setRefreshAttempts] = useState(0);
  const [isIdle, setIsIdle] = useState(false);
  const [showIdleWarning, setShowIdleWarning] = useState(false);
  const [activityTracker, setActivityTracker] = useState(null);
  const [sessionExtended, setSessionExtended] = useState(false);

  // Initialize session tracking
  useEffect(() => {
    if (isAuthenticated && tokens) {
      initializeSession();
    } else {
      cleanupSession();
    }

    return () => cleanupSession();
  }, [isAuthenticated, tokens]);

  // Session monitoring interval
  useEffect(() => {
    if (!isAuthenticated || !sessionInfo) return;

    const interval = setInterval(() => {
      checkSessionStatus();
    }, SESSION_CONFIG.CHECK_INTERVAL);

    return () => clearInterval(interval);
  }, [sessionInfo, isAuthenticated]);

  const initializeSession = useCallback(() => {
    if (!tokens?.accessToken) return;

    try {
      // Parse token to get expiry
      const tokenPayload = JSON.parse(atob(tokens.accessToken.split('.')[1]));
      const expiryTime = tokenPayload.exp * 1000;
      const currentTime = Date.now();
      
      const sessionData = {
        userId: user?.sub,
        username: user?.username,
        email: user?.email,
        tokenIssuedAt: tokenPayload.iat * 1000,
        tokenExpiresAt: expiryTime,
        sessionStarted: currentTime,
        lastActivity: currentTime,
        refreshCount: 0
      };

      setSessionInfo(sessionData);
      
      // Store session info
      sessionStorage.setItem(SESSION_CONFIG.SESSION_STORAGE_KEY, JSON.stringify(sessionData));

      // Initialize activity tracking
      if (activityTracker) {
        activityTracker.destroy();
      }
      
      const tracker = new ActivityTracker(handleIdleTimeout);
      setActivityTracker(tracker);
      
      console.log('Session initialized:', sessionData);
    } catch (error) {
      console.error('Failed to initialize session:', error);
    }
  }, [tokens, user, activityTracker]);

  const checkSessionStatus = useCallback(() => {
    if (!sessionInfo) return;

    const currentTime = Date.now();
    const timeUntilExpiry = sessionInfo.tokenExpiresAt - currentTime;
    
    setTimeToExpiry(timeUntilExpiry);

    // Auto-refresh if approaching expiry
    if (timeUntilExpiry <= SESSION_CONFIG.AUTO_REFRESH_THRESHOLD && 
        timeUntilExpiry > 0 && 
        !isRefreshing &&
        refreshAttempts < SESSION_CONFIG.MAX_REFRESH_ATTEMPTS) {
      handleTokenRefresh();
    }
    
    // Show warning if very close to expiry
    else if (timeUntilExpiry <= SESSION_CONFIG.WARNING_THRESHOLD && timeUntilExpiry > 0) {
      setShowWarning(true);
    }
    
    // Force logout if token has expired
    else if (timeUntilExpiry <= 0) {
      handleSessionExpiry();
    }
  }, [sessionInfo, isRefreshing, refreshAttempts]);

  const handleTokenRefresh = useCallback(async () => {
    if (isRefreshing) return;

    try {
      setIsRefreshing(true);
      setRefreshAttempts(prev => prev + 1);
      
      console.log('Attempting token refresh...');
      const newTokens = await refreshTokens();
      
      if (newTokens) {
        // Update session info with new token expiry
        const tokenPayload = JSON.parse(atob(newTokens.accessToken.split('.')[1]));
        const updatedSessionInfo = {
          ...sessionInfo,
          tokenExpiresAt: tokenPayload.exp * 1000,
          refreshCount: sessionInfo.refreshCount + 1,
          lastRefresh: Date.now()
        };
        
        setSessionInfo(updatedSessionInfo);
        sessionStorage.setItem(SESSION_CONFIG.SESSION_STORAGE_KEY, JSON.stringify(updatedSessionInfo));
        
        setRefreshAttempts(0);
        setShowWarning(false);
        setSessionExtended(true);
        
        // Hide extended message after 3 seconds
        setTimeout(() => setSessionExtended(false), 3000);
        
        console.log('Token refreshed successfully');
      }
    } catch (error) {
      console.error('Token refresh failed:', error);
      
      if (refreshAttempts >= SESSION_CONFIG.MAX_REFRESH_ATTEMPTS) {
        handleSessionExpiry();
      }
    } finally {
      setIsRefreshing(false);
    }
  }, [isRefreshing, refreshAttempts, sessionInfo, refreshTokens]);

  const handleSessionExpiry = useCallback(() => {
    console.log('Session expired, logging out...');
    setShowWarning(false);
    setShowIdleWarning(false);
    cleanupSession();
    logout();
  }, [logout]);

  const handleIdleTimeout = useCallback(() => {
    setIsIdle(true);
    setShowIdleWarning(true);
  }, []);

  const handleContinueSession = useCallback(() => {
    setIsIdle(false);
    setShowIdleWarning(false);
    
    // Reset activity tracker
    if (activityTracker) {
      activityTracker.resetTimer();
    }
  }, [activityTracker]);

  const handleIdleLogout = useCallback(() => {
    console.log('User idle timeout, logging out...');
    setShowIdleWarning(false);
    cleanupSession();
    logout();
  }, [logout]);

  const cleanupSession = useCallback(() => {
    if (activityTracker) {
      activityTracker.destroy();
      setActivityTracker(null);
    }
    
    setSessionInfo(null);
    setTimeToExpiry(null);
    setShowWarning(false);
    setIsRefreshing(false);
    setRefreshAttempts(0);
    setIsIdle(false);
    setShowIdleWarning(false);
    
    sessionStorage.removeItem(SESSION_CONFIG.SESSION_STORAGE_KEY);
  }, [activityTracker]);

  const extendSession = useCallback(() => {
    setShowWarning(false);
    handleTokenRefresh();
  }, [handleTokenRefresh]);

  const formatTimeRemaining = (milliseconds) => {
    if (milliseconds <= 0) return 'Expired';
    
    const minutes = Math.floor(milliseconds / (1000 * 60));
    const seconds = Math.floor((milliseconds % (1000 * 60)) / 1000);
    
    if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    }
    return `${seconds}s`;
  };

  const getSessionProgress = () => {
    if (!sessionInfo || !timeToExpiry) return 100;
    
    const totalSessionTime = sessionInfo.tokenExpiresAt - sessionInfo.tokenIssuedAt;
    const timeElapsed = totalSessionTime - timeToExpiry;
    return Math.max(0, Math.min(100, (timeElapsed / totalSessionTime) * 100));
  };

  const sessionContextValue = {
    sessionInfo,
    timeToExpiry,
    isRefreshing,
    isIdle,
    refreshSession: handleTokenRefresh,
    extendSession,
    getSessionProgress,
    formatTimeRemaining
  };

  return (
    <SessionContext.Provider value={sessionContextValue}>
      {children}
      
      {/* Session Expiry Warning Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
        open={showWarning} 
        onClose={() => {}} 
        maxWidth="sm" 
        fullWidth
        disableEscapeKeyDown
      >
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content sx={{ textAlign: 'center', py: 4 }}>
          <Warning sx={{ fontSize: 64, color: 'warning.main', mb: 2 }} />
          <div  variant="h6" gutterBottom>
            Session Expiring Soon
          </div>
          <div  variant="body1" color="text.secondary" gutterBottom>
            Your session will expire in {formatTimeRemaining(timeToExpiry)}
          </div>
          
          <div  sx={{ mt: 3, mb: 3 }}>
            <div className="w-full bg-gray-200 rounded-full h-2" 
              variant="determinate" 
              value={100 - getSessionProgress()} 
              color="warning"
              sx={{ height: 8, borderRadius: 4 }}
            />
          </div>
          
          {isRefreshing && (
            <div  sx={{ mb: 2 }}>
              <div className="w-full bg-gray-200 rounded-full h-2" />
              <div  variant="caption" color="text.secondary">
                Refreshing session...
              </div>
            </div>
          )}
          
          <div  sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              onClick={handleSessionExpiry}
              disabled={isRefreshing}
            >
              Logout
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="contained"
              onClick={extendSession}
              disabled={isRefreshing}
              startIcon={<Security />}
            >
              Extend Session
            </button>
          </div>
        </div>
      </div>

      {/* Idle Warning Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
        open={showIdleWarning} 
        onClose={() => {}} 
        maxWidth="sm" 
        fullWidth
        disableEscapeKeyDown
      >
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content sx={{ textAlign: 'center', py: 4 }}>
          <Schedule sx={{ fontSize: 64, color: 'info.main', mb: 2 }} />
          <div  variant="h6" gutterBottom>
            Are you still there?
          </div>
          <div  variant="body1" color="text.secondary" gutterBottom>
            You've been inactive for a while. For security, your session will end automatically.
          </div>
          
          <div  sx={{ display: 'flex', gap: 2, justifyContent: 'center', mt: 3 }}>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              onClick={handleIdleLogout}
            >
              Logout
            </button>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="contained"
              onClick={handleContinueSession}
            >
              Continue Session
            </button>
          </div>
        </div>
      </div>

      {/* Session Extended Notification */}
      <div className="fixed bottom-4 right-4 bg-gray-800 text-white p-4 rounded-md shadow-lg"
        open={sessionExtended}
        autoHideDuration={3000}
        onClose={() => setSessionExtended(false)}
        anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
      >
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          onClose={() => setSessionExtended(false)} 
          severity="success"
          variant="filled"
          action={
            <button className="p-2 rounded-full hover:bg-gray-100" size="small" color="inherit" onClick={() => setSessionExtended(false)}>
              <Close fontSize="small" />
            </button>
          }
        >
          Session successfully extended
        </div>
      </div>
    </SessionContext.Provider>
  );
}

export default SessionManager;