import React, { createContext, useContext, useReducer, useEffect } from 'react';
import { fetchAuthSession, signIn, signUp, confirmSignUp, signOut, resetPassword, confirmResetPassword, getCurrentUser } from '@aws-amplify/auth';
import { isCognitoConfigured } from '../config/amplify';
import devAuth from '../services/devAuth';

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
      
      // DEVELOPMENT MODE - Auto-login with test user
      const isDevelopmentMode = import.meta.env.DEV || !isCognitoConfigured();
      
      if (isDevelopmentMode) {
        console.log('🔧 DEVELOPMENT MODE - Auto-login enabled');
        
        // Create a mock development user
        const devUser = {
          username: 'dev_user',
          userId: 'dev-user-123',
          email: 'dev@example.com',
          firstName: 'Developer',
          lastName: 'User',
          isPremium: true // Enable all features in dev mode
        };
        
        const devTokens = {
          accessToken: 'dev-access-token',
          idToken: 'dev-id-token',
          refreshToken: 'dev-refresh-token'
        };
        
        dispatch({
          type: AUTH_ACTIONS.LOGIN_SUCCESS,
          payload: {
            user: devUser,
            tokens: devTokens
          }
        });
        
        console.log('✅ Development user logged in automatically');
        return;
      }
      
      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log('Cognito not configured - using development authentication');
        try {
          const user = await devAuth.getCurrentUser();
          const session = await devAuth.fetchAuthSession();
          
          if (user && session.tokens) {
            dispatch({
              type: AUTH_ACTIONS.LOGIN_SUCCESS,
              payload: {
                user,
                tokens: session.tokens
              }
            });
          } else {
            dispatch({ type: AUTH_ACTIONS.LOGOUT });
          }
        } catch (error) {
          console.log('No dev auth session found');
          dispatch({ type: AUTH_ACTIONS.LOGOUT });
        }
        return;
      }
      
      // Get current authenticated user
      const user = await getCurrentUser();
      
      // Get current session with tokens
      const session = await fetchAuthSession();
      
      if (user && session.tokens) {
        dispatch({
          type: AUTH_ACTIONS.LOGIN_SUCCESS,
          payload: {
            user: {
              username: user.username,
              userId: user.userId,
              signInDetails: user.signInDetails
            },
            tokens: {
              accessToken: session.tokens.accessToken.toString(),
              idToken: session.tokens.idToken?.toString(),
              refreshToken: session.tokens.refreshToken?.toString()
            }
          }
        });
      } else {
        dispatch({ type: AUTH_ACTIONS.LOGOUT });
      }
    } catch (error) {
      console.log('No authenticated user found:', error);
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
    }
  };

  const login = async (username, password) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log('Cognito not configured - using development authentication');
        try {
          const result = await devAuth.signIn(username, password);
          
          dispatch({
            type: AUTH_ACTIONS.LOGIN_SUCCESS,
            payload: {
              user: result.user,
              tokens: result.tokens
            }
          });
          
          return { success: true };
        } catch (error) {
          console.error('Dev auth login error:', error);
          const errorMessage = getErrorMessage(error);
          dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: errorMessage });
          return { success: false, error: errorMessage };
        }
      }

      const { isSignedIn, nextStep } = await signIn({
        username,
        password
      });

      if (isSignedIn) {
        // Get user and session after successful sign in
        const user = await getCurrentUser();
        const session = await fetchAuthSession();
        
        dispatch({
          type: AUTH_ACTIONS.LOGIN_SUCCESS,
          payload: {
            user: {
              username: user.username,
              userId: user.userId,
              signInDetails: user.signInDetails
            },
            tokens: {
              accessToken: session.tokens.accessToken.toString(),
              idToken: session.tokens.idToken?.toString(),
              refreshToken: session.tokens.refreshToken?.toString()
            }
          }
        });
        
        return { success: true };
      } else {
        // Handle additional steps (MFA, password change, etc.)
        return { 
          success: false, 
          nextStep: nextStep,
          message: 'Additional authentication step required'
        };
      }
    } catch (error) {
      console.error('Login error:', error);
      const errorMessage = getErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const register = async (username, password, email, firstName, lastName) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log('Cognito not configured - using development authentication');
        try {
          const result = await devAuth.signUp(username, password, email, firstName, lastName);
          
          dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });
          
          return {
            success: true,
            isComplete: result.isSignUpComplete,
            nextStep: result.nextStep,
            message: result.isSignUpComplete 
              ? 'Registration completed successfully'
              : 'Please check your email for verification code'
          };
        } catch (error) {
          console.error('Dev auth registration error:', error);
          const errorMessage = getErrorMessage(error);
          dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
          return { success: false, error: errorMessage };
        }
      }

      const { isSignUpComplete, nextStep } = await signUp({
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

      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

      return {
        success: true,
        isComplete: isSignUpComplete,
        nextStep: nextStep,
        message: isSignUpComplete 
          ? 'Registration completed successfully'
          : 'Please check your email for verification code'
      };
    } catch (error) {
      console.error('Registration error:', error);
      const errorMessage = getErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const confirmRegistration = async (username, confirmationCode) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log('Cognito not configured - using development authentication');
        try {
          const result = await devAuth.confirmSignUp(username, confirmationCode);
          
          dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });
          
          return {
            success: true,
            isComplete: result.isSignUpComplete,
            message: 'Account confirmed successfully. You can now sign in.'
          };
        } catch (error) {
          console.error('Dev auth confirmation error:', error);
          const errorMessage = getErrorMessage(error);
          dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
          return { success: false, error: errorMessage };
        }
      }

      const { isSignUpComplete } = await confirmSignUp({
        username,
        confirmationCode
      });

      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

      return {
        success: true,
        isComplete: isSignUpComplete,
        message: 'Account confirmed successfully. You can now sign in.'
      };
    } catch (error) {
      console.error('Confirmation error:', error);
      const errorMessage = getErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const logout = async () => {
    try {
      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log('Cognito not configured - using development authentication');
        await devAuth.signOut();
        dispatch({ type: AUTH_ACTIONS.LOGOUT });
        return { success: true };
      }

      await signOut();
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
      return { success: true };
    } catch (error) {
      console.error('Logout error:', error);
      // Even if logout fails, clear local state
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
      return { success: false, error: getErrorMessage(error) };
    }
  };

  const forgotPassword = async (username) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log('Cognito not configured - using development authentication');
        try {
          const result = await devAuth.resetPassword(username);
          
          dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });
          
          return {
            success: true,
            nextStep: result.nextStep,
            message: 'Password reset code sent to your email'
          };
        } catch (error) {
          console.error('Dev auth password reset error:', error);
          const errorMessage = getErrorMessage(error);
          dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
          return { success: false, error: errorMessage };
        }
      }

      const output = await resetPassword({ username });
      
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

      return {
        success: true,
        nextStep: output.nextStep,
        message: 'Password reset code sent to your email'
      };
    } catch (error) {
      console.error('Forgot password error:', error);
      const errorMessage = getErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const confirmForgotPassword = async (username, confirmationCode, newPassword) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log('Cognito not configured - using development authentication');
        try {
          await devAuth.confirmResetPassword(username, confirmationCode, newPassword);
          
          dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });
          
          return {
            success: true,
            message: 'Password reset successfully. You can now sign in with your new password.'
          };
        } catch (error) {
          console.error('Dev auth confirm password reset error:', error);
          const errorMessage = getErrorMessage(error);
          dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
          return { success: false, error: errorMessage };
        }
      }

      await confirmResetPassword({
        username,
        confirmationCode,
        newPassword
      });

      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

      return {
        success: true,
        message: 'Password reset successfully. You can now sign in with your new password.'
      };
    } catch (error) {
      console.error('Confirm password reset error:', error);
      const errorMessage = getErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const refreshSession = async () => {
    try {
      const session = await fetchAuthSession({ forceRefresh: true });
      
      if (session.tokens) {
        dispatch({
          type: AUTH_ACTIONS.UPDATE_TOKENS,
          payload: {
            accessToken: session.tokens.accessToken.toString(),
            idToken: session.tokens.idToken?.toString(),
            refreshToken: session.tokens.refreshToken?.toString()
          }
        });
        return { success: true };
      }
      
      return { success: false, error: 'No valid tokens' };
    } catch (error) {
      console.error('Session refresh error:', error);
      return { success: false, error: getErrorMessage(error) };
    }
  };

  const clearError = () => {
    dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });
  };

  // Helper function to get user-friendly error messages
  const getErrorMessage = (error) => {
    if (error.name === 'NotAuthorizedException') {
      return 'Invalid username or password';
    }
    if (error.name === 'UserNotConfirmedException') {
      return 'Please confirm your account before signing in';
    }
    if (error.name === 'UsernameExistsException') {
      return 'Username already exists';
    }
    if (error.name === 'CodeMismatchException') {
      return 'Invalid verification code';
    }
    if (error.name === 'ExpiredCodeException') {
      return 'Verification code has expired';
    }
    return error.message || 'An unexpected error occurred';
  };

  const value = {
    ...state,
    login,
    register,
    confirmRegistration,
    logout,
    forgotPassword,
    confirmForgotPassword,
    refreshSession,
    clearError,
    checkAuthState
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

// Hook to use auth context
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;