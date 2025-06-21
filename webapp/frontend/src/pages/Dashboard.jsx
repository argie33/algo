import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createComponentLogger } from '../utils/errorLogger'
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

// Create component-specific logger
const logger = createComponentLogger('Dashboard');

const Dashboard = () => {
  const { data: marketData, isLoading, error } = useQuery(
    'market-overview',
    async () => {
      try {
        const result = await getMarketOverview();
        logger.success('getMarketOverview', result);
        return result;
      } catch (err) {
        logger.error('getMarketOverview', err);
        throw err;
      }
    },
    {
      refetchInterval: 60000, // Refetch every minute
      onError: (err) => logger.queryError('market-overview', err)
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

  // Use available backend fields
  const rawData = marketData?.data || marketData || {};
  console.log('Dashboard marketData:', marketData);

  const marketBreadth = rawData.market_breadth || {};
  const marketCap = rawData.market_cap || {};
  const sentimentIndicators = rawData.sentiment_indicators || {};
  // No sector performance or top gainers/losers available

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
            value={formatNumber(marketBreadth.total_stocks || 0, 0)}
            icon={<Business />}
            color="primary"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Market Cap"
            value={formatCurrency(marketCap.total || 0, 0)}
            icon={<AttachMoney />}
            color="success"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Advancing"
            value={formatNumber(marketBreadth.advancing || 0, 0)}
            subtitle={`Declining: ${formatNumber(marketBreadth.declining || 0, 0)}`}
            icon={<TrendingUp />}
            color="success"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Advance/Decline Ratio"
            value={marketBreadth.advance_decline_ratio !== undefined ? marketBreadth.advance_decline_ratio : 'N/A'}
            subtitle={`Avg Change: ${marketBreadth.average_change_percent !== undefined ? marketBreadth.average_change_percent : 'N/A'}%`}
            icon={<Assessment />}
            color="info"
          />
        </Grid>
      </Grid>

      {/* Sentiment Indicators */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
                Fear & Greed Index
              </Typography>
              {sentimentIndicators.fear_greed ? (
                <Box>
                  <Typography variant="h4" color="primary" sx={{ fontWeight: 700 }}>
                    {sentimentIndicators.fear_greed.value !== undefined ? Number(sentimentIndicators.fear_greed.value).toFixed(1) : 'N/A'}
                  </Typography>
                  <Chip label={sentimentIndicators.fear_greed.value_text} sx={{ mt: 1 }} />
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Last updated: {sentimentIndicators.fear_greed.timestamp ? new Date(sentimentIndicators.fear_greed.timestamp).toLocaleDateString() : 'N/A'}
                  </Typography>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
                AAII Investor Sentiment
              </Typography>
              {sentimentIndicators.aaii ? (
                <Box>
                  <Typography variant="body2">Bullish: <b>{sentimentIndicators.aaii.bullish !== undefined ? (sentimentIndicators.aaii.bullish * 100).toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2">Neutral: <b>{sentimentIndicators.aaii.neutral !== undefined ? (sentimentIndicators.aaii.neutral * 100).toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2">Bearish: <b>{sentimentIndicators.aaii.bearish !== undefined ? (sentimentIndicators.aaii.bearish * 100).toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Week ending: {sentimentIndicators.aaii.week_ending ? new Date(sentimentIndicators.aaii.week_ending).toLocaleDateString() : 'N/A'}
                  </Typography>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
                NAAIM Exposure Index
              </Typography>
              {sentimentIndicators.naaim ? (
                <Box>
                  <Typography variant="body2">Average: <b>{sentimentIndicators.naaim.average !== undefined ? sentimentIndicators.naaim.average.toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2">Bullish: <b>{sentimentIndicators.naaim.bullish_8100 !== undefined ? sentimentIndicators.naaim.bullish_8100.toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2">Bearish: <b>{sentimentIndicators.naaim.bearish !== undefined ? sentimentIndicators.naaim.bearish.toFixed(1) + '%' : 'N/A'}</b></Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    Week ending: {sentimentIndicators.naaim.week_ending ? new Date(sentimentIndicators.naaim.week_ending).toLocaleDateString() : 'N/A'}
                  </Typography>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  )
}

export default Dashboard
