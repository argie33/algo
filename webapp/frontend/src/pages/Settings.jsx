import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  Container,
  Paper,
  Tabs,
  Tab,
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Button,
  TextField,
  Switch,
  FormControlLabel,
  Divider,
  Alert,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Avatar,
  CircularProgress,
  Snackbar,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction,
} from "@mui/material";
import {
  AccountCircle,
  Security,
  Api,
  Notifications,
  Palette,
  Visibility,
  VisibilityOff,
  Download,
  Warning,
  CheckCircle,
  Save,
  Cancel,
  Add,
  Delete,
} from "@mui/icons-material";
import api, { getApiConfig } from "../services/api";
import { createComponentLogger } from "../utils/errorLogger";

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`settings-tabpanel-${index}`}
      aria-labelledby={`settings-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

const Settings = () => {
  useDocumentTitle("Settings");
  const { user, isAuthenticated, isLoading, logout, checkAuthState } =
    useAuth();
  const navigate = useNavigate();

  // Memoize API config to prevent new object creation on every render
  const apiConfig = useMemo(() => getApiConfig(), []);
  const { apiUrl } = apiConfig;

  // Memoize logger to prevent useCallback recreation on every render
  const logger = useMemo(() => createComponentLogger("Settings"), []);

  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [snackbar, setSnackbar] = useState({
    open: false,
    message: "",
    severity: "success",
  });
  const [_apiKeys, _setApiKeys] = useState([]);
  const [addApiKeyDialog, setAddApiKeyDialog] = useState(false);
  const [showApiKeys, setShowApiKeys] = useState({});

  // New API key form
  const [newApiKey, setNewApiKey] = useState({
    brokerName: "",
    apiKey: "",
    apiSecret: "",
    sandbox: true,
  });

  // User profile form
  const [profileData, setProfileData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    timezone: "America/New_York",
    currency: "USD",
  });

  // Notification preferences
  const [passwordDialog, setPasswordDialog] = useState({
    open: false,
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
    errors: {},
  });
  const [notifications, setNotifications] = useState({
    email: true,
    push: true,
    priceAlerts: true,
    portfolioUpdates: true,
    marketNews: false,
    weeklyReports: true,
  });

  // Theme preferences
  const [themeSettings, setThemeSettings] = useState({
    darkMode: false,
    primaryColor: "#1976d2",
    chartStyle: "candlestick",
    layout: "standard",
  });

  // Authentication guard - disabled
  // useEffect(() => {
  //   if (!isLoading && !isAuthenticated) {
  //     navigate('/login');
  //   }
  // }, [isAuthenticated, isLoading, navigate]);

  // Define loadApiKeys first since it's referenced in loadUserSettings
  const loadApiKeys = useCallback(async () => {
    try {
      const response = await api.getApiKeys();

      if (response && response.ok) {
        // Convert object to array format that the component expects
        const apiKeysData = response.data || {};
        const apiKeysArray = Object.entries(apiKeysData).map(([brokerName, keyData]) => ({
          brokerName,
          ...keyData,
          createdAt: keyData.lastValidated || new Date().toISOString()
        }));
        _setApiKeys(apiKeysArray);
      } else {
        if (import.meta.env && import.meta.env.DEV)
          console.error(
            "API keys endpoint returned non-OK status:",
            response?.status || "unknown"
          );
        throw new Error(
          `API keys endpoint failed: ${response?.status || "unknown"}`
        );
      }
    } catch (error) {
      logger.error("Load API Keys Failed", error, {
        userId: user?.sub || user?.id,
        apiUrl,
        operation: "loadApiKeys",
        responseStatus: error.response?.status,
        responseData: error.response?.data,
      });
      _setApiKeys([]); // Set empty array and let user see there's no data
      throw error; // Re-throw so parent catch can handle it
    }
  }, [apiUrl, logger, user?.id, user?.sub]); // Dependencies required by ESLint

  // Define loadUserSettings after loadApiKeys with useCallback to prevent infinite loops
  const loadUserSettings = useCallback(async () => {
    try {
      setLoading(true);

      // Load user profile data
      setProfileData({
        firstName: user?.firstName || "",
        lastName: user?.lastName || "",
        email: user?.email || "",
        phone: user?.phone || "",
        timezone: user?.timezone || "America/New_York",
        currency: user?.currency || "USD",
      });

      // Load API keys with error handling
      try {
        await loadApiKeys();
      } catch (apiError) {
        logger.error("API Keys Loading Failed", apiError, {
          userId: user?.sub || user?.id,
          apiUrl,
          operation: "loadApiKeys",
          context: "settings initialization",
        });
        showSnackbar(`Failed to load API keys: ${apiError.message}`, "error");
        // Don't fail the entire settings load if API keys fail
      }

      // Load notification preferences
      try {
        const notifResponse = await fetch(
          `${apiUrl}/api/settings/preferences`,
          {
            headers: {
              Authorization: `Bearer ${user?.tokens?.accessToken || "dev-token"}`,
            },
          }
        );
        if (notifResponse.ok) {
          const notifData = await notifResponse.json();
          setNotifications((prev) => ({ ...prev, ...notifData.preferences }));
        } else if (notifResponse.status === 404) {
          // Endpoint doesn't exist - stop trying, use defaults
          console.log("Notifications endpoint not implemented, using defaults");
        }
      } catch (error) {
        console.log("Failed to load notification preferences, using defaults");
      }

      // Load theme preferences
      try {
        const themeResponse = await fetch(
          `${apiUrl}/api/settings/preferences`,
          {
            headers: {
              Authorization: `Bearer ${user?.tokens?.accessToken || "dev-token"}`,
            },
          }
        );
        if (themeResponse.ok) {
          const themeData = await themeResponse.json();
          setThemeSettings((prev) => ({ ...prev, ...themeData.preferences }));
        } else if (themeResponse.status === 404) {
          // Endpoint doesn't exist - stop trying, use defaults
          console.log("Theme endpoint not implemented, using defaults");
        }
      } catch (error) {
        console.log("Failed to load theme preferences, using defaults");
      }
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Error loading settings:", error);
      showSnackbar("Failed to load settings", "error");

      // Set empty profile data to show there's an issue
      setProfileData({
        firstName: "",
        lastName: "",
        email: "",
        phone: "",
        timezone: "America/New_York",
        currency: "USD",
      });
    } finally {
      setLoading(false);
    }
  }, [
    apiUrl,
    logger,
    loadApiKeys,
    user?.currency,
    user?.email,
    user?.firstName,
    user?.id,
    user?.lastName,
    user?.phone,
    user?.sub,
    user?.timezone,
    user?.tokens?.accessToken,
  ]); // Dependencies required by ESLint

  // Load settings when authenticated - USING REF TO AVOID USER OBJECT DEPENDENCY
  const hasLoadedRef = useRef(false);

  useEffect(() => {
    console.log("🔥 Settings useEffect triggered!", {
      isAuthenticated,
      isAuthenticatedType: typeof isAuthenticated,
      hasLoaded: hasLoadedRef.current,
      loading,
      loadingType: typeof loading,
      timestamp: new Date().toISOString(),
      loadUserSettingsRef: loadUserSettings,
    });

    // Only load if authenticated and we haven't loaded yet
    if (isAuthenticated && !hasLoadedRef.current && !loading) {
      console.log(
        "🚨 CALLING loadUserSettings - this should happen ONLY ONCE!"
      );
      hasLoadedRef.current = true; // Mark as loaded immediately

      logger.info("User authenticated, loading settings", {
        userId: user?.sub || user?.id,
        email: user?.email,
      });
      loadUserSettings();
    }
  }, [
    isAuthenticated,
    loadUserSettings,
    loading,
    logger,
    user?.email,
    user?.id,
    user?.sub,
  ]); // Dependencies required by ESLint

  // Separate session recovery logic (production only)
  useEffect(() => {
    if (
      !isLoading &&
      !user &&
      !isAuthenticated &&
      import.meta.env &&
      import.meta.env.PROD
    ) {
      logger.error(
        "No authenticated session found",
        new Error("Session check failed"),
        {
          isAuthenticated,
          isLoading,
          hasUser: !!user,
        }
      );
      // Only attempt recovery once, don't include checkAuthState in dependencies
      checkAuthState().catch((error) => {
        logger.error("Session recovery failed", error);
      });
    }
  }, [isLoading, isAuthenticated, user, checkAuthState, logger]); // Dependencies required by ESLint

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const showSnackbar = (message, severity = "success") => {
    setSnackbar({ open: true, message, severity });
  };

  const handleSaveProfile = async () => {
    try {
      setLoading(true);

      const response = await fetch(`${apiUrl}/api/user/profile`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${user?.tokens?.accessToken || "dev-token"}`,
        },
        body: JSON.stringify(profileData),
      });

      if (response.ok) {
        const updatedUser = await response.json();
        showSnackbar("Profile updated successfully");

        // Update the user context with new data
        if (updatedUser.user) {
          // This would typically update the auth context
          // For now, just refresh the settings
          await loadUserSettings();
        }
      } else {
        const error = await response.json();
        logger.error(
          "Profile Update Failed",
          new Error(`Profile update rejected: ${response.status}`),
          {
            userId: user?.sub || user?.id,
            profileData,
            responseStatus: response.status,
            errorData: error,
            operation: "updateProfile",
          }
        );
        showSnackbar(error.error || "Failed to update profile", "error");
      }
    } catch (error) {
      logger.error("Profile Save Error", error, {
        userId: user?.sub || user?.id,
        profileData,
        operation: "handleSaveProfile",
        context: "network or server error",
      });
      showSnackbar("Failed to update profile", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleAddApiKey = async () => {
    try {
      setLoading(true);

      const response = await api.saveApiKey(newApiKey);

      if (response && response.ok) {
        showSnackbar("API key added successfully");
        setAddApiKeyDialog(false);
        setNewApiKey({
          brokerName: "",
          apiKey: "",
          apiSecret: "",
          sandbox: true,
        });
        await loadApiKeys();
      } else {
        const error = await response.json();
        showSnackbar(error.error || "Failed to add API key", "error");
      }
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Error adding API key:", error);
      showSnackbar("Failed to add API key", "error");
    } finally {
      setLoading(false);
    }
  };

  const _deleteApiKey = async (brokerName) => {
    try {
      await api.deleteApiKey(brokerName);
      showSnackbar("API key deleted successfully");
      await loadApiKeys();
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Error deleting API key:", error);
      showSnackbar("Failed to delete API key", "error");
    }
  };

  const _testConnection = async (brokerName) => {
    try {
      setLoading(true);

      const response = await api.testApiKey({
        provider: brokerName,
        keyId: newApiKey.keyId || newApiKey.key,
        secret: newApiKey.secret
      });

      if (response.ok && response.isValid) {
        showSnackbar(
          `✅ Connection successful! API key is valid.`,
          "success"
        );
      } else {
        showSnackbar(
          `❌ Connection failed: ${response.error || "Invalid API key"}`,
          "error"
        );
      }
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Error testing connection:", error);
      showSnackbar("Failed to test connection", "error");
    } finally {
      setLoading(false);
    }
  };

  const _saveSettings = async () => {
    try {
      setLoading(true);

      const response = await api.saveApiKey({
        provider: newApiKey.brokerName,
        keyId: newApiKey.keyId || newApiKey.key,
        secret: newApiKey.secret
      });

      if (response.ok) {
        showSnackbar(
          `✅ API key saved successfully!`,
          "success"
        );

        // Refresh API keys list
        await loadApiKeys();
        
        // Reset form
        setNewApiKey({ provider: "", keyId: "", secret: "" });
      } else {
        showSnackbar(response.error || "Failed to save API key", "error");
      }
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Error saving API key:", error);
      showSnackbar("Failed to save API key", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveNotifications = async () => {
    try {
      setLoading(true);

      const response = await api.updateSettings({ 
        preferences: { ...themeSettings, ...notifications } 
      });

      if (response.ok) {
        showSnackbar("Notification preferences updated successfully");
      } else {
        showSnackbar(
          response.error || "Failed to update notification preferences",
          "error"
        );
      }
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Error saving notifications:", error);
      showSnackbar("Failed to update notification preferences", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleSaveTheme = async () => {
    try {
      setLoading(true);

      const response = await api.updateSettings({ 
        preferences: { ...themeSettings, ...notifications } 
      });

      if (response.ok) {
        showSnackbar("Theme preferences updated successfully");
      } else {
        showSnackbar(
          response.error || "Failed to update theme preferences",
          "error"
        );
      }
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Error saving theme:", error);
      showSnackbar("Failed to update theme preferences", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async () => {
    setPasswordDialog({
      open: true,
      currentPassword: "",
      newPassword: "",
      confirmPassword: "",
      errors: {},
    });
  };

  const validatePasswordChange = () => {
    const errors = {};

    if (!passwordDialog.currentPassword) {
      errors.currentPassword = "Current password is required";
    }

    if (!passwordDialog.newPassword) {
      errors.newPassword = "New password is required";
    } else if (passwordDialog.newPassword.length < 8) {
      errors.newPassword = "Password must be at least 8 characters";
    } else if (
      !/(?=.*[a-z])(?=.*[A-Z])(?=.*\d)/.test(passwordDialog.newPassword)
    ) {
      errors.newPassword =
        "Password must contain uppercase, lowercase, and number";
    }

    if (passwordDialog.newPassword !== passwordDialog.confirmPassword) {
      errors.confirmPassword = "Passwords do not match";
    }

    if (passwordDialog.currentPassword === passwordDialog.newPassword) {
      errors.newPassword =
        "New password must be different from current password";
    }

    return errors;
  };

  const handlePasswordDialogSubmit = async () => {
    const errors = validatePasswordChange();

    if (Object.keys(errors).length > 0) {
      setPasswordDialog((prev) => ({ ...prev, errors }));
      return;
    }

    try {
      setLoading(true);

      const response = await fetch(`${apiUrl}/api/user/change-password`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${user?.tokens?.accessToken || "dev-token"}`,
        },
        body: JSON.stringify({
          currentPassword: passwordDialog.currentPassword,
          newPassword: passwordDialog.newPassword,
        }),
      });

      if (response.ok) {
        showSnackbar("Password changed successfully", "success");
        setPasswordDialog({
          open: false,
          currentPassword: "",
          newPassword: "",
          confirmPassword: "",
          errors: {},
        });
      } else {
        const errorData = await response.json();
        if (response.status === 401) {
          setPasswordDialog((prev) => ({
            ...prev,
            errors: { currentPassword: "Current password is incorrect" },
          }));
        } else {
          showSnackbar(
            errorData.message || "Failed to change password",
            "error"
          );
        }
      }
    } catch (error) {
      showSnackbar("Network error. Please try again.", "error");
    } finally {
      setLoading(false);
    }
  };

  const handlePasswordDialogClose = () => {
    setPasswordDialog({
      open: false,
      currentPassword: "",
      newPassword: "",
      confirmPassword: "",
      errors: {},
    });
  };

  const handleToggleTwoFactor = async () => {
    try {
      setLoading(true);

      const action = user?.twoFactorEnabled ? "disable" : "enable";
      const response = await fetch(`${apiUrl}/api/user/two-factor/${action}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${user?.tokens?.accessToken || "dev-token"}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        showSnackbar(
          user?.twoFactorEnabled
            ? "Two-factor authentication disabled"
            : "Two-factor authentication enabled"
        );

        // Show QR code or setup instructions if enabling
        if (!user?.twoFactorEnabled && data.qrCode) {
          showSnackbar(
            "Please scan the QR code with your authenticator app",
            "info"
          );
        }

        // Refresh user settings
        await loadUserSettings();
      } else {
        const error = await response.json();
        showSnackbar(
          error.error || "Failed to toggle two-factor authentication",
          "error"
        );
      }
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Error toggling two-factor auth:", error);
      showSnackbar("Failed to toggle two-factor authentication", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadRecoveryCodes = async () => {
    try {
      setLoading(true);

      const response = await fetch(`${apiUrl}/api/user/recovery-codes`, {
        headers: {
          Authorization: `Bearer ${user?.tokens?.accessToken || "dev-token"}`,
        },
      });

      if (response.ok) {
        const data = await response.json();

        // Create and download recovery codes file
        const codesText = data.codes.join("\n");
        const blob = new Blob([codesText], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "recovery-codes.txt";
        link.click();
        URL.revokeObjectURL(url);

        showSnackbar("Recovery codes downloaded successfully", "success");
      } else {
        const error = await response.json();
        showSnackbar(
          error.error || "Failed to download recovery codes",
          "error"
        );
      }
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV)
        console.error("Error downloading recovery codes:", error);
      showSnackbar("Failed to download recovery codes", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (
      window.confirm(
        "Are you sure you want to delete your account? This action cannot be undone."
      )
    ) {
      if (
        window.confirm(
          'This will permanently delete all your data. Type "DELETE" to confirm.'
        )
      ) {
        const userInput = window.prompt(
          'Type "DELETE" to confirm account deletion:'
        );
        if (userInput === "DELETE") {
          try {
            setLoading(true);

            const response = await fetch(`${apiUrl}/api/user/delete-account`, {
              method: "DELETE",
              headers: {
                Authorization: `Bearer ${user?.tokens?.accessToken || "dev-token"}`,
              },
            });

            if (response.ok) {
              showSnackbar("Account deleted successfully", "success");
              await logout();
              navigate("/");
            } else {
              const error = await response.json();
              showSnackbar(error.error || "Failed to delete account", "error");
            }
          } catch (error) {
            if (import.meta.env && import.meta.env.DEV)
              console.error("Error deleting account:", error);
            showSnackbar("Failed to delete account", "error");
          } finally {
            setLoading(false);
          }
        }
      }
    }
  };

  const handleRevokeAllSessions = async () => {
    if (
      window.confirm(
        "This will sign you out of all devices except this one. Continue?"
      )
    ) {
      try {
        setLoading(true);

        const response = await fetch(`${apiUrl}/api/user/revoke-sessions`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${user?.tokens?.accessToken || "dev-token"}`,
          },
        });

        if (response.ok) {
          showSnackbar("All other sessions have been revoked", "success");
        } else {
          const error = await response.json();
          showSnackbar(error.error || "Failed to revoke sessions", "error");
        }
      } catch (error) {
        if (import.meta.env && import.meta.env.DEV)
          console.error("Error revoking sessions:", error);
        showSnackbar("Failed to revoke sessions", "error");
      } finally {
        setLoading(false);
      }
    }
  };

  // Show loading state while authentication is being checked
  if (loading || isLoading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="60vh"
        >
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  // If we don't have a user object at all, show a fallback with more options
  if (!user && !isLoading) {
    // Log authentication info to console for debugging (but don't log as error in development)
    if (import.meta.env && import.meta.env.PROD) {
      logger.error(
        "Authentication Error",
        new Error("Unable to load user information"),
        {
          userObject: user,
          isAuthenticated,
          isLoading,
          apiUrl,
          reason:
            "No user object available after authentication loading completed",
          suggestedActions: ["refresh page", "login again", "check session"],
          url: window.location.href,
        }
      );
    } else {
      console.log(
        "🔧 DEV: Settings page - no authenticated user, showing login prompt"
      );
    }

    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Alert
          severity="warning"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => window.location.reload()}
              aria-label="Refresh page to re-authenticate"
            >
              Refresh
            </Button>
          }
        >
          Unable to load user information. This may be due to an expired session
          or authentication issue.
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h3" component="h1" gutterBottom>
        Account Settings
      </Typography>
      <Typography variant="subtitle1" color="text.secondary" sx={{ mb: 4 }}>
        Manage your account preferences, API connections, and security settings
      </Typography>

      <Paper sx={{ width: "100%" }}>
        <Tabs
          value={activeTab}
          onChange={handleTabChange}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ borderBottom: 1, borderColor: "divider" }}
          aria-label="Settings navigation tabs"
        >
          <Tab
            value={0}
            icon={<AccountCircle />}
            label="Profile"
            aria-label="Profile settings"
          />
          <Tab
            value={1}
            icon={<Api />}
            label="API Keys"
            data-testid="api-keys-tab"
            aria-label="API keys management"
          />
          <Tab
            value={2}
            icon={<Notifications />}
            label="Notifications"
            aria-label="Notification preferences"
          />
          <Tab
            value={3}
            icon={<Palette />}
            label="Appearance"
            aria-label="Appearance and theme settings"
          />
          <Tab
            value={4}
            icon={<Security />}
            label="Security"
            aria-label="Security and account settings"
          />
        </Tabs>

        {/* Profile Tab */}
        <TabPanel value={activeTab} index={0}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={8}>
              <Card>
                <CardHeader title="Personal Information" />
                <CardContent>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="First Name"
                        value={profileData.firstName}
                        onChange={(e) =>
                          setProfileData({
                            ...profileData,
                            firstName: e.target.value,
                          })
                        }
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="Last Name"
                        value={profileData.lastName}
                        onChange={(e) =>
                          setProfileData({
                            ...profileData,
                            lastName: e.target.value,
                          })
                        }
                      />
                    </Grid>
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        label="Email"
                        type="email"
                        value={profileData.email}
                        onChange={(e) =>
                          setProfileData({
                            ...profileData,
                            email: e.target.value,
                          })
                        }
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <FormControl fullWidth>
                        <InputLabel>Timezone</InputLabel>
                        <Select
                          value={profileData.timezone}
                          onChange={(e) =>
                            setProfileData({
                              ...profileData,
                              timezone: e.target.value,
                            })
                          }
                        >
                          <MenuItem value="America/New_York">
                            Eastern Time
                          </MenuItem>
                          <MenuItem value="America/Chicago">
                            Central Time
                          </MenuItem>
                          <MenuItem value="America/Denver">
                            Mountain Time
                          </MenuItem>
                          <MenuItem value="America/Los_Angeles">
                            Pacific Time
                          </MenuItem>
                          <MenuItem value="Europe/London">London</MenuItem>
                          <MenuItem value="Asia/Tokyo">Tokyo</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <FormControl fullWidth>
                        <InputLabel>Currency</InputLabel>
                        <Select
                          value={profileData.currency}
                          onChange={(e) =>
                            setProfileData({
                              ...profileData,
                              currency: e.target.value,
                            })
                          }
                        >
                          <MenuItem value="USD">USD - US Dollar</MenuItem>
                          <MenuItem value="EUR">EUR - Euro</MenuItem>
                          <MenuItem value="GBP">GBP - British Pound</MenuItem>
                          <MenuItem value="CAD">CAD - Canadian Dollar</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                  </Grid>
                  <Box sx={{ mt: 3, display: "flex", gap: 2 }}>
                    <Button
                      variant="contained"
                      startIcon={<Save />}
                      onClick={handleSaveProfile}
                      disabled={loading}
                      aria-label="Save profile changes"
                    >
                      Save Changes
                    </Button>
                    <Button
                      variant="outlined"
                      startIcon={<Cancel />}
                      onClick={loadUserSettings}
                      aria-label="Cancel and reset profile changes"
                    >
                      Reset
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card>
                <CardHeader title="Account Overview" />
                <CardContent>
                  <Box display="flex" alignItems="center" mb={2}>
                    <Avatar sx={{ mr: 2, width: 56, height: 56 }}>
                      {(
                        user?.firstName?.[0] ||
                        user?.username?.[0] ||
                        "U"
                      ).toUpperCase()}
                    </Avatar>
                    <Box>
                      <Typography variant="h6">
                        {user?.firstName || "Unknown"}{" "}
                        {user?.lastName || "User"}
                      </Typography>
                      <Typography color="text.secondary">
                        {user?.email || "No email provided"}
                      </Typography>
                    </Box>
                  </Box>
                  <Divider sx={{ my: 2 }} />
                  <List dense aria-label="Account information">
                    <ListItem>
                      <ListItemText
                        primary="Account Status"
                        secondary="Active"
                      />
                      <ListItemSecondaryAction>
                        <Chip label="Active" color="success" size="small" />
                      </ListItemSecondaryAction>
                    </ListItem>
                    <ListItem>
                      <ListItemText
                        primary="Member Since"
                        secondary={new Date(
                          user?.createdAt || Date.now()
                        ).toLocaleDateString()}
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>

        {/* API Keys Tab */}
        <TabPanel value={activeTab} index={1}>
          <Grid container spacing={4}>
            <Grid item xs={12}>
              <Card>
                <CardHeader
                  title="API Keys"
                  subheader="Manage your API keys for data providers and trading platforms"
                  action={
                    <Button
                      variant="contained"
                      startIcon={<Add />}
                      onClick={() => setAddApiKeyDialog(true)}
                      data-testid="add-api-key-button"
                      aria-label="Add new API key"
                    >
                      Add API Key
                    </Button>
                  }
                />
                <CardContent>
                  {_apiKeys.length === 0 ? (
                    <Alert severity="info" sx={{ mb: 2 }}>
                      No API keys configured. Add your first API key to start
                      accessing real market data.
                    </Alert>
                  ) : (
                    <Grid container spacing={2}>
                      {_apiKeys.map((apiKey) => (
                        <Grid item xs={12} md={6} key={apiKey.brokerName}>
                          <Card variant="outlined">
                            <CardContent>
                              <Box
                                display="flex"
                                justifyContent="space-between"
                                alignItems="center"
                              >
                                <Box>
                                  <Typography variant="h6">
                                    {apiKey.brokerName}
                                  </Typography>
                                  <Typography
                                    variant="body2"
                                    color="text.secondary"
                                  >
                                    Added:{" "}
                                    {new Date(
                                      apiKey.createdAt
                                    ).toLocaleDateString()}
                                  </Typography>
                                </Box>
                                <Box>
                                  <Chip
                                    label={apiKey.status || "Active"}
                                    color={
                                      apiKey.status === "active"
                                        ? "success"
                                        : "default"
                                    }
                                    size="small"
                                  />
                                  <IconButton
                                    onClick={() =>
                                      _deleteApiKey(apiKey.brokerName)
                                    }
                                    color="error"
                                    aria-label={`Delete ${apiKey.brokerName} API key`}
                                  >
                                    <Delete />
                                  </IconButton>
                                </Box>
                              </Box>
                            </CardContent>
                          </Card>
                        </Grid>
                      ))}
                    </Grid>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>

        {/* Notifications Tab */}
        <TabPanel value={activeTab} index={2}>
          <Card>
            <CardHeader
              title="Notification Preferences"
              action={
                <Button
                  variant="contained"
                  startIcon={<Save />}
                  onClick={handleSaveNotifications}
                  disabled={loading}
                  aria-label="Save notification preferences"
                >
                  Save
                </Button>
              }
            />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Delivery Methods
                  </Typography>
                  <Box sx={{ display: "flex", flexDirection: "column" }}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.email}
                          onChange={(e) =>
                            setNotifications({
                              ...notifications,
                              email: e.target.checked,
                            })
                          }
                        />
                      }
                      label="Email Notifications"
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.push}
                          onChange={(e) =>
                            setNotifications({
                              ...notifications,
                              push: e.target.checked,
                            })
                          }
                        />
                      }
                      label="Push Notifications"
                    />
                  </Box>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Content Types
                  </Typography>
                  <Box sx={{ display: "flex", flexDirection: "column" }}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.priceAlerts}
                          onChange={(e) =>
                            setNotifications({
                              ...notifications,
                              priceAlerts: e.target.checked,
                            })
                          }
                        />
                      }
                      label="Price Alerts"
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.portfolioUpdates}
                          onChange={(e) =>
                            setNotifications({
                              ...notifications,
                              portfolioUpdates: e.target.checked,
                            })
                          }
                        />
                      }
                      label="Portfolio Updates"
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.marketNews}
                          onChange={(e) =>
                            setNotifications({
                              ...notifications,
                              marketNews: e.target.checked,
                            })
                          }
                        />
                      }
                      label="Market News"
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.weeklyReports}
                          onChange={(e) =>
                            setNotifications({
                              ...notifications,
                              weeklyReports: e.target.checked,
                            })
                          }
                        />
                      }
                      label="Weekly Reports"
                    />
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* Appearance Tab */}
        <TabPanel value={activeTab} index={3}>
          <Card>
            <CardHeader
              title="Appearance Settings"
              action={
                <Button
                  variant="contained"
                  startIcon={<Save />}
                  onClick={handleSaveTheme}
                  disabled={loading}
                  aria-label="Save appearance settings"
                >
                  Save
                </Button>
              }
            />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Theme Settings
                  </Typography>
                  <Box sx={{ mb: 2 }}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={themeSettings.darkMode}
                          onChange={(e) =>
                            setThemeSettings({
                              ...themeSettings,
                              darkMode: e.target.checked,
                            })
                          }
                        />
                      }
                      label="Dark Mode"
                    />
                  </Box>
                  <FormControl fullWidth sx={{ mb: 2 }}>
                    <InputLabel>Primary Color</InputLabel>
                    <Select
                      value={themeSettings.primaryColor}
                      onChange={(e) =>
                        setThemeSettings({
                          ...themeSettings,
                          primaryColor: e.target.value,
                        })
                      }
                    >
                      <MenuItem value="#1976d2">Blue</MenuItem>
                      <MenuItem value="#2e7d32">Green</MenuItem>
                      <MenuItem value="#ed6c02">Orange</MenuItem>
                      <MenuItem value="#9c27b0">Purple</MenuItem>
                      <MenuItem value="#d32f2f">Red</MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl fullWidth>
                    <InputLabel>Layout Style</InputLabel>
                    <Select
                      value={themeSettings.layout}
                      onChange={(e) =>
                        setThemeSettings({
                          ...themeSettings,
                          layout: e.target.value,
                        })
                      }
                    >
                      <MenuItem value="standard">Standard</MenuItem>
                      <MenuItem value="compact">Compact</MenuItem>
                      <MenuItem value="spacious">Spacious</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Chart Settings
                  </Typography>
                  <FormControl fullWidth sx={{ mb: 2 }}>
                    <InputLabel>Default Chart Style</InputLabel>
                    <Select
                      value={themeSettings.chartStyle}
                      onChange={(e) =>
                        setThemeSettings({
                          ...themeSettings,
                          chartStyle: e.target.value,
                        })
                      }
                    >
                      <MenuItem value="candlestick">Candlestick</MenuItem>
                      <MenuItem value="line">Line</MenuItem>
                      <MenuItem value="area">Area</MenuItem>
                      <MenuItem value="bar">Bar</MenuItem>
                    </Select>
                  </FormControl>
                  <Alert severity="info">
                    Theme changes will be applied immediately. Some changes may
                    require a page refresh.
                  </Alert>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* Security Tab */}
        <TabPanel value={activeTab} index={4}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardHeader title="Password & Authentication" />
                <CardContent>
                  <Button
                    variant="outlined"
                    fullWidth
                    sx={{ mb: 2 }}
                    startIcon={<Security />}
                    onClick={handleChangePassword}
                    disabled={loading}
                    aria-label="Change account password"
                  >
                    Change Password
                  </Button>
                  <Button
                    variant="outlined"
                    fullWidth
                    sx={{ mb: 2 }}
                    startIcon={<Security />}
                    onClick={handleToggleTwoFactor}
                    disabled={loading}
                    aria-label={`${user?.twoFactorEnabled ? "Disable" : "Enable"} two-factor authentication`}
                  >
                    {user?.twoFactorEnabled ? "Disable" : "Enable"} Two-Factor
                    Authentication
                  </Button>
                  <Button
                    variant="outlined"
                    fullWidth
                    startIcon={<Download />}
                    onClick={handleDownloadRecoveryCodes}
                    disabled={loading || !user?.twoFactorEnabled}
                    aria-label="Download two-factor authentication recovery codes"
                  >
                    Download Recovery Codes
                  </Button>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card>
                <CardHeader title="Account Actions" />
                <CardContent>
                  <Button
                    variant="outlined"
                    fullWidth
                    onClick={logout}
                    sx={{ mb: 2 }}
                    disabled={loading}
                    aria-label="Sign out of account"
                  >
                    Sign Out
                  </Button>
                  <Button
                    variant="outlined"
                    color="error"
                    fullWidth
                    startIcon={<Warning />}
                    onClick={handleDeleteAccount}
                    disabled={loading}
                    aria-label="Delete account permanently"
                  >
                    Delete Account
                  </Button>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12}>
              <Card>
                <CardHeader title="Active Sessions" />
                <CardContent>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 2 }}
                  >
                    Manage your active login sessions across different devices.
                  </Typography>
                  <List aria-label="Active sessions">
                    <ListItem>
                      <ListItemIcon>
                        <CheckCircle color="success" />
                      </ListItemIcon>
                      <ListItemText
                        primary="Current Session"
                        secondary={`${navigator.userAgent.includes("Chrome") ? "Chrome" : "Browser"} on ${navigator.platform} - ${new Date().toLocaleString()}`}
                      />
                      <ListItemSecondaryAction>
                        <Chip label="Current" color="primary" size="small" />
                      </ListItemSecondaryAction>
                    </ListItem>
                  </List>
                  <Button
                    variant="outlined"
                    color="warning"
                    startIcon={<Security />}
                    onClick={handleRevokeAllSessions}
                    disabled={loading}
                    aria-label="Revoke all other active sessions"
                  >
                    Revoke All Other Sessions
                  </Button>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>
      </Paper>

      {/* Add API Key Dialog */}
      <Dialog
        open={addApiKeyDialog}
        onClose={() => setAddApiKeyDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Add Broker API Key</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Broker</InputLabel>
                <Select
                  value={newApiKey.brokerName}
                  onChange={(e) =>
                    setNewApiKey({ ...newApiKey, brokerName: e.target.value })
                  }
                >
                  <MenuItem value="alpaca" data-provider="alpaca">
                    Alpaca
                  </MenuItem>
                  <MenuItem value="polygon" data-provider="polygon">
                    Polygon
                  </MenuItem>
                  <MenuItem value="robinhood" data-provider="robinhood">
                    Robinhood
                  </MenuItem>
                  <MenuItem value="td_ameritrade" data-provider="td_ameritrade">
                    TD Ameritrade
                  </MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="API Key"
                type={showApiKeys.apiKey ? "text" : "password"}
                value={newApiKey.apiKey}
                data-testid="api-key-input"
                onChange={(e) =>
                  setNewApiKey({ ...newApiKey, apiKey: e.target.value })
                }
                InputProps={{
                  endAdornment: (
                    <IconButton
                      onClick={() =>
                        setShowApiKeys({
                          ...showApiKeys,
                          apiKey: !showApiKeys.apiKey,
                        })
                      }
                      aria-label={
                        showApiKeys.apiKey ? "Hide API key" : "Show API key"
                      }
                    >
                      {showApiKeys.apiKey ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  ),
                }}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="API Secret"
                type={showApiKeys.apiSecret ? "text" : "password"}
                value={newApiKey.apiSecret}
                onChange={(e) =>
                  setNewApiKey({ ...newApiKey, apiSecret: e.target.value })
                }
                InputProps={{
                  endAdornment: (
                    <IconButton
                      onClick={() =>
                        setShowApiKeys({
                          ...showApiKeys,
                          apiSecret: !showApiKeys.apiSecret,
                        })
                      }
                      aria-label={
                        showApiKeys.apiSecret
                          ? "Hide API secret"
                          : "Show API secret"
                      }
                    >
                      {showApiKeys.apiSecret ? (
                        <VisibilityOff />
                      ) : (
                        <Visibility />
                      )}
                    </IconButton>
                  ),
                }}
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={newApiKey.sandbox}
                    onChange={(e) =>
                      setNewApiKey({ ...newApiKey, sandbox: e.target.checked })
                    }
                  />
                }
                label="Sandbox Environment (recommended for testing)"
              />
            </Grid>
          </Grid>
          <Alert severity="info" sx={{ mt: 2 }}>
            API keys are encrypted and stored securely. We recommend starting
            with sandbox mode for testing.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => setAddApiKeyDialog(false)}
            aria-label="Cancel adding API key"
          >
            Cancel
          </Button>
          <Button
            onClick={handleAddApiKey}
            variant="contained"
            disabled={!newApiKey.brokerName || !newApiKey.apiKey || loading}
            aria-label="Add new API key"
          >
            Add API Key
          </Button>
        </DialogActions>
      </Dialog>

      {/* Password Change Dialog */}
      <Dialog
        open={passwordDialog.open}
        onClose={handlePasswordDialogClose}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Change Password</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Current Password"
            type="password"
            fullWidth
            variant="outlined"
            value={passwordDialog.currentPassword}
            onChange={(e) =>
              setPasswordDialog((prev) => ({
                ...prev,
                currentPassword: e.target.value,
                errors: { ...prev.errors, currentPassword: "" },
              }))
            }
            error={Boolean(passwordDialog.errors.currentPassword)}
            helperText={passwordDialog.errors.currentPassword}
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="New Password"
            type="password"
            fullWidth
            variant="outlined"
            value={passwordDialog.newPassword}
            onChange={(e) =>
              setPasswordDialog((prev) => ({
                ...prev,
                newPassword: e.target.value,
                errors: { ...prev.errors, newPassword: "" },
              }))
            }
            error={Boolean(passwordDialog.errors.newPassword)}
            helperText={
              passwordDialog.errors.newPassword ||
              "Must be at least 8 characters with uppercase, lowercase, and number"
            }
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            label="Confirm New Password"
            type="password"
            fullWidth
            variant="outlined"
            value={passwordDialog.confirmPassword}
            onChange={(e) =>
              setPasswordDialog((prev) => ({
                ...prev,
                confirmPassword: e.target.value,
                errors: { ...prev.errors, confirmPassword: "" },
              }))
            }
            error={Boolean(passwordDialog.errors.confirmPassword)}
            helperText={passwordDialog.errors.confirmPassword}
            onKeyPress={(e) => {
              if (e.key === "Enter") {
                handlePasswordDialogSubmit();
              }
            }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handlePasswordDialogClose}>Cancel</Button>
          <Button
            onClick={handlePasswordDialogSubmit}
            variant="contained"
            disabled={loading}
            startIcon={loading && <CircularProgress size={20} />}
          >
            {loading ? "Changing..." : "Change Password"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert
          onClose={() => setSnackbar({ ...snackbar, open: false })}
          severity={snackbar.severity}
          sx={{ width: "100%" }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default Settings;
