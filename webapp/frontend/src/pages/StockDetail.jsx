import React from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
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
import { formatCurrency, formatPercent, formatNumber } from '../utils/formatters'

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
  const { symbol } = useParams()
  const [tabValue, setTabValue] = React.useState(0)

  // Fetch stock profile data
  const { data: profile, isLoading: profileLoading, error: profileError } = useQuery({
    queryKey: ['stockProfile', symbol],
    queryFn: () => api.getStockProfile(symbol),
    enabled: !!symbol
  })

  // Fetch key metrics
  const { data: metrics, isLoading: metricsLoading } = useQuery({
    queryKey: ['stockMetrics', symbol],
    queryFn: () => api.getStockMetrics(symbol),
    enabled: !!symbol
  })

  // Fetch financial data
  const { data: financials, isLoading: financialsLoading } = useQuery({
    queryKey: ['stockFinancials', symbol],
    queryFn: () => api.getStockFinancials(symbol),
    enabled: !!symbol
  })

  // Fetch analyst recommendations
  const { data: recommendations, isLoading: recLoading } = useQuery({
    queryKey: ['stockRecommendations', symbol],
    queryFn: () => api.getAnalystRecommendations(symbol),
    enabled: !!symbol
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
          <Tab label="Financials" icon={<AccountBalance />} />
          <Tab label="Ratios" icon={<Timeline />} />
          <Tab label="Recommendations" icon={<TrendingUp />} />
        </Tabs>
      </Box>

      {/* Tab Panels */}
      <TabPanel value={tabValue} index={0}>
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
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        {financialsLoading ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : (
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Income Statement (TTM)
                  </Typography>
                  <TableContainer>
                    <Table size="small">
                      <TableBody>
                        <TableRow>
                          <TableCell>Revenue</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 'bold' }}>
                            {formatCurrency(currentFinancials.revenue)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Gross Profit</TableCell>
                          <TableCell align="right">
                            {formatCurrency(currentFinancials.gross_profit)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Operating Income</TableCell>
                          <TableCell align="right">
                            {formatCurrency(currentFinancials.operating_income)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Net Income</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 'bold' }}>
                            {formatCurrency(currentFinancials.net_income)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>EPS</TableCell>
                          <TableCell align="right">
                            {formatCurrency(currentFinancials.eps)}
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Cash Flow (TTM)
                  </Typography>
                  <TableContainer>
                    <Table size="small">
                      <TableBody>
                        <TableRow>
                          <TableCell>Operating Cash Flow</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 'bold' }}>
                            {formatCurrency(currentFinancials.operating_cash_flow)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Capital Expenditure</TableCell>
                          <TableCell align="right">
                            {formatCurrency(currentFinancials.capital_expenditure)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Free Cash Flow</TableCell>
                          <TableCell align="right" sx={{ fontWeight: 'bold' }}>
                            {formatCurrency(currentFinancials.free_cash_flow)}
                          </TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell>Dividends Paid</TableCell>
                          <TableCell align="right">
                            {formatCurrency(currentFinancials.dividends_paid)}
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
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

      <TabPanel value={tabValue} index={3}>
        {recLoading ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : (
          <Grid container spacing={3}>
            <Grid item xs={12} md={8}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Analyst Recommendations Summary
                  </Typography>
                  {recData.length > 0 ? (
                    <TableContainer>
                      <Table>
                        <TableBody>
                          {recData.map((rec, index) => (
                            <TableRow key={index}>
                              <TableCell>
                                <Box display="flex" alignItems="center" gap={1}>
                                  <Box 
                                    width={16} 
                                    height={16} 
                                    bgcolor={rec.color} 
                                    borderRadius={1} 
                                  />
                                  {rec.name}
                                </Box>
                              </TableCell>
                              <TableCell align="right" sx={{ fontWeight: 'bold' }}>
                                {rec.value}
                              </TableCell>
                              <TableCell align="right" width="200px">
                                <LinearProgress
                                  variant="determinate"
                                  value={(rec.value / Math.max(...recData.map(r => r.value))) * 100}
                                  sx={{ 
                                    height: 8, 
                                    borderRadius: 1,
                                    '& .MuiLinearProgress-bar': {
                                      backgroundColor: rec.color
                                    }
                                  }}
                                />
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  ) : (
                    <Typography color="text.secondary">
                      No analyst recommendations available
                    </Typography>
                  )}
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={4}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Recommendation Score
                  </Typography>
                  {currentRecs.recommendation_score && (
                    <Box textAlign="center" p={2}>
                      <Typography variant="h3" fontWeight="bold" color="primary.main">
                        {formatNumber(currentRecs.recommendation_score, 1)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Average Score (1-5 scale)
                      </Typography>
                    </Box>
                  )}
                  
                  {currentRecs.target_price && (
                    <Box mt={3}>
                      <Typography variant="subtitle1" gutterBottom>
                        Price Target
                      </Typography>
                      <Typography variant="h5" fontWeight="bold">
                        {formatCurrency(currentRecs.target_price)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Upside: {formatPercent((currentRecs.target_price - stockData.price) / stockData.price)}
                      </Typography>
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}
      </TabPanel>
    </Container>
  )
}

export default StockDetail
