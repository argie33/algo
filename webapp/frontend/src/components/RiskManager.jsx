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
      <div className="grid" container spacing={3}>
        {/* Risk Status Cards */}
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Shield color={totalRiskLevel.level === 'low' ? 'success' : totalRiskLevel.level === 'medium' ? 'warning' : 'error'} />
                <div  variant="h6" sx={{ ml: 1 }}>
                  Portfolio Risk
                </div>
              </div>
              <div  variant="h4" color={totalRiskLevel.color}>
                {(riskMetrics.totalRisk * 100).toFixed(2)}%
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                label={totalRiskLevel.label}
                color={totalRiskLevel.level === 'low' ? 'success' : totalRiskLevel.level === 'medium' ? 'warning' : 'error'}
                size="small"
              />
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <TrendingDown color="error" />
                <div  variant="h6" sx={{ ml: 1 }}>
                  Max Drawdown
                </div>
              </div>
              <div  variant="h4" color="error.main">
                {(riskMetrics.maxDrawdown * 100).toFixed(2)}%
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2"
                variant="determinate"
                value={(riskMetrics.maxDrawdown / riskSettings.maxDrawdown) * 100}
                color="error"
                sx={{ mt: 1 }}
              />
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <MonetizationOn color="primary" />
                <div  variant="h6" sx={{ ml: 1 }}>
                  Value at Risk
                </div>
              </div>
              <div  variant="h4" color="primary.main">
                ${riskMetrics.valueAtRisk.toFixed(0)}
              </div>
              <div  variant="body2" color="text.secondary">
                95% confidence, 1 day
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <PieChart color="info" />
                <div  variant="h6" sx={{ ml: 1 }}>
                  Concentration
                </div>
              </div>
              <div  variant="h4" color={concentrationRiskLevel.color}>
                {(riskMetrics.concentration * 100).toFixed(1)}%
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                label={concentrationRiskLevel.label}
                color={concentrationRiskLevel.level === 'low' ? 'success' : concentrationRiskLevel.level === 'medium' ? 'warning' : 'error'}
                size="small"
              />
            </div>
          </div>
        </div>

        {/* Risk Metrics Table */}
        <div className="grid" item xs={12} md={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Risk Metrics
              </div>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Metric</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Current</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Limit</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Status</td>
                    </tr>
                  </thead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Portfolio Risk</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{(riskMetrics.totalRisk * 100).toFixed(2)}%</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{(riskSettings.maxPortfolioRisk * 100).toFixed(2)}%</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          icon={riskMetrics.totalRisk <= riskSettings.maxPortfolioRisk ? <CheckCircle /> : <Error />}
                          label={riskMetrics.totalRisk <= riskSettings.maxPortfolioRisk ? 'OK' : 'EXCEEDED'}
                          color={riskMetrics.totalRisk <= riskSettings.maxPortfolioRisk ? 'success' : 'error'}
                          size="small"
                        />
                      </td>
                    </tr>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Max Drawdown</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{(riskMetrics.maxDrawdown * 100).toFixed(2)}%</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{(riskSettings.maxDrawdown * 100).toFixed(2)}%</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          icon={riskMetrics.maxDrawdown <= riskSettings.maxDrawdown ? <CheckCircle /> : <Error />}
                          label={riskMetrics.maxDrawdown <= riskSettings.maxDrawdown ? 'OK' : 'EXCEEDED'}
                          color={riskMetrics.maxDrawdown <= riskSettings.maxDrawdown ? 'success' : 'error'}
                          size="small"
                        />
                      </td>
                    </tr>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Concentration</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{(riskMetrics.concentration * 100).toFixed(1)}%</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{(riskSettings.maxConcentration * 100).toFixed(1)}%</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          icon={riskMetrics.concentration <= riskSettings.maxConcentration ? <CheckCircle /> : <Error />}
                          label={riskMetrics.concentration <= riskSettings.maxConcentration ? 'OK' : 'EXCEEDED'}
                          color={riskMetrics.concentration <= riskSettings.maxConcentration ? 'success' : 'error'}
                          size="small"
                        />
                      </td>
                    </tr>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Volatility</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{(riskMetrics.volatility * 100).toFixed(1)}%</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">25.0%</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          icon={riskMetrics.volatility <= 0.25 ? <CheckCircle /> : <Error />}
                          label={riskMetrics.volatility <= 0.25 ? 'OK' : 'HIGH'}
                          color={riskMetrics.volatility <= 0.25 ? 'success' : 'warning'}
                          size="small"
                        />
                      </td>
                    </tr>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Beta</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{riskMetrics.beta.toFixed(2)}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">1.5</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          icon={riskMetrics.beta <= 1.5 ? <CheckCircle /> : <Error />}
                          label={riskMetrics.beta <= 1.5 ? 'OK' : 'HIGH'}
                          color={riskMetrics.beta <= 1.5 ? 'success' : 'warning'}
                          size="small"
                        />
                      </td>
                    </tr>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Sharpe Ratio</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{riskMetrics.sharpeRatio.toFixed(2)}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">1.0</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          icon={riskMetrics.sharpeRatio >= 1.0 ? <CheckCircle /> : <Warning />}
                          label={riskMetrics.sharpeRatio >= 1.0 ? 'GOOD' : 'POOR'}
                          color={riskMetrics.sharpeRatio >= 1.0 ? 'success' : 'warning'}
                          size="small"
                        />
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        {/* Risk Controls */}
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                <div  variant="h6">
                  Risk Controls
                </div>
                <div>
                  <div className="mb-4"Label
                    control={
                      <input type="checkbox" className="toggle"
                        checked={riskMonitoring}
                        onChange={(e) => setRiskMonitoring(e.target.checked)}
                        color="primary"
                      />
                    }
                    label="Monitor"
                  />
                </div>
              </div>

              <div  sx={{ mb: 2 }}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant={emergencyStop ? "outlined" : "contained"}
                  color={emergencyStop ? "success" : "error"}
                  fullWidth
                  onClick={emergencyStop ? handleResumeTrading : handleEmergencyStop}
                  startIcon={emergencyStop ? <PlayArrow /> : <Stop />}
                >
                  {emergencyStop ? 'Resume Trading' : 'Emergency Stop'}
                </button>
              </div>

              <hr className="border-gray-200" sx={{ my: 2 }} />

              <div  sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={riskSettings.stopLossEnabled}
                      onChange={(e) => updateRiskSettings('stopLossEnabled', e.target.checked)}
                    />
                  }
                  label="Auto Stop Loss"
                />
                
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={riskSettings.takeProfitEnabled}
                      onChange={(e) => updateRiskSettings('takeProfitEnabled', e.target.checked)}
                    />
                  }
                  label="Auto Take Profit"
                />
                
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={riskSettings.riskAlertsEnabled}
                      onChange={(e) => updateRiskSettings('riskAlertsEnabled', e.target.checked)}
                    />
                  }
                  label="Risk Alerts"
                />
                
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={riskSettings.autoHedging}
                      onChange={(e) => updateRiskSettings('autoHedging', e.target.checked)}
                    />
                  }
                  label="Auto Hedging"
                />
              </div>

              <div  sx={{ mt: 2 }}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined"
                  fullWidth
                  onClick={() => setOpenSettingsDialog(true)}
                  startIcon={<Settings />}
                >
                  Risk Settings
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderPositionRisk = () => (
    <div className="grid" container spacing={3}>
      <div className="grid" item xs={12}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Position Risk Analysis
            </div>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Position Value</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Portfolio Weight</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Risk Level</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Unrealized P&L</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Risk Value</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Actions</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {portfolioData.map((holding) => {
                    const positionRisk = calculatePositionRisk(holding);
                    const riskLevel = getRiskLevel(positionRisk.risk);
                    
                    return (
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={holding.id}>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" fontWeight="bold">
                            {holding.symbol}
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                          ${holding.currentValue?.toFixed(2) || '0.00'}
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                          {(positionRisk.weight * 100).toFixed(1)}%
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                            label={riskLevel.label}
                            color={riskLevel.level === 'low' ? 'success' : riskLevel.level === 'medium' ? 'warning' : 'error'}
                            size="small"
                          />
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                          <div 
                            color={holding.gainLoss >= 0 ? 'success.main' : 'error.main'}
                          >
                            ${holding.gainLoss?.toFixed(2) || '0.00'}
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                          ${positionRisk.riskValue.toFixed(2)}
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                          <div  title="Set Stop Loss">
                            <button className="p-2 rounded-full hover:bg-gray-100" size="small" color="error">
                              <Stop />
                            </button>
                          </div>
                          <div  title="Hedge Position">
                            <button className="p-2 rounded-full hover:bg-gray-100" size="small" color="primary">
                              <Shield />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const renderRiskAlerts = () => (
    <div className="grid" container spacing={3}>
      <div className="grid" item xs={12}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
              <div  variant="h6">
                Risk Alerts
              </div>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                size="small"
                onClick={() => setRiskAlerts([])}
                disabled={riskAlerts.length === 0}
              >
                Clear All
              </button>
            </div>
            
            {riskAlerts.length === 0 ? (
              <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="success">
                <div  sx={{ display: 'flex', alignItems: 'center' }}>
                  <CheckCircle sx={{ mr: 1 }} />
                  No active risk alerts. Portfolio is within acceptable risk parameters.
                </div>
              </div>
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
                          <div  variant="body2">{alert.message}</div>
                          <div  variant="caption" color="text.secondary">
                            {alert.timestamp.toLocaleString()}
                          </div>
                          {alert.action && (
                            <div  variant="caption" color="primary.main" sx={{ display: 'block' }}>
                              Recommended action: {alert.action}
                            </div>
                          )}
                        </>
                      }
                    />
                    <ListItemSecondaryAction>
                      <button className="p-2 rounded-full hover:bg-gray-100"
                        onClick={() => handleClearAlert(alert.id)}
                        size="small"
                      >
                        <CheckCircle />
                      </button>
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
              </List>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <div  variant="h5">
          <Security sx={{ mr: 1, verticalAlign: 'middle' }} />
          Risk Management
        </div>
        
        <div  sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {emergencyStop && (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
              icon={<Stop />}
              label="EMERGENCY STOP ACTIVE"
              color="error"
              variant="filled"
            />
          )}
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            onClick={calculateRiskMetrics}
            startIcon={<Refresh />}
            disabled={loading}
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="border-b border-gray-200" value={tabValue} onChange={(e, newValue) => setTabValue(newValue)} sx={{ mb: 3 }}>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Overview" />
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Position Risk" />
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Alerts" />
      </div>

      {tabValue === 0 && renderRiskOverview()}
      {tabValue === 1 && renderPositionRisk()}
      {tabValue === 2 && renderRiskAlerts()}

      {/* Risk Settings Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
        open={openSettingsDialog} 
        onClose={() => setOpenSettingsDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Risk Management Settings</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div className="grid" container spacing={3} sx={{ mt: 1 }}>
            <div className="grid" item xs={12} md={6}>
              <div  variant="subtitle1" gutterBottom>
                Portfolio Risk Limits
              </div>
              
              <div  sx={{ mb: 2 }}>
                <div  variant="body2" gutterBottom>
                  Max Portfolio Risk: {(riskSettings.maxPortfolioRisk * 100).toFixed(1)}%
                </div>
                <Slider
                  value={riskSettings.maxPortfolioRisk * 100}
                  onChange={(e, value) => updateRiskSettings('maxPortfolioRisk', value / 100)}
                  min={0.5}
                  max={10}
                  step={0.1}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </div>

              <div  sx={{ mb: 2 }}>
                <div  variant="body2" gutterBottom>
                  Max Position Size: {(riskSettings.maxPositionSize * 100).toFixed(1)}%
                </div>
                <Slider
                  value={riskSettings.maxPositionSize * 100}
                  onChange={(e, value) => updateRiskSettings('maxPositionSize', value / 100)}
                  min={1}
                  max={25}
                  step={0.5}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </div>

              <div  sx={{ mb: 2 }}>
                <div  variant="body2" gutterBottom>
                  Max Drawdown: {(riskSettings.maxDrawdown * 100).toFixed(1)}%
                </div>
                <Slider
                  value={riskSettings.maxDrawdown * 100}
                  onChange={(e, value) => updateRiskSettings('maxDrawdown', value / 100)}
                  min={2}
                  max={50}
                  step={1}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </div>
            </div>

            <div className="grid" item xs={12} md={6}>
              <div  variant="subtitle1" gutterBottom>
                Additional Risk Controls
              </div>
              
              <div  sx={{ mb: 2 }}>
                <div  variant="body2" gutterBottom>
                  Max Daily Loss: {(riskSettings.maxDailyLoss * 100).toFixed(1)}%
                </div>
                <Slider
                  value={riskSettings.maxDailyLoss * 100}
                  onChange={(e, value) => updateRiskSettings('maxDailyLoss', value / 100)}
                  min={1}
                  max={20}
                  step={0.5}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </div>

              <div  sx={{ mb: 2 }}>
                <div  variant="body2" gutterBottom>
                  Max Concentration: {(riskSettings.maxConcentration * 100).toFixed(1)}%
                </div>
                <Slider
                  value={riskSettings.maxConcentration * 100}
                  onChange={(e, value) => updateRiskSettings('maxConcentration', value / 100)}
                  min={5}
                  max={50}
                  step={1}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}%`}
                />
              </div>

              <div  sx={{ mb: 2 }}>
                <div  variant="body2" gutterBottom>
                  Max Leverage: {riskSettings.maxLeverage.toFixed(1)}x
                </div>
                <Slider
                  value={riskSettings.maxLeverage}
                  onChange={(e, value) => updateRiskSettings('maxLeverage', value)}
                  min={1}
                  max={5}
                  step={0.1}
                  valueLabelDisplay="auto"
                  valueLabelFormat={(value) => `${value}x`}
                />
              </div>
            </div>
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setOpenSettingsDialog(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setOpenSettingsDialog(false)} variant="contained">
            Save Settings
          </button>
        </div>
      </div>
    </div>
  );
};

export default RiskManager;