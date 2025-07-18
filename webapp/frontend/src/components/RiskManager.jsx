import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  LinearProgress,
  Alert,
  Chip,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip,
  Switch,
  FormControlLabel,
  TextField,
  Slider,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  ListItemSecondaryAction,
  Tabs,
  Tab,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import {
  Warning,
  Security,
  TrendingDown,
  TrendingUp,
  Shield,
  Speed,
  AccountBalance,
  Assessment,
  Stop,
  PlayArrow,
  Pause,
  Settings,
  Refresh,
  NotificationsActive,
  Error,
  CheckCircle,
  Info,
  ExpandMore,
  Timeline,
  PieChart,
  ShowChart,
  MonetizationOn,
  Lock,
  LockOpen
} from '@mui/icons-material';
import { PieChart as RechartsPieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, LineChart, Line } from 'recharts';

const COLORS = ['#f44336', '#ff9800', '#ffeb3b', '#4caf50', '#2196f3'];

const RiskManager = ({ portfolioData, positions, onRiskAlert }) => {
  const [tabValue, setTabValue] = useState(0);
  const [riskMetrics, setRiskMetrics] = useState({
    totalRisk: 0,
    maxDrawdown: 0,
    valueAtRisk: 0,
    sharpeRatio: 0,
    beta: 0,
    volatility: 0,
    concentration: 0,
    leverage: 0,
    dailyPnL: 0,
    weeklyPnL: 0,
    monthlyPnL: 0
  });

  const [riskSettings, setRiskSettings] = useState({
    maxPortfolioRisk: 0.02,
    maxPositionSize: 0.05,
    maxDrawdown: 0.10,
    maxDailyLoss: 0.05,
    maxConcentration: 0.20,
    maxLeverage: 2.0,
    stopLossEnabled: true,
    takeProfitEnabled: true,
    riskAlertsEnabled: true,
    autoHedging: false,
    emergencyStopEnabled: true
  });

  const [riskAlerts, setRiskAlerts] = useState([]);
  const [riskMonitoring, setRiskMonitoring] = useState(true);
  const [emergencyStop, setEmergencyStop] = useState(false);
  const [loading, setLoading] = useState(false);
  const [openSettingsDialog, setOpenSettingsDialog] = useState(false);

  // Risk limits and thresholds
  const riskLevels = {
    low: { min: 0, max: 0.01, color: '#4caf50', label: 'Low' },
    medium: { min: 0.01, max: 0.025, color: '#ff9800', label: 'Medium' },
    high: { min: 0.025, max: 0.05, color: '#f44336', label: 'High' },
    extreme: { min: 0.05, max: 1, color: '#d32f2f', label: 'Extreme' }
  };

  // Calculate portfolio risk metrics
  const calculateRiskMetrics = useCallback(() => {
    if (!portfolioData || portfolioData.length === 0) return;

    const totalValue = portfolioData.reduce((sum, holding) => sum + (holding.currentValue || 0), 0);
    const totalCost = portfolioData.reduce((sum, holding) => sum + (holding.costBasis || 0), 0);
    
    // Calculate daily returns for volatility
    const returns = portfolioData.map(holding => {
      const dailyReturn = holding.gainLossPercent / 100 || 0;
      return dailyReturn;
    });

    // Portfolio metrics
    const totalGainLoss = totalValue - totalCost;
    const dailyPnL = totalGainLoss; // Simplified - would need historical data
    const totalRisk = Math.abs(totalGainLoss / totalValue) || 0;
    
    // Concentration risk (largest position as % of portfolio)
    const concentration = totalValue > 0 ? Math.max(...portfolioData.map(h => h.currentValue / totalValue)) : 0;
    
    // Volatility calculation (simplified)
    const volatility = returns.length > 0 ? Math.sqrt(returns.reduce((sum, r) => sum + r * r, 0) / returns.length) : 0;
    
    // Beta calculation (simplified - would need market data)
    const beta = 1.0; // Placeholder
    
    // Sharpe ratio (simplified)
    const riskFreeRate = 0.02; // 2% annual
    const avgReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length || 0;
    const sharpeRatio = volatility > 0 ? (avgReturn - riskFreeRate / 252) / volatility : 0;
    
    // Value at Risk (95% confidence, 1 day)
    const valueAtRisk = totalValue * volatility * 1.645; // 95% confidence z-score
    
    // Max drawdown (simplified)
    const maxDrawdown = Math.max(...portfolioData.map(h => Math.abs(h.gainLossPercent / 100))) || 0;

    setRiskMetrics({
      totalRisk,
      maxDrawdown,
      valueAtRisk,
      sharpeRatio,
      beta,
      volatility: volatility * Math.sqrt(252), // Annualized
      concentration,
      leverage: 1.0, // Simplified
      dailyPnL,
      weeklyPnL: dailyPnL * 5, // Simplified
      monthlyPnL: dailyPnL * 22 // Simplified
    });

    // Check for risk alerts
    checkRiskAlerts(totalRisk, maxDrawdown, concentration, valueAtRisk);
  }, [portfolioData]);

  // Check for risk alerts
  const checkRiskAlerts = (totalRisk, maxDrawdown, concentration, valueAtRisk) => {
    const alerts = [];
    
    if (totalRisk > riskSettings.maxPortfolioRisk) {
      alerts.push({
        id: Date.now() + 1,
        type: 'error',
        title: 'Portfolio Risk Exceeded',
        message: `Portfolio risk (${(totalRisk * 100).toFixed(2)}%) exceeds maximum allowed (${(riskSettings.maxPortfolioRisk * 100).toFixed(2)}%)`,
        timestamp: new Date(),
        action: 'Reduce position sizes or add hedging'
      });
    }

    if (maxDrawdown > riskSettings.maxDrawdown) {
      alerts.push({
        id: Date.now() + 2,
        type: 'error',
        title: 'Max Drawdown Exceeded',
        message: `Maximum drawdown (${(maxDrawdown * 100).toFixed(2)}%) exceeds limit (${(riskSettings.maxDrawdown * 100).toFixed(2)}%)`,
        timestamp: new Date(),
        action: 'Consider emergency stop or position reduction'
      });
    }

    if (concentration > riskSettings.maxConcentration) {
      alerts.push({
        id: Date.now() + 3,
        type: 'warning',
        title: 'High Concentration Risk',
        message: `Largest position (${(concentration * 100).toFixed(2)}%) exceeds concentration limit (${(riskSettings.maxConcentration * 100).toFixed(2)}%)`,
        timestamp: new Date(),
        action: 'Diversify portfolio or reduce position size'
      });
    }

    if (alerts.length > 0) {
      setRiskAlerts(prev => [...prev, ...alerts]);
      if (onRiskAlert) {
        onRiskAlert(alerts);
      }
    }
  };

  // Calculate risk level
  const getRiskLevel = (risk) => {
    for (const [level, config] of Object.entries(riskLevels)) {
      if (risk >= config.min && risk < config.max) {
        return { level, ...config };
      }
    }
    return { level: 'extreme', ...riskLevels.extreme };
  };

  // Emergency stop function
  const handleEmergencyStop = () => {
    setEmergencyStop(true);
    const alert = {
      id: Date.now(),
      type: 'error',
      title: 'EMERGENCY STOP ACTIVATED',
      message: 'All trading has been halted. Manual intervention required.',
      timestamp: new Date(),
      action: 'Review positions and risk before resuming'
    };
    setRiskAlerts(prev => [alert, ...prev]);
  };

  // Resume trading
  const handleResumeTrading = () => {
    setEmergencyStop(false);
    const alert = {
      id: Date.now(),
      type: 'info',
      title: 'Trading Resumed',
      message: 'Trading has been resumed after emergency stop.',
      timestamp: new Date(),
      action: 'Monitor risk levels closely'
    };
    setRiskAlerts(prev => [alert, ...prev]);
  };

  // Clear alert
  const handleClearAlert = (alertId) => {
    setRiskAlerts(prev => prev.filter(alert => alert.id !== alertId));
  };

  // Update risk settings
  const updateRiskSettings = (key, value) => {
    setRiskSettings(prev => ({
      ...prev,
      [key]: value
    }));
  };

  // Calculate position risk
  const calculatePositionRisk = (holding) => {
    const positionValue = holding.currentValue || 0;
    const totalPortfolioValue = portfolioData.reduce((sum, h) => sum + (h.currentValue || 0), 0);
    const positionWeight = totalPortfolioValue > 0 ? positionValue / totalPortfolioValue : 0;
    const positionRisk = Math.abs(holding.gainLossPercent / 100) || 0;
    
    return {
      weight: positionWeight,
      risk: positionRisk,
      value: positionValue,
      riskValue: positionValue * positionRisk
    };
  };

  // Auto-recalculate metrics
  useEffect(() => {
    calculateRiskMetrics();
  }, [portfolioData, calculateRiskMetrics]);

  // Risk monitoring interval
  useEffect(() => {
    let interval;
    if (riskMonitoring) {
      interval = setInterval(() => {
        calculateRiskMetrics();
      }, 30000); // Update every 30 seconds
    }
    return () => clearInterval(interval);
  }, [riskMonitoring, calculateRiskMetrics]);

  const renderRiskOverview = () => {
    const totalRiskLevel = getRiskLevel(riskMetrics.totalRisk);
    const concentrationRiskLevel = getRiskLevel(riskMetrics.concentration);
    const volatilityRiskLevel = getRiskLevel(riskMetrics.volatility);

    return (
      <Grid container spacing={3}>
        {/* Risk Status Cards */}
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Shield color={totalRiskLevel.level === 'low' ? 'success' : totalRiskLevel.level === 'medium' ? 'warning' : 'error'} />
                <Typography variant="h6" sx={{ ml: 1 }}>
                  Portfolio Risk
                </Typography>
              </Box>
              <Typography variant="h4" color={totalRiskLevel.color}>
                {(riskMetrics.totalRisk * 100).toFixed(2)}%
              </Typography>
              <Chip
                label={totalRiskLevel.label}
                color={totalRiskLevel.level === 'low' ? 'success' : totalRiskLevel.level === 'medium' ? 'warning' : 'error'}
                size="small"
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <TrendingDown color="error" />
                <Typography variant="h6" sx={{ ml: 1 }}>
                  Max Drawdown
                </Typography>
              </Box>
              <Typography variant="h4" color="error.main">
                {(riskMetrics.maxDrawdown * 100).toFixed(2)}%
              </Typography>
              <LinearProgress
                variant="determinate"
                value={(riskMetrics.maxDrawdown / riskSettings.maxDrawdown) * 100}
                color="error"
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <MonetizationOn color="primary" />
                <Typography variant="h6" sx={{ ml: 1 }}>
                  Value at Risk
                </Typography>
              </Box>
              <Typography variant="h4" color="primary.main">
                ${riskMetrics.valueAtRisk.toFixed(0)}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                95% confidence, 1 day
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <PieChart color="info" />
                <Typography variant="h6" sx={{ ml: 1 }}>
                  Concentration
                </Typography>
              </Box>
              <Typography variant="h4" color={concentrationRiskLevel.color}>
                {(riskMetrics.concentration * 100).toFixed(1)}%
              </Typography>
              <Chip
                label={concentrationRiskLevel.label}
                color={concentrationRiskLevel.level === 'low' ? 'success' : concentrationRiskLevel.level === 'medium' ? 'warning' : 'error'}
                size="small"
              />
            </CardContent>
          </Card>
        </Grid>

        {/* Risk Metrics Table */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Risk Metrics
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Metric</TableCell>
                      <TableCell align="right">Current</TableCell>
                      <TableCell align="right">Limit</TableCell>
                      <TableCell align="right">Status</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    <TableRow>
                      <TableCell>Portfolio Risk</TableCell>
                      <TableCell align="right">{(riskMetrics.totalRisk * 100).toFixed(2)}%</TableCell>
                      <TableCell align="right">{(riskSettings.maxPortfolioRisk * 100).toFixed(2)}%</TableCell>
                      <TableCell align="right">
                        <Chip
                          icon={riskMetrics.totalRisk <= riskSettings.maxPortfolioRisk ? <CheckCircle /> : <Error />}
                          label={riskMetrics.totalRisk <= riskSettings.maxPortfolioRisk ? 'OK' : 'EXCEEDED'}
                          color={riskMetrics.totalRisk <= riskSettings.maxPortfolioRisk ? 'success' : 'error'}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Max Drawdown</TableCell>
                      <TableCell align="right">{(riskMetrics.maxDrawdown * 100).toFixed(2)}%</TableCell>
                      <TableCell align="right">{(riskSettings.maxDrawdown * 100).toFixed(2)}%</TableCell>
                      <TableCell align="right">
                        <Chip
                          icon={riskMetrics.maxDrawdown <= riskSettings.maxDrawdown ? <CheckCircle /> : <Error />}
                          label={riskMetrics.maxDrawdown <= riskSettings.maxDrawdown ? 'OK' : 'EXCEEDED'}
                          color={riskMetrics.maxDrawdown <= riskSettings.maxDrawdown ? 'success' : 'error'}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Concentration</TableCell>
                      <TableCell align="right">{(riskMetrics.concentration * 100).toFixed(1)}%</TableCell>
                      <TableCell align="right">{(riskSettings.maxConcentration * 100).toFixed(1)}%</TableCell>
                      <TableCell align="right">
                        <Chip
                          icon={riskMetrics.concentration <= riskSettings.maxConcentration ? <CheckCircle /> : <Error />}
                          label={riskMetrics.concentration <= riskSettings.maxConcentration ? 'OK' : 'EXCEEDED'}
                          color={riskMetrics.concentration <= riskSettings.maxConcentration ? 'success' : 'error'}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Volatility</TableCell>
                      <TableCell align="right">{(riskMetrics.volatility * 100).toFixed(1)}%</TableCell>
                      <TableCell align="right">25.0%</TableCell>
                      <TableCell align="right">
                        <Chip
                          icon={riskMetrics.volatility <= 0.25 ? <CheckCircle /> : <Error />}
                          label={riskMetrics.volatility <= 0.25 ? 'OK' : 'HIGH'}
                          color={riskMetrics.volatility <= 0.25 ? 'success' : 'warning'}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Beta</TableCell>
                      <TableCell align="right">{riskMetrics.beta.toFixed(2)}</TableCell>
                      <TableCell align="right">1.5</TableCell>
                      <TableCell align="right">
                        <Chip
                          icon={riskMetrics.beta <= 1.5 ? <CheckCircle /> : <Error />}
                          label={riskMetrics.beta <= 1.5 ? 'OK' : 'HIGH'}
                          color={riskMetrics.beta <= 1.5 ? 'success' : 'warning'}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell>Sharpe Ratio</TableCell>
                      <TableCell align="right">{riskMetrics.sharpeRatio.toFixed(2)}</TableCell>
                      <TableCell align="right">1.0</TableCell>
                      <TableCell align="right">
                        <Chip
                          icon={riskMetrics.sharpeRatio >= 1.0 ? <CheckCircle /> : <Warning />}
                          label={riskMetrics.sharpeRatio >= 1.0 ? 'GOOD' : 'POOR'}
                          color={riskMetrics.sharpeRatio >= 1.0 ? 'success' : 'warning'}
                          size="small"
                        />
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Risk Controls */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="h6">
                  Risk Controls
                </Typography>
                <Box>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={riskMonitoring}
                        onChange={(e) => setRiskMonitoring(e.target.checked)}
                        color="primary"
                      />
                    }
                    label="Monitor"
                  />
                </Box>
              </Box>

              <Box sx={{ mb: 2 }}>
                <Button
                  variant={emergencyStop ? "outlined" : "contained"}
                  color={emergencyStop ? "success" : "error"}
                  fullWidth
                  onClick={emergencyStop ? handleResumeTrading : handleEmergencyStop}
                  startIcon={emergencyStop ? <PlayArrow /> : <Stop />}
                >
                  {emergencyStop ? 'Resume Trading' : 'Emergency Stop'}
                </Button>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={riskSettings.stopLossEnabled}
                      onChange={(e) => updateRiskSettings('stopLossEnabled', e.target.checked)}
                    />
                  }
                  label="Auto Stop Loss"
                />
                
                <FormControlLabel
                  control={
                    <Switch
                      checked={riskSettings.takeProfitEnabled}
                      onChange={(e) => updateRiskSettings('takeProfitEnabled', e.target.checked)}
                    />
                  }
                  label="Auto Take Profit"
                />
                
                <FormControlLabel
                  control={
                    <Switch
                      checked={riskSettings.riskAlertsEnabled}
                      onChange={(e) => updateRiskSettings('riskAlertsEnabled', e.target.checked)}
                    />
                  }
                  label="Risk Alerts"
                />
                
                <FormControlLabel
                  control={
                    <Switch
                      checked={riskSettings.autoHedging}
                      onChange={(e) => updateRiskSettings('autoHedging', e.target.checked)}
                    />
                  }
                  label="Auto Hedging"
                />
              </Box>

              <Box sx={{ mt: 2 }}>
                <Button
                  variant="outlined"
                  fullWidth
                  onClick={() => setOpenSettingsDialog(true)}
                  startIcon={<Settings />}
                >
                  Risk Settings
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    );
  };

  const renderPositionRisk = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Position Risk Analysis
            </Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell align="right">Position Value</TableCell>
                    <TableCell align="right">Portfolio Weight</TableCell>
                    <TableCell align="right">Risk Level</TableCell>
                    <TableCell align="right">Unrealized P&L</TableCell>
                    <TableCell align="right">Risk Value</TableCell>
                    <TableCell align="center">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {portfolioData.map((holding) => {
                    const positionRisk = calculatePositionRisk(holding);
                    const riskLevel = getRiskLevel(positionRisk.risk);
                    
                    return (
                      <TableRow key={holding.id}>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">
                            {holding.symbol}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          ${holding.currentValue?.toFixed(2) || '0.00'}
                        </TableCell>
                        <TableCell align="right">
                          {(positionRisk.weight * 100).toFixed(1)}%
                        </TableCell>
                        <TableCell align="right">
                          <Chip
                            label={riskLevel.label}
                            color={riskLevel.level === 'low' ? 'success' : riskLevel.level === 'medium' ? 'warning' : 'error'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography
                            color={holding.gainLoss >= 0 ? 'success.main' : 'error.main'}
                          >
                            ${holding.gainLoss?.toFixed(2) || '0.00'}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          ${positionRisk.riskValue.toFixed(2)}
                        </TableCell>
                        <TableCell align="center">
                          <Tooltip title="Set Stop Loss">
                            <IconButton size="small" color="error">
                              <Stop />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Hedge Position">
                            <IconButton size="small" color="primary">
                              <Shield />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderRiskAlerts = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
              <Typography variant="h6">
                Risk Alerts
              </Typography>
              <Button
                variant="outlined"
                size="small"
                onClick={() => setRiskAlerts([])}
                disabled={riskAlerts.length === 0}
              >
                Clear All
              </Button>
            </Box>
            
            {riskAlerts.length === 0 ? (
              <Alert severity="success">
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <CheckCircle sx={{ mr: 1 }} />
                  No active risk alerts. Portfolio is within acceptable risk parameters.
                </Box>
              </Alert>
            ) : (
              <List>
                {riskAlerts.map((alert) => (
                  <ListItem key={alert.id} divider>
                    <ListItemIcon>
                      {alert.type === 'error' ? <Error color="error" /> : 
                       alert.type === 'warning' ? <Warning color="warning" /> : 
                       <Info color="info" />}
                    </ListItemIcon>
                    <ListItemText
                      primary={alert.title}
                      secondary={
                        <>
                          <Typography variant="body2">{alert.message}</Typography>
                          <Typography variant="caption" color="text.secondary">
                            {alert.timestamp.toLocaleString()}
                          </Typography>
                          {alert.action && (
                            <Typography variant="caption" color="primary.main" sx={{ display: 'block' }}>
                              Recommended action: {alert.action}
                            </Typography>
                          )}
                        </>
                      }
                    />
                    <ListItemSecondaryAction>
                      <IconButton
                        onClick={() => handleClearAlert(alert.id)}
                        size="small"
                      >
                        <CheckCircle />
                      </IconButton>
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
              </List>
            )}
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h5">
          <Security sx={{ mr: 1, verticalAlign: 'middle' }} />
          Risk Management
        </Typography>
        
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {emergencyStop && (
            <Chip
              icon={<Stop />}
              label="EMERGENCY STOP ACTIVE"
              color="error"
              variant="filled"
            />
          )}
          <Button
            variant="outlined"
            onClick={calculateRiskMetrics}
            startIcon={<Refresh />}
            disabled={loading}
          >
            Refresh
          </Button>
        </Box>
      </Box>

      <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)} sx={{ mb: 3 }}>
        <Tab label="Overview" />
        <Tab label="Position Risk" />
        <Tab label="Alerts" />
      </Tabs>

      {tabValue === 0 && renderRiskOverview()}
      {tabValue === 1 && renderPositionRisk()}
      {tabValue === 2 && renderRiskAlerts()}

      {/* Risk Settings Dialog */}
      <Dialog 
        open={openSettingsDialog} 
        onClose={() => setOpenSettingsDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Risk Management Settings</DialogTitle>
        <DialogContent>
          <Grid container spacing={3} sx={{ mt: 1 }}>
            <Grid item xs={12} md={6}>
              <Typography variant="subtitle1" gutterBottom>
                Portfolio Risk Limits
              </Typography>
              
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>
                  Max Portfolio Risk: {(riskSettings.maxPortfolioRisk * 100).toFixed(1)}%
                </Typography>
                <Slider
                  value={riskSettings.maxPortfolioRisk * 100}
                  onChange={(e, value) => updateRiskSettings('maxPortfolioRisk', value / 100)}
                  min={0.5}
                  max={10}
                  step={0.1}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </Box>

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>
                  Max Position Size: {(riskSettings.maxPositionSize * 100).toFixed(1)}%
                </Typography>
                <Slider
                  value={riskSettings.maxPositionSize * 100}
                  onChange={(e, value) => updateRiskSettings('maxPositionSize', value / 100)}
                  min={1}
                  max={25}
                  step={0.5}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </Box>

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>
                  Max Drawdown: {(riskSettings.maxDrawdown * 100).toFixed(1)}%
                </Typography>
                <Slider
                  value={riskSettings.maxDrawdown * 100}
                  onChange={(e, value) => updateRiskSettings('maxDrawdown', value / 100)}
                  min={2}
                  max={50}
                  step={1}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </Box>
            </Grid>

            <Grid item xs={12} md={6}>
              <Typography variant="subtitle1" gutterBottom>
                Additional Risk Controls
              </Typography>
              
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>
                  Max Daily Loss: {(riskSettings.maxDailyLoss * 100).toFixed(1)}%
                </Typography>
                <Slider
                  value={riskSettings.maxDailyLoss * 100}
                  onChange={(e, value) => updateRiskSettings('maxDailyLoss', value / 100)}
                  min={1}
                  max={20}
                  step={0.5}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </Box>

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>
                  Max Concentration: {(riskSettings.maxConcentration * 100).toFixed(1)}%
                </Typography>
                <Slider
                  value={riskSettings.maxConcentration * 100}
                  onChange={(e, value) => updateRiskSettings('maxConcentration', value / 100)}
                  min={5}
                  max={50}
                  step={1}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </Box>

              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" gutterBottom>
                  Max Leverage: {riskSettings.maxLeverage.toFixed(1)}x
                </Typography>
                <Slider
                  value={riskSettings.maxLeverage}
                  onChange={(e, value) => updateRiskSettings('maxLeverage', value)}
                  min={1}
                  max={5}
                  step={0.1}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}x`}
                />
              </Box>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenSettingsDialog(false)}>Cancel</Button>
          <Button onClick={() => setOpenSettingsDialog(false)} variant="contained">
            Save Settings
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default RiskManager;