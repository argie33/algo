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
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
        <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={60} />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">{String(error)}</div>
      </div>
    )
  }

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  display="flex" justifyContent="space-between" alignItems="center" mb={4}>
        <div  variant="h4" component="h1" sx={{ fontWeight: 700 }}>
          Advanced Crypto Dashboard
        </div>
        <div  display="flex" alignItems="center" gap={2}>
          <div className="mb-4"Label
            control={
              <input type="checkbox" className="toggle"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                size="small"
              />
            }
            label="Auto-refresh"
          />
          <div  title="Refresh data">
            <button className="p-2 rounded-full hover:bg-gray-100" onClick={handleRefresh} color="primary">
              <Refresh />
            </button>
          </div>
          {lastUpdated && (
            <div  variant="caption" color="text.secondary">
              Last updated: {new Date(lastUpdated).toLocaleTimeString()}
            </div>
          )}
        </div>
      </div>

      {/* Main Tabs */}
      <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <div className="border-b border-gray-200" value={activeTab} onChange={handleTabChange}>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" icon={<PieChart />} label="Portfolio Analytics" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" icon={<AutoGraph />} label="Trading Signals" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" icon={<Shield />} label="Risk Management" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" icon={<Analytics />} label="Market Analytics" />
        </div>
      </div>

      {/* Portfolio Analytics Tab */}
      {activeTab === 0 && portfolioAnalytics && (
        <div className="grid" container spacing={3}>
          {/* Portfolio Overview */}
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3, mb: 3 }}>
              <div  variant="h6" gutterBottom>Portfolio Performance</div>
              <div className="grid" container spacing={3}>
                <div className="grid" item xs={12} sm={3}>
                  <div  textAlign="center">
                    <div  variant="h4" sx={{ fontWeight: 700, color: 'primary.main' }}>
                      {formatCurrency(portfolioAnalytics.analytics?.totalValue || 0)}
                    </div>
                    <div  variant="body2" color="text.secondary">Total Value</div>
                  </div>
                </div>
                <div className="grid" item xs={12} sm={3}>
                  <div  textAlign="center">
                    <div  
                      variant="h4" 
                      sx={{ 
                        fontWeight: 700, 
                        color: (portfolioAnalytics.analytics?.totalPnLPercent || 0) >= 0 ? 'success.main' : 'error.main' 
                      }}
                    >
                      {formatPercentage(portfolioAnalytics.analytics?.totalPnLPercent || 0)}
                    </div>
                    <div  variant="body2" color="text.secondary">Total P&L</div>
                  </div>
                </div>
                <div className="grid" item xs={12} sm={3}>
                  <div  textAlign="center">
                    <div  variant="h4" sx={{ fontWeight: 700 }}>
                      {portfolioAnalytics.analytics?.sharpeRatio?.toFixed(2) || '0.00'}
                    </div>
                    <div  variant="body2" color="text.secondary">Sharpe Ratio</div>
                  </div>
                </div>
                <div className="grid" item xs={12} sm={3}>
                  <div  textAlign="center">
                    <div  variant="h4" sx={{ fontWeight: 700 }}>
                      {portfolioAnalytics.analytics?.volatility?.toFixed(1) || '0.0'}%
                    </div>
                    <div  variant="body2" color="text.secondary">Volatility</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Holdings Breakdown */}
            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
              <div  variant="h6" gutterBottom>Portfolio Holdings</div>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Asset</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Quantity</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Current Price</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Market Value</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">P&L</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Weight</td>
                    </tr>
                  </thead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                    {portfolioAnalytics.portfolio?.map((holding) => {
                      const marketValue = holding.quantity * holding.current_price
                      const pnl = marketValue - holding.cost_basis
                      const pnlPercent = (pnl / holding.cost_basis) * 100
                      const weight = (marketValue / portfolioAnalytics.analytics.totalValue) * 100

                      return (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={holding.symbol}>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  display="flex" alignItems="center">
                              <div  variant="body2" sx={{ fontWeight: 600 }}>
                                {holding.symbol}
                              </div>
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body2">
                              {holding.quantity.toFixed(6)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body2">
                              {formatCurrency(holding.current_price)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body2">
                              {formatCurrency(marketValue)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  
                              variant="body2" 
                              color={pnl >= 0 ? 'success.main' : 'error.main'}
                              sx={{ fontWeight: 600 }}
                            >
                              {formatCurrency(pnl)} ({formatPercentage(pnlPercent)})
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body2">
                              {weight.toFixed(1)}%
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Analytics Summary */}
          <div className="grid" item xs={12} md={4}>
            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3, mb: 3 }}>
              <div  variant="h6" gutterBottom>Portfolio Metrics</div>
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
                      <div  display="flex" alignItems="center">
                        <div className="w-full bg-gray-200 rounded-full h-2" 
                          variant="determinate" 
                          value={portfolioAnalytics.analytics?.diversificationScore || 0} 
                          sx={{ width: 100, mr: 1 }}
                        />
                        <div  variant="body2">
                          {portfolioAnalytics.analytics?.diversificationScore?.toFixed(0) || '0'}
                        </div>
                      </div>
                    }
                  />
                </ListItem>
              </List>
            </div>

            {/* Sector Breakdown */}
            {portfolioAnalytics.analytics?.sectorBreakdown && (
              <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
                <div  variant="h6" gutterBottom>Sector Breakdown</div>
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
                <div  mt={2}>
                  {Object.entries(portfolioAnalytics.analytics.sectorBreakdown).map(([sector, data], index) => (
                    <div  key={sector} display="flex" alignItems="center" justifyContent="space-between" mb={1}>
                      <div  display="flex" alignItems="center">
                        <div  
                          sx={{ 
                            width: 12, 
                            height: 12, 
                            backgroundColor: `hsl(${index * 45}, 70%, 50%)`, 
                            borderRadius: '50%', 
                            mr: 1 
                          }} 
                        />
                        <div  variant="body2">{sector}</div>
                      </div>
                      <div  variant="body2" fontWeight={600}>{data.percentage.toFixed(1)}%</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Insights and Recommendations */}
          {portfolioAnalytics.insights && (
            <div className="grid" item xs={12}>
              <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
                <div  variant="h6" gutterBottom>Portfolio Insights & Recommendations</div>
                <div className="grid" container spacing={2}>
                  <div className="grid" item xs={12} sm={4}>
                    <div className="bg-white shadow-md rounded-lg" variant="outlined">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  display="flex" alignItems="center" mb={1}>
                          <Shield color="primary" sx={{ mr: 1 }} />
                          <div  variant="h6">Risk Level</div>
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={portfolioAnalytics.insights.riskLevel}
                          color={
                            portfolioAnalytics.insights.riskLevel === 'Low' ? 'success' :
                            portfolioAnalytics.insights.riskLevel === 'Medium' ? 'warning' : 'error'
                          }
                          sx={{ mb: 1 }}
                        />
                        <div  variant="body2" color="text.secondary">
                          Based on volatility and risk metrics
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="grid" item xs={12} sm={4}>
                    <div className="bg-white shadow-md rounded-lg" variant="outlined">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  display="flex" alignItems="center" mb={1}>
                          <Assessment color="primary" sx={{ mr: 1 }} />
                          <div  variant="h6">Diversification</div>
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={`Grade ${portfolioAnalytics.insights.diversificationGrade}`}
                          sx={{ 
                            mb: 1,
                            backgroundColor: getGradeColor(portfolioAnalytics.insights.diversificationGrade),
                            color: 'white'
                          }}
                        />
                        <div  variant="body2" color="text.secondary">
                          Portfolio diversification quality
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="grid" item xs={12} sm={4}>
                    <div className="bg-white shadow-md rounded-lg" variant="outlined">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  display="flex" alignItems="center" mb={1}>
                          <Insights color="primary" sx={{ mr: 1 }} />
                          <div  variant="h6">Recommendations</div>
                        </div>
                        <div  variant="h6" sx={{ mb: 1 }}>
                          {portfolioAnalytics.insights.recommendations?.length || 0}
                        </div>
                        <div  variant="body2" color="text.secondary">
                          Active recommendations
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Recommendations List */}
                {portfolioAnalytics.insights.recommendations && portfolioAnalytics.insights.recommendations.length > 0 && (
                  <div  mt={3}>
                    <div  variant="h6" gutterBottom>Active Recommendations</div>
                    {portfolioAnalytics.insights.recommendations.map((rec, index) => (
                      <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
                        key={index}
                        severity={rec.priority === 'high' ? 'warning' : 'info'}
                        sx={{ mb: 1 }}
                      >
                        <div  variant="body2" fontWeight={600}>{rec.message}</div>
                        <div  variant="body2">{rec.action}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Trading Signals Tab */}
      {activeTab === 1 && tradingSignals && (
        <div className="grid" container spacing={3}>
          {tradingSignals.signals?.map((signal) => (
            <div className="grid" item xs={12} md={6} lg={4} key={signal.symbol}>
              <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
                <div  display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                  <div  variant="h6">{signal.symbol}</div>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    label={signal.overallSignal?.direction || 'Neutral'}
                    sx={{ 
                      backgroundColor: getSignalColor(signal.overallSignal?.direction),
                      color: 'white'
                    }}
                  />
                </div>

                {/* Signal Strength */}
                <div  mb={2}>
                  <div  variant="body2" gutterBottom>
                    Signal Strength: {signal.overallSignal?.strength?.toFixed(0) || 0}%
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2" 
                    variant="determinate" 
                    value={signal.overallSignal?.strength || 0}
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </div>

                {/* Key Indicators */}
                <div className="grid" container spacing={1}>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">RSI</div>
                    <div  variant="body2" fontWeight={600}>
                      {signal.indicators?.rsi?.current?.toFixed(1) || '--'}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">MACD</div>
                    <div  variant="body2" fontWeight={600}>
                      {signal.indicators?.macd?.trend || '--'}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Trend</div>
                    <div  variant="body2" fontWeight={600}>
                      {signal.signals?.trend?.direction || '--'}
                    </div>
                  </div>
                  <div className="grid" item xs={6}>
                    <div  variant="caption" color="text.secondary">Volume</div>
                    <div  variant="body2" fontWeight={600}>
                      {signal.signals?.volume?.strength || '--'}
                    </div>
                  </div>
                </div>

                {/* Recommendations */}
                {signal.recommendations && signal.recommendations.length > 0 && (
                  <div  mt={2}>
                    <div  variant="caption" color="text.secondary">Top Recommendation</div>
                    <div  variant="body2" fontWeight={600}>
                      {signal.recommendations[0].action?.toUpperCase() || 'HOLD'}
                    </div>
                    <div  variant="body2" color="text.secondary">
                      {signal.recommendations[0].reason}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Risk Management Tab */}
      {activeTab === 2 && riskAnalysis && (
        <div className="grid" container spacing={3}>
          {/* Risk Overview */}
          <div className="grid" item xs={12}>
            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3, mb: 3 }}>
              <div  variant="h6" gutterBottom>Risk Assessment Overview</div>
              <div className="grid" container spacing={3}>
                <div className="grid" item xs={12} sm={3}>
                  <div  textAlign="center">
                    <div  
                      variant="h4" 
                      sx={{ 
                        fontWeight: 700, 
                        color: getGradeColor(riskAnalysis.risk_analysis?.overallRiskScore?.risk_grade)
                      }}
                    >
                      {riskAnalysis.risk_analysis?.overallRiskScore?.risk_grade || 'C'}
                    </div>
                    <div  variant="body2" color="text.secondary">Risk Grade</div>
                  </div>
                </div>
                <div className="grid" item xs={12} sm={3}>
                  <div  textAlign="center">
                    <div  variant="h4" sx={{ fontWeight: 700 }}>
                      {riskAnalysis.risk_analysis?.overallRiskScore?.overall_score || 50}
                    </div>
                    <div  variant="body2" color="text.secondary">Risk Score</div>
                  </div>
                </div>
                <div className="grid" item xs={12} sm={3}>
                  <div  textAlign="center">
                    <div  variant="h4" sx={{ fontWeight: 700 }}>
                      {formatCurrency(riskAnalysis.risk_analysis?.var?.var_amount || 0)}
                    </div>
                    <div  variant="body2" color="text.secondary">Value at Risk (95%)</div>
                  </div>
                </div>
                <div className="grid" item xs={12} sm={3}>
                  <div  textAlign="center">
                    <div  variant="h4" sx={{ fontWeight: 700 }}>
                      {formatPercentage(riskAnalysis.risk_analysis?.maxDrawdown?.max_drawdown_percentage || 0)}
                    </div>
                    <div  variant="body2" color="text.secondary">Max Drawdown</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Risk Components */}
          <div className="grid" item xs={12} md={6}>
            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
              <div  variant="h6" gutterBottom>Risk Components</div>
              <List>
                <ListItem>
                  <ListItemIcon><Security /></ListItemIcon>
                  <ListItemText 
                    primary="Concentration Risk" 
                    secondary={
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
                    <div  variant="body2">
                      {riskAnalysis.risk_analysis?.concentrationRisk?.concentration_score?.toFixed(0) || '50'}
                    </div>
                  </ListItemSecondaryAction>
                </ListItem>
                <ListItem>
                  <ListItemIcon><Timeline /></ListItemIcon>
                  <ListItemText 
                    primary="Liquidity Risk" 
                    secondary={
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
                    <div  variant="body2">
                      {riskAnalysis.risk_analysis?.liquidityRisk?.overall_liquidity_score?.toFixed(0) || '60'}
                    </div>
                  </ListItemSecondaryAction>
                </ListItem>
                <ListItem>
                  <ListItemIcon><ShowChart /></ListItemIcon>
                  <ListItemText 
                    primary="Correlation Risk" 
                    secondary={
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
                    <div  variant="body2">
                      {(riskAnalysis.risk_analysis?.correlationRisk?.average_correlation * 100)?.toFixed(0) || '60'}%
                    </div>
                  </ListItemSecondaryAction>
                </ListItem>
              </List>
            </div>
          </div>

          {/* Stress Tests */}
          <div className="grid" item xs={12} md={6}>
            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
              <div  variant="h6" gutterBottom>Stress Test Results</div>
              {riskAnalysis.risk_analysis?.stressTests?.stress_tests?.slice(0, 5).map((test, index) => (
                <div  key={index} mb={2}>
                  <div  display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                    <div  variant="body2" fontWeight={600}>{test.scenario}</div>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      size="small"
                      label={test.severity}
                      color={
                        test.severity === 'moderate' ? 'info' :
                        test.severity === 'high' ? 'warning' : 'error'
                      }
                    />
                  </div>
                  <div  variant="caption" color="text.secondary">
                    {test.description}
                  </div>
                  <div  display="flex" justifyContent="space-between" mt={1}>
                    <div  variant="body2" color="error.main">
                      {formatPercentage(test.loss_percentage)}
                    </div>
                    <div  variant="body2" color="error.main">
                      {formatCurrency(test.loss_amount)}
                    </div>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2" 
                    variant="determinate" 
                    value={Math.min(100, test.loss_percentage)} 
                    color="error"
                    sx={{ mt: 1, height: 4 }}
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Risk Recommendations */}
          {riskAnalysis.risk_analysis?.recommendations && (
            <div className="grid" item xs={12}>
              <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
                <div  variant="h6" gutterBottom>Risk Management Recommendations</div>
                <div className="grid" container spacing={2}>
                  {riskAnalysis.risk_analysis.recommendations.map((rec, index) => (
                    <div className="grid" item xs={12} md={6} key={index}>
                      <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
                        severity={rec.priority === 'high' ? 'error' : rec.priority === 'medium' ? 'warning' : 'info'}
                        sx={{ height: '100%' }}
                      >
                        <div  variant="body2" fontWeight={600} gutterBottom>
                          {rec.title}
                        </div>
                        <div  variant="body2" gutterBottom>
                          {rec.description}
                        </div>
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
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Market Analytics Tab */}
      {activeTab === 3 && marketAnalytics && (
        <div className="grid" container spacing={3}>
          {/* Market Health Score */}
          <div className="grid" item xs={12}>
            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3, mb: 3 }}>
              <div  variant="h6" gutterBottom>Market Health Overview</div>
              <div className="grid" container spacing={3} alignItems="center">
                <div className="grid" item xs={12} sm={3}>
                  <div  textAlign="center">
                    <div  
                      variant="h3" 
                      sx={{ 
                        fontWeight: 700, 
                        color: getGradeColor(marketAnalytics.market_health_score?.grade)
                      }}
                    >
                      {marketAnalytics.market_health_score?.grade || 'C'}
                    </div>
                    <div  variant="h6" color="text.secondary">Health Grade</div>
                  </div>
                </div>
                <div className="grid" item xs={12} sm={3}>
                  <div  textAlign="center">
                    <div  variant="h3" sx={{ fontWeight: 700 }}>
                      {marketAnalytics.market_health_score?.score || 50}
                    </div>
                    <div  variant="h6" color="text.secondary">Health Score</div>
                  </div>
                </div>
                <div className="grid" item xs={12} sm={6}>
                  <div>
                    <div  variant="h6" gutterBottom>Market Status</div>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      label={marketAnalytics.market_health_score?.status?.toUpperCase() || 'CAUTIOUS'}
                      color={
                        marketAnalytics.market_health_score?.status === 'healthy' ? 'success' :
                        marketAnalytics.market_health_score?.status === 'cautious' ? 'warning' : 'error'
                      }
                      sx={{ mb: 1 }}
                    />
                    <div  variant="body2" color="text.secondary">
                      Overall market conditions and sentiment
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Market Metrics */}
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
              <div  variant="h6" gutterBottom>Key Market Metrics</div>
              <div className="grid" container spacing={2}>
                <div className="grid" item xs={6} sm={3}>
                  <div  textAlign="center" p={2} sx={{ backgroundColor: 'action.hover', borderRadius: 1 }}>
                    <div  variant="h6" sx={{ fontWeight: 700 }}>
                      {formatCurrency(marketAnalytics.market_metrics?.total_market_cap || 0, 0)}
                    </div>
                    <div  variant="caption">Market Cap</div>
                  </div>
                </div>
                <div className="grid" item xs={6} sm={3}>
                  <div  textAlign="center" p={2} sx={{ backgroundColor: 'action.hover', borderRadius: 1 }}>
                    <div  variant="h6" sx={{ fontWeight: 700 }}>
                      {formatCurrency(marketAnalytics.market_metrics?.total_volume_24h || 0, 0)}
                    </div>
                    <div  variant="caption">24h Volume</div>
                  </div>
                </div>
                <div className="grid" item xs={6} sm={3}>
                  <div  textAlign="center" p={2} sx={{ backgroundColor: 'action.hover', borderRadius: 1 }}>
                    <div  variant="h6" sx={{ fontWeight: 700 }}>
                      {marketAnalytics.market_metrics?.btc_dominance?.toFixed(1) || '42.5'}%
                    </div>
                    <div  variant="caption">BTC Dominance</div>
                  </div>
                </div>
                <div className="grid" item xs={6} sm={3}>
                  <div  textAlign="center" p={2} sx={{ backgroundColor: 'action.hover', borderRadius: 1 }}>
                    <div  variant="h6" sx={{ fontWeight: 700 }}>
                      {marketAnalytics.sentiment_analysis?.fear_greed_index?.value || 35}
                    </div>
                    <div  variant="caption">Fear & Greed</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Sector Performance */}
          <div className="grid" item xs={12} md={4}>
            <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3 }}>
              <div  variant="h6" gutterBottom>Top Performing Sectors</div>
              {marketAnalytics.sector_analysis?.sectors?.slice(0, 5).map((sector, index) => (
                <div  key={sector.name} display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <div  variant="body2">{sector.name}</div>
                  <div  display="flex" alignItems="center">
                    <div  
                      variant="body2" 
                      sx={{ 
                        fontWeight: 600,
                        color: sector.change_24h >= 0 ? 'success.main' : 'error.main'
                      }}
                    >
                      {sector.change_24h >= 0 ? '+' : ''}{sector.change_24h?.toFixed(1)}%
                    </div>
                    {sector.change_24h >= 0 ? 
                      <TrendingUp fontSize="small" color="success" sx={{ ml: 0.5 }} /> :
                      <TrendingDown fontSize="small" color="error" sx={{ ml: 0.5 }} />
                    }
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CryptoAdvancedDashboard