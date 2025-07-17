import React, { createContext, useContext, useReducer, useEffect } from 'react';
import { fetchAuthSession, signIn, signUp, confirmSignUp, signOut, resetPassword, confirmResetPassword, getCurrentUser } from '@aws-amplify/auth';
import SessionManager from '../components/auth/SessionManager';

// Initial auth state
const initialState = {
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,
  tokens: null
};

// Auth actions
const AUTH_ACTIONS = {
  LOADING: 'LOADING',
  LOGIN_SUCCESS: 'LOGIN_SUCCESS',
  LOGIN_FAILURE: 'LOGIN_FAILURE',
  LOGOUT: 'LOGOUT',
  SET_ERROR: 'SET_ERROR',
  CLEAR_ERROR: 'CLEAR_ERROR',
  UPDATE_TOKENS: 'UPDATE_TOKENS'
};

// Auth reducer
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
        error: null
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
        error: null
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
    default:
      return state;
  }
}

// Create auth context
const AuthContext = createContext();

// Auth provider component
export function AuthProvider({ children }) {
  const [state, dispatch] = useReducer(authReducer, initialState);

  // Check if user is authenticated on app start
  useEffect(() => {
    checkAuthState();
  }, []);

  const checkAuthState = async () => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      
      // Check if Cognito is properly configured
      const cognitoConfig = window.__CONFIG__?.COGNITO;
      const isCognitoValid = cognitoConfig?.USER_POOL_ID && 
                            cognitoConfig?.CLIENT_ID && 
                            !cognitoConfig.USER_POOL_ID.includes('MISSING') &&
                            !cognitoConfig.CLIENT_ID.includes('missing');
      
      if (!isCognitoValid) {
        console.warn('⚠️ Cognito misconfigured, checking for demo session');
        const demoUser = localStorage.getItem('demo-user');
        if (demoUser) {
          const user = JSON.parse(demoUser);
          dispatch({
            type: AUTH_ACTIONS.LOGIN_SUCCESS,
            payload: {
              user: {
                username: user.name || user.email,
                userId: user.id,
                email: user.email,
                firstName: user.name?.split(' ')[0] || '',
                lastName: user.name?.split(' ')[1] || '',
                isDemoUser: true
              },
              tokens: {
                accessToken: user.signInUserSession?.accessToken?.jwtToken || 'demo-token',
                idToken: user.signInUserSession?.idToken?.jwtToken || 'demo-token'
              }
            }
          });
          return;
        } else {
          // No demo session, user needs to authenticate via fallback
          dispatch({ type: AUTH_ACTIONS.LOGOUT });
          return;
        }
      }
      
      // COGNITO ONLY - Use real authentication
      console.log('🚀 Using AWS Cognito authentication');
      
      try {
        // Get current authenticated user
        const user = await getCurrentUser();
        
        // Get current session with tokens
        const session = await fetchAuthSession();
        
        if (user && session.tokens) {
          const tokens = {
            accessToken: session.tokens.accessToken.toString(),
            idToken: session.tokens.idToken?.toString(),
            refreshToken: session.tokens.refreshToken?.toString()
          };
          
          // Store access token for API requests
          localStorage.setItem('accessToken', tokens.accessToken);
          
          dispatch({
            type: AUTH_ACTIONS.LOGIN_SUCCESS,
            payload: {
              user: {
                username: user.username,
                userId: user.userId,
                email: user.signInDetails?.loginId || user.username,
                firstName: user.userAttributes?.given_name || '',
                lastName: user.userAttributes?.family_name || '',
                signInDetails: user.signInDetails
              },
              tokens
            }
          });
          console.log('✅ User authenticated with Cognito');
          return;
        }
      } catch (error) {
        console.log('No Cognito session found:', error);
      }
      
      // No valid session found
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
    } catch (error) {
      console.error('Error checking auth state:', error);
      dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: error.message });
    } finally {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });
    }
  };

  const login = async (username, password) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      console.log('🔐 Signing in with Cognito...');
      
      // Clear any local state first
      localStorage.removeItem('accessToken');
      
      // Try to sign out first if there's already a signed in user
      try {
        await signOut();
        console.log('🧹 Cleared existing session before sign in');
        // Wait a moment for signOut to complete
        await new Promise(resolve => setTimeout(resolve, 500));
      } catch (error) {
        console.log('No existing session to clear:', error.message);
      }
      
      const { isSignedIn, nextStep } = await signIn({ username, password });

      if (isSignedIn) {
        await checkAuthState(); // This will update the state with user info
        return { success: true };
      } else if (nextStep.signInStep === 'CONFIRM_SIGN_UP') {
        return { 
          success: false, 
          nextStep: 'CONFIRM_SIGN_UP',
          message: 'Please confirm your account with the verification code sent to your email.'
        };
      } else {
        return { 
          success: false, 
          message: 'Additional steps required for sign in.'
        };
      }
    } catch (error) {
      console.error('❌ Login error:', error);
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

  const logout = async () => {
    try {
      console.log('🚪 Signing out...');
      
      // Clear local storage first
      localStorage.removeItem('accessToken');
      
      // Clear React state
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
      
      // Sign out from Cognito
      await signOut();
      
      console.log('✅ Logout successful');
      return { success: true };
    } catch (error) {
      console.error('❌ Logout error:', error);
      // Even if logout fails, we've already cleared local state
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
        
        localStorage.setItem('accessToken', tokens.accessToken);
        dispatch({ type: AUTH_ACTIONS.UPDATE_TOKENS, payload: tokens });
        return tokens;
      }
    } catch (error) {
      console.error('❌ Token refresh error:', error);
      await logout();
      throw error;
    }
  };

  const value = {
    user: state.user,
    isAuthenticated: state.isAuthenticated,
    isLoading: state.isLoading,
    error: state.error,
    tokens: state.tokens,
    login,
    register,
    confirmRegistration,
    logout,
    resetPasswordRequest,
    confirmPasswordReset,
    forgotPassword: resetPasswordRequest, // Alias for Settings.jsx compatibility
    clearError,
    refreshTokens,
    checkAuthState
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