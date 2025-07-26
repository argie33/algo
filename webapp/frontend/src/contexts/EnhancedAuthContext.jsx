import React, { createContext, useContext, useReducer, useEffect } from 'react';
import AuthDiagnostics from '../services/authDiagnostics';

const AuthContext = createContext();

// Initial state with detailed error tracking
const initialState = {
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,
  detailedError: null,
  diagnostics: null,
  authMode: 'unknown', // 'full', 'limited', 'disabled', 'error'
  configurationStatus: 'checking'
};

// Enhanced auth actions
const AUTH_ACTIONS = {
  LOADING: 'LOADING',
  CONFIG_SUCCESS: 'CONFIG_SUCCESS',
  CONFIG_FAILURE: 'CONFIG_FAILURE',
  LOGIN_SUCCESS: 'LOGIN_SUCCESS',
  LOGIN_FAILURE: 'LOGIN_FAILURE',
  LOGOUT: 'LOGOUT',
  SET_ERROR: 'SET_ERROR',
  SET_DETAILED_ERROR: 'SET_DETAILED_ERROR',
  SET_DIAGNOSTICS: 'SET_DIAGNOSTICS',
  CLEAR_ERROR: 'CLEAR_ERROR'
};

function authReducer(state, action) {
  switch (action.type) {
    case AUTH_ACTIONS.LOADING:
      return {
        ...state,
        isLoading: action.payload,
        error: null
      };

    case AUTH_ACTIONS.CONFIG_SUCCESS:
      return {
        ...state,
        authMode: action.payload.authMode,
        configurationStatus: 'success',
        isLoading: false,
        error: null,
        detailedError: null
      };

    case AUTH_ACTIONS.CONFIG_FAILURE:
      return {
        ...state,
        authMode: 'error',
        configurationStatus: 'failed',
        isLoading: false,
        error: action.payload.error,
        detailedError: action.payload.detailedError,
        diagnostics: action.payload.diagnostics
      };

    case AUTH_ACTIONS.LOGIN_SUCCESS:
      return {
        ...state,
        user: action.payload.user,
        isAuthenticated: true,
        isLoading: false,
        error: null,
        detailedError: null
      };

    case AUTH_ACTIONS.LOGIN_FAILURE:
      return {
        ...state,
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: action.payload.error,
        detailedError: action.payload.detailedError
      };

    case AUTH_ACTIONS.SET_DETAILED_ERROR:
      return {
        ...state,
        detailedError: action.payload,
        isLoading: false
      };

    case AUTH_ACTIONS.SET_DIAGNOSTICS:
      return {
        ...state,
        diagnostics: action.payload
      };

    case AUTH_ACTIONS.CLEAR_ERROR:
      return {
        ...state,
        error: null,
        detailedError: null
      };

    default:
      return state;
  }
}

