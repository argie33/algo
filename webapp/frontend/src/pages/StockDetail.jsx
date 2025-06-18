import React from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { createComponentLogger } from '../utils/errorLogger'
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Chip,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Paper,
  Divider,
  CircularProgress,
  Alert,
  LinearProgress
} from '@mui/material'
import {
  TrendingUp,
  TrendingDown,
  Business,
  AccountBalance,
  Analytics,
  Timeline
} from '@mui/icons-material'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell
} from 'recharts'
import api from '../services/api'
import { formatCurrency, formatPercentage as formatPercent, formatNumber } from '../utils/formatters'

// Use centralized error logging (logger will be defined in component)

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`simple-tabpanel-${index}`}
      aria-labelledby={`simple-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  )
}

function StockDetail() {
  const logger = createComponentLogger('StockDetail');
  
  const { symbol } = useParams()
  const [tabValue, setTabValue] = React.useState(0)
  // Fetch stock profile data
  const { data: profile, isLoading: profileLoading, error: profileError } = useQuery({
    queryKey: ['stockProfile', symbol],
    queryFn: () => api.getStockProfile(symbol),
    enabled: !!symbol,
    onError: (error) => logger.queryError('stockProfile', error, { symbol })
  })

  // Fetch key metrics
  const { data: metrics, isLoading: metricsLoading, error: metricsError } = useQuery({
    queryKey: ['stockMetrics', symbol],
    queryFn: () => api.getStockMetrics(symbol),
    enabled: !!symbol,
    onError: (error) => logger.queryError('stockMetrics', error, { symbol })
  })
  // Fetch financial data
  const { data: financials, isLoading: financialsLoading, error: financialsError } = useQuery({
    queryKey: ['stockFinancials', symbol],
    queryFn: () => api.getStockFinancials(symbol),
    enabled: !!symbol,
    onError: (error) => logger.queryError('stockFinancials', error, { symbol })
  })

  // Fetch analyst recommendations
  const { data: recommendations, isLoading: recLoading, error: recError } = useQuery({
    queryKey: ['stockRecommendations', symbol],
    queryFn: () => api.getAnalystRecommendations(symbol),
    enabled: !!symbol,
    onError: (error) => logger.queryError('analystRecommendations', error, { symbol })  })

  // Fetch comprehensive financial statements
  const { data: balanceSheet, isLoading: balanceSheetLoading, error: balanceSheetError } = useQuery({
    queryKey: ['balanceSheet', symbol, 'annual'],
    queryFn: () => api.getBalanceSheet(symbol, 'annual'),
    enabled: !!symbol && tabValue === 2,
    onError: (error) => logger.queryError('balanceSheet', error, { symbol, period: 'annual' })
  })
  const { data: incomeStatement, isLoading: incomeStatementLoading, error: incomeStatementError } = useQuery({
    queryKey: ['incomeStatement', symbol, 'annual'],
    queryFn: () => api.getIncomeStatement(symbol, 'annual'),
    enabled: !!symbol && tabValue === 2,
    onError: (error) => logger.queryError('incomeStatement', error, { symbol, period: 'annual' })
  })
  const { data: cashFlowStatement, isLoading: cashFlowLoading, error: cashFlowError } = useQuery({
    queryKey: ['cashFlowStatement', symbol, 'annual'],
    queryFn: () => api.getCashFlowStatement(symbol, 'annual'),
    enabled: !!symbol && tabValue === 2,
    onError: (error) => logger.queryError('cashFlowStatement', error, { symbol, period: 'annual' })
  })  // Fetch comprehensive analyst data
  const { data: analystOverview, isLoading: analystOverviewLoading, error: analystOverviewError } = useQuery({
    queryKey: ['analystOverview', symbol],
    queryFn: () => api.getAnalystOverview(symbol),
    enabled: !!symbol && tabValue === 4,
    onError: (error) => logger.queryError('analystOverview', error, { symbol })
  })
  // Fetch recent price data only when Price tab is selected - lightweight and fast
  const { data: recentPrices, isLoading: recentPricesLoading, error: recentPricesError } = useQuery({
    queryKey: ['stockPricesRecent', symbol],
    queryFn: () => api.getStockPricesRecent(symbol, 30), // Only 30 days for performance
    enabled: !!symbol && tabValue === 1, // Only load when Price tab is selected
    onError: (error) => logger.queryError('stockPricesRecent', error, { symbol })
  })

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue)
  }

  if (profileLoading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress size={60} />
        </Box>
      </Container>
    )
  }

  if (profileError) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="error">
          Error loading stock data: {profileError.message}
        </Alert>
      </Container>
    )
  }

  if (!profile || profile.length === 0) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="warning">
          Stock not found: {symbol}
        </Alert>
      </Container>
    )
  }

  const stockData = profile[0]
  const currentMetrics = metrics?.[0] || {}
  const currentFinancials = financials?.[0] || {}
  const currentRecs = recommendations?.[0] || {}

  // Price change calculation
  const priceChange = stockData.price - (stockData.previous_close || stockData.price)
  const priceChangePercent = ((priceChange / (stockData.previous_close || stockData.price)) * 100)
  const isPositiveChange = priceChange >= 0

  // Key statistics for display
  const keyStats = [
    { label: 'Market Cap', value: formatCurrency(currentMetrics.market_capitalization) },
    { label: 'P/E Ratio', value: currentMetrics.pe_ratio ? formatNumber(currentMetrics.pe_ratio, 2) : 'N/A' },
    { label: 'EPS', value: currentMetrics.earnings_per_share ? formatCurrency(currentMetrics.earnings_per_share) : 'N/A' },
    { label: 'Dividend Yield', value: currentMetrics.dividend_yield ? formatPercent(currentMetrics.dividend_yield) : 'N/A' },
    { label: 'Book Value', value: currentMetrics.book_value ? formatCurrency(currentMetrics.book_value) : 'N/A' },
    { label: 'Revenue TTM', value: formatCurrency(currentFinancials.revenue) },
    { label: 'Net Income TTM', value: formatCurrency(currentFinancials.net_income) },
    { label: 'Free Cash Flow', value: formatCurrency(currentFinancials.free_cash_flow) }
  ]

  // Financial ratios
  const ratios = [
    { label: 'Current Ratio', value: currentMetrics.current_ratio ? formatNumber(currentMetrics.current_ratio, 2) : 'N/A' },
    { label: 'Debt to Equity', value: currentMetrics.debt_to_equity ? formatNumber(currentMetrics.debt_to_equity, 2) : 'N/A' },
    { label: 'ROE', value: currentMetrics.return_on_equity ? formatPercent(currentMetrics.return_on_equity) : 'N/A' },
    { label: 'ROA', value: currentMetrics.return_on_assets ? formatPercent(currentMetrics.return_on_assets) : 'N/A' },
    { label: 'Gross Margin', value: currentMetrics.gross_margin ? formatPercent(currentMetrics.gross_margin) : 'N/A' },
    { label: 'Operating Margin', value: currentMetrics.operating_margin ? formatPercent(currentMetrics.operating_margin) : 'N/A' },
    { label: 'Net Margin', value: currentMetrics.net_margin ? formatPercent(currentMetrics.net_margin) : 'N/A' },
    { label: 'Asset Turnover', value: currentMetrics.asset_turnover ? formatNumber(currentMetrics.asset_turnover, 2) : 'N/A' }
  ]

  // Analyst recommendation distribution for pie chart
  const recData = currentRecs.strong_buy || currentRecs.buy || currentRecs.hold || currentRecs.sell || currentRecs.strong_sell ? [
    { name: 'Strong Buy', value: currentRecs.strong_buy || 0, color: '#4caf50' },
    { name: 'Buy', value: currentRecs.buy || 0, color: '#8bc34a' },
    { name: 'Hold', value: currentRecs.hold || 0, color: '#ffc107' },
    { name: 'Sell', value: currentRecs.sell || 0, color: '#ff9800' },
    { name: 'Strong Sell', value: currentRecs.strong_sell || 0, color: '#f44336' }
  ].filter(item => item.value > 0) : []

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header Section */}
      <Box mb={4}>
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <Business sx={{ fontSize: 40, color: 'primary.main' }} />
          <Box>
            <Typography variant="h3" component="h1" fontWeight="bold">
              {stockData.symbol}
            </Typography>
            <Typography variant="h6" color="text.secondary" gutterBottom>
              {stockData.company_name}
            </Typography>
          </Box>
        </Box>

        {/* Price and Change */}
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <Typography variant="h4" fontWeight="bold">
            {formatCurrency(stockData.price)}
          </Typography>
          <Box display="flex" alignItems="center" gap={1}>
            {isPositiveChange ? (
              <TrendingUp sx={{ color: 'success.main' }} />
            ) : (
              <TrendingDown sx={{ color: 'error.main' }} />
            )}
            <Typography 
              variant="h6" 
              color={isPositiveChange ? 'success.main' : 'error.main'}
              fontWeight="bold"
            >
              {formatCurrency(priceChange)} ({formatPercent(priceChangePercent / 100)})
            </Typography>
          </Box>
        </Box>

        {/* Industry and Sector Chips */}
        <Box display="flex" gap={1} flexWrap="wrap">
          {stockData.sector && (
            <Chip label={stockData.sector} color="primary" variant="outlined" />
          )}
          {stockData.industry && (
            <Chip label={stockData.industry} color="secondary" variant="outlined" />
          )}
          {stockData.country && (
            <Chip label={stockData.country} variant="outlined" />
          )}
        </Box>
      </Box>

      {/* Company Description */}
      {stockData.description && (
        <Card sx={{ mb: 4 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Company Overview
            </Typography>
            <Typography variant="body1" color="text.secondary">
              {stockData.description}
            </Typography>
          </CardContent>
        </Card>
      )}
      {/* Tab Navigation */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={tabValue} onChange={handleTabChange} aria-label="stock detail tabs">
          <Tab label="Overview" icon={<Analytics />} />
          <Tab label="Price & Volume" icon={<Timeline />} />
          <Tab label="Financials" icon={<AccountBalance />} />
          <Tab label="Ratios" icon={<Timeline />} />
          <Tab label="Recommendations" icon={<TrendingUp />} />
        </Tabs>
      </Box>{/* Tab Panels */}      <TabPanel value={tabValue} index={0}>
        {/* Company Overview and Key Metrics - No Price Chart */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Key Statistics
                </Typography>
                <TableContainer>
                  <Table size="small">
                    <TableBody>
                      {keyStats.map((stat, index) => (
                        <TableRow key={index}>
                          <TableCell component="th" scope="row">
                            {stat.label}
                          </TableCell>
                          <TableCell align="right" sx={{ fontWeight: 'bold' }}>
                            {stat.value}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            {recData.length > 0 && (
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Analyst Recommendations
                  </Typography>
                  <Box height={200}>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={recData}
                          cx="50%"
                          cy="50%"
                          innerRadius={40}
                          outerRadius={80}
                          paddingAngle={5}
                          dataKey="value"
                        >
                          {recData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </Box>
                  <Box mt={2}>
                    {recData.map((rec, index) => (
                      <Box key={index} display="flex" alignItems="center" gap={1} mb={0.5}>
                        <Box 
                          width={12} 
                          height={12} 
                          bgcolor={rec.color} 
                          borderRadius="50%" 
                        />
                        <Typography variant="body2">
                          {rec.name}: {rec.value}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </CardContent>
              </Card>
            )}
          </Grid>
        </Grid>
      </TabPanel>      {/* Price & Volume Tab - Lightweight, no technical indicators */}
      <TabPanel value={tabValue} index={1}>
        {/* Price Chart Section */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Recent Price Chart (30 Days)
                </Typography>
                {recentPricesLoading ? (
                  <Box display="flex" justifyContent="center" alignItems="center" height={300}>
                    <CircularProgress />
                  </Box>
                ) : recentPrices && recentPrices.data && recentPrices.data.data && recentPrices.data.data.length > 0 ? (
                  <Box height={300}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={recentPrices.data.data.reverse()} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="date" 
                          tickFormatter={(value) => new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        />
                        <YAxis 
                          domain={['dataMin - 5', 'dataMax + 5']}
                          tickFormatter={(value) => `$${value.toFixed(2)}`}
                        />
                        <Tooltip 
                          labelFormatter={(value) => new Date(value).toLocaleDateString()}
                          formatter={(value, name) => [`$${value.toFixed(2)}`, name === 'close' ? 'Close Price' : name]}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="close" 
                          stroke="#2196f3" 
                          strokeWidth={2}
                          dot={false}
                          name="Close Price"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </Box>
                ) : (
                  <Box display="flex" justifyContent="center" alignItems="center" height={300}>
                    <Typography color="text.secondary">
                      {recentPricesError ? `Error loading price data: ${recentPricesError.message}` : 'Price chart data not available'}
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Price Summary */}
        {recentPrices && recentPrices.data && recentPrices.data.summary && (
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Price Summary (Last 30 Days)
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="body2" color="text.secondary">Latest Price</Typography>
                        <Typography variant="h6" fontWeight="bold">
                          {formatCurrency(recentPrices.data.summary.latestPrice)}
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="body2" color="text.secondary">Period Return</Typography>
                        <Typography 
                          variant="h6" 
                          fontWeight="bold"
                          color={recentPrices.data.summary.periodReturn >= 0 ? 'success.main' : 'error.main'}
                        >
                          {recentPrices.data.summary.periodReturn.toFixed(2)}%
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="body2" color="text.secondary">Latest Volume</Typography>
                        <Typography variant="h6" fontWeight="bold">
                          {formatNumber(recentPrices.data.summary.latestVolume)}
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="body2" color="text.secondary">Data Points</Typography>
                        <Typography variant="h6" fontWeight="bold">
                          {recentPrices.data.dataPoints} days
                        </Typography>
                      </Box>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}

        {/* OHLCV Data Table */}
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Recent Price & Volume Data (OHLCV)
                </Typography>
                {recentPrices && recentPrices.data && recentPrices.data.data && recentPrices.data.data.length > 0 ? (
                  <TableContainer>
                    <Table size="small">
                      <TableBody>
                        <TableRow>
                          <TableCell><strong>Date</strong></TableCell>
                          <TableCell align="right"><strong>Open</strong></TableCell>
                          <TableCell align="right"><strong>High</strong></TableCell>
                          <TableCell align="right"><strong>Low</strong></TableCell>
                          <TableCell align="right"><strong>Close</strong></TableCell>
                          <TableCell align="right"><strong>Volume</strong></TableCell>
                        </TableRow>
                        {recentPrices.data.data.slice(0, 15).map((dayData, index) => (
                          <TableRow key={index}>
                            <TableCell>{new Date(dayData.date).toLocaleDateString()}</TableCell>
                            <TableCell align="right">{formatCurrency(dayData.open)}</TableCell>
                            <TableCell align="right">{formatCurrency(dayData.high)}</TableCell>
                            <TableCell align="right">{formatCurrency(dayData.low)}</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 'bold' }}>
                              {formatCurrency(dayData.close)}
                            </TableCell>
                            <TableCell align="right">{formatNumber(dayData.volume)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Box display="flex" justifyContent="center" alignItems="center" height={200}>
                    <Typography color="text.secondary">
                      {recentPricesError ? `Error: ${recentPricesError.message}` : 'OHLCV data not available'}
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel><TabPanel value={tabValue} index={2}>
        {(balanceSheetLoading || incomeStatementLoading || cashFlowLoading) ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : (
          <Box>
            {/* Financial Statements Header */}
            <Typography variant="h5" gutterBottom sx={{ mb: 3 }}>
              Financial Statements - {symbol?.toUpperCase()}
            </Typography>
            
            <Grid container spacing={3}>
              {/* Income Statement */}
              <Grid item xs={12} lg={4}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
                      <AccountBalance sx={{ mr: 1 }} />
                      Income Statement (Annual)
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    {incomeStatement?.data?.length > 0 ? (
                      <Box>
                        {incomeStatement.data.slice(0, 3).map((period, periodIndex) => (
                          <Box key={period.date} sx={{ mb: 3 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                              {new Date(period.date).getFullYear()}
                            </Typography>
                            <TableContainer>
                              <Table size="small">
                                <TableBody>
                                  {Object.entries(period.items)
                                    .filter(([key]) => [
                                      'Total Revenue', 'Revenue', 'Gross Profit', 
                                      'Operating Income', 'Net Income', 'Basic EPS'
                                    ].some(item => key.includes(item)))
                                    .slice(0, 6)
                                    .map(([key, value]) => (
                                    <TableRow key={key}>
                                      <TableCell sx={{ py: 0.5, fontSize: '0.875rem' }}>
                                        {key.replace(/([A-Z])/g, ' $1').trim()}
                                      </TableCell>
                                      <TableCell align="right" sx={{ py: 0.5, fontSize: '0.875rem' }}>
                                        {value ? formatCurrency(value, 0) : 'N/A'}
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </TableContainer>
                            {periodIndex < 2 && <Divider sx={{ mt: 2 }} />}
                          </Box>
                        ))}
                      </Box>
                    ) : (
                      <Typography color="text.secondary">No income statement data available</Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Balance Sheet */}
              <Grid item xs={12} lg={4}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
                      <Analytics sx={{ mr: 1 }} />
                      Balance Sheet (Annual)
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    {balanceSheet?.data?.length > 0 ? (
                      <Box>
                        {balanceSheet.data.slice(0, 3).map((period, periodIndex) => (
                          <Box key={period.date} sx={{ mb: 3 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                              {new Date(period.date).getFullYear()}
                            </Typography>
                            <TableContainer>
                              <Table size="small">
                                <TableBody>
                                  {Object.entries(period.items)
                                    .filter(([key]) => [
                                      'Total Assets', 'Current Assets', 'Total Debt', 
                                      'Total Equity', 'Cash', 'Total Liabilities'
                                    ].some(item => key.includes(item)))
                                    .slice(0, 6)
                                    .map(([key, value]) => (
                                    <TableRow key={key}>
                                      <TableCell sx={{ py: 0.5, fontSize: '0.875rem' }}>
                                        {key.replace(/([A-Z])/g, ' $1').trim()}
                                      </TableCell>
                                      <TableCell align="right" sx={{ py: 0.5, fontSize: '0.875rem' }}>
                                        {value ? formatCurrency(value, 0) : 'N/A'}
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </TableContainer>
                            {periodIndex < 2 && <Divider sx={{ mt: 2 }} />}
                          </Box>
                        ))}
                      </Box>
                    ) : (
                      <Typography color="text.secondary">No balance sheet data available</Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Cash Flow Statement */}
              <Grid item xs={12} lg={4}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
                      <Timeline sx={{ mr: 1 }} />
                      Cash Flow (Annual)
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    {cashFlowStatement?.data?.length > 0 ? (
                      <Box>
                        {cashFlowStatement.data.slice(0, 3).map((period, periodIndex) => (
                          <Box key={period.date} sx={{ mb: 3 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                              {new Date(period.date).getFullYear()}
                            </Typography>
                            <TableContainer>
                              <Table size="small">
                                <TableBody>
                                  {Object.entries(period.items)
                                    .filter(([key]) => [
                                      'Operating Cash Flow', 'Free Cash Flow', 'Capital Expenditure',
                                      'Dividends Paid', 'Net Cash Flow', 'Cash From Operations'
                                    ].some(item => key.includes(item)))
                                    .slice(0, 6)
                                    .map(([key, value]) => (
                                    <TableRow key={key}>
                                      <TableCell sx={{ py: 0.5, fontSize: '0.875rem' }}>
                                        {key.replace(/([A-Z])/g, ' $1').trim()}
                                      </TableCell>
                                      <TableCell align="right" sx={{ py: 0.5, fontSize: '0.875rem' }}>
                                        {value ? formatCurrency(value, 0) : 'N/A'}
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </TableContainer>
                            {periodIndex < 2 && <Divider sx={{ mt: 2 }} />}
                          </Box>
                        ))}
                      </Box>
                    ) : (
                      <Typography color="text.secondary">No cash flow data available</Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Financial Statement Summary Charts */}
            <Grid container spacing={3} sx={{ mt: 2 }}>
              {/* Revenue Trend */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>Revenue Trend</Typography>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart data={
                        incomeStatement?.data?.slice(0, 5).reverse().map(period => ({
                          year: new Date(period.date).getFullYear(),
                          revenue: period.items['Total Revenue'] || period.items['Revenue'] || 0
                        })) || []
                      }>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="year" />
                        <YAxis tickFormatter={(value) => formatCurrency(value, 0)} />
                        <Tooltip formatter={(value) => [formatCurrency(value, 0), 'Revenue']} />
                        <Line type="monotone" dataKey="revenue" stroke="#1976d2" strokeWidth={2} />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>

              {/* Net Income Trend */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>Net Income Trend</Typography>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart data={
                        incomeStatement?.data?.slice(0, 5).reverse().map(period => ({
                          year: new Date(period.date).getFullYear(),
                          netIncome: period.items['Net Income'] || 0
                        })) || []
                      }>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="year" />
                        <YAxis tickFormatter={(value) => formatCurrency(value, 0)} />
                        <Tooltip formatter={(value) => [formatCurrency(value, 0), 'Net Income']} />
                        <Line type="monotone" dataKey="netIncome" stroke="#4caf50" strokeWidth={2} />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Box>
        )}
        </TabPanel>

      <TabPanel value={tabValue} index={3}>
        {metricsLoading ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : (
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Financial Ratios
              </Typography>
              <Grid container spacing={2}>
                {ratios.map((ratio, index) => (
                  <Grid item xs={12} sm={6} md={3} key={index}>
                    <Box 
                      p={2} 
                      border={1} 
                      borderColor="divider" 
                      borderRadius={1}
                      textAlign="center"
                    >
                      <Typography variant="body2" color="text.secondary">
                        {ratio.label}
                      </Typography>
                      <Typography variant="h6" fontWeight="bold">
                        {ratio.value}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        )}
        </TabPanel>

      <TabPanel value={tabValue} index={4}>
        {analystOverviewLoading ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : (
          <Box>
            <Typography variant="h5" gutterBottom sx={{ mb: 3 }}>
              Analyst Coverage - {symbol?.toUpperCase()}
            </Typography>
            
            <Grid container spacing={3}>
              {/* Earnings Estimates */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Earnings Estimates
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    {analystOverview?.data?.earnings_estimates?.length > 0 ? (
                      <TableContainer>
                        <Table size="small">
                          <TableBody>
                            {analystOverview.data.earnings_estimates.map((estimate) => (
                              <TableRow key={estimate.period}>
                                <TableCell sx={{ fontWeight: 'bold' }}>
                                  {estimate.period === '0q' ? 'Current Quarter' :
                                   estimate.period === '+1q' ? 'Next Quarter' :
                                   estimate.period === '0y' ? 'Current Year' :
                                   estimate.period === '+1y' ? 'Next Year' : estimate.period}
                                </TableCell>
                                <TableCell align="right">
                                  {estimate.avg_estimate ? formatCurrency(estimate.avg_estimate) : 'N/A'}
                                </TableCell>
                                <TableCell align="right">
                                  <Chip 
                                    label={`${estimate.number_of_analysts || 0} analysts`} 
                                    size="small" 
                                    variant="outlined"
                                  />
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : (
                      <Typography color="text.secondary">No earnings estimates available</Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Revenue Estimates */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Revenue Estimates
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    {analystOverview?.data?.revenue_estimates?.length > 0 ? (
                      <TableContainer>
                        <Table size="small">
                          <TableBody>
                            {analystOverview.data.revenue_estimates.map((estimate) => (
                              <TableRow key={estimate.period}>
                                <TableCell sx={{ fontWeight: 'bold' }}>
                                  {estimate.period === '0q' ? 'Current Quarter' :
                                   estimate.period === '+1q' ? 'Next Quarter' :
                                   estimate.period === '0y' ? 'Current Year' :
                                   estimate.period === '+1y' ? 'Next Year' : estimate.period}
                                </TableCell>
                                <TableCell align="right">
                                  {estimate.avg_estimate ? formatCurrency(estimate.avg_estimate, 0) : 'N/A'}
                                </TableCell>
                                <TableCell align="right">
                                  <Chip 
                                    label={`${estimate.number_of_analysts || 0} analysts`} 
                                    size="small" 
                                    variant="outlined"
                                  />
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : (
                      <Typography color="text.secondary">No revenue estimates available</Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* EPS Revisions */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      EPS Revisions
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    {analystOverview?.data?.eps_revisions?.length > 0 ? (
                      <TableContainer>
                        <Table size="small">
                          <TableBody>
                            {analystOverview.data.eps_revisions.map((revision) => (
                              <TableRow key={revision.period}>
                                <TableCell sx={{ fontWeight: 'bold' }}>
                                  {revision.period === '0q' ? 'Current Quarter' :
                                   revision.period === '+1q' ? 'Next Quarter' :
                                   revision.period === '0y' ? 'Current Year' :
                                   revision.period === '+1y' ? 'Next Year' : revision.period}
                                </TableCell>
                                <TableCell align="right">
                                  <Box display="flex" gap={1}>
                                    <Chip 
                                      label={`↑${revision.up_last30days || 0}`} 
                                      size="small" 
                                      color="success"
                                      variant="outlined"
                                    />
                                    <Chip 
                                      label={`↓${revision.down_last30days || 0}`} 
                                      size="small" 
                                      color="error"
                                      variant="outlined"
                                    />
                                  </Box>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : (
                      <Typography color="text.secondary">No EPS revisions available</Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Growth Estimates */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Growth Estimates
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    {analystOverview?.data?.growth_estimates?.length > 0 ? (
                      <TableContainer>
                        <Table size="small">
                          <TableBody>
                            {analystOverview.data.growth_estimates.map((growth) => (
                              <TableRow key={growth.period}>
                                <TableCell sx={{ fontWeight: 'bold' }}>
                                  {growth.period === '0q' ? 'Current Quarter' :
                                   growth.period === '+1q' ? 'Next Quarter' :
                                   growth.period === '0y' ? 'Current Year' :
                                   growth.period === '+1y' ? 'Next Year' :
                                   growth.period === '+5y' ? 'Next 5 Years' : growth.period}
                                </TableCell>
                                <TableCell align="right">
                                  {growth.stock_trend ? formatPercent(growth.stock_trend / 100) : 'N/A'}
                                </TableCell>
                                <TableCell align="right" sx={{ fontSize: '0.75rem', color: 'text.secondary' }}>
                                  vs Index: {growth.index_trend ? formatPercent(growth.index_trend / 100) : 'N/A'}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : (
                      <Typography color="text.secondary">No growth estimates available</Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Analyst Recommendations */}
              <Grid item xs={12}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Analyst Recommendations
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    {analystOverview?.data?.recommendations?.length > 0 ? (
                      <Box>
                        {analystOverview.data.recommendations.slice(0, 3).map((rec, index) => (
                          <Box key={index} sx={{ mb: 2 }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                              {new Date(rec.collected_date).toLocaleDateString()} - {rec.period}
                            </Typography>
                            <Grid container spacing={2}>
                              <Grid item>
                                <Chip 
                                  label={`Strong Buy: ${rec.strong_buy || 0}`} 
                                  color="success"
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                              <Grid item>
                                <Chip 
                                  label={`Buy: ${rec.buy || 0}`} 
                                  color="success"
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                              <Grid item>
                                <Chip 
                                  label={`Hold: ${rec.hold || 0}`} 
                                  color="warning"
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                              <Grid item>
                                <Chip 
                                  label={`Sell: ${rec.sell || 0}`} 
                                  color="error"
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                              <Grid item>
                                <Chip 
                                  label={`Strong Sell: ${rec.strong_sell || 0}`} 
                                  color="error"
                                  variant="outlined"
                                  size="small"
                                />
                              </Grid>
                            </Grid>
                            {index < 2 && <Divider sx={{ mt: 2 }} />}
                          </Box>
                        ))}
                      </Box>
                    ) : (
                      <Typography color="text.secondary">No analyst recommendations available</Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Earnings History */}
              <Grid item xs={12}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Earnings History
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                    
                    {analystOverview?.data?.earnings_history?.length > 0 ? (
                      <TableContainer>
                        <Table>
                          <TableBody>
                            {analystOverview.data.earnings_history.slice(0, 8).map((history) => (
                              <TableRow key={history.quarter}>
                                <TableCell sx={{ fontWeight: 'bold' }}>
                                  {new Date(history.quarter).toLocaleDateString()}
                                </TableCell>
                                <TableCell align="right">
                                  Actual: {history.eps_actual ? formatCurrency(history.eps_actual) : 'N/A'}
                                </TableCell>
                                <TableCell align="right">
                                  Estimate: {history.eps_estimate ? formatCurrency(history.eps_estimate) : 'N/A'}
                                </TableCell>
                                <TableCell align="right">
                                  <Chip 
                                    label={history.surprise_percent ? `${formatPercent(history.surprise_percent / 100)} surprise` : 'N/A'}
                                    color={history.surprise_percent > 0 ? 'success' : history.surprise_percent < 0 ? 'error' : 'default'}
                                    size="small"
                                    variant="outlined"
                                  />
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : (
                      <Typography color="text.secondary">No earnings history available</Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Box>
        )}
      </TabPanel>
    </Container>
  )
}

export default StockDetail
