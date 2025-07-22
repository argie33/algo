import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, Tabs, Tab, Button, Chip,
  Alert, LinearProgress, CircularProgress, IconButton, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  FormControl, InputLabel, Select, MenuItem, Switch, FormControlLabel,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, Accordion, AccordionSummary, AccordionDetails, Divider,
  List, ListItem, ListItemIcon, ListItemText, Badge, Slider,
  ToggleButton, ToggleButtonGroup, Fab, SpeedDial, SpeedDialAction
} from '@mui/material';
import {
  TrendingUp, TrendingDown, PlayArrow, Stop, Settings, Refresh,
  Timeline, Assessment, Speed, Security, Warning, CheckCircle,
  ShowChart, AccountBalance, BarChart, PieChart, DonutLarge,
  CandlestickChart, AutoGraph, Analytics, Psychology, Science,
  SmartToy, Memory, Storage, CloudQueue, Notifications,
  ExpandMore, Add, Edit, Delete, Save, Cancel, More
} from '@mui/icons-material';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, AreaChart, Area, BarChart as RechartsBarChart,
  Bar, PieChart as RechartsPieChart, Cell, ComposedChart,
  ScatterChart, Scatter
} from 'recharts';
import { useApiKeys } from './ApiKeyProvider';
import { getApiConfig } from '../services/api';

const { apiUrl: API_BASE } = getApiConfig();

