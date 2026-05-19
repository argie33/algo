import { useState, useEffect } from "react";
import {
  Container,
  Box,
  Typography,
  Tabs,
  Tab,
  Card,
  CardContent,
  TextField,
  Button,
  Alert,
  Switch,
  FormControlLabel,
  CircularProgress,
  Grid,
} from "@mui/material";
import { Settings as SettingsIcon } from "@mui/icons-material";
import api, { getSettings, updateSettings } from "../services/api";

function TabPanel(props) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`settings-tabpanel-${index}`}
      aria-labelledby={`settings-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );
}

const Settings = () => {
  const [tabIndex, setTabIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [settings, setSettings] = useState({});
  const [_apiKeys, setApiKeys] = useState({});
  const [_showAddKeyDialog, setShowAddKeyDialog] = useState(false);
  const [newApiKey, setNewApiKey] = useState({
    provider: "alpaca",
    keyId: "",
    secret: "",
  });

  // Load settings on mount
  useEffect(() => {
    const loadSettings = async () => {
      setLoading(true);
      try {
        const settingsRes = await getSettings();
        setSettings(settingsRes?.data || settingsRes || {});
      } catch (err) {
        setError("Failed to load settings");
        console.error("Settings load error:", err);
      } finally {
        setLoading(false);
      }
    };

    loadSettings();
  }, []);

  const handleTabChange = (event, newValue) => {
    setTabIndex(newValue);
  };

  const handleSaveGeneralSettings = async () => {
    try {
      setLoading(true);
      await updateSettings(settings);
      setMessage("Settings saved successfully!");
      setTimeout(() => setMessage(""), 3000);
    } catch (err) {
      setError("Failed to save settings");
      console.error("Error:", err);
    } finally {
      setLoading(false);
    }
  };

  const _handleAddApiKey = async () => {
    try {
      setLoading(true);

      // Test the API key first
      const testResult = await api.testApiKey?.(newApiKey);
      if (!testResult?.isValid) {
        setError(testResult?.error || "API key validation failed");
        return;
      }

      // Save the API key
      await api.saveApiKey?.(newApiKey);
      setMessage("API key saved successfully!");
      setShowAddKeyDialog(false);
      setNewApiKey({ provider: "alpaca", keyId: "", secret: "" });

      // Reload API keys
      const keysRes = await api.getApiKeys?.();
      setApiKeys(keysRes?.data || {});
    } catch (err) {
      setError("Failed to save API key");
    } finally {
      setLoading(false);
    }
  };

  const _handleDeleteApiKey = async (provider) => {
    try {
      setLoading(true);
      await api.deleteApiKey?.({ provider });
      setMessage("API key deleted successfully!");

      // Reload API keys
      const keysRes = await api.getApiKeys?.();
      setApiKeys(keysRes?.data || {});
    } catch (err) {
      setError("Failed to delete API key");
    } finally {
      setLoading(false);
    }
  };

  const handleNotificationChange = async (key, value) => {
    const updated = {
      ...settings,
      [key]: value,
    };
    setSettings(updated);

    try {
      await updateSettings(updated);
      setMessage("Preferences updated!");
      setTimeout(() => setMessage(""), 3000);
    } catch (err) {
      setError("Failed to update preferences");
      console.error("Error:", err);
    }
  };

  if (loading && !settings.profile) {
    return (
      <Container maxWidth="md" sx={{ py: 4, display: "flex", justifyContent: "center" }}>
        <CircularProgress />
      </Container>
    );
  }

  const profile = settings.profile || {};
  const notifications = settings.notifications || {};

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 4 }}>
        <SettingsIcon sx={{ mr: 2, fontSize: 32 }} />
        <Typography variant="h4">Settings</Typography>
      </Box>

      {message && (
        <Alert severity="success" sx={{ mb: 3 }} onClose={() => setMessage("")}>
          {message}
        </Alert>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError("")}>
          {error}
        </Alert>
      )}

      <Card>
        <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
          <Tabs value={tabIndex} onChange={handleTabChange} aria-label="settings tabs">
            <Tab
              label="General Settings"
              id="settings-tab-0"
              aria-controls="settings-tabpanel-0"
            />
            <Tab
              label="Preferences"
              id="settings-tab-1"
              aria-controls="settings-tabpanel-1"
            />
            <Tab
              label="Account"
              id="settings-tab-3"
              aria-controls="settings-tabpanel-3"
            />
          </Tabs>
        </Box>

        {/* General Settings Tab */}
        <TabPanel value={tabIndex} index={0}>
          <CardContent>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <TextField
                label="Theme"
                value={settings.theme || "dark"}
                onChange={(e) => setSettings({ ...settings, theme: e.target.value })}
                select
                SelectProps={{ native: true }}
                fullWidth
              >
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </TextField>

              <TextField
                label="Default View"
                value={settings.defaultView || "market"}
                onChange={(e) => setSettings({ ...settings, defaultView: e.target.value })}
                select
                SelectProps={{ native: true }}
                fullWidth
              >
                <option value="market">Market Overview</option>
                <option value="stocks">Stock Analysis</option>
                <option value="economic">Economic Data</option>
              </TextField>

              <Box sx={{ pt: 2 }}>
                <Button
                  variant="contained"
                  onClick={handleSaveGeneralSettings}
                  disabled={loading}
                >
                  Save Settings
                </Button>
              </Box>
            </Box>
          </CardContent>
        </TabPanel>

        {/* Preferences Tab */}
        <TabPanel value={tabIndex} index={1}>
          <CardContent>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={notifications.email || false}
                    onChange={(e) => handleNotificationChange("email", e.target.checked)}
                  />
                }
                label="Email Notifications"
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={notifications.push || false}
                    onChange={(e) => handleNotificationChange("push", e.target.checked)}
                  />
                }
                label="Push Notifications"
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={notifications.alerts || false}
                    onChange={(e) => handleNotificationChange("alerts", e.target.checked)}
                  />
                }
                label="Trading Alerts"
              />

              <Typography variant="caption" color="textSecondary" sx={{ pt: 2 }}>
                Changes are automatically saved
              </Typography>
            </Box>
          </CardContent>
        </TabPanel>

        {/* Account Tab */}
        <TabPanel value={tabIndex} index={2}>
          <CardContent>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}>
                <TextField
                  label="First Name"
                  value={profile.firstName || ""}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      profile: { ...profile, firstName: e.target.value },
                    })
                  }
                  fullWidth
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  label="Last Name"
                  value={profile.lastName || ""}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      profile: { ...profile, lastName: e.target.value },
                    })
                  }
                  fullWidth
                />
              </Grid>

              <Grid item xs={12}>
                <TextField
                  label="Email"
                  type="email"
                  value={profile.email || ""}
                  disabled
                  fullWidth
                  helperText="Email cannot be changed"
                />
              </Grid>

              <Grid item xs={12}>
                <Box sx={{ pt: 2 }}>
                  <Button variant="contained" onClick={handleSaveGeneralSettings}>
                    Save Profile
                  </Button>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </TabPanel>
      </Card>
    </Container>
  );
};

export default Settings;
