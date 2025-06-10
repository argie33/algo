import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Tabs,
  Tab,
  LinearProgress,
  Alert,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip
} from '@mui/material'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell, Legend } from 'recharts'

import { 
  getMarketOverview, 
  getValuationMetrics, 
  getGrowthMetrics, 
  getDividendMetrics, 
  getFinancialStrengthMetrics 
} from '../services/api'
import { formatCurrency, formatNumber, formatPercentage, getChangeColor, getMarketCapCategory } from '../utils/formatters'

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658', '#ff7c7c']

const TabPanel = ({ children, value, index, ...other }) => (
  <div
    role="tabpanel"
    hidden={value !== index}
    id={`market-tabpanel-${index}`}
    aria-labelledby={`market-tab-${index}`}
    {...other}
  >
    {value === index && (
      <Box sx={{ pt: 3 }}>
        {children}
      </Box>
    )}
  </div>
)

const MetricTable = ({ data, columns, title }) => (
  <Card>
    <CardContent>
      <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
        {title}
      </Typography>
      <TableContainer component={Paper} elevation={0}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ backgroundColor: 'grey.50' }}>
              {columns.map((col) => (
                <TableCell key={col.key} sx={{ fontWeight: 600 }}>
                  {col.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.slice(0, 10).map((item, index) => (
              <TableRow key={item.ticker || index} hover>
                {columns.map((col) => (
                  <TableCell key={col.key}>
                    {col.render ? col.render(item[col.key], item) : item[col.key] || 'N/A'}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </CardContent>
  </Card>
)

function MarketOverview() {
  const [tabValue, setTabValue] = useState(0)

  const { data: marketData, isLoading: marketLoading, error: marketError } = useQuery(
    'market-overview',
    getMarketOverview,
    { refetchInterval: 60000 }
  )

  const { data: valuationData, isLoading: valuationLoading } = useQuery(
    'valuation-metrics',
    () => getValuationMetrics({ limit: 20 }),
    { enabled: tabValue === 1 }
  )

  const { data: growthData, isLoading: growthLoading } = useQuery(
    'growth-metrics',
    () => getGrowthMetrics({ limit: 20 }),
    { enabled: tabValue === 2 }
  )

  const { data: dividendData, isLoading: dividendLoading } = useQuery(
    'dividend-metrics',
    () => getDividendMetrics({ limit: 20 }),
    { enabled: tabValue === 3 }
  )

  const { data: strengthData, isLoading: strengthLoading } = useQuery(
    'strength-metrics',
    () => getFinancialStrengthMetrics({ limit: 20 }),
    { enabled: tabValue === 4 }
  )

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue)
  }

  if (marketError) {
    return (
      <Box>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
          Market Overview
        </Typography>
        <Alert severity="error">
          Failed to load market data: {marketError.message}
        </Alert>
      </Box>
    )
  }

  const overview = marketData?.data?.overview
  const sectorPerformance = marketData?.data?.sector_performance || []

  // Prepare chart data
  const sectorChartData = sectorPerformance.slice(0, 8).map(sector => ({
    name: sector.sector?.substring(0, 15) || 'Other',
    performance: parseFloat(sector.avg_change) || 0,
    marketCap: parseFloat(sector.sector_market_cap) || 0,
    stocks: parseInt(sector.stock_count) || 0
  }))

  const valuationColumns = [
    { key: 'ticker', label: 'Ticker' },
    { key: 'short_name', label: 'Company', render: (val) => val?.substring(0, 30) + (val?.length > 30 ? '...' : '') },
    { key: 'sector', label: 'Sector', render: (val) => <Chip label={val || 'Other'} size="small" variant="outlined" /> },
    { key: 'trailing_pe', label: 'P/E', render: (val) => formatNumber(val) },
    { key: 'price_to_book', label: 'P/B', render: (val) => formatNumber(val) },
    { key: 'market_cap', label: 'Market Cap', render: (val) => formatCurrency(val, 0) }
  ]

  const growthColumns = [
    { key: 'ticker', label: 'Ticker' },
    { key: 'short_name', label: 'Company', render: (val) => val?.substring(0, 30) + (val?.length > 30 ? '...' : '') },
    { key: 'revenue_growth_pct', label: 'Revenue Growth', render: (val) => formatPercentage(val) },
    { key: 'earnings_growth_pct', label: 'Earnings Growth', render: (val) => formatPercentage(val) },
    { key: 'return_on_equity_pct', label: 'ROE', render: (val) => formatPercentage(val) },
    { key: 'profit_margin_pct', label: 'Profit Margin', render: (val) => formatPercentage(val) }
  ]

  const dividendColumns = [
    { key: 'ticker', label: 'Ticker' },
    { key: 'short_name', label: 'Company', render: (val) => val?.substring(0, 30) + (val?.length > 30 ? '...' : '') },
    { key: 'dividend_yield', label: 'Yield', render: (val) => formatPercentage(val) },
    { key: 'dividend_rate', label: 'Rate', render: (val) => formatCurrency(val) },
    { key: 'trailing_pe', label: 'P/E', render: (val) => formatNumber(val) },
    { key: 'market_cap', label: 'Market Cap', render: (val) => formatCurrency(val, 0) }
  ]

  const strengthColumns = [
    { key: 'ticker', label: 'Ticker' },
    { key: 'short_name', label: 'Company', render: (val) => val?.substring(0, 30) + (val?.length > 30 ? '...' : '') },
    { key: 'current_ratio', label: 'Current Ratio', render: (val) => formatNumber(val) },
    { key: 'debt_to_equity', label: 'Debt/Equity', render: (val) => formatNumber(val) },
    { key: 'return_on_equity_pct', label: 'ROE', render: (val) => formatPercentage(val) },
    { key: 'free_cashflow', label: 'FCF', render: (val) => formatCurrency(val, 0) }
  ]

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
        Market Overview
      </Typography>

      {marketLoading && <LinearProgress sx={{ mb: 2 }} />}

      {/* Sector Performance Chart */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} lg={8}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Sector Performance Today
              </Typography>
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={sectorChartData} margin={{ top: 5, right: 30, left: 20, bottom: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="name" 
                    tick={{ fontSize: 11 }}
                    angle={-45}
                    textAnchor="end"
                    height={80}
                  />
                  <YAxis 
                    tick={{ fontSize: 11 }}
                    tickFormatter={(value) => `${value}%`}
                  />
                  <Tooltip 
                    formatter={(value, name) => [
                      `${value.toFixed(2)}%`, 
                      'Avg Change'
                    ]}
                    labelFormatter={(label) => `Sector: ${label}`}
                    contentStyle={{ 
                      backgroundColor: 'rgba(255, 255, 255, 0.95)',
                      border: '1px solid #ccc',
                      borderRadius: '8px'
                    }}
                  />
                  <Bar 
                    dataKey="performance" 
                    fill={(entry) => entry > 0 ? '#2e7d32' : '#d32f2f'}
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={4}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Cap Distribution
              </Typography>
              <ResponsiveContainer width="100%" height={320}>
                <PieChart>
                  <Pie
                    data={sectorChartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={120}
                    paddingAngle={5}
                    dataKey="marketCap"
                  >
                    {sectorChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip 
                    formatter={(value) => [formatCurrency(value, 0), 'Market Cap']}
                  />
                  <Legend 
                    wrapperStyle={{ fontSize: '12px' }}
                    iconSize={8}
                  />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs for different metrics */}
      <Card>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={handleTabChange} aria-label="market metrics tabs">
            <Tab label="Overview" />
            <Tab label="Valuation" />
            <Tab label="Growth" />
            <Tab label="Dividends" />
            <Tab label="Financial Strength" />
          </Tabs>
        </Box>

        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Typography variant="h4" color="primary" sx={{ fontWeight: 600 }}>
                    {formatNumber(overview?.total_stocks || 0, 0)}
                  </Typography>
                  <Typography variant="subtitle1" color="text.secondary">
                    Total Stocks
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Typography variant="h4" color="success.main" sx={{ fontWeight: 600 }}>
                    {formatNumber(overview?.gainers || 0, 0)}
                  </Typography>
                  <Typography variant="subtitle1" color="text.secondary">
                    Gainers Today
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Typography variant="h4" color="error.main" sx={{ fontWeight: 600 }}>
                    {formatNumber(overview?.losers || 0, 0)}
                  </Typography>
                  <Typography variant="subtitle1" color="text.secondary">
                    Losers Today
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {valuationLoading ? (
            <LinearProgress />
          ) : (
            <MetricTable 
              data={valuationData?.data?.data}
              columns={valuationColumns}
              title="Best Value Stocks (Low P/E Ratio)"
            />
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          {growthLoading ? (
            <LinearProgress />
          ) : (
            <MetricTable 
              data={growthData?.data?.data}
              columns={growthColumns}
              title="High Growth Stocks"
            />
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          {dividendLoading ? (
            <LinearProgress />
          ) : (
            <MetricTable 
              data={dividendData?.data?.data}
              columns={dividendColumns}
              title="High Dividend Yield Stocks"
            />
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={4}>
          {strengthLoading ? (
            <LinearProgress />
          ) : (
            <MetricTable 
              data={strengthData?.data?.data}
              columns={strengthColumns}
              title="Financially Strong Stocks"
            />
          )}
        </TabPanel>
      </Card>
    </Box>
  )
}

export default MarketOverview