const AdvancedTradingDashboard = () => {
  const [dashboardData, setDashboardData] = useState(null);
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/advanced/dashboard?type=comprehensive', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const data = await response.json();
      
      if (data.success) {
        setDashboardData(data.data.dashboard);
      }
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const generateAdvancedSignal = async () => {
    try {
      const response = await fetch('/api/advanced/signals/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          symbol: selectedSymbol,
          timeframe: '1d',
          lookback: 100
        })
      });
      const data = await response.json();
      
      if (data.success) {
        alert('Advanced signal generated successfully!');
        // Refresh dashboard data
        fetchDashboardData();
      }
    } catch (error) {
      console.error('Error generating signal:', error);
    }
  };

  const optimizePortfolio = async () => {
    try {
      const response = await fetch('/api/advanced/portfolio/optimize', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          riskTolerance: 0.5,
          constraints: {
            maxWeight: 0.4,
            minWeight: 0.05
          }
        })
      });
      const data = await response.json();
      
      if (data.success) {
        alert('Portfolio optimization completed successfully!');
        // Refresh dashboard data
        fetchDashboardData();
      }
    } catch (error) {
      console.error('Error optimizing portfolio:', error);
    }
  };

  const runBacktest = async () => {
    try {
      const response = await fetch('/api/advanced/backtest/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          symbols: ['AAPL', 'MSFT', 'GOOGL', 'AMZN'],
          startDate: '2023-01-01',
          endDate: '2024-01-01',
          strategy: 'ma_crossover_rsi',
          initialCapital: 100000
        })
      });
      const data = await response.json();
      
      if (data.success) {
        alert('Backtesting completed successfully!');
        console.log('Backtest results:', data.data.backtest);
      }
    } catch (error) {
      console.error('Error running backtest:', error);
    }
  };

  const executeAutomatedTrading = async () => {
    try {
      const response = await fetch('/api/advanced/trading/execute', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          riskTolerance: 0.05,
          maxPositions: 20
        })
      });
      const data = await response.json();
      
      if (data.success) {
        alert('Automated trading executed successfully!');
        console.log('Trading results:', data.data.trading);
      }
    } catch (error) {
      console.error('Error executing automated trading:', error);
    }
  };

  if (loading) {
    return (
      <div className="advanced-dashboard-loading">
        <div className="loading-spinner"></div>
        <p>Loading Advanced Trading Dashboard...</p>
      </div>
    );
  }

  return (
    <div className="advanced-trading-dashboard">
      <div className="dashboard-header">
        <h1>🚀 Advanced Trading Dashboard</h1>
        <p className="subtitle">Institutional-Grade Trading & Analytics Platform</p>
      </div>

      <div className="dashboard-tabs">
        <button 
          className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          📊 Overview
        </button>
        <button 
          className={`tab-button ${activeTab === 'signals' ? 'active' : ''}`}
          onClick={() => setActiveTab('signals')}
        >
          🎯 Signals
        </button>
        <button 
          className={`tab-button ${activeTab === 'portfolio' ? 'active' : ''}`}
          onClick={() => setActiveTab('portfolio')}
        >
          💼 Portfolio
        </button>
        <button 
          className={`tab-button ${activeTab === 'trading' ? 'active' : ''}`}
          onClick={() => setActiveTab('trading')}
        >
          🤖 Trading
        </button>
        <button 
          className={`tab-button ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
        >
          📈 Analytics
        </button>
      </div>

      <div className="dashboard-content">
        {activeTab === 'overview' && (
          <div className="overview-tab">
            <div className="stats-grid">
              <div className="stat-card">
                <h3>🏆 Portfolio Performance</h3>
                <div className="stat-value">
                  {dashboardData?.dashboard?.portfolio?.metrics?.totalReturn 
                    ? `${(dashboardData.dashboard.portfolio.metrics.totalReturn * 100).toFixed(2)}%`
                    : 'N/A'}
                </div>
                <div className="stat-label">Total Return</div>
              </div>
              
              <div className="stat-card">
                <h3>⚡ Active Signals</h3>
                <div className="stat-value">
                  {dashboardData?.dashboard?.signals?.summary?.total || 0}
                </div>
                <div className="stat-label">Trading Signals</div>
              </div>
              
              <div className="stat-card">
                <h3>🎯 Signal Accuracy</h3>
                <div className="stat-value">
                  {dashboardData?.dashboard?.signals?.summary?.averageConfidence 
                    ? `${(dashboardData.dashboard.signals.summary.averageConfidence * 100).toFixed(1)}%`
                    : 'N/A'}
                </div>
                <div className="stat-label">Average Confidence</div>
              </div>
              
              <div className="stat-card">
                <h3>⚖️ Risk Level</h3>
                <div className="stat-value">
                  {dashboardData?.dashboard?.risk?.summary?.level || 'N/A'}
                </div>
                <div className="stat-label">Risk Assessment</div>
              </div>
            </div>

            <div className="feature-showcase">
              <h3>🔥 Advanced Features</h3>
              <div className="features-grid">
                <div className="feature-card">
                  <h4>🎯 Advanced Signal Processing</h4>
                  <p>Multi-indicator analysis with confidence scoring</p>
                  <button onClick={generateAdvancedSignal} className="action-button">
                    Generate Signal
                  </button>
                </div>
                
                <div className="feature-card">
                  <h4>💼 Portfolio Optimization</h4>
                  <p>Modern Portfolio Theory implementation</p>
                  <button onClick={optimizePortfolio} className="action-button">
                    Optimize Portfolio
                  </button>
                </div>
                
                <div className="feature-card">
                  <h4>🔄 Backtesting Engine</h4>
                  <p>Historical strategy validation</p>
                  <button onClick={runBacktest} className="action-button">
                    Run Backtest
                  </button>
                </div>
                
                <div className="feature-card">
                  <h4>🤖 Automated Trading</h4>
                  <p>Systematic trading execution</p>
                  <button onClick={executeAutomatedTrading} className="action-button">
                    Execute Trading
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'signals' && (
          <div className="signals-tab">
            <div className="signals-header">
              <h3>🎯 Advanced Trading Signals</h3>
              <div className="signal-controls">
                <select 
                  value={selectedSymbol} 
                  onChange={(e) => setSelectedSymbol(e.target.value)}
                  className="symbol-selector"
                >
                  <option value="AAPL">AAPL</option>
                  <option value="MSFT">MSFT</option>
                  <option value="GOOGL">GOOGL</option>
                  <option value="AMZN">AMZN</option>
                  <option value="TSLA">TSLA</option>
                </select>
                <button onClick={generateAdvancedSignal} className="generate-button">
                  Generate Advanced Signal
                </button>
              </div>
            </div>

            <div className="signals-grid">
              {dashboardData?.dashboard?.signals?.topOpportunities?.map((signal, index) => (
                <div key={index} className="signal-card">
                  <div className="signal-header">
                    <span className="signal-symbol">{signal.symbol}</span>
                    <span className={`signal-action ${signal.recommendation?.action}`}>
                      {signal.recommendation?.action?.toUpperCase() || 'HOLD'}
                    </span>
                  </div>
                  <div className="signal-details">
                    <div className="confidence-bar">
                      <div 
                        className="confidence-fill"
                        style={{ width: `${(signal.recommendation?.confidence || 0) * 100}%` }}
                      ></div>
                      <span className="confidence-text">
                        {((signal.recommendation?.confidence || 0) * 100).toFixed(1)}% Confidence
                      </span>
                    </div>
                    <p className="signal-rationale">
                      {signal.recommendation?.rationale || 'No rationale available'}
                    </p>
                  </div>
                </div>
              )) || (
                <div className="no-signals">
                  <p>No signals available. Generate some signals to see them here!</p>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'portfolio' && (
          <div className="portfolio-tab">
            <div className="portfolio-header">
              <h3>💼 Portfolio Optimization</h3>
              <button onClick={optimizePortfolio} className="optimize-button">
                Optimize Portfolio
              </button>
            </div>

            <div className="portfolio-content">
              <div className="portfolio-metrics">
                <h4>📊 Portfolio Metrics</h4>
                <div className="metrics-grid">
                  <div className="metric-item">
                    <span className="metric-label">Total Value:</span>
                    <span className="metric-value">
                      ${dashboardData?.dashboard?.portfolio?.metrics?.totalValue?.toLocaleString() || 'N/A'}
                    </span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-label">Total Return:</span>
                    <span className="metric-value">
                      {dashboardData?.dashboard?.portfolio?.metrics?.totalReturn 
                        ? `${(dashboardData.dashboard.portfolio.metrics.totalReturn * 100).toFixed(2)}%`
                        : 'N/A'}
                    </span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-label">Position Count:</span>
                    <span className="metric-value">
                      {dashboardData?.dashboard?.portfolio?.metrics?.positionCount || 0}
                    </span>
                  </div>
                  <div className="metric-item">
                    <span className="metric-label">Concentration Risk:</span>
                    <span className="metric-value">
                      {dashboardData?.dashboard?.portfolio?.metrics?.concentrationRisk 
                        ? `${(dashboardData.dashboard.portfolio.metrics.concentrationRisk * 100).toFixed(1)}%`
                        : 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="portfolio-holdings">
                <h4>📈 Current Holdings</h4>
                <div className="holdings-list">
                  {dashboardData?.dashboard?.portfolio?.holdings?.map((holding, index) => (
                    <div key={index} className="holding-item">
                      <div className="holding-symbol">{holding.symbol}</div>
                      <div className="holding-details">
                        <span>Qty: {holding.quantity}</span>
                        <span>Price: ${holding.currentPrice?.toFixed(2) || 'N/A'}</span>
                        <span>Value: ${holding.marketValue?.toLocaleString() || 'N/A'}</span>
                        <span className={`pnl ${holding.unrealizedPnl >= 0 ? 'positive' : 'negative'}`}>
                          PnL: ${holding.unrealizedPnl?.toFixed(2) || 'N/A'}
                        </span>
                      </div>
                    </div>
                  )) || (
                    <div className="no-holdings">
                      <p>No portfolio holdings found.</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'trading' && (
          <div className="trading-tab">
            <div className="trading-header">
              <h3>🤖 Automated Trading</h3>
              <button onClick={executeAutomatedTrading} className="execute-button">
                Execute Trading Strategy
              </button>
            </div>

            <div className="trading-content">
              <div className="trading-status">
                <h4>📊 Trading Status</h4>
                <div className="status-grid">
                  <div className="status-item">
                    <span className="status-label">Status:</span>
                    <span className="status-value">
                      {dashboardData?.dashboard?.automatedTrading?.summary?.status || 'Unknown'}
                    </span>
                  </div>
                  <div className="status-item">
                    <span className="status-label">Performance:</span>
                    <span className="status-value">
                      {dashboardData?.dashboard?.automatedTrading?.summary?.performance || 'N/A'}
                    </span>
                  </div>
                  <div className="status-item">
                    <span className="status-label">Risk:</span>
                    <span className="status-value">
                      {dashboardData?.dashboard?.automatedTrading?.summary?.risk || 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="trading-activity">
                <h4>📈 Recent Activity</h4>
                <div className="activity-list">
                  {dashboardData?.dashboard?.automatedTrading?.activity?.map((activity, index) => (
                    <div key={index} className="activity-item">
                      <div className="activity-symbol">{activity.symbol}</div>
                      <div className="activity-details">
                        <span className={`activity-action ${activity.action}`}>
                          {activity.action?.toUpperCase()}
                        </span>
                        <span>Qty: {activity.quantity}</span>
                        <span>Price: ${activity.price?.toFixed(2) || 'N/A'}</span>
                      </div>
                    </div>
                  )) || (
                    <div className="no-activity">
                      <p>No recent trading activity.</p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'analytics' && (
          <div className="analytics-tab">
            <div className="analytics-header">
              <h3>📈 Advanced Analytics</h3>
              <button onClick={runBacktest} className="backtest-button">
                Run Backtest
              </button>
            </div>

            <div className="analytics-content">
              <div className="performance-metrics">
                <h4>🏆 Performance Metrics</h4>
                <div className="metrics-grid">
                  <div className="metric-card">
                    <h5>Total Return</h5>
                    <div className="metric-value">
                      {dashboardData?.dashboard?.performance?.metrics?.totalReturn 
                        ? `${(dashboardData.dashboard.performance.metrics.totalReturn * 100).toFixed(2)}%`
                        : 'N/A'}
                    </div>
                  </div>
                  <div className="metric-card">
                    <h5>Volatility</h5>
                    <div className="metric-value">
                      {dashboardData?.dashboard?.performance?.metrics?.volatility 
                        ? `${(dashboardData.dashboard.performance.metrics.volatility * 100).toFixed(2)}%`
                        : 'N/A'}
                    </div>
                  </div>
                  <div className="metric-card">
                    <h5>Sharpe Ratio</h5>
                    <div className="metric-value">
                      {dashboardData?.dashboard?.performance?.metrics?.sharpeRatio?.toFixed(2) || 'N/A'}
                    </div>
                  </div>
                  <div className="metric-card">
                    <h5>Max Drawdown</h5>
                    <div className="metric-value">
                      {dashboardData?.dashboard?.performance?.metrics?.maxDrawdown 
                        ? `${(dashboardData.dashboard.performance.metrics.maxDrawdown * 100).toFixed(2)}%`
                        : 'N/A'}
                    </div>
                  </div>
                </div>
              </div>

              <div className="risk-analysis">
                <h4>⚖️ Risk Analysis</h4>
                <div className="risk-metrics">
                  <div className="risk-item">
                    <span className="risk-label">Risk Level:</span>
                    <span className="risk-value">
                      {dashboardData?.dashboard?.risk?.summary?.level || 'N/A'}
                    </span>
                  </div>
                  <div className="risk-item">
                    <span className="risk-label">Risk Profile:</span>
                    <span className="risk-value">
                      {dashboardData?.dashboard?.risk?.summary?.profile || 'N/A'}
                    </span>
                  </div>
                  <div className="risk-item">
                    <span className="risk-label">Recommendation:</span>
                    <span className="risk-value">
                      {dashboardData?.dashboard?.risk?.summary?.recommendation || 'N/A'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdvancedTradingDashboard;