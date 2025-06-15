import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TextField,
  Button,
  Chip,
  CircularProgress,
  Alert,
  Divider,
  ToggleButton,
  ToggleButtonGroup
} from '@mui/material'
import {
  AccountBalance,
  Assessment,
  Timeline,
  TrendingUp,
  Search,
  BusinessCenter
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
  Bar
} from 'recharts'
import {
  getBalanceSheet,
  getIncomeStatement,
  getCashFlowStatement,
  getFinancialStatements,
  getTickerEarningsEstimates,
  getTickerRevenueEstimates,
  getTickerEarningsHistory,
  getTickerEpsRevisions,
  getTickerEpsTrend,
  getTickerGrowthEstimates,
  getAnalystOverview
} from '../services/api'
import { formatCurrency, formatPercentage, formatNumber } from '../utils/formatters'

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`financial-tabpanel-${index}`}
      aria-labelledby={`financial-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  )
}

function FinancialData() {
  const [tabValue, setTabValue] = useState(0)
  const [ticker, setTicker] = useState('AAPL')
  const [period, setPeriod] = useState('annual')
  const [searchTicker, setSearchTicker] = useState('')

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue)
  }

  const handleSearch = () => {
    if (searchTicker.trim()) {
      setTicker(searchTicker.trim().toUpperCase())
    }
  }

  const handlePeriodChange = (event, newPeriod) => {
    if (newPeriod !== null) {
      setPeriod(newPeriod)
    }
  }

  // Comprehensive financial data queries
  const { data: balanceSheet, isLoading: balanceSheetLoading, error: balanceSheetError } = useQuery({
    queryKey: ['balanceSheet', ticker, period],
    queryFn: () => getBalanceSheet(ticker, period),
    enabled: !!ticker && tabValue === 0
  })

  const { data: incomeStatement, isLoading: incomeStatementLoading, error: incomeStatementError } = useQuery({
    queryKey: ['incomeStatement', ticker, period],
    queryFn: () => getIncomeStatement(ticker, period),
    enabled: !!ticker && tabValue === 1
  })

  const { data: cashFlowStatement, isLoading: cashFlowLoading, error: cashFlowError } = useQuery({
    queryKey: ['cashFlowStatement', ticker, period],
    queryFn: () => getCashFlowStatement(ticker, period),
    enabled: !!ticker && tabValue === 2
  })

  const { data: analystOverview, isLoading: analystOverviewLoading, error: analystError } = useQuery({
    queryKey: ['analystOverview', ticker],
    queryFn: () => getAnalystOverview(ticker),
    enabled: !!ticker && tabValue === 3
  })

  const renderFinancialTable = (data, title, icon) => {
    if (!data?.data || data.data.length === 0) {
      return (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
              {icon}
              <Box sx={{ ml: 1 }}>{title}</Box>
            </Typography>
            <Alert severity="info">No {title.toLowerCase()} data available for {ticker}</Alert>
          </CardContent>
        </Card>
      )
    }

    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
            {icon}
            <Box sx={{ ml: 1 }}>{title} - {ticker}</Box>
          </Typography>
          <Divider sx={{ mb: 2 }} />
          
          <Grid container spacing={3}>
            {data.data.slice(0, 5).map((period, index) => (
              <Grid item xs={12} md={6} lg={4} key={period.date}>
                <Card variant="outlined">
                  <CardContent sx={{ p: 2 }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mb: 2 }}>
                      {new Date(period.date).getFullYear()}
                    </Typography>
                    <TableContainer>
                      <Table size="small">
                        <TableBody>
                          {Object.entries(period.items)
                            .slice(0, 10)
                            .map(([key, value]) => (
                            <TableRow key={key}>
                              <TableCell sx={{ py: 0.5, fontSize: '0.875rem', border: 'none' }}>
                                {key.replace(/([A-Z])/g, ' $1').trim()}
                              </TableCell>
                              <TableCell align="right" sx={{ py: 0.5, fontSize: '0.875rem', fontWeight: 'bold', border: 'none' }}>
                                {value ? formatCurrency(value, 0) : 'N/A'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          {/* Trend Chart */}
          <Box sx={{ mt: 4 }}>
            <Typography variant="h6" gutterBottom>Trend Analysis</Typography>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={
                data.data.slice(0, 5).reverse().map(period => {
                  const items = period.items
                  const firstItem = Object.entries(items)[0]
                  return {
                    year: new Date(period.date).getFullYear(),
                    value: firstItem ? firstItem[1] : 0,
                    name: firstItem ? firstItem[0] : 'N/A'
                  }
                })
              }>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis tickFormatter={(value) => formatCurrency(value, 0)} />
                <Tooltip 
                  formatter={(value, name) => [formatCurrency(value, 0), 'Value']}
                  labelFormatter={(year) => `Year: ${year}`}
                />
                <Line type="monotone" dataKey="value" stroke="#1976d2" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </Box>
        </CardContent>
      </Card>
    )
  }

  const renderAnalystData = () => {
    if (analystOverviewLoading) {
      return (
        <Box display="flex" justifyContent="center" p={4}>
          <CircularProgress />
        </Box>
      )
    }

    if (analystError) {
      return (
        <Alert severity="error">
          Failed to load analyst data: {analystError.message}
        </Alert>
      )
    }

    const data = analystOverview?.data
    
    return (
      <Grid container spacing={3}>
        {/* Earnings Estimates */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Earnings Estimates</Typography>
              <Divider sx={{ mb: 2 }} />
              {data?.earnings_estimates?.length > 0 ? (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Period</TableCell>
                        <TableCell align="right">Avg Estimate</TableCell>
                        <TableCell align="right">Analysts</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {data.earnings_estimates.map((estimate) => (
                        <TableRow key={estimate.period}>
                          <TableCell>
                            {estimate.period === '0q' ? 'Current Quarter' :
                             estimate.period === '+1q' ? 'Next Quarter' :
                             estimate.period === '0y' ? 'Current Year' :
                             estimate.period === '+1y' ? 'Next Year' : estimate.period}
                          </TableCell>
                          <TableCell align="right">
                            {estimate.avg_estimate ? formatCurrency(estimate.avg_estimate) : 'N/A'}
                          </TableCell>
                          <TableCell align="right">
                            {estimate.number_of_analysts || 0}
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
              <Typography variant="h6" gutterBottom>Revenue Estimates</Typography>
              <Divider sx={{ mb: 2 }} />
              {data?.revenue_estimates?.length > 0 ? (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Period</TableCell>
                        <TableCell align="right">Avg Estimate</TableCell>
                        <TableCell align="right">Growth</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {data.revenue_estimates.map((estimate) => (
                        <TableRow key={estimate.period}>
                          <TableCell>
                            {estimate.period === '0q' ? 'Current Quarter' :
                             estimate.period === '+1q' ? 'Next Quarter' :
                             estimate.period === '0y' ? 'Current Year' :
                             estimate.period === '+1y' ? 'Next Year' : estimate.period}
                          </TableCell>
                          <TableCell align="right">
                            {estimate.avg_estimate ? formatCurrency(estimate.avg_estimate, 0) : 'N/A'}
                          </TableCell>
                          <TableCell align="right">
                            {estimate.growth ? formatPercentage(estimate.growth / 100) : 'N/A'}
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

        {/* Earnings History */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Earnings History</Typography>
              <Divider sx={{ mb: 2 }} />
              {data?.earnings_history?.length > 0 ? (
                <Box>
                  <TableContainer>
                    <Table>
                      <TableHead>
                        <TableRow>
                          <TableCell>Quarter</TableCell>
                          <TableCell align="right">Actual EPS</TableCell>
                          <TableCell align="right">Estimated EPS</TableCell>
                          <TableCell align="right">Difference</TableCell>
                          <TableCell align="right">Surprise %</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {data.earnings_history.slice(0, 8).map((history) => (
                          <TableRow key={history.quarter}>
                            <TableCell>
                              {new Date(history.quarter).toLocaleDateString()}
                            </TableCell>
                            <TableCell align="right">
                              {history.eps_actual ? formatCurrency(history.eps_actual) : 'N/A'}
                            </TableCell>
                            <TableCell align="right">
                              {history.eps_estimate ? formatCurrency(history.eps_estimate) : 'N/A'}
                            </TableCell>
                            <TableCell align="right">
                              {history.eps_difference ? formatCurrency(history.eps_difference) : 'N/A'}
                            </TableCell>
                            <TableCell align="right">
                              <Chip 
                                label={history.surprise_percent ? formatPercentage(history.surprise_percent / 100) : 'N/A'}
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

                  {/* Earnings Surprise Chart */}
                  <Box sx={{ mt: 3 }}>
                    <Typography variant="h6" gutterBottom>Earnings Surprise Trend</Typography>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={
                        data.earnings_history.slice(0, 8).reverse().map(history => ({
                          quarter: new Date(history.quarter).toLocaleDateString('en-US', { year: 'numeric', month: 'short' }),
                          surprise: history.surprise_percent || 0,
                          actual: history.eps_actual || 0,
                          estimate: history.eps_estimate || 0
                        }))
                      }>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="quarter" />
                        <YAxis />
                        <Tooltip 
                          formatter={(value, name) => [
                            name === 'surprise' ? `${value.toFixed(2)}%` : formatCurrency(value),
                            name === 'surprise' ? 'Surprise %' : name === 'actual' ? 'Actual EPS' : 'Estimated EPS'
                          ]}
                        />
                        <Bar dataKey="surprise" fill="#1976d2" />
                      </BarChart>
                    </ResponsiveContainer>
                  </Box>
                </Box>
              ) : (
                <Typography color="text.secondary">No earnings history available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    )
  }

  return (
    <Container maxWidth="xl">
      <Box sx={{ py: 3 }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 600 }}>
          Financial Data Analysis
        </Typography>
        
        {/* Search Section */}
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  label="Enter Stock Symbol"
                  value={searchTicker}
                  onChange={(e) => setSearchTicker(e.target.value.toUpperCase())}
                  onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                  placeholder="e.g., AAPL, MSFT, GOOGL"
                  InputProps={{
                    startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />
                  }}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <ToggleButtonGroup
                  value={period}
                  exclusive
                  onChange={handlePeriodChange}
                  size="small"
                >
                  <ToggleButton value="annual">Annual</ToggleButton>
                  <ToggleButton value="quarterly">Quarterly</ToggleButton>
                  <ToggleButton value="ttm">TTM</ToggleButton>
                </ToggleButtonGroup>
              </Grid>
              <Grid item xs={12} md={4}>
                <Button
                  variant="contained"
                  onClick={handleSearch}
                  startIcon={<Search />}
                  disabled={!searchTicker.trim()}
                >
                  Analyze
                </Button>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* Tabs */}
        <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
          <Tabs value={tabValue} onChange={handleTabChange}>
            <Tab label="Balance Sheet" icon={<AccountBalance />} />
            <Tab label="Income Statement" icon={<Assessment />} />
            <Tab label="Cash Flow" icon={<Timeline />} />
            <Tab label="Analyst Data" icon={<TrendingUp />} />
          </Tabs>
        </Box>

        {/* Tab Panels */}
        <TabPanel value={tabValue} index={0}>
          {balanceSheetLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : balanceSheetError ? (
            <Alert severity="error">Failed to load balance sheet: {balanceSheetError.message}</Alert>
          ) : (
            renderFinancialTable(balanceSheet, 'Balance Sheet', <AccountBalance />)
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {incomeStatementLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : incomeStatementError ? (
            <Alert severity="error">Failed to load income statement: {incomeStatementError.message}</Alert>
          ) : (
            renderFinancialTable(incomeStatement, 'Income Statement', <Assessment />)
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          {cashFlowLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : cashFlowError ? (
            <Alert severity="error">Failed to load cash flow: {cashFlowError.message}</Alert>
          ) : (
            renderFinancialTable(cashFlowStatement, 'Cash Flow Statement', <Timeline />)
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          {renderAnalystData()}
        </TabPanel>
      </Box>
    </Container>
  )
}

export default FinancialData
