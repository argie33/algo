import {
  createContext,
  useContext,
  useReducer,
  useEffect,
  useState,
  useCallback,
} from "react";
import {
  fetchAuthSession,
  signIn,
  signUp,
  confirmSignUp,
  resendSignUpCode,
  signOut,
  resetPassword,
  confirmResetPassword,
  getCurrentUser,
} from "aws-amplify/auth";
import { isCognitoConfigured } from "../config/amplify";
import { setRefreshCallback } from "../services/api";
import { tokenManager } from "../services/tokenManager";
import SessionWarningDialog from "../components/auth/SessionWarningDialog";
import sessionManager from "../services/sessionManager";
import { getErrorMessage } from "../utils/cognitoErrorHandler";

// Initial auth state
const initialState = {
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,
  tokens: null,
};

// Auth actions
const AUTH_ACTIONS = {
  LOADING: "LOADING",
  LOGIN_SUCCESS: "LOGIN_SUCCESS",
  LOGIN_FAILURE: "LOGIN_FAILURE",
  LOGOUT: "LOGOUT",
  SET_ERROR: "SET_ERROR",
  CLEAR_ERROR: "CLEAR_ERROR",
  UPDATE_TOKENS: "UPDATE_TOKENS",
};

// Helper to extract groups from Cognito idToken JWT
function extractGroupsFromIdToken(idToken) {
  try {
    if (!idToken) return { groups: [], role: 'user' };
    const parts = idToken.split('.');
    if (parts.length !== 3) return { groups: [], role: 'user' };
    const payload = JSON.parse(atob(parts[1]));
    const groups = payload['cognito:groups'] || [];
    const role = groups.includes('admin') ? 'admin' : 'user';
    return { groups, role };
  } catch (error) {
    console.warn('Failed to extract groups from idToken:', error);
    return { groups: [], role: 'user' };
  }
}

// Auth reducer
function authReducer(state, action) {
  switch (action.type) {
    case AUTH_ACTIONS.LOADING:
      return {
        ...state,
        isLoading: action.payload,
      };
    case AUTH_ACTIONS.LOGIN_SUCCESS: {
      const user = action.payload.user;
      const tokens = action.payload.tokens;
      const { groups, role } = extractGroupsFromIdToken(tokens?.idToken);
      return {
        ...state,
        user: {
          ...user,
          groups: user.groups || groups,
          role: user.role || role,
          isAdmin: (user.role || role) === 'admin',
        },
        tokens,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      };
    }
    case AUTH_ACTIONS.LOGIN_FAILURE:
      return {
        ...state,
        user: null,
        tokens: null,
        isAuthenticated: false,
        isLoading: false,
        error: action.payload,
      };
    case AUTH_ACTIONS.LOGOUT:
      // Clear stored tokens
      tokenManager.clearTokens();

      return {
        ...state,
        user: null,
        tokens: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
      };
    case AUTH_ACTIONS.SET_ERROR:
      return {
        ...state,
        error: action.payload,
        isLoading: false,
      };
    case AUTH_ACTIONS.CLEAR_ERROR:
      return {
        ...state,
        error: null,
      };
    case AUTH_ACTIONS.UPDATE_TOKENS:
      return {
        ...state,
        tokens: action.payload,
      };
    default:
      return state;
  }
}

// Create auth context with explicit undefined check and defaults
const AuthContext = createContext(null);

// Create a safe default context value to prevent undefined errors
const defaultContextValue = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  tokens: null,
  login: async () => {},
  signup: async () => {},
  confirmAccount: async () => {},
  forgotPassword: async () => {},
  resetPassword: async () => {},
};

