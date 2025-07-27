import React, { createContext, useContext, useReducer, useEffect } from 'react';
import { fetchAuthSession, signIn, signUp, confirmSignUp, confirmSignIn, signOut, resetPassword, confirmResetPassword, getCurrentUser } from '@aws-amplify/auth';
import SessionManager from '../components/auth/SessionManager';
import secureSessionStorage from '../utils/secureSessionStorage';

// SIMPLIFIED AUTH CONTEXT - NAVIGATION REMOVED
// Authentication state management only - no navigation logic

// Enhanced retry configuration
const RETRY_CONFIG = {
  maxRetries: 3, // Reduced retries
  baseDelay: 1000,
  maxDelay: 10000, // Reduced max delay
  retryableErrors: [
    'NetworkError',
    'TimeoutError', 
    'ENOTFOUND',
    'ECONNREFUSED',
    'NETWORK_ERROR'
  ]
};

// Initial auth state - navigation removed
const initialState = {
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,
  tokens: null,
  retryCount: 0,
  maxRetries: RETRY_CONFIG.maxRetries,
  lastRetryTime: 0,
  mfaChallenge: null,
  mfaChallengeSession: null
};

// Auth actions - navigation actions removed
const AUTH_ACTIONS = {
  LOADING: 'LOADING',
  LOGIN_SUCCESS: 'LOGIN_SUCCESS',
  LOGIN_FAILURE: 'LOGIN_FAILURE',
  LOGOUT: 'LOGOUT',
  SET_ERROR: 'SET_ERROR',
  CLEAR_ERROR: 'CLEAR_ERROR',
  UPDATE_TOKENS: 'UPDATE_TOKENS',
  INCREMENT_RETRY: 'INCREMENT_RETRY',
  RESET_RETRIES: 'RESET_RETRIES',
  MFA_CHALLENGE: 'MFA_CHALLENGE',
  MFA_SUCCESS: 'MFA_SUCCESS',
  CLEAR_MFA: 'CLEAR_MFA'
};

// Simplified auth reducer - no navigation state
function authReducer(state, action) {
  switch (action.type) {
    case AUTH_ACTIONS.LOADING:
      return {
        ...state,
        isLoading: action.payload
      };
    case AUTH_ACTIONS.LOGIN_SUCCESS:
      return {
        ...state,
        user: action.payload.user,
        tokens: action.payload.tokens,
        isAuthenticated: true,
        isLoading: false,
        error: null,
        retryCount: 0 // Reset on success
      };
    case AUTH_ACTIONS.LOGIN_FAILURE:
      return {
        ...state,
        user: null,
        tokens: null,
        isAuthenticated: false,
        isLoading: false,
        error: action.payload
      };
    case AUTH_ACTIONS.LOGOUT:
      return {
        ...state,
        user: null,
        tokens: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
        retryCount: 0
      };
    case AUTH_ACTIONS.SET_ERROR:
      return {
        ...state,
        error: action.payload,
        isLoading: false
      };
    case AUTH_ACTIONS.CLEAR_ERROR:
      return {
        ...state,
        error: null
      };
    case AUTH_ACTIONS.UPDATE_TOKENS:
      return {
        ...state,
        tokens: action.payload
      };
    case AUTH_ACTIONS.INCREMENT_RETRY:
      return {
        ...state,
        retryCount: state.retryCount + 1,
        lastRetryTime: Date.now()
      };
    case AUTH_ACTIONS.RESET_RETRIES:
      return {
        ...state,
        retryCount: 0,
        lastRetryTime: 0
      };
    case AUTH_ACTIONS.MFA_CHALLENGE:
      return {
        ...state,
        mfaChallenge: action.payload.challenge,
        mfaChallengeSession: action.payload.session,
        isLoading: false,
        error: null
      };
    case AUTH_ACTIONS.MFA_SUCCESS:
      return {
        ...state,
        mfaChallenge: null,
        mfaChallengeSession: null
      };
    case AUTH_ACTIONS.CLEAR_MFA:
      return {
        ...state,
        mfaChallenge: null,
        mfaChallengeSession: null,
        error: null
      };
    default:
      return state;
  }
}

// Create auth context
const AuthContext = createContext();

