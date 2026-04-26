import { useState } from "react";
import {
  Container,
  Paper,
  Typography,
  Box,
  TextField,
  Button,
  Alert,
  Grid,
  Card,
  CardContent,
  CardHeader,
} from "@mui/material";
import { Settings as SettingsIcon } from "@mui/icons-material";

const Settings = () => {
  const [message, setMessage] = useState("");
  const [apiKey, setApiKey] = useState("");

  const handleSaveSettings = () => {
    setMessage("Settings saved successfully!");
    setTimeout(() => setMessage(""), 3000);
  };

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 4 }}>
        <SettingsIcon sx={{ mr: 2, fontSize: 32 }} />
        <Typography variant="h4">Settings</Typography>
      </Box>

      {message && (
        <Alert severity="success" sx={{ mb: 3 }}>
          {message}
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* General Settings */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="General Settings" />
            <CardContent>
              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <TextField
                  label="Theme"
                  defaultValue="light"
                  select
                  SelectProps={{ native: true }}
                  fullWidth
                >
                  <option value="light">Light</option>
                  <option value="dark">Dark</option>
                </TextField>

                <TextField
                  label="Default View"
                  defaultValue="market"
                  select
                  SelectProps={{ native: true }}
                  fullWidth
                >
                  <option value="market">Market Overview</option>
                  <option value="stocks">Stock Analysis</option>
                  <option value="economic">Economic Data</option>
                </TextField>

                <Button variant="contained" onClick={handleSaveSettings}>
                  Save Settings
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* API Configuration */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="API Configuration" />
            <CardContent>
              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <TextField
                  label="API Key"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  fullWidth
                  placeholder="Enter your API key"
                />
                <TextField
                  label="API Endpoint"
                  defaultValue="http://localhost:3001"
                  disabled
                  fullWidth
                />
                <Button variant="contained">Test Connection</Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* About */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="About" />
            <CardContent>
              <Typography variant="body2" color="textSecondary">
                Bullseye Financial Dashboard
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
                Version: 1.0.0
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
                API Server: http://localhost:3001
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
};

export default Settings;