// Auth provider component
export function AuthProvider({ children }) {
  const [state, dispatch] = useReducer(authReducer, initialState);
  const [sessionWarning, setSessionWarning] = useState({
    show: false,
    timeRemaining: 0,
  });

  const refreshSession = useCallback(async () => {
    try {
      const cognitoConfigured = isCognitoConfigured();

      // Strict AWS Cognito only - no fallbacks
      if (!cognitoConfigured) {
        return { success: false, error: "Cognito not configured" };
      }

      const session = await fetchAuthSession({ forceRefresh: true });

      if (session.tokens) {
        const tokens = {
          accessToken: session.tokens.accessToken.toString(),
          idToken: session.tokens.idToken?.toString(),
          refreshToken: session.tokens.refreshToken?.toString(),
        };
        // CRITICAL: update tokenManager so api.js interceptor retries with the new token
        tokenManager.setTokens({ access: tokens.accessToken, id: tokens.idToken, refresh: tokens.refreshToken });
        dispatch({
          type: AUTH_ACTIONS.UPDATE_TOKENS,
          payload: tokens,
        });
        return { success: true };
      }

      return { success: false, error: "No valid tokens" };
    } catch (error) {
      console.error("❌ Session refresh error:", error);
      return { success: false, error: formatErrorMessage(error) };
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      sessionStorage.removeItem("accessToken");
      sessionStorage.removeItem("authToken");

      await signOut();
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
      return { success: true };
    } catch (error) {
      console.error("Logout error:", error);
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
      return { success: false, error: formatErrorMessage(error) };
    }
  }, []);

  const checkAuthState = useCallback(async () => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });

      // In unit test environment, don't attempt authentication checks that might hang
      // But allow E2E tests (Playwright) to use dev auth
      const isUnitTestEnv = (
        // Check for vitest testing environment
        (typeof globalThis !== 'undefined' && globalThis.__vitest_worker__) ||
        (typeof window !== 'undefined' && window.__vitest_worker__) ||
        import.meta.env?.MODE === 'test' ||
        (typeof process !== 'undefined' && process.env.NODE_ENV === 'test') ||
        // Check if we're in jsdom environment
        (typeof window !== 'undefined' && window.navigator?.userAgent?.includes('jsdom')) ||
        // Check for vitest globals
        (typeof globalThis !== 'undefined' &&
         (globalThis.vi || globalThis.vitest || globalThis.__vitest__))
      ) &&
      // Exclude Playwright tests (they have window.playwright object)
      !(typeof window !== 'undefined' && window.playwright);

      if (isUnitTestEnv) {
        dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });
        dispatch({ type: AUTH_ACTIONS.LOGOUT });
        return;
      }

      // Check if we're in a real production environment
      const isProductionBuild = import.meta.env.PROD;
      const cognitoConfigured = isCognitoConfigured();
      const forceDevAuth = import.meta.env.VITE_FORCE_DEV_AUTH === "true";

      // Strict AWS Cognito only - no development auth fallback
      if (cognitoConfigured) {
        try {
          // Race against 10s timeout — prevents infinite hang when tokens are stale
          // and Amplify's refresh network call to Cognito never resolves.
          const { user, session } = await Promise.race([
            (async () => {
              const u = await getCurrentUser();
              const s = await fetchAuthSession();
              return { user: u, session: s };
            })(),
            new Promise((_, reject) =>
              setTimeout(() => reject(new Error('Auth check timed out')), 10000)
            ),
          ]);

          if (user && session.tokens) {
            const tokens = {
              accessToken: session.tokens.accessToken.toString(),
              idToken: session.tokens.idToken?.toString(),
              refreshToken: session.tokens.refreshToken?.toString(),
            };

            tokenManager.setTokens({ access: tokens.accessToken, id: tokens.idToken, refresh: tokens.refreshToken });

            dispatch({
              type: AUTH_ACTIONS.LOGIN_SUCCESS,
              payload: {
                user: {
                  username: user.username,
                  userId: user.userId,
                  email: user.signInDetails?.loginId || user.username,
                  firstName: user.userAttributes?.given_name || "",
                  lastName: user.userAttributes?.family_name || "",
                  signInDetails: user.signInDetails,
                },
                tokens,
              },
            });
            return;
          }
        } catch (error) {
          // UserUnAuthenticatedException = no session, expected when no user is logged in
          const isExpectedLogout = error?.name === 'UserUnAuthenticatedException' ||
            error?.message?.includes('User needs to be authenticated') ||
            error?.message?.includes('not authenticated') ||
            error?.message?.includes('No current user');
          if (isExpectedLogout) {
            console.info('[AUTH] No active session — user not logged in');
          } else {
            console.error("❌ Cognito authentication failed:", error?.message);
          }
          // In production with Cognito configured, we DO NOT fall back - this is an auth failure
        }
      }

      // No valid session found (Cognito not configured or session expired)
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
    } catch (error) {
      console.log("Authentication check failed:", error);
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
    }
  }, []); // Empty dependency array since dispatch is stable

  // Wait for Cognito config, then check auth state
  useEffect(() => {
    const initAuth = async () => {
      // Wait for Cognito config to be available (up to 5 seconds)
      let attempts = 0;
      const maxAttempts = 50; // 50 * 100ms = 5 seconds

      while (!isCognitoConfigured() && attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 100));
        attempts++;
      }

      if (isCognitoConfigured()) {
        console.log("[AUTH] Cognito configured, checking auth state");
      } else {
        console.warn("[AUTH] Cognito not configured after 5s, proceeding unauthenticated");
      }

      await checkAuthState();
      setRefreshCallback(refreshSession);
    };

    initAuth().catch(error => {
      console.error("[AUTH] Failed to initialize auth:", error);
      checkAuthState();
      setRefreshCallback(refreshSession);
    });
  }, [checkAuthState, refreshSession]);

  // Initialize session manager when authenticated
  useEffect(() => {
    if (state.isAuthenticated && state.user) {
      try {
        // Initialize session manager with proper authContext object
        const authContextObj = {
          refreshSession,
          logout,
        };
        sessionManager.initialize(authContextObj);

        // Set session manager callbacks
        sessionManager.setCallbacks({
          onTokenRefresh: (_result) => {
          },
          onSessionWarning: (warningData) => {
            setSessionWarning({
              show: true,
              timeRemaining: warningData.timeRemaining,
            });
          },
          onSessionExpired: async () => {
            await logout();
          },
          onRefreshError: (error, attempts) => {
            console.error(
              `❌ Token refresh failed (attempt ${attempts}):`,
              error
            );
          },
        });

        // Start session and token refresh timer
        const rememberMe = localStorage.getItem('rememberMe') === 'true';
        sessionManager.startSession(rememberMe);
        // Start proactive token refresh timer
        if (state.tokens?.accessToken) {
          sessionManager.startTokenRefreshTimer(state.tokens.accessToken);
        }
      } catch (error) {
        console.error("❌ Failed to initialize session manager:", error);
        // Don't throw error to prevent app crash
      }
    } else if (!state.isAuthenticated) {
      // End session when logged out
      sessionManager.endSession();
      setSessionWarning({ show: false, timeRemaining: 0 });
    }

    // Cleanup function for component unmount
    return () => {
      sessionManager.clearAllTimers();
    };
  }, [
    state.isAuthenticated,
    state.user,
    state.tokens?.accessToken,
    refreshSession,
    logout,
    setSessionWarning,
  ]);

  // Restart token refresh timer when tokens change
  useEffect(() => {
    if (state.tokens?.accessToken && state.isAuthenticated) {
      sessionManager.startTokenRefreshTimer(state.tokens.accessToken);
    }
  }, [state.tokens?.accessToken, state.isAuthenticated]);

  const login = async (username, password, rememberMe = false) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      const cognitoConfigured = isCognitoConfigured();

      // Strict AWS Cognito only - no fallbacks
      if (!cognitoConfigured) {
        const errorMessage = "Cognito authentication is not properly configured. Please verify credentials are set in config.js";
        dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: errorMessage });
        return { success: false, error: errorMessage };
      }

      const { isSignedIn, nextStep } = await signIn({
        username,
        password,
      });

      if (isSignedIn) {
        // Get user and session after successful sign in
        const user = await getCurrentUser();
        const session = await fetchAuthSession();

        const tokens = {
          accessToken: session.tokens.accessToken.toString(),
          idToken: session.tokens.idToken?.toString(),
          refreshToken: session.tokens.refreshToken?.toString(),
        };

        // Store access token for API requests
        tokenManager.setTokens({ access: tokens.accessToken, id: tokens.idToken, refresh: tokens.refreshToken });

        dispatch({
          type: AUTH_ACTIONS.LOGIN_SUCCESS,
          payload: {
            user: {
              username: user.username,
              userId: user.userId,
              email: user.signInDetails?.loginId || user.username,
              firstName: user.userAttributes?.given_name || "",
              lastName: user.userAttributes?.family_name || "",
              signInDetails: user.signInDetails,
            },
            tokens,
          },
        });

        // Store rememberMe preference for session manager to use
        if (rememberMe) {
          localStorage.setItem('rememberMe', 'true');
        } else {
          localStorage.removeItem('rememberMe');
        }

        return { success: true, rememberMe };
      } else {
        // Handle additional steps (MFA, password change, etc.)
        return {
          success: false,
          nextStep: nextStep,
          message: "Additional authentication step required",
        };
      }
    } catch (error) {
      console.error("❌ Cognito login error:", error);
      const errorMessage = formatErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const register = async (username, password, email, firstName, lastName) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // Strict AWS Cognito only - no fallbacks
      if (!isCognitoConfigured()) {
        const errorMessage = "Cognito authentication is not properly configured. Please verify credentials are set in config.js";
        dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
        return { success: false, error: errorMessage };
      }

      const { isSignUpComplete, nextStep } = await signUp({
        username,
        password,
        options: {
          userAttributes: {
            email,
            given_name: firstName,
            family_name: lastName,
          },
        },
      });

      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

      return {
        success: true,
        isComplete: isSignUpComplete,
        nextStep: nextStep,
        message: isSignUpComplete
          ? "Registration completed successfully"
          : "Please check your email for verification code",
      };
    } catch (error) {
      console.error("Registration error:", error);
      const errorMessage = formatErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const confirmRegistration = async (username, confirmationCode) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // Strict AWS Cognito only - no fallbacks
      if (!isCognitoConfigured()) {
        const errorMessage = "Cognito authentication is not properly configured. Please verify credentials are set in config.js";
        dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
        return { success: false, error: errorMessage };
      }

      const { isSignUpComplete } = await confirmSignUp({
        username,
        confirmationCode,
      });

      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

      return {
        success: true,
        isComplete: isSignUpComplete,
        message: "Account confirmed successfully. You can now sign in.",
      };
    } catch (error) {
      console.error("Confirmation error:", error);
      const errorMessage = formatErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const resendConfirmationCode = async (username) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // Strict AWS Cognito only - no fallbacks
      if (!isCognitoConfigured()) {
        const errorMessage = "Cognito authentication is not properly configured. Please verify credentials are set in config.js";
        dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
        return { success: false, error: errorMessage };
      }

      await resendSignUpCode({ username });

      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

      return {
        success: true,
        message: "New verification code sent to your email",
      };
    } catch (error) {
      console.error("Resend confirmation error:", error);
      const errorMessage = formatErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const forgotPassword = async (username) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // Strict AWS Cognito only - no fallbacks
      if (!isCognitoConfigured()) {
        const errorMessage = "Cognito authentication is not properly configured. Please verify credentials are set in config.js";
        dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
        return { success: false, error: errorMessage };
      }

      const output = await resetPassword({ username });

      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

      return {
        success: true,
        nextStep: output.nextStep,
        message: "Password reset code sent to your email",
      };
    } catch (error) {
      console.error("Forgot password error:", error);
      const errorMessage = formatErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const confirmForgotPassword = async (
    username,
    confirmationCode,
    newPassword
  ) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // Strict AWS Cognito only - no fallbacks
      if (!isCognitoConfigured()) {
        const errorMessage = "Cognito authentication is not properly configured. Please verify credentials are set in config.js";
        dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
        return { success: false, error: errorMessage };
      }

      await confirmResetPassword({
        username,
        confirmationCode,
        newPassword,
      });

      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

      return {
        success: true,
        message:
          "Password reset successfully. You can now sign in with your new password.",
      };
    } catch (error) {
      console.error("Confirm password reset error:", error);
      const errorMessage = formatErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const clearError = () => {
    dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });
  };

  // Session warning handlers
  const handleExtendSession = async () => {
    sessionManager.extendSession();
    setSessionWarning({ show: false, timeRemaining: 0 });
  };

  const handleSessionLogout = async () => {
    setSessionWarning({ show: false, timeRemaining: 0 });
    await logout();
  };

  const handleCloseWarning = () => {
    setSessionWarning({ show: false, timeRemaining: 0 });
  };

  // Helper function to get user-friendly error messages
  const formatErrorMessage = (error) => {
    // First try the centralized error handler for comprehensive message mapping
    const mappedMessage = getErrorMessage(error);
    if (mappedMessage !== (error.message || 'An error occurred')) {
      return mappedMessage;
    }
    // Fallback to inline handling for specific cases
    if (error.name === "NotAuthorizedException") {
      return "Invalid username or password";
    }
    if (error.name === "UserNotConfirmedException") {
      return "Please confirm your account before signing in";
    }
    if (error.name === "UsernameExistsException") {
      return "Username already exists";
    }
    if (error.name === "CodeMismatchException") {
      return "Invalid verification code";
    }
    if (error.name === "ExpiredCodeException") {
      return "Verification code has expired";
    }
    return error.message || "An unexpected error occurred";
  };

  const value = {
    ...state,
    login,
    register,
    confirmRegistration,
    resendConfirmationCode,
    logout,
    forgotPassword,
    confirmForgotPassword,
    refreshSession,
    clearError,
    checkAuthState,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}

      {/* Session Warning Dialog */}
      <SessionWarningDialog
        open={sessionWarning.show}
        timeRemaining={sessionWarning.timeRemaining}
        onExtend={handleExtendSession}
        onLogout={handleSessionLogout}
        onClose={handleCloseWarning}
      />
    </AuthContext.Provider>
  );
}

// Hook to use auth context with safe fallback

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === null) {
    // In production, this might be called before provider is ready
    console.warn("useAuth called outside AuthProvider - using defaults");
    return defaultContextValue;
  }
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

// Export AuthContext for advanced usage
export { AuthContext };

// Make AuthProvider the default export for Fast Refresh compatibility
export default AuthProvider;