// Simplified auth provider - no navigation logic
export function AuthProvider({ children }) {
  const [state, dispatch] = useReducer(authReducer, initialState);

  // Check authentication on app start - simplified
  useEffect(() => {
    checkAuthState();
  }, []);

  // Helper function to check if error is retryable
  const isRetryableError = (error) => {
    if (!error) return false;
    const errorString = error.toString().toLowerCase();
    return RETRY_CONFIG.retryableErrors.some(retryableError => 
      errorString.includes(retryableError.toLowerCase())
    );
  };

  // Calculate exponential backoff delay
  const getBackoffDelay = (retryCount) => {
    const delay = Math.min(
      RETRY_CONFIG.baseDelay * Math.pow(2, retryCount),
      RETRY_CONFIG.maxDelay
    );
    return delay + Math.random() * 1000; // Add jitter
  };

  // IMPROVED checkAuthState - better state management and token consistency
  const checkAuthState = async (forceRetry = false) => {
    const now = Date.now();
    const timeSinceLastRetry = now - state.lastRetryTime;
    const backoffDelay = getBackoffDelay(state.retryCount);
    
    // Improved retry logic - don't increment retries on successful calls
    if (!forceRetry && state.retryCount >= state.maxRetries) {
      console.warn('🛑 Auth retry limit reached.');
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: 'Authentication service temporarily unavailable.' });
      return { success: false, reason: 'retry_limit' };
    }
    
    if (!forceRetry && timeSinceLastRetry < backoffDelay) {
      console.warn(`🛑 Auth retry backoff active. Wait ${Math.ceil((backoffDelay - timeSinceLastRetry) / 1000)}s`);
      return { success: false, reason: 'backoff' };
    }
    
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      
      // Only increment retry on actual attempts, not successful checks
      if (!forceRetry) {
        dispatch({ type: AUTH_ACTIONS.INCREMENT_RETRY });
      }
      
      // Clear any demo/fallback sessions
      localStorage.removeItem('demo-user');
      sessionStorage.removeItem('demo-user');
      
      // Initialize runtime configuration
      try {
        const { initializeRuntimeConfig } = await import('../services/runtimeConfig');
        await initializeRuntimeConfig();
        console.log('✅ Runtime configuration loaded');
      } catch (runtimeError) {
        console.warn('⚠️ Runtime config failed:', runtimeError);
      }
      
      // Check Cognito configuration
      const { FEATURES } = await import('../config/environment');
      const { isCognitoConfigured } = await import('../config/amplify');
      
      if (!FEATURES.authentication.enabled || !FEATURES.authentication.methods.cognito || !isCognitoConfigured()) {
        console.warn('❌ Cognito not configured properly');
        dispatch({ type: AUTH_ACTIONS.LOGOUT });
        return { success: false, reason: 'config' };
      }
      
      // First check if we have existing valid tokens in secure storage
      const existingTokens = secureSessionStorage.getTokens();
      if (existingTokens.accessToken) {
        console.log('🔄 Found existing tokens, validating...');
        
        try {
          // Try to get current user with existing session
          const user = await getCurrentUser();
          if (user) {
            // Session is still valid, update our state
            const mfaEnabled = user.userAttributes?.['custom:mfa_enabled'] === 'true' || 
                               user.userAttributes?.phone_number_verified === 'true' ||
                               false;

            dispatch({
              type: AUTH_ACTIONS.LOGIN_SUCCESS,
              payload: {
                user: {
                  username: user.username,
                  userId: user.userId,
                  email: user.signInDetails?.loginId || user.username,
                  firstName: user.userAttributes?.given_name || '',
                  lastName: user.userAttributes?.family_name || '',
                  signInDetails: user.signInDetails,
                  mfaEnabled: mfaEnabled
                },
                tokens: existingTokens
              }
            });
            
            dispatch({ type: AUTH_ACTIONS.RESET_RETRIES });
            console.log('✅ User authenticated with existing session');
            return { success: true, reason: 'existing_session' };
          }
        } catch (error) {
          console.log('Existing session invalid, getting fresh session...');
        }
      }
      
      // Try to get fresh session from Cognito
      try {
        const user = await getCurrentUser();
        const session = await fetchAuthSession();
        
        if (user && session.tokens) {
          const tokens = {
            accessToken: session.tokens.accessToken.toString(),
            idToken: session.tokens.idToken?.toString(),
            refreshToken: session.tokens.refreshToken?.toString()
          };
          
          // FIXED: Use only secureSessionStorage for consistency
          const tokenData = {
            ...tokens,
            userId: user.userId,
            username: user.username,
            email: user.signInDetails?.loginId || user.username
          };
          secureSessionStorage.storeTokens(tokenData);
          
          // REMOVED: localStorage.setItem('accessToken', tokens.accessToken);
          // This was causing storage inconsistency issues

          const mfaEnabled = user.userAttributes?.['custom:mfa_enabled'] === 'true' || 
                             user.userAttributes?.phone_number_verified === 'true' ||
                             false;

          dispatch({
            type: AUTH_ACTIONS.LOGIN_SUCCESS,
            payload: {
              user: {
                username: user.username,
                userId: user.userId,
                email: user.signInDetails?.loginId || user.username,
                firstName: user.userAttributes?.given_name || '',
                lastName: user.userAttributes?.family_name || '',
                signInDetails: user.signInDetails,
                mfaEnabled: mfaEnabled
              },
              tokens
            }
          });
          
          dispatch({ type: AUTH_ACTIONS.RESET_RETRIES });
          console.log('✅ User authenticated with fresh Cognito session');
          return { success: true, reason: 'fresh_session' };
        }
      } catch (error) {
        console.log('No Cognito session found:', error);
      }
      
      // No valid session found
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
      return { success: false, reason: 'no_session' };
    } catch (error) {
      console.error('Error checking auth state:', error);
      
      if (isRetryableError(error) && state.retryCount < state.maxRetries) {
        console.warn('⚠️ Retryable error encountered:', error.message);
        dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: error.message });
        return { success: false, reason: 'retryable_error' };
      } else {
        console.error('❌ Authentication error:', error.message);
        dispatch({ type: AUTH_ACTIONS.LOGOUT });
        return { success: false, reason: 'auth_error' };
      }
    } finally {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });
    }
  };

  // Login method - simplified, no navigation
  const login = async (username, password) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      console.log('🔐 Signing in with Cognito...');
      
      // Clear any existing tokens first
      secureSessionStorage.clearSession();
      
      // Try to sign out first if there's already a session
      try {
        await signOut();
        await new Promise(resolve => setTimeout(resolve, 500));
      } catch (error) {
        console.log('No existing session to clear:', error.message);
      }
      
      const { isSignedIn, nextStep } = await signIn({ username, password });

      if (isSignedIn) {
        dispatch({ type: AUTH_ACTIONS.RESET_RETRIES });
        await checkAuthState(true);
        return { success: true };
      } else if (nextStep.signInStep === 'CONFIRM_SIGN_UP') {
        return { 
          success: false, 
          nextStep: 'CONFIRM_SIGN_UP',
          message: 'Please confirm your account with the verification code sent to your email.'
        };
      } else if (nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_SMS_MFA_CODE') {
        dispatch({ 
          type: AUTH_ACTIONS.MFA_CHALLENGE, 
          payload: { 
            challenge: 'SMS_MFA',
            session: nextStep,
            destination: nextStep.additionalInfo?.destination || 'your phone'
          }
        });
        return { 
          success: false, 
          nextStep: 'MFA_CHALLENGE',
          challengeType: 'SMS_MFA',
          message: `Enter the verification code sent to ${nextStep.additionalInfo?.destination || 'your phone'}.`
        };
      } else if (nextStep.signInStep === 'CONFIRM_SIGN_IN_WITH_TOTP_MFA_CODE') {
        dispatch({ 
          type: AUTH_ACTIONS.MFA_CHALLENGE, 
          payload: { 
            challenge: 'TOTP_MFA',
            session: nextStep
          }
        });
        return { 
          success: false, 
          nextStep: 'MFA_CHALLENGE',
          challengeType: 'TOTP_MFA',
          message: 'Enter the code from your authenticator app.'
        };
      } else {
        return { 
          success: false, 
          message: `Additional steps required for sign in: ${nextStep.signInStep}`
        };
      }
    } catch (error) {
      console.error('❌ Login error:', error);
      dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: error.message });
      return { success: false, message: error.message };
    }
  };

  const confirmMFA = async (challengeResponse) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      const { isSignedIn } = await confirmSignIn({ challengeResponse });

      if (isSignedIn) {
        dispatch({ type: AUTH_ACTIONS.MFA_SUCCESS });
        await checkAuthState(true);
        return { success: true };
      } else {
        return { success: false, message: 'MFA verification failed' };
      }
    } catch (error) {
      dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: error.message });
      return { success: false, message: error.message };
    }
  };

  const register = async (username, password, email, firstName, lastName) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      console.log('📝 Registering with Cognito...');
      const { isSignUpComplete, userId, nextStep } = await signUp({
        username,
        password,
        options: {
          userAttributes: {
            email,
            given_name: firstName,
            family_name: lastName
          }
        }
      });

      if (isSignUpComplete) {
        return { success: true, message: 'Registration successful!' };
      } else if (nextStep.signUpStep === 'CONFIRM_SIGN_UP') {
        return { 
          success: false, 
          nextStep: 'CONFIRM_SIGN_UP',
          message: 'Please check your email for a verification code.'
        };
      } else {
        return { 
          success: false, 
          message: 'Additional steps required for registration.'
        };
      }
    } catch (error) {
      console.error('❌ Registration error:', error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: error.message });
      return { success: false, message: error.message };
    }
  };

  const confirmRegistration = async (username, confirmationCode) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      
      console.log('✅ Confirming registration...');
      const { isSignUpComplete, nextStep } = await confirmSignUp({
        username,
        confirmationCode
      });

      if (isSignUpComplete) {
        return { success: true, message: 'Account confirmed successfully!' };
      } else {
        return { 
          success: false, 
          message: 'Additional steps required.'
        };
      }
    } catch (error) {
      console.error('❌ Confirmation error:', error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: error.message });
      return { success: false, message: error.message };
    } finally {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });
    }
  };

  // Logout - simplified, no navigation
  const logout = async () => {
    try {
      console.log('🚪 Signing out...');
      
      // Clear all stored tokens consistently
      secureSessionStorage.clearSession();
      
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
      await signOut();
      
      console.log('✅ Logout successful');
      return { success: true };
    } catch (error) {
      console.error('❌ Logout error:', error);
      return { success: false, message: error.message };
    }
  };

  const resetPasswordRequest = async (username) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      
      console.log('🔄 Requesting password reset...');
      const output = await resetPassword({ username });
      
      return { 
        success: true, 
        message: 'Password reset code sent to your email.',
        nextStep: output.nextStep
      };
    } catch (error) {
      console.error('❌ Password reset error:', error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: error.message });
      return { success: false, message: error.message };
    } finally {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });
    }
  };

  const confirmPasswordReset = async (username, confirmationCode, newPassword) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      
      console.log('🔄 Confirming password reset...');
      await confirmResetPassword({ username, confirmationCode, newPassword });
      
      return { success: true, message: 'Password reset successfully!' };
    } catch (error) {
      console.error('❌ Password reset confirmation error:', error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: error.message });
      return { success: false, message: error.message };
    } finally {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });
    }
  };

  const clearError = () => {
    dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });
  };

  const refreshTokens = async () => {
    try {
      const session = await fetchAuthSession();
      if (session.tokens) {
        const tokens = {
          accessToken: session.tokens.accessToken.toString(),
          idToken: session.tokens.idToken?.toString(),
          refreshToken: session.tokens.refreshToken?.toString()
        };
        
        const tokenData = {
          ...tokens,
          userId: state.user?.userId,
          username: state.user?.username,
          email: state.user?.email
        };
        secureSessionStorage.storeTokens(tokenData);
        dispatch({ type: AUTH_ACTIONS.UPDATE_TOKENS, payload: tokens });
        return tokens;
      }
    } catch (error) {
      console.error('❌ Token refresh error:', error);
      await logout();
      throw error;
    }
  };

  const updateUserMfaStatus = (mfaEnabled) => {
    if (state.user) {
      dispatch({
        type: AUTH_ACTIONS.LOGIN_SUCCESS,
        payload: {
          user: {
            ...state.user,
            mfaEnabled: mfaEnabled
          },
          tokens: state.tokens
        }
      });
    }
  };

  // Simplified value object - no navigation methods
  const value = {
    user: state.user,
    isAuthenticated: state.isAuthenticated,
    isLoading: state.isLoading,
    error: state.error,
    tokens: state.tokens,
    mfaChallenge: state.mfaChallenge,
    mfaChallengeSession: state.mfaChallengeSession,
    login,
    confirmMFA,
    register,
    confirmRegistration,
    logout,
    resetPasswordRequest,
    confirmPasswordReset,
    forgotPassword: resetPasswordRequest, // Alias for Settings.jsx compatibility
    clearError,
    refreshTokens,
    checkAuthState,
    updateUserMfaStatus,
    retryCount: state.retryCount,
    maxRetries: state.maxRetries
  };

  return (
    <AuthContext.Provider value={value}>
      <SessionManager>
        {children}
      </SessionManager>
    </AuthContext.Provider>
  );
}

// Custom hook to use auth context
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;