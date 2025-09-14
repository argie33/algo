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
} from "@aws-amplify/auth";
import { isCognitoConfigured } from "../config/amplify";
import devAuth from "../services/devAuth";
import sessionManager from "../services/sessionManager";
import SessionWarningDialog from "../components/auth/SessionWarningDialog";

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

// Auth reducer
function authReducer(state, action) {
  switch (action.type) {
    case AUTH_ACTIONS.LOADING:
      return {
        ...state,
        isLoading: action.payload,
      };
    case AUTH_ACTIONS.LOGIN_SUCCESS:
      return {
        ...state,
        user: action.payload.user,
        tokens: action.payload.tokens,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      };
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
      localStorage.removeItem("accessToken");
      localStorage.removeItem("authToken");
      sessionStorage.removeItem("accessToken");
      sessionStorage.removeItem("authToken");

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

// Create auth context with default values to prevent undefined errors
const AuthContext = createContext({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  error: null,
  tokens: null,
  login: async () => {},
  signup: async () => {},
  confirmAccount: async () => {},
  forgotPassword: async () => {},
  resetPassword: async () => {},
});

// Auth provider component
export function AuthProvider({ children }) {
  const [state, dispatch] = useReducer(authReducer, initialState);
  const [sessionWarning, setSessionWarning] = useState({
    show: false,
    timeRemaining: 0,
  });

  const refreshSession = useCallback(async () => {
    try {
      const session = await fetchAuthSession({ forceRefresh: true });

      if (session.tokens) {
        dispatch({
          type: AUTH_ACTIONS.UPDATE_TOKENS,
          payload: {
            accessToken: session.tokens.accessToken.toString(),
            idToken: session.tokens.idToken?.toString(),
            refreshToken: session.tokens.refreshToken?.toString(),
          },
        });
        return { success: true };
      }

      return { success: false, error: "No valid tokens" };
    } catch (error) {
      console.error("Session refresh error:", error);
      return { success: false, error: getErrorMessage(error) };
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      // Clear stored auth token
      localStorage.removeItem("accessToken");
      localStorage.removeItem("authToken");
      sessionStorage.removeItem("accessToken");
      sessionStorage.removeItem("authToken");

      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log(
          "Cognito not configured - using development authentication"
        );
        await devAuth.signOut();
        dispatch({ type: AUTH_ACTIONS.LOGOUT });
        return { success: true };
      }

      await signOut();
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
      return { success: true };
    } catch (error) {
      console.error("Logout error:", error);
      // Even if logout fails, clear local state
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
      return { success: false, error: getErrorMessage(error) };
    }
  }, []);

  const checkAuthState = useCallback(async () => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });

      // Check if we're in a real production environment
      const isProductionBuild = import.meta.env.PROD;
      const cognitoConfigured = isCognitoConfigured();
      const forceDevAuth = import.meta.env.VITE_FORCE_DEV_AUTH === "true";

      // Use Cognito in production or when properly configured (unless dev auth is forced)
      if (isProductionBuild && cognitoConfigured && !forceDevAuth) {
        console.log("🚀 PRODUCTION MODE - Using AWS Cognito authentication");

        try {
          // Get current authenticated user
          const user = await getCurrentUser();

          // Get current session with tokens
          const session = await fetchAuthSession();

          if (user && session.tokens) {
            const tokens = {
              accessToken: session.tokens.accessToken.toString(),
              idToken: session.tokens.idToken?.toString(),
              refreshToken: session.tokens.refreshToken?.toString(),
            };

            // Store access token for API requests
            localStorage.setItem("accessToken", tokens.accessToken);

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
            console.log("✅ User authenticated with Cognito");
            return;
          }
        } catch (error) {
          console.log("No Cognito session found:", error);
        }
      }

      // Development fallback when Cognito is not configured OR dev auth is forced
      if ((!cognitoConfigured && import.meta.env.DEV) || forceDevAuth) {
        console.log(
          forceDevAuth
            ? "🔧 DEVELOPMENT MODE - Dev auth forced via VITE_FORCE_DEV_AUTH=true"
            : "🔧 DEVELOPMENT MODE - Cognito not configured, using dev auth fallback"
        );

        try {
          const user = await devAuth.getCurrentUser();
          const session = await devAuth.fetchAuthSession();

          if (user && session.tokens) {
            // Store access token for API requests
            localStorage.setItem("accessToken", session.tokens.accessToken);

            dispatch({
              type: AUTH_ACTIONS.LOGIN_SUCCESS,
              payload: {
                user,
                tokens: session.tokens,
              },
            });
            console.log("✅ Development user authenticated");
            return;
          }
        } catch (error) {
          console.log("No dev auth session found");
        }
      }

      // No valid session found
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
    } catch (error) {
      console.log("Authentication check failed:", error);
      dispatch({ type: AUTH_ACTIONS.LOGOUT });
    }
  }, []); // Empty dependency array since dispatch is stable

  // Check if user is authenticated on app start
  useEffect(() => {
    checkAuthState();
  }, [checkAuthState]);

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
            console.log("🔄 Tokens refreshed automatically");
          },
          onSessionWarning: (warningData) => {
            setSessionWarning({
              show: true,
              timeRemaining: warningData.timeRemaining,
            });
          },
          onSessionExpired: async () => {
            console.log("❌ Session expired, logging out");
            await logout();
          },
          onRefreshError: (error, attempts) => {
            console.error(
              `❌ Token refresh failed (attempt ${attempts}):`,
              error
            );
          },
        });

        // Start session
        const rememberMe = localStorage.getItem("rememberMe") === "true";
        sessionManager.startSession(rememberMe);
      } catch (error) {
        console.error("❌ Failed to initialize session manager:", error);
        // Don't throw error to prevent app crash
      }
    } else if (!state.isAuthenticated) {
      // End session when logged out
      sessionManager.endSession();
      setSessionWarning({ show: false, timeRemaining: 0 });
    }
  }, [
    state.isAuthenticated,
    state.user,
    refreshSession,
    logout,
    setSessionWarning,
  ]);

  const login = async (username, password) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      const isProductionBuild = import.meta.env.PROD;
      const cognitoConfigured = isCognitoConfigured();
      const forceDevAuth = import.meta.env.VITE_FORCE_DEV_AUTH === "true";

      // Use Cognito in production or when properly configured (unless dev auth is forced)
      if (isProductionBuild && cognitoConfigured && !forceDevAuth) {
        console.log("🚀 PRODUCTION LOGIN - Using AWS Cognito");

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
          localStorage.setItem("accessToken", tokens.accessToken);

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

          console.log("✅ Production login successful");
          return { success: true };
        } else {
          // Handle additional steps (MFA, password change, etc.)
          return {
            success: false,
            nextStep: nextStep,
            message: "Additional authentication step required",
          };
        }
      }

      // Development fallback when Cognito is not configured OR dev auth is forced
      if ((!cognitoConfigured && import.meta.env.DEV) || forceDevAuth) {
        console.log(
          forceDevAuth
            ? "🔧 DEVELOPMENT LOGIN - Dev auth forced via VITE_FORCE_DEV_AUTH=true"
            : "🔧 DEVELOPMENT LOGIN - Using dev auth fallback"
        );

        try {
          const result = await devAuth.signIn(username, password);

          // Check if login was successful and has tokens
          if (!result.success || !result.tokens) {
            const errorMsg =
              result.error?.message || "Login failed - no tokens received";
            console.error("Dev auth login failed:", errorMsg);
            dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: errorMsg });
            return { success: false, error: errorMsg };
          }

          // Store access token for API requests
          localStorage.setItem("accessToken", result.tokens.accessToken);

          dispatch({
            type: AUTH_ACTIONS.LOGIN_SUCCESS,
            payload: {
              user: result.user,
              tokens: result.tokens,
            },
          });

          console.log("✅ Development login successful");
          return { success: true };
        } catch (error) {
          console.error("Dev auth login error:", error);
          const errorMessage = getErrorMessage(error);
          dispatch({ type: AUTH_ACTIONS.LOGIN_FAILURE, payload: errorMessage });
          return { success: false, error: errorMessage };
        }
      }

      // If we get here, neither production nor development auth is available
      throw new Error("Authentication service is not properly configured");
    } catch (error) {
      console.error("Login error:", error);
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
        console.log(
          "Cognito not configured - using development authentication"
        );
        try {
          const result = await devAuth.signUp(
            username,
            password,
            email,
            firstName,
            lastName
          );

          dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

          return {
            success: true,
            isComplete: result.isSignUpComplete,
            nextStep: result.nextStep,
            message: result.isSignUpComplete
              ? "Registration completed successfully"
              : "Please check your email for verification code",
          };
        } catch (error) {
          console.error("Dev auth registration error:", error);
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
        console.log(
          "Cognito not configured - using development authentication"
        );
        try {
          const result = await devAuth.confirmSignUp(
            username,
            confirmationCode
          );

          dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

          return {
            success: true,
            isComplete: result.isSignUpComplete,
            message: "Account confirmed successfully. You can now sign in.",
          };
        } catch (error) {
          console.error("Dev auth confirmation error:", error);
          const errorMessage = getErrorMessage(error);
          dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
          return { success: false, error: errorMessage };
        }
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
      const errorMessage = getErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const resendConfirmationCode = async (username) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log(
          "Cognito not configured - using development authentication"
        );
        try {
          // For dev auth, we simulate sending a new code
          await new Promise((resolve) => setTimeout(resolve, 1000));

          dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

          return {
            success: true,
            message:
              "New verification code sent to your email (development mode)",
          };
        } catch (error) {
          console.error("Dev auth resend error:", error);
          const errorMessage = getErrorMessage(error);
          dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
          return { success: false, error: errorMessage };
        }
      }

      await resendSignUpCode({ username });

      dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

      return {
        success: true,
        message: "New verification code sent to your email",
      };
    } catch (error) {
      console.error("Resend confirmation error:", error);
      const errorMessage = getErrorMessage(error);
      dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
      return { success: false, error: errorMessage };
    }
  };

  const forgotPassword = async (username) => {
    try {
      dispatch({ type: AUTH_ACTIONS.LOADING, payload: true });
      dispatch({ type: AUTH_ACTIONS.CLEAR_ERROR });

      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log(
          "Cognito not configured - using development authentication"
        );
        try {
          const result = await devAuth.resetPassword(username);

          dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

          return {
            success: true,
            nextStep: result.nextStep,
            message: "Password reset code sent to your email",
          };
        } catch (error) {
          console.error("Dev auth password reset error:", error);
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
        message: "Password reset code sent to your email",
      };
    } catch (error) {
      console.error("Forgot password error:", error);
      const errorMessage = getErrorMessage(error);
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

      // If Cognito is not configured, use dev auth
      if (!isCognitoConfigured()) {
        console.log(
          "Cognito not configured - using development authentication"
        );
        try {
          await devAuth.confirmResetPassword(
            username,
            confirmationCode,
            newPassword
          );

          dispatch({ type: AUTH_ACTIONS.LOADING, payload: false });

          return {
            success: true,
            message:
              "Password reset successfully. You can now sign in with your new password.",
          };
        } catch (error) {
          console.error("Dev auth confirm password reset error:", error);
          const errorMessage = getErrorMessage(error);
          dispatch({ type: AUTH_ACTIONS.SET_ERROR, payload: errorMessage });
          return { success: false, error: errorMessage };
        }
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
      const errorMessage = getErrorMessage(error);
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
  const getErrorMessage = (error) => {
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

// Hook to use auth context
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

// Export AuthContext for advanced usage
export { AuthContext };

// Make AuthProvider the default export for Fast Refresh compatibility
export default AuthProvider;
