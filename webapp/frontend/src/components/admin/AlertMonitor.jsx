import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  Typography,
  Grid,
  Box,
  Chip,
  Alert,
  AlertTitle,
  Button,
  Switch,
  FormControlLabel,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Divider,
  Badge,
  LinearProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from "@mui/material";
import {
  Warning as WarningIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  Refresh as RefreshIcon,
  Email as EmailIcon,
  CheckCircle as CheckCircleIcon,
  Settings as SettingsIcon,
  ExpandMore as ExpandMoreIcon,
  Close as CloseIcon,
  BugReport,
  Message,
} from "@mui/icons-material";

const AlertMonitor = ({ alertData, onConfigUpdate, onRefresh }) => {
  const [alerts, setAlerts] = useState(
    alertData || { active: [], summary: {}, recent: [] }
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [testingNotifications, setTestingNotifications] = useState(false);
  const [alertConfig, setAlertConfig] = useState({
    thresholds: {
      latency: { warning: 100, critical: 200 },
      errorRate: { warning: 0.02, critical: 0.05 },
      costDaily: { warning: 40, critical: 50 },
    },
    notifications: {
      email: { enabled: false, recipients: [] },
      slack: { enabled: false, webhook: "", channel: "#alerts" },
      webhook: { enabled: false, url: "" },
    },
  });

  useEffect(() => {
    setAlerts(alertData || { active: [], summary: {}, recent: [] });
  }, [alertData]);

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case "critical":
        return <ErrorIcon color="error" />;
      case "warning":
        return <WarningIcon color="warning" />;
      case "info":
        return <InfoIcon color="info" />;
      default:
        return <CheckCircleIcon color="success" />;
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case "critical":
        return "error";
      case "warning":
        return "warning";
      case "info":
        return "info";
      default:
        return "default";
    }
  };

  const formatTimeAgo = (timestamp) => {
    const now = Date.now();
    const diff = now - timestamp;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) return `${days}d ago`;
    if (hours > 0) return `${hours}h ago`;
    if (minutes > 0) return `${minutes}m ago`;
    return "Just now";
  };

  const handleTestNotifications = async () => {
    setTestingNotifications(true);
    try {
      // Mock API call to test notifications
      const response = await fetch("/api/liveDataAdmin/alerts/test", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("token")}`,
          "Content-Type": "application/json",
        },
      });

      if (response.ok) {
        console.log("Test notifications sent successfully");
      }
    } catch (error) {
      console.error("Failed to test notifications:", error);
    } finally {
      setTestingNotifications(false);
    }
  };

  const handleConfigSave = async () => {
    try {
      // Mock API call to save configuration
      const response = await fetch("/api/liveDataAdmin/alerts/configure", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("token")}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(alertConfig),
      });

      if (response.ok) {
        onConfigUpdate?.(alertConfig);
        setSettingsOpen(false);
      }
    } catch (error) {
      console.error("Failed to save alert configuration:", error);
    }
  };

  const handleForceHealthCheck = async () => {
    try {
      const response = await fetch("/api/liveDataAdmin/alerts/health-check", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
      });

      if (response.ok) {
        onRefresh?.();
      }
    } catch (error) {
      console.error("Failed to force health check:", error);
    }
  };

  return (
    <Box>
      {/* Alert Overview */}
      <Card elevation={2} sx={{ mb: 3 }}>
        <CardContent>
          <Box
            display="flex"
            justifyContent="space-between"
            alignItems="center"
            mb={2}
          >
            <Typography variant="h6" fontWeight="bold">
              Alert Monitor & Health Status
            </Typography>
            <Box display="flex" gap={1}>
              <Button
                startIcon={<BugReport />}
                variant="outlined"
                onClick={handleTestNotifications}
                disabled={testingNotifications}
                size="small"
              >
                Test Alerts
              </Button>
              <Button
                startIcon={<RefreshIcon />}
                variant="outlined"
                onClick={handleForceHealthCheck}
                size="small"
              >
                Health Check
              </Button>
              <Button
                startIcon={<SettingsIcon />}
                variant="outlined"
                onClick={() => setSettingsOpen(true)}
                size="small"
              >
                Configure
              </Button>
              <Button
                startIcon={<RefreshIcon />}
                variant="contained"
                onClick={onRefresh}
                size="small"
              >
                Refresh
              </Button>
            </Box>
          </Box>

          {/* Alert Summary Cards */}
          <Grid container spacing={3}>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="error.light"
                borderRadius={1}
              >
                <Badge
                  badgeContent={alerts.summary?.critical || 0}
                  color="error"
                >
                  <ErrorIcon fontSize="large" sx={{ color: "white" }} />
                </Badge>
                <Typography variant="h6" color="white" mt={1}>
                  Critical Alerts
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="warning.light"
                borderRadius={1}
              >
                <Badge
                  badgeContent={alerts.summary?.warning || 0}
                  color="warning"
                >
                  <WarningIcon fontSize="large" sx={{ color: "white" }} />
                </Badge>
                <Typography variant="h6" color="white" mt={1}>
                  Warning Alerts
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="info.light"
                borderRadius={1}
              >
                <Badge badgeContent={alerts.summary?.info || 0} color="info">
                  <InfoIcon fontSize="large" sx={{ color: "white" }} />
                </Badge>
                <Typography variant="h6" color="white" mt={1}>
                  Info Alerts
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="success.light"
                borderRadius={1}
              >
                <CheckCircleIcon fontSize="large" sx={{ color: "white" }} />
                <Typography variant="h6" color="white" mt={1}>
                  System Healthy
                </Typography>
                <Typography variant="body2" color="white">
                  {alerts.summary?.total === 0
                    ? "All Good"
                    : `${alerts.summary?.total || 0} Issues`}
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Grid container spacing={3}>
        {/* Active Alerts */}
        <Grid item xs={12} lg={8}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Active Alerts
              </Typography>

              {!alerts.active || alerts.active.length === 0 ? (
                <Alert severity="success">
                  <AlertTitle>All Systems Operational</AlertTitle>
                  No active alerts detected. All systems are running normally.
                </Alert>
              ) : (
                <Box>
                  {alerts.active.map((alert) => (
                    <Accordion key={alert.id} sx={{ mb: 1 }}>
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Box
                          display="flex"
                          alignItems="center"
                          width="100%"
                          gap={2}
                        >
                          {getSeverityIcon(alert.severity)}
                          <Box flexGrow={1}>
                            <Typography variant="subtitle1" fontWeight="medium">
                              {alert.title}
                            </Typography>
                            <Typography variant="body2" color="textSecondary">
                              {formatTimeAgo(alert.createdAt)}
                              {alert.count > 1 &&
                                ` • ${alert.count} occurrences`}
                            </Typography>
                          </Box>
                          <Chip
                            label={alert.severity}
                            size="small"
                            color={getSeverityColor(alert.severity)}
                          />
                        </Box>
                      </AccordionSummary>
                      <AccordionDetails>
                        <Typography variant="body2" paragraph>
                          {alert.message}
                        </Typography>

                        {alert.metadata &&
                          Object.keys(alert.metadata).length > 0 && (
                            <Box>
                              <Typography variant="subtitle2" gutterBottom>
                                Details:
                              </Typography>
                              <Box
                                component="pre"
                                sx={{
                                  fontSize: "0.75rem",
                                  bgcolor: "grey.100",
                                  p: 1,
                                  borderRadius: 1,
                                  overflow: "auto",
                                }}
                              >
                                {JSON.stringify(alert.metadata, null, 2)}
                              </Box>
                            </Box>
                          )}

                        <Box
                          display="flex"
                          justifyContent="space-between"
                          alignItems="center"
                          mt={2}
                        >
                          <Typography variant="caption" color="textSecondary">
                            Created:{" "}
                            {new Date(alert.createdAt).toLocaleString()}
                          </Typography>
                          <Button
                            size="small"
                            startIcon={<CloseIcon />}
                            color="primary"
                          >
                            Acknowledge
                          </Button>
                        </Box>
                      </AccordionDetails>
                    </Accordion>
                  ))}
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Notification Status */}
        <Grid item xs={12} lg={4}>
          <Card elevation={2} sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Notification Channels
              </Typography>

              <Box
                display="flex"
                alignItems="center"
                justifyContent="space-between"
                mb={2}
              >
                <Box display="flex" alignItems="center" gap={1}>
                  <EmailIcon
                    color={
                      alertConfig.notifications.email.enabled
                        ? "primary"
                        : "disabled"
                    }
                  />
                  <Typography variant="body2">Email</Typography>
                </Box>
                <Chip
                  label={
                    alertConfig.notifications.email.enabled
                      ? "Enabled"
                      : "Disabled"
                  }
                  size="small"
                  color={
                    alertConfig.notifications.email.enabled
                      ? "success"
                      : "default"
                  }
                />
              </Box>

              <Box
                display="flex"
                alignItems="center"
                justifyContent="space-between"
                mb={2}
              >
                <Box display="flex" alignItems="center" gap={1}>
                  <Message
                    color={
                      alertConfig.notifications.slack.enabled
                        ? "primary"
                        : "disabled"
                    }
                  />
                  <Typography variant="body2">Slack</Typography>
                </Box>
                <Chip
                  label={
                    alertConfig.notifications.slack.enabled
                      ? "Enabled"
                      : "Disabled"
                  }
                  size="small"
                  color={
                    alertConfig.notifications.slack.enabled
                      ? "success"
                      : "default"
                  }
                />
              </Box>

              <Box
                display="flex"
                alignItems="center"
                justifyContent="space-between"
                mb={2}
              >
                <Box display="flex" alignItems="center" gap={1}>
                  <WebhookIcon
                    color={
                      alertConfig.notifications.webhook.enabled
                        ? "primary"
                        : "disabled"
                    }
                  />
                  <Typography variant="body2">Webhook</Typography>
                </Box>
                <Chip
                  label={
                    alertConfig.notifications.webhook.enabled
                      ? "Enabled"
                      : "Disabled"
                  }
                  size="small"
                  color={
                    alertConfig.notifications.webhook.enabled
                      ? "success"
                      : "default"
                  }
                />
              </Box>

              <Divider sx={{ my: 2 }} />

              <Button
                fullWidth
                startIcon={<BugReport />}
                variant="outlined"
                onClick={handleTestNotifications}
                disabled={testingNotifications}
              >
                {testingNotifications ? "Testing..." : "Test All Channels"}
              </Button>
            </CardContent>
          </Card>

          {/* Recent Alert History */}
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Recent Activity
              </Typography>

              {!alerts.recent || alerts.recent.length === 0 ? (
                <Typography variant="body2" color="textSecondary">
                  No recent activity
                </Typography>
              ) : (
                <Box>
                  {alerts.recent.slice(0, 5).map((alert, index) => (
                    <Box
                      key={index}
                      display="flex"
                      alignItems="center"
                      gap={2}
                      mb={1}
                    >
                      {getSeverityIcon(alert.severity)}
                      <Box flexGrow={1}>
                        <Typography variant="body2" fontWeight="medium">
                          {alert.title}
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                          {formatTimeAgo(alert.createdAt)}
                        </Typography>
                      </Box>
                      <Chip
                        label={alert.action || "created"}
                        size="small"
                        variant="outlined"
                      />
                    </Box>
                  ))}
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Health Thresholds */}
        <Grid item xs={12}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Health Monitoring Thresholds
              </Typography>

              <Grid container spacing={3}>
                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" gutterBottom>
                    Latency Monitoring
                  </Typography>
                  <Box mb={1}>
                    <Typography variant="body2" color="textSecondary">
                      Warning: {alertConfig.thresholds.latency.warning}ms
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={50}
                      color="warning"
                      sx={{ height: 6, borderRadius: 3 }}
                    />
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      Critical: {alertConfig.thresholds.latency.critical}ms
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={80}
                      color="error"
                      sx={{ height: 6, borderRadius: 3 }}
                    />
                  </Box>
                </Grid>

                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" gutterBottom>
                    Error Rate Monitoring
                  </Typography>
                  <Box mb={1}>
                    <Typography variant="body2" color="textSecondary">
                      Warning:{" "}
                      {(alertConfig.thresholds.errorRate.warning * 100).toFixed(
                        1
                      )}
                      %
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={30}
                      color="warning"
                      sx={{ height: 6, borderRadius: 3 }}
                    />
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      Critical:{" "}
                      {(
                        alertConfig.thresholds.errorRate.critical * 100
                      ).toFixed(1)}
                      %
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={60}
                      color="error"
                      sx={{ height: 6, borderRadius: 3 }}
                    />
                  </Box>
                </Grid>

                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" gutterBottom>
                    Daily Cost Monitoring
                  </Typography>
                  <Box mb={1}>
                    <Typography variant="body2" color="textSecondary">
                      Warning: ${alertConfig.thresholds.costDaily.warning}
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={70}
                      color="warning"
                      sx={{ height: 6, borderRadius: 3 }}
                    />
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">
                      Critical: ${alertConfig.thresholds.costDaily.critical}
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={90}
                      color="error"
                      sx={{ height: 6, borderRadius: 3 }}
                    />
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Alert Configuration Dialog */}
      <Dialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Alert Configuration</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <Typography variant="h6" gutterBottom>
              Alert Thresholds
            </Typography>

            <Grid container spacing={2} mb={3}>
              <Grid item xs={6}>
                <TextField
                  fullWidth
                  label="Latency Warning (ms)"
                  type="number"
                  value={alertConfig.thresholds.latency.warning}
                  onChange={(e) =>
                    setAlertConfig((prev) => ({
                      ...prev,
                      thresholds: {
                        ...prev.thresholds,
                        latency: {
                          ...prev.thresholds.latency,
                          warning: parseInt(e.target.value),
                        },
                      },
                    }))
                  }
                />
              </Grid>
              <Grid item xs={6}>
                <TextField
                  fullWidth
                  label="Latency Critical (ms)"
                  type="number"
                  value={alertConfig.thresholds.latency.critical}
                  onChange={(e) =>
                    setAlertConfig((prev) => ({
                      ...prev,
                      thresholds: {
                        ...prev.thresholds,
                        latency: {
                          ...prev.thresholds.latency,
                          critical: parseInt(e.target.value),
                        },
                      },
                    }))
                  }
                />
              </Grid>
            </Grid>

            <Typography variant="h6" gutterBottom>
              Notification Channels
            </Typography>

            <FormControlLabel
              control={
                <Switch
                  checked={alertConfig.notifications.email.enabled}
                  onChange={(e) =>
                    setAlertConfig((prev) => ({
                      ...prev,
                      notifications: {
                        ...prev.notifications,
                        email: {
                          ...prev.notifications.email,
                          enabled: e.target.checked,
                        },
                      },
                    }))
                  }
                />
              }
              label="Email Notifications"
            />

            <FormControlLabel
              control={
                <Switch
                  checked={alertConfig.notifications.slack.enabled}
                  onChange={(e) =>
                    setAlertConfig((prev) => ({
                      ...prev,
                      notifications: {
                        ...prev.notifications,
                        slack: {
                          ...prev.notifications.slack,
                          enabled: e.target.checked,
                        },
                      },
                    }))
                  }
                />
              }
              label="Slack Notifications"
            />

            <FormControlLabel
              control={
                <Switch
                  checked={alertConfig.notifications.webhook.enabled}
                  onChange={(e) =>
                    setAlertConfig((prev) => ({
                      ...prev,
                      notifications: {
                        ...prev.notifications,
                        webhook: {
                          ...prev.notifications.webhook,
                          enabled: e.target.checked,
                        },
                      },
                    }))
                  }
                />
              }
              label="Webhook Notifications"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSettingsOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleConfigSave}>
            Save Configuration
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default AlertMonitor;
