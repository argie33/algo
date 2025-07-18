import React, { useState, useEffect } from 'react'
import {
  Box,
  Container,
  Grid,
  Paper,
  Typography,
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  LinearProgress,
  Alert,
  CircularProgress,
  IconButton,
  Tooltip,
  Badge,
  Avatar,
  Switch,
  FormControlLabel,
  ButtonGroup,
  Button,
  Divider,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction
} from '@mui/material'
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  AccountBalance,
  Psychology,
  Security,
  Assessment,
  PieChart,
  Timeline,
  Warning,
  CheckCircle,
  Cancel,
  Refresh,
  AutoGraph,
  Speed,
  Shield,
  Analytics,
  MonetizationOn,
  Insights,
  TrendingFlat
} from '@mui/icons-material'
import { formatCurrency, formatPercentage, formatLargeNumber } from '../utils/formatters'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  PieChart as RechartsPieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar
} from 'recharts'

const CryptoAdvancedDashboard = () => {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState(0)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [portfolioAnalytics, setPortfolioAnalytics] = useState(null)
  const [tradingSignals, setTradingSignals] = useState({})
  const [riskAnalysis, setRiskAnalysis] = useState(null)
  const [marketAnalytics, setMarketAnalytics] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  useEffect(() => {
    fetchAdvancedCryptoData()
    // Set up auto-refresh every 30 seconds if enabled
    const interval = autoRefresh ? setInterval(fetchAdvancedCryptoData, 30 * 1000) : null
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [autoRefresh])

  const fetchAdvancedCryptoData = async () => {
    try {
      setLoading(true)
      
      const [portfolioResponse, signalsResponse, riskResponse, marketResponse] = await Promise.all([
        fetch('/api/crypto-advanced/portfolio/demo-user'),
        fetch('/api/crypto-signals/multi/BTC,ETH,BNB,ADA,SOL'),
        fetch('/api/crypto-risk/portfolio/demo-user'),
        fetch('/api/crypto-analytics/overview')
      ])

      const [portfolioData, signalsData, riskData, marketData] = await Promise.all([
        portfolioResponse.json(),
        signalsResponse.json(),
        riskResponse.json(),
        marketResponse.json()
      ])

      setPortfolioAnalytics(portfolioData.data)
      setTradingSignals(signalsData.data)
      setRiskAnalysis(riskData.data)
      setMarketAnalytics(marketData.data)
      setLastUpdated(new Date().toISOString())
      setLoading(false)
      setError(null)
      
    } catch (err) {
      setError('Failed to fetch advanced crypto data')
      setLoading(false)
    }
  }

  const handleRefresh = () => {
    fetchAdvancedCryptoData()
  }

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue)
  }

  const getGradeColor = (grade) => {
    switch (grade) {
      case 'A': return '#4caf50'
      case 'B': return '#2196f3'
      case 'C': return '#ff9800'
      case 'D': return '#ff9800'
      case 'F': return '#f44336'
      default: return '#666666'
    }
  }

  const getRiskLevelColor = (level) => {
    switch (level?.toLowerCase()) {
      case 'low': return '#4caf50'
      case 'medium': return '#ff9800'
      case 'high': return '#f44336'
      default: return '#666666'
    }
  }

  const getSignalColor = (direction) => {
    switch (direction?.toLowerCase()) {
      case 'bullish': return '#4caf50'
      case 'bearish': return '#f44336'
      case 'neutral': return '#666666'
      default: return '#666666'
    }
  }

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress size={60} />
        </Box>
      </Container>
    )
  }

  if (error) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Alert severity="error">{String(error)}</Alert>
      </Container>
    )
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={4}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          Advanced Crypto Dashboard
        </Typography>
        <Box display="flex" alignItems="center" gap={2}>
          <FormControlLabel
            control={
              <Switch
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                size="small"
              />
            }
            label="Auto-refresh"
          />
          <Tooltip title="Refresh data">
            <IconButton onClick={handleRefresh} color="primary">
              <Refresh />
            </IconButton>
          </Tooltip>
          {lastUpdated && (
            <Typography variant="caption" color="text.secondary">
              Last updated: {new Date(lastUpdated).toLocaleTimeString()}
            </Typography>
          )}
        </Box>
      </Box>

      {/* Main Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={handleTabChange}>
          <Tab icon={<PieChart />} label="Portfolio Analytics" />
          <Tab icon={<AutoGraph />} label="Trading Signals" />
          <Tab icon={<Shield />} label="Risk Management" />
          <Tab icon={<Analytics />} label="Market Analytics" />
        </Tabs>
      </Box>

      {/* Portfolio Analytics Tab */}
      {activeTab === 0 && portfolioAnalytics && (
        <Grid container spacing={3}>
          {/* Portfolio Overview */}
          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 3, mb: 3 }}>
              <Typography variant="h6" gutterBottom>Portfolio Performance</Typography>
              <Grid container spacing={3}>
                <Grid item xs={12} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h4" sx={{ fontWeight: 700, color: 'primary.main' }}>
                      {formatCurrency(portfolioAnalytics.analytics?.totalValue || 0)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Total Value</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <Box textAlign="center">
                    <Typography 
                      variant="h4" 
                      sx={{ 
                        fontWeight: 700, 
                        color: (portfolioAnalytics.analytics?.totalPnLPercent || 0) >= 0 ? 'success.main' : 'error.main' 
                      }}
                    >
                      {formatPercentage(portfolioAnalytics.analytics?.totalPnLPercent || 0)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Total P&L</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {portfolioAnalytics.analytics?.sharpeRatio?.toFixed(2) || '0.00'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Sharpe Ratio</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {portfolioAnalytics.analytics?.volatility?.toFixed(1) || '0.0'}%
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Volatility</Typography>
                  </Box>
                </Grid>
              </Grid>
            </Paper>

            {/* Holdings Breakdown */}
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>Portfolio Holdings</Typography>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Asset</TableCell>
                      <TableCell align="right">Quantity</TableCell>
                      <TableCell align="right">Current Price</TableCell>
                      <TableCell align="right">Market Value</TableCell>
                      <TableCell align="right">P&L</TableCell>
                      <TableCell align="right">Weight</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {portfolioAnalytics.portfolio?.map((holding) => {
                      const marketValue = holding.quantity * holding.current_price
                      const pnl = marketValue - holding.cost_basis
                      const pnlPercent = (pnl / holding.cost_basis) * 100
                      const weight = (marketValue / portfolioAnalytics.analytics.totalValue) * 100

                      return (
                        <TableRow key={holding.symbol}>
                          <TableCell>
                            <Box display="flex" alignItems="center">
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                {holding.symbol}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {holding.quantity.toFixed(6)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {formatCurrency(holding.current_price)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {formatCurrency(marketValue)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography 
                              variant="body2" 
                              color={pnl >= 0 ? 'success.main' : 'error.main'}
                              sx={{ fontWeight: 600 }}
                            >
                              {formatCurrency(pnl)} ({formatPercentage(pnlPercent)})
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {weight.toFixed(1)}%
                            </Typography>
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </Paper>
          </Grid>

          {/* Analytics Summary */}
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 3, mb: 3 }}>
              <Typography variant="h6" gutterBottom>Portfolio Metrics</Typography>
              <List dense>
                <ListItem>
                  <ListItemIcon><Assessment /></ListItemIcon>
                  <ListItemText 
                    primary="Value at Risk (95%)" 
                    secondary={formatCurrency(portfolioAnalytics.analytics?.valueAtRisk || 0)}
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon><Speed /></ListItemIcon>
                  <ListItemText 
                    primary="Max Drawdown" 
                    secondary={formatPercentage(portfolioAnalytics.analytics?.maximumDrawdown || 0)}
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon><TrendingUp /></ListItemIcon>
                  <ListItemText 
                    primary="Beta to Market" 
                    secondary={portfolioAnalytics.analytics?.betaToMarket?.toFixed(2) || '1.00'}
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon><PieChart /></ListItemIcon>
                  <ListItemText 
                    primary="Diversification Score" 
                    secondary={
                      <Box display="flex" alignItems="center">
                        <LinearProgress 
                          variant="determinate" 
                          value={portfolioAnalytics.analytics?.diversificationScore || 0} 
                          sx={{ width: 100, mr: 1 }}
                        />
                        <Typography variant="body2">
                          {portfolioAnalytics.analytics?.diversificationScore?.toFixed(0) || '0'}
                        </Typography>
                      </Box>
                    }
                  />
                </ListItem>
              </List>
            </Paper>

            {/* Sector Breakdown */}
            {portfolioAnalytics.analytics?.sectorBreakdown && (
              <Paper sx={{ p: 3 }}>
                <Typography variant="h6" gutterBottom>Sector Breakdown</Typography>
                <ResponsiveContainer width="100%" height={200}>
                  <RechartsPieChart>
                    <Pie
                      data={Object.entries(portfolioAnalytics.analytics.sectorBreakdown).map(([sector, data]) => ({
                        name: sector,
                        value: data.percentage,
                        color: '#1976d2'
                      }))}
                      cx="50%"
                      cy="50%"
                      innerRadius={40}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {Object.entries(portfolioAnalytics.analytics.sectorBreakdown).map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 50%)`} />
                      ))}
                    </Pie>
                    <RechartsTooltip formatter={(value) => `${value.toFixed(1)}%`} />
                  </RechartsPieChart>
                </ResponsiveContainer>
                <Box mt={2}>
                  {Object.entries(portfolioAnalytics.analytics.sectorBreakdown).map(([sector, data], index) => (
                    <Box key={sector} display="flex" alignItems="center" justifyContent="space-between" mb={1}>
                      <Box display="flex" alignItems="center">
                        <Box 
                          sx={{ 
                            width: 12, 
                            height: 12, 
                            backgroundColor: `hsl(${index * 45}, 70%, 50%)`, 
                            borderRadius: '50%', 
                            mr: 1 
                          }} 
                        />
                        <Typography variant="body2">{sector}</Typography>
                      </Box>
                      <Typography variant="body2" fontWeight={600}>{data.percentage.toFixed(1)}%</Typography>
                    </Box>
                  ))}
                </Box>
              </Paper>
            )}
          </Grid>

          {/* Insights and Recommendations */}
          {portfolioAnalytics.insights && (
            <Grid item xs={12}>
              <Paper sx={{ p: 3 }}>
                <Typography variant="h6" gutterBottom>Portfolio Insights & Recommendations</Typography>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={4}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box display="flex" alignItems="center" mb={1}>
                          <Shield color="primary" sx={{ mr: 1 }} />
                          <Typography variant="h6">Risk Level</Typography>
                        </Box>
                        <Chip 
                          label={portfolioAnalytics.insights.riskLevel}
                          color={
                            portfolioAnalytics.insights.riskLevel === 'Low' ? 'success' :
                            portfolioAnalytics.insights.riskLevel === 'Medium' ? 'warning' : 'error'
                          }
                          sx={{ mb: 1 }}
                        />
                        <Typography variant="body2" color="text.secondary">
                          Based on volatility and risk metrics
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box display="flex" alignItems="center" mb={1}>
                          <Assessment color="primary" sx={{ mr: 1 }} />
                          <Typography variant="h6">Diversification</Typography>
                        </Box>
                        <Chip 
                          label={`Grade ${portfolioAnalytics.insights.diversificationGrade}`}
                          sx={{ 
                            mb: 1,
                            backgroundColor: getGradeColor(portfolioAnalytics.insights.diversificationGrade),
                            color: 'white'
                          }}
                        />
                        <Typography variant="body2" color="text.secondary">
                          Portfolio diversification quality
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box display="flex" alignItems="center" mb={1}>
                          <Insights color="primary" sx={{ mr: 1 }} />
                          <Typography variant="h6">Recommendations</Typography>
                        </Box>
                        <Typography variant="h6" sx={{ mb: 1 }}>
                          {portfolioAnalytics.insights.recommendations?.length || 0}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Active recommendations
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>

                {/* Recommendations List */}
                {portfolioAnalytics.insights.recommendations && portfolioAnalytics.insights.recommendations.length > 0 && (
                  <Box mt={3}>
                    <Typography variant="h6" gutterBottom>Active Recommendations</Typography>
                    {portfolioAnalytics.insights.recommendations.map((rec, index) => (
                      <Alert 
                        key={index}
                        severity={rec.priority === 'high' ? 'warning' : 'info'}
                        sx={{ mb: 1 }}
                      >
                        <Typography variant="body2" fontWeight={600}>{rec.message}</Typography>
                        <Typography variant="body2">{rec.action}</Typography>
                      </Alert>
                    ))}
                  </Box>
                )}
              </Paper>
            </Grid>
          )}
        </Grid>
      )}

      {/* Trading Signals Tab */}
      {activeTab === 1 && tradingSignals && (
        <Grid container spacing={3}>
          {tradingSignals.signals?.map((signal) => (
            <Grid item xs={12} md={6} lg={4} key={signal.symbol}>
              <Paper sx={{ p: 3 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                  <Typography variant="h6">{signal.symbol}</Typography>
                  <Chip 
                    label={signal.overallSignal?.direction || 'Neutral'}
                    sx={{ 
                      backgroundColor: getSignalColor(signal.overallSignal?.direction),
                      color: 'white'
                    }}
                  />
                </Box>

                {/* Signal Strength */}
                <Box mb={2}>
                  <Typography variant="body2" gutterBottom>
                    Signal Strength: {signal.overallSignal?.strength?.toFixed(0) || 0}%
                  </Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={signal.overallSignal?.strength || 0}
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>

                {/* Key Indicators */}
                <Grid container spacing={1}>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">RSI</Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {signal.indicators?.rsi?.current?.toFixed(1) || '--'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">MACD</Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {signal.indicators?.macd?.trend || '--'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Trend</Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {signal.signals?.trend?.direction || '--'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Volume</Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {signal.signals?.volume?.strength || '--'}
                    </Typography>
                  </Grid>
                </Grid>

                {/* Recommendations */}
                {signal.recommendations && signal.recommendations.length > 0 && (
                  <Box mt={2}>
                    <Typography variant="caption" color="text.secondary">Top Recommendation</Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {signal.recommendations[0].action?.toUpperCase() || 'HOLD'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {signal.recommendations[0].reason}
                    </Typography>
                  </Box>
                )}
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}

      {/* Risk Management Tab */}
      {activeTab === 2 && riskAnalysis && (
        <Grid container spacing={3}>
          {/* Risk Overview */}
          <Grid item xs={12}>
            <Paper sx={{ p: 3, mb: 3 }}>
              <Typography variant="h6" gutterBottom>Risk Assessment Overview</Typography>
              <Grid container spacing={3}>
                <Grid item xs={12} sm={3}>
                  <Box textAlign="center">
                    <Typography 
                      variant="h4" 
                      sx={{ 
                        fontWeight: 700, 
                        color: getGradeColor(riskAnalysis.risk_analysis?.overallRiskScore?.risk_grade)
                      }}
                    >
                      {riskAnalysis.risk_analysis?.overallRiskScore?.risk_grade || 'C'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Risk Grade</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {riskAnalysis.risk_analysis?.overallRiskScore?.overall_score || 50}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Risk Score</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {formatCurrency(riskAnalysis.risk_analysis?.var?.var_amount || 0)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Value at Risk (95%)</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {formatPercentage(riskAnalysis.risk_analysis?.maxDrawdown?.max_drawdown_percentage || 0)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">Max Drawdown</Typography>
                  </Box>
                </Grid>
              </Grid>
            </Paper>
          </Grid>

          {/* Risk Components */}
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>Risk Components</Typography>
              <List>
                <ListItem>
                  <ListItemIcon><Security /></ListItemIcon>
                  <ListItemText 
                    primary="Concentration Risk" 
                    secondary={
                      <Chip 
                        size="small"
                        label={riskAnalysis.risk_analysis?.concentrationRisk?.risk_level || 'Medium'}
                        color={
                          riskAnalysis.risk_analysis?.concentrationRisk?.risk_level === 'low' ? 'success' :
                          riskAnalysis.risk_analysis?.concentrationRisk?.risk_level === 'medium' ? 'warning' : 'error'
                        }
                      />
                    }
                  />
                  <ListItemSecondaryAction>
                    <Typography variant="body2">
                      {riskAnalysis.risk_analysis?.concentrationRisk?.concentration_score?.toFixed(0) || '50'}
                    </Typography>
                  </ListItemSecondaryAction>
                </ListItem>
                <ListItem>
                  <ListItemIcon><Timeline /></ListItemIcon>
                  <ListItemText 
                    primary="Liquidity Risk" 
                    secondary={
                      <Chip 
                        size="small"
                        label={riskAnalysis.risk_analysis?.liquidityRisk?.risk_level || 'Medium'}
                        color={
                          riskAnalysis.risk_analysis?.liquidityRisk?.risk_level === 'low' ? 'success' :
                          riskAnalysis.risk_analysis?.liquidityRisk?.risk_level === 'medium' ? 'warning' : 'error'
                        }
                      />
                    }
                  />
                  <ListItemSecondaryAction>
                    <Typography variant="body2">
                      {riskAnalysis.risk_analysis?.liquidityRisk?.overall_liquidity_score?.toFixed(0) || '60'}
                    </Typography>
                  </ListItemSecondaryAction>
                </ListItem>
                <ListItem>
                  <ListItemIcon><ShowChart /></ListItemIcon>
                  <ListItemText 
                    primary="Correlation Risk" 
                    secondary={
                      <Chip 
                        size="small"
                        label={riskAnalysis.risk_analysis?.correlationRisk?.risk_level || 'Medium'}
                        color={
                          riskAnalysis.risk_analysis?.correlationRisk?.risk_level === 'low' ? 'success' :
                          riskAnalysis.risk_analysis?.correlationRisk?.risk_level === 'medium' ? 'warning' : 'error'
                        }
                      />
                    }
                  />
                  <ListItemSecondaryAction>
                    <Typography variant="body2">
                      {(riskAnalysis.risk_analysis?.correlationRisk?.average_correlation * 100)?.toFixed(0) || '60'}%
                    </Typography>
                  </ListItemSecondaryAction>
                </ListItem>
              </List>
            </Paper>
          </Grid>

          {/* Stress Tests */}
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>Stress Test Results</Typography>
              {riskAnalysis.risk_analysis?.stressTests?.stress_tests?.slice(0, 5).map((test, index) => (
                <Box key={index} mb={2}>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                    <Typography variant="body2" fontWeight={600}>{test.scenario}</Typography>
                    <Chip 
                      size="small"
                      label={test.severity}
                      color={
                        test.severity === 'moderate' ? 'info' :
                        test.severity === 'high' ? 'warning' : 'error'
                      }
                    />
                  </Box>
                  <Typography variant="caption" color="text.secondary">
                    {test.description}
                  </Typography>
                  <Box display="flex" justifyContent="space-between" mt={1}>
                    <Typography variant="body2" color="error.main">
                      {formatPercentage(test.loss_percentage)}
                    </Typography>
                    <Typography variant="body2" color="error.main">
                      {formatCurrency(test.loss_amount)}
                    </Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={Math.min(100, test.loss_percentage)} 
                    color="error"
                    sx={{ mt: 1, height: 4 }}
                  />
                </Box>
              ))}
            </Paper>
          </Grid>

          {/* Risk Recommendations */}
          {riskAnalysis.risk_analysis?.recommendations && (
            <Grid item xs={12}>
              <Paper sx={{ p: 3 }}>
                <Typography variant="h6" gutterBottom>Risk Management Recommendations</Typography>
                <Grid container spacing={2}>
                  {riskAnalysis.risk_analysis.recommendations.map((rec, index) => (
                    <Grid item xs={12} md={6} key={index}>
                      <Alert 
                        severity={rec.priority === 'high' ? 'error' : rec.priority === 'medium' ? 'warning' : 'info'}
                        sx={{ height: '100%' }}
                      >
                        <Typography variant="body2" fontWeight={600} gutterBottom>
                          {rec.title}
                        </Typography>
                        <Typography variant="body2" gutterBottom>
                          {rec.description}
                        </Typography>
                        <List dense>
                          {rec.actions?.map((action, actionIndex) => (
                            <ListItem key={actionIndex} sx={{ py: 0.5 }}>
                              <ListItemIcon sx={{ minWidth: 20 }}>
                                <CheckCircle fontSize="small" />
                              </ListItemIcon>
                              <ListItemText primary={action} />
                            </ListItem>
                          ))}
                        </List>
                      </Alert>
                    </Grid>
                  ))}
                </Grid>
              </Paper>
            </Grid>
          )}
        </Grid>
      )}

      {/* Market Analytics Tab */}
      {activeTab === 3 && marketAnalytics && (
        <Grid container spacing={3}>
          {/* Market Health Score */}
          <Grid item xs={12}>
            <Paper sx={{ p: 3, mb: 3 }}>
              <Typography variant="h6" gutterBottom>Market Health Overview</Typography>
              <Grid container spacing={3} alignItems="center">
                <Grid item xs={12} sm={3}>
                  <Box textAlign="center">
                    <Typography 
                      variant="h3" 
                      sx={{ 
                        fontWeight: 700, 
                        color: getGradeColor(marketAnalytics.market_health_score?.grade)
                      }}
                    >
                      {marketAnalytics.market_health_score?.grade || 'C'}
                    </Typography>
                    <Typography variant="h6" color="text.secondary">Health Grade</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h3" sx={{ fontWeight: 700 }}>
                      {marketAnalytics.market_health_score?.score || 50}
                    </Typography>
                    <Typography variant="h6" color="text.secondary">Health Score</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Box>
                    <Typography variant="h6" gutterBottom>Market Status</Typography>
                    <Chip 
                      label={marketAnalytics.market_health_score?.status?.toUpperCase() || 'CAUTIOUS'}
                      color={
                        marketAnalytics.market_health_score?.status === 'healthy' ? 'success' :
                        marketAnalytics.market_health_score?.status === 'cautious' ? 'warning' : 'error'
                      }
                      sx={{ mb: 1 }}
                    />
                    <Typography variant="body2" color="text.secondary">
                      Overall market conditions and sentiment
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </Paper>
          </Grid>

          {/* Market Metrics */}
          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>Key Market Metrics</Typography>
              <Grid container spacing={2}>
                <Grid item xs={6} sm={3}>
                  <Box textAlign="center" p={2} sx={{ backgroundColor: 'action.hover', borderRadius: 1 }}>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>
                      {formatCurrency(marketAnalytics.market_metrics?.total_market_cap || 0, 0)}
                    </Typography>
                    <Typography variant="caption">Market Cap</Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box textAlign="center" p={2} sx={{ backgroundColor: 'action.hover', borderRadius: 1 }}>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>
                      {formatCurrency(marketAnalytics.market_metrics?.total_volume_24h || 0, 0)}
                    </Typography>
                    <Typography variant="caption">24h Volume</Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box textAlign="center" p={2} sx={{ backgroundColor: 'action.hover', borderRadius: 1 }}>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>
                      {marketAnalytics.market_metrics?.btc_dominance?.toFixed(1) || '42.5'}%
                    </Typography>
                    <Typography variant="caption">BTC Dominance</Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box textAlign="center" p={2} sx={{ backgroundColor: 'action.hover', borderRadius: 1 }}>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>
                      {marketAnalytics.sentiment_analysis?.fear_greed_index?.value || 35}
                    </Typography>
                    <Typography variant="caption">Fear & Greed</Typography>
                  </Box>
                </Grid>
              </Grid>
            </Paper>
          </Grid>

          {/* Sector Performance */}
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 3 }}>
              <Typography variant="h6" gutterBottom>Top Performing Sectors</Typography>
              {marketAnalytics.sector_analysis?.sectors?.slice(0, 5).map((sector, index) => (
                <Box key={sector.name} display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body2">{sector.name}</Typography>
                  <Box display="flex" alignItems="center">
                    <Typography 
                      variant="body2" 
                      sx={{ 
                        fontWeight: 600,
                        color: sector.change_24h >= 0 ? 'success.main' : 'error.main'
                      }}
                    >
                      {sector.change_24h >= 0 ? '+' : ''}{sector.change_24h?.toFixed(1)}%
                    </Typography>
                    {sector.change_24h >= 0 ? 
                      <TrendingUp fontSize="small" color="success" sx={{ ml: 0.5 }} /> :
                      <TrendingDown fontSize="small" color="error" sx={{ ml: 0.5 }} />
                    }
                  </Box>
                </Box>
              ))}
            </Paper>
          </Grid>
        </Grid>
      )}
    </Container>
  )
}

export default CryptoAdvancedDashboard