import { useState, useEffect } from "react";
import {
  Container,
  Box,
  Typography,
  Tabs,
  Tab,
  Card,
  CardContent,
  CardHeader,
  TextField,
  Button,
  Alert,
  Switch,
  FormControlLabel,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
} from "@mui/material";
import { Settings as SettingsIcon, Delete as DeleteIcon } from "@mui/icons-material";
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
  const [apiKeys, setApiKeys] = useState({});
  const [showAddKeyDialog, setShowAddKeyDialog] = useState(false);
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

  const handleAddApiKey = async () => {
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

  const handleDeleteApiKey = async (provider) => {
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
              label="API Keys"
              id="settings-tab-1"
              aria-controls="settings-tabpanel-1"
              data-testid="api-keys-tab"
            />
            <Tab
              label="Preferences"
              id="settings-tab-2"
              aria-controls="settings-tabpanel-2"
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

        {/* API Keys Tab */}
        <TabPanel value={tabIndex} index={1}>
          <CardContent>
            <Box sx={{ mb: 3 }}>
              <Button
                variant="contained"
                onClick={() => setShowAddKeyDialog(true)}
                data-testid="add-api-key-button"
                sx={{ mb: 2 }}
              >
                Add API Key
              </Button>

              {Object.keys(apiKeys).length > 0 ? (
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Provider</TableCell>
                        <TableCell>Key ID</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {Object.entries(apiKeys).map(([provider, key]) => (
                        <TableRow key={provider}>
                          <TableCell sx={{ textTransform: "capitalize" }}>
                            {provider}
                          </TableCell>
                          <TableCell>{key.keyId || "—"}</TableCell>
                          <TableCell>
                            {key.isValid ? "✓ Valid" : "✗ Invalid"}
                          </TableCell>
                          <TableCell>
                            <Button
                              size="small"
                              color="error"
                              startIcon={<DeleteIcon />}
                              onClick={() => handleDeleteApiKey(provider)}
                              disabled={loading}
                            >
                              Delete
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Typography color="textSecondary">No API keys configured</Typography>
              )}
            </Box>
          </CardContent>
        </TabPanel>

        {/* Preferences Tab */}
        <TabPanel value={tabIndex} index={2}>
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
        <TabPanel value={tabIndex} index={3}>
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

      {/* Add API Key Dialog */}
      <Dialog open={showAddKeyDialog} onClose={() => setShowAddKeyDialog(false)}>
        <DialogTitle>Add API Key</DialogTitle>
        <DialogContent sx={{ minWidth: 400, pt: 2 }}>
          <TextField
            label="Provider"
            value={newApiKey.provider}
            onChange={(e) => setNewApiKey({ ...newApiKey, provider: e.target.value })}
            select
            SelectProps={{ native: true }}
            fullWidth
            sx={{ mb: 2 }}
          >
            <option value="alpaca">Alpaca</option>
            <option value="polygon">Polygon</option>
            <option value="fred">FRED</option>
          </TextField>

          <TextField
            label="API Key ID"
            value={newApiKey.keyId}
            onChange={(e) => setNewApiKey({ ...newApiKey, keyId: e.target.value })}
            placeholder="Your API key ID"
            fullWidth
            sx={{ mb: 2 }}
          />

          <TextField
            label="API Secret"
            type="password"
            value={newApiKey.secret}
            onChange={(e) => setNewApiKey({ ...newApiKey, secret: e.target.value })}
            placeholder="Your API secret"
            fullWidth
            sx={{ mb: 2 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowAddKeyDialog(false)}>Cancel</Button>
          <Button onClick={handleAddApiKey} variant="contained" disabled={loading}>
            Add Key
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default Settings;
