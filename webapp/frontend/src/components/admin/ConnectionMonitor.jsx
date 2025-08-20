import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  Typography,
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  IconButton,
  Tooltip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Alert,
  Switch,
  FormControlLabel,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from "@mui/material";
import {
  Close as CloseIcon,
  Refresh as RefreshIcon,
  Check as CheckIcon,
  Error as ErrorIcon,
  NetworkCheck as NetworkIcon,
  Add as AddIcon,
} from "@mui/icons-material";

const ConnectionMonitor = ({
  connectionsData,
  onConnectionAction,
  onRefresh,
}) => {
  const [connections, setConnections] = useState(connectionsData || []);
  const [createDialog, setCreateDialog] = useState(false);
  const [newConnection, setNewConnection] = useState({
    provider: "",
    symbols: "",
    autoReconnect: true,
  });

  useEffect(() => {
    setConnections(connectionsData || []);
  }, [connectionsData]);

  const getConnectionStatusColor = (status) => {
    switch (status) {
      case "connected":
        return "success";
      case "connecting":
        return "warning";
      case "disconnected":
        return "error";
      case "reconnecting":
        return "warning";
      default:
        return "default";
    }
  };

  const getConnectionStatusIcon = (status) => {
    switch (status) {
      case "connected":
        return <CheckIcon color="success" />;
      case "connecting":
        return <RefreshIcon color="warning" />;
      case "disconnected":
        return <ErrorIcon color="error" />;
      case "reconnecting":
        return <RefreshIcon color="warning" />;
      default:
        return <NetworkIcon />;
    }
  };

  const handleCreateConnection = async () => {
    try {
      const symbols = newConnection.symbols
        .split(",")
        .map((s) => s.trim().toUpperCase());
      const connectionData = {
        provider: newConnection.provider,
        symbols,
        autoReconnect: newConnection.autoReconnect,
      };

      // API call to create connection
      const response = await fetch("/api/liveDataAdmin/connections", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify(connectionData),
      });

      if (response.ok) {
        const result = await response.json();
        setConnections((prev) => [
          ...prev,
          {
            id: result.connectionId,
            provider: newConnection.provider,
            symbols,
            status: "connecting",
            created: new Date(),
            lastActivity: new Date(),
            metrics: {
              messagesReceived: 0,
              bytesReceived: 0,
              errors: 0,
              latency: [],
            },
          },
        ]);
        setCreateDialog(false);
        setNewConnection({ provider: "", symbols: "", autoReconnect: true });
        onConnectionAction?.("create", connectionData);
      }
    } catch (error) {
      console.error("Failed to create connection:", error);
    }
  };

  const handleCloseConnection = async (connectionId) => {
    try {
      // API call to close connection
      const response = await fetch(
        `/api/liveDataAdmin/connections/${connectionId}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${localStorage.getItem("token")}`,
          },
        }
      );

      if (response.ok) {
        setConnections((prev) =>
          prev.filter((conn) => conn.id !== connectionId)
        );
        onConnectionAction?.("close", connectionId);
      }
    } catch (error) {
      console.error("Failed to close connection:", error);
    }
  };

  const formatDuration = (date) => {
    const now = new Date();
    const diff = now - new Date(date);
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) return `${days}d ${hours % 24}h`;
    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    return `${minutes}m`;
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  return (
    <Box>
      {/* Connection Overview */}
      <Card elevation={2} sx={{ mb: 3 }}>
        <CardContent>
          <Box
            display="flex"
            justifyContent="space-between"
            alignItems="center"
            mb={2}
          >
            <Typography variant="h6" fontWeight="bold">
              Live Connection Monitor
            </Typography>
            <Box display="flex" gap={1}>
              <Button
                startIcon={<AddIcon />}
                variant="contained"
                onClick={() => setCreateDialog(true)}
                size="small"
              >
                New Connection
              </Button>
              <Button
                startIcon={<RefreshIcon />}
                variant="outlined"
                onClick={onRefresh}
                size="small"
              >
                Refresh
              </Button>
            </Box>
          </Box>

          <Grid container spacing={3}>
            <Grid item xs={12} sm={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="primary">
                  {connections.filter((c) => c.status === "connected").length}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  Active Connections
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="info.main">
                  {connections.reduce(
                    (sum, c) => sum + (c.symbols?.length || 0),
                    0
                  )}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  Total Symbols
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="success.main">
                  {connections
                    .reduce(
                      (sum, c) => sum + (c.metrics?.messagesReceived || 0),
                      0
                    )
                    .toLocaleString()}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  Messages Received
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="warning.main">
                  {formatBytes(
                    connections.reduce(
                      (sum, c) => sum + (c.metrics?.bytesReceived || 0),
                      0
                    )
                  )}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  Data Transferred
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Connection Details Table */}
      <Card elevation={2}>
        <CardContent>
          <Typography variant="h6" fontWeight="bold" gutterBottom>
            Connection Details
          </Typography>

          {connections.length === 0 ? (
            <Alert severity="info">
              No active connections. Create a new connection to start monitoring
              live data feeds.
            </Alert>
          ) : (
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Connection</TableCell>
                    <TableCell>Provider</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell align="right">Symbols</TableCell>
                    <TableCell align="right">Messages</TableCell>
                    <TableCell align="right">Data</TableCell>
                    <TableCell align="right">Errors</TableCell>
                    <TableCell align="right">Uptime</TableCell>
                    <TableCell align="right">Avg Latency</TableCell>
                    <TableCell align="center">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {connections.map((connection) => (
                    <TableRow key={connection.id}>
                      <TableCell>
                        <Box>
                          <Typography variant="body2" fontWeight="medium">
                            {connection.id.split("-")[0]}...
                          </Typography>
                          <Typography variant="caption" color="textSecondary">
                            Created:{" "}
                            {new Date(connection.created).toLocaleTimeString()}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" fontWeight="medium">
                          {connection.provider}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          {getConnectionStatusIcon(connection.status)}
                          <Chip
                            label={connection.status}
                            size="small"
                            color={getConnectionStatusColor(connection.status)}
                          />
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Tooltip
                          title={connection.symbols?.join(", ") || "No symbols"}
                        >
                          <span>{connection.symbols?.length || 0}</span>
                        </Tooltip>
                      </TableCell>
                      <TableCell align="right">
                        {(
                          connection.metrics?.messagesReceived || 0
                        ).toLocaleString()}
                      </TableCell>
                      <TableCell align="right">
                        {formatBytes(connection.metrics?.bytesReceived || 0)}
                      </TableCell>
                      <TableCell align="right">
                        <Typography
                          variant="body2"
                          color={
                            (connection.metrics?.errors || 0) > 0
                              ? "error"
                              : "textPrimary"
                          }
                        >
                          {connection.metrics?.errors || 0}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        {formatDuration(connection.created)}
                      </TableCell>
                      <TableCell align="right">
                        {connection.metrics?.latency?.length > 0
                          ? `${(connection.metrics.latency.reduce((a, b) => a + b, 0) / connection.metrics.latency.length).toFixed(0)}ms`
                          : "N/A"}
                      </TableCell>
                      <TableCell align="center">
                        <Tooltip title="Close Connection">
                          <IconButton
                            size="small"
                            onClick={() => handleCloseConnection(connection.id)}
                            color="error"
                          >
                            <CloseIcon />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Create Connection Dialog */}
      <Dialog
        open={createDialog}
        onClose={() => setCreateDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create New Connection</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <FormControl fullWidth>
                  <InputLabel>Data Provider</InputLabel>
                  <Select
                    value={newConnection.provider}
                    label="Data Provider"
                    onChange={(e) =>
                      setNewConnection((prev) => ({
                        ...prev,
                        provider: e.target.value,
                      }))
                    }
                  >
                    <MenuItem value="alpaca">Alpaca Markets</MenuItem>
                    <MenuItem value="polygon">Polygon.io</MenuItem>
                    <MenuItem value="finnhub">Finnhub</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Symbols (comma-separated)"
                  placeholder="AAPL, MSFT, GOOGL, TSLA"
                  value={newConnection.symbols}
                  onChange={(e) =>
                    setNewConnection((prev) => ({
                      ...prev,
                      symbols: e.target.value,
                    }))
                  }
                  helperText="Enter stock symbols separated by commas"
                />
              </Grid>
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={newConnection.autoReconnect}
                      onChange={(e) =>
                        setNewConnection((prev) => ({
                          ...prev,
                          autoReconnect: e.target.checked,
                        }))
                      }
                    />
                  }
                  label="Auto-reconnect on disconnect"
                />
              </Grid>
              <Grid item xs={12}>
                <Alert severity="info">
                  This will create a new WebSocket connection to stream
                  real-time data for the specified symbols.
                </Alert>
              </Grid>
            </Grid>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialog(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleCreateConnection}
            disabled={!newConnection.provider || !newConnection.symbols}
          >
            Create Connection
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ConnectionMonitor;
