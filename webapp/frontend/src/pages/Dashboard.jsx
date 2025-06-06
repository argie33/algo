import React from 'react'
import { useQuery } from 'react-query'
import {
  Grid,
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  LinearProgress,
  Alert,
  Paper,
  List,
  ListItem,
  ListItemText,
  Divider
} from '@mui/material'
import {
  TrendingUp,
  TrendingDown,
  Business,
  AttachMoney,
  Assessment
} from '@mui/icons-material'
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts'

import { getMarketOverview } from '../services/api'
import { formatCurrency, formatNumber, formatPercentage, getChangeColor, getChangeIcon } from '../utils/formatters'

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d']

const MetricCard = ({ title, value, subtitle, icon, trend, color = 'primary' }) => (
  <Card sx={{ height: '100%' }}>
    <CardContent>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <Box sx={{ color: `${color}.main`, mr: 2 }}>
          {icon}
        </Box>
        <Typography variant="h6" color="text.secondary">
          {title}
        </Typography>
      </Box>
      <Typography variant="h4" sx={{ mb: 1, fontWeight: 600 }}>
        {value}
      </Typography>
      {subtitle && (
        <Typography variant="body2" color="text.secondary">
          {subtitle}
        </Typography>
      )}
      {trend && (
        <Box sx={{ display: 'flex', alignItems: 'center', mt: 1 }}>
          <Typography 
            variant="body2" 
            sx={{ 
              color: getChangeColor(trend),
              fontWeight: 500
            }}
          >
            {getChangeIcon(trend)} {formatPercentage(trend)}
          </Typography>
        </Box>
      )}
    </CardContent>
  </Card>
)

const StockListCard = ({ title, stocks, showChange = false }) => (
  <Card sx={{ height: '100%' }}>
    <CardContent>
      <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
        {title}
      </Typography>
      <List dense>
        {stocks?.slice(0, 5).map((stock, index) => (
          <React.Fragment key={stock.ticker}>
            {index > 0 && <Divider />}
            <ListItem sx={{ px: 0 }}>
              <ListItemText
                primary={
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Box>
                      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        {stock.ticker}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {stock.short_name}
                      </Typography>
                    </Box>
                    {showChange && (
                      <Chip
                        label={formatPercentage(stock.regular_market_change_percent)}
                        size="small"
                        sx={{
                          backgroundColor: getChangeColor(stock.regular_market_change_percent) + '20',
                          color: getChangeColor(stock.regular_market_change_percent),
                          fontWeight: 600
                        }}
                      />
                    )}
                  </Box>
                }
              />
            </ListItem>
          </React.Fragment>
        ))}
      </List>
    </CardContent>
  </Card>
)

const Dashboard = () => {
  const { data: marketData, isLoading, error } = useQuery(
    'market-overview',
    getMarketOverview,
    {
      refetchInterval: 60000, // Refetch every minute
    }
  )

  if (isLoading) {
    return (
      <Box>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
          Market Dashboard
        </Typography>
        <LinearProgress />
      </Box>
    )
  }

  if (error) {
    return (
      <Box>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
          Market Dashboard
        </Typography>
        <Alert severity="error">
          Failed to load market data: {error.message}
        </Alert>
      </Box>
    )
  }

  const overview = marketData?.data?.overview
  const topGainers = marketData?.data?.top_gainers
  const topLosers = marketData?.data?.top_losers
  const sectorPerformance = marketData?.data?.sector_performance

  // Prepare sector chart data
  const sectorChartData = sectorPerformance?.slice(0, 6).map(sector => ({
    name: sector.sector?.replace(/[&,]/g, '') || 'Other',
    value: parseFloat(sector.avg_change) || 0,
    stockCount: parseInt(sector.stock_count) || 0
  })) || []

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
        Market Dashboard
      </Typography>

      {/* Key Metrics */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Total Stocks"
            value={formatNumber(overview?.total_stocks || 0, 0)}
            icon={<Business />}
            color="primary"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Market Cap"
            value={formatCurrency(overview?.total_market_cap || 0, 0)}
            icon={<AttachMoney />}
            color="success"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Gainers"
            value={formatNumber(overview?.gainers || 0, 0)}
            subtitle={`${formatNumber(overview?.losers || 0, 0)} losers`}
            icon={<TrendingUp />}
            color="success"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Avg P/E Ratio"
            value={formatNumber(overview?.avg_pe || 0)}
            subtitle={`Avg P/B: ${formatNumber(overview?.avg_pb || 0)}`}
            icon={<Assessment />}
            color="info"
          />
        </Grid>
      </Grid>

      {/* Charts and Lists */}
      <Grid container spacing={3}>
        {/* Sector Performance Chart */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Sector Performance Today
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={sectorChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="name" 
                    tick={{ fontSize: 12 }}
                    angle={-45}
                    textAnchor="end"
                    height={80}
                  />
                  <YAxis 
                    tick={{ fontSize: 12 }}
                    tickFormatter={(value) => `${value}%`}
                  />
                  <Tooltip 
                    formatter={(value, name) => [`${value.toFixed(2)}%`, 'Avg Change']}
                    labelFormatter={(label) => `Sector: ${label}`}
                  />
                  <Bar 
                    dataKey="value" 
                    fill="#1976d2"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Market Distribution */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: 400 }}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Sector Distribution (by Stock Count)
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={sectorChartData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={5}
                    dataKey="stockCount"
                  >
                    {sectorChartData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip 
                    formatter={(value, name) => [`${value} stocks`, 'Count']}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Top Gainers */}
        <Grid item xs={12} md={6}>
          <StockListCard
            title="🚀 Top Gainers Today"
            stocks={topGainers}
            showChange={true}
          />
        </Grid>

        {/* Top Losers */}
        <Grid item xs={12} md={6}>
          <StockListCard
            title="📉 Top Losers Today"
            stocks={topLosers}
            showChange={true}
          />
        </Grid>
      </Grid>
    </Box>
  )
}

export default Dashboard