export function EnhancedAuthProvider({ children }) {
  const [state, dispatch] = useReducer(authReducer, initialState);
  const diagnostics = new AuthDiagnostics();

  // Initialize authentication with comprehensive error handling
  useEffect(() => {
    initializeAuth();
  }, []);

  const initializeAuth = async () => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });

      console.log('🚀 Initializing authentication system...');
      
      // Run comprehensive diagnostics
      const diagnosticResults = await diagnostics.runFullDiagnostics();
      
      dispatch({ 
        type: AUTH_ACTIONS.SET_DIAGNOSTICS, 
        payload: diagnosticResults 
      });

      // Check if we have any valid configuration source
      const validSources = Object.entries(diagnosticResults.configurationSources)
        .filter(([_, source]) => source.valid);

      if (validSources.length === 0) {
        const detailedError = {
          type: 'CONFIGURATION_ERROR',
          title: 'Authentication Configuration Missing',
          message: 'No valid authentication configuration found',
          details: diagnosticResults.configurationSources,
          recommendations: diagnosticResults.recommendations.filter(r => r.category === 'Configuration'),
          quickFix: this.getQuickFixSuggestion(diagnosticResults),
          timestamp: new Date().toISOString()
        };

        dispatch({
          type: AUTH_ACTIONS.CONFIG_FAILURE,
          payload: {
            error: 'Authentication configuration missing',
            detailedError,
            diagnostics: diagnosticResults
          }
        });
        return;
      }

      // Check Amplify configuration
      if (!diagnosticResults.amplifyStatus.configured) {
        const detailedError = {
          type: 'AMPLIFY_ERROR',
          title: 'AWS Amplify Not Configured',
          message: 'Amplify authentication library is not properly initialized',
          details: diagnosticResults.amplifyStatus,
          recommendations: diagnosticResults.recommendations.filter(r => r.category === 'Amplify'),
          quickFix: 'Run Amplify.configure() with valid Cognito settings',
          timestamp: new Date().toISOString()
        };

        dispatch({
          type: AUTH_ACTIONS.CONFIG_FAILURE,
          payload: {
            error: 'Amplify configuration failed',
            detailedError,
            diagnostics: diagnosticResults
          }
        });
        return;
      }

      // Try to get current user
      await checkCurrentUser();

      dispatch({
        type: AUTH_ACTIONS.CONFIG_SUCCESS,
        payload: { authMode: 'full' }
      });

    } catch (error) {
      console.error('❌ Authentication initialization failed:', error);
      
      const detailedError = {
        type: 'INITIALIZATION_ERROR',
        title: 'Authentication System Failed to Initialize',
        message: error.message,
        stack: error.stack,
        timestamp: new Date().toISOString(),
        quickFix: 'Check browser console for detailed diagnostics'
      };

      dispatch({
        type: AUTH_ACTIONS.CONFIG_FAILURE,
        payload: {
          error: 'Authentication initialization failed',
          detailedError,
          diagnostics: await diagnostics.runFullDiagnostics()
        }
      });
    }
  };

  const checkCurrentUser = async () => {
    try {
      const { getCurrentUser } = await import('@aws-amplify/auth');
      const user = await getCurrentUser();
      
      dispatch({
        type: AUTH_ACTIONS.LOGIN_SUCCESS,
        payload: { user }
      });
    } catch (error) {
      // User not authenticated - this is expected
      console.log('ℹ️ No current user session found');
    }
  };

  const login = async (username, password) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });

      const { signIn } = await import('@aws-amplify/auth');
      const result = await signIn({
        username,
        password
      });

      if (result.isSignedIn) {
        const user = await getCurrentUser();
        dispatch({
          type: AUTH_ACTIONS.LOGIN_SUCCESS,
          payload: { user }
        });
        return { success: true };
      }

      return { success: false, nextStep: result.nextStep };

    } catch (error) {
      console.error('❌ Login failed:', error);

      const detailedError = {
        type: 'LOGIN_ERROR',
        title: 'Login Failed',
        message: this.getHumanReadableError(error),
        originalError: error.message,
        errorCode: error.name,
        timestamp: new Date().toISOString(),
        quickFix: this.getLoginErrorFix(error)
      };

      dispatch({
        type: AUTH_ACTIONS.LOGIN_FAILURE,
        payload: {
          error: detailedError.message,
          detailedError
        }
      });

      return { success: false, error: detailedError.message };
    }
  };

  const logout = async () => {
    try {
      const { signOut } = await import('@aws-amplify/auth');
      await signOut();
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
    } catch (error) {
      console.error('❌ Logout failed:', error);
      // Force logout even if AWS call fails
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
    }
  };

  // Utility methods for better error messages
  const getHumanReadableError = (error) => {
    const errorMap = {
      'UserNotConfirmedException': 'Please check your email and confirm your account before signing in.',
      'NotAuthorizedException': 'Invalid username or password. Please check your credentials and try again.',
      'UserNotFoundException': 'No account found with this username. Please check your username or sign up.',
      'TooManyRequestsException': 'Too many failed attempts. Please wait a few minutes before trying again.',
      'InvalidPasswordException': 'Password does not meet requirements. Please use a stronger password.',
      'UsernameExistsException': 'An account with this username already exists.',
      'NetworkError': 'Network connection failed. Please check your internet connection.',
      'AuthUserPoolException': 'Authentication service is not properly configured. Please contact support.'
    };

    return errorMap[error.name] || error.message || 'An unexpected error occurred during authentication.';
  };

  const getLoginErrorFix = (error) => {
    const fixMap = {
      'UserNotConfirmedException': 'Check your email for a confirmation link',
      'NotAuthorizedException': 'Double-check your username and password',
      'UserNotFoundException': 'Verify your username or create a new account',
      'TooManyRequestsException': 'Wait 15 minutes before trying again',
      'NetworkError': 'Check your internet connection',
      'AuthUserPoolException': 'Contact system administrator - authentication not configured'
    };

    return fixMap[error.name] || 'Try refreshing the page and logging in again';
  };

  const getQuickFixSuggestion = (diagnostics) => {
    const cfSource = diagnostics.configurationSources.cloudformation;
    const envSource = diagnostics.configurationSources.environment;

    if (!cfSource.available && !envSource.available) {
      return 'Create a .env file with VITE_COGNITO_USER_POOL_ID and VITE_COGNITO_CLIENT_ID';
    }

    if (cfSource.available && !cfSource.valid) {
      return 'Check your CloudFormation stack deployment and outputs';
    }

    if (envSource.available && !envSource.valid) {
      return 'Fix your .env file configuration';
    }

    return 'Run diagnostics to identify the specific issue';
  };

  const clearError = () => {
    dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });
  };

  const value = {
    ...state,
    login,
    logout,
    clearError,
    diagnostics: state.diagnostics,
    getErrorSummary: () => diagnostics.getErrorSummary()
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an EnhancedAuthProvider');
  }
  return context;
};

export default AuthContext;