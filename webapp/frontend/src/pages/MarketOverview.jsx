import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createComponentLogger } from '../utils/errorLogger'
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
  getMarketSentimentHistory, 
  getMarketSectorPerformance, 
  getMarketBreadth, 
  getEconomicIndicators 
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

// Create component-specific logger
const logger = createComponentLogger('MarketOverview');

function MarketOverview() {  const [tabValue, setTabValue] = useState(0)
  const { data: marketData, isLoading: marketLoading, error: marketError } = useQuery(
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
      refetchInterval: 60000,
      onError: (err) => logger.queryError('market-overview', err)
    }
  )

  const { data: sentimentData, isLoading: sentimentLoading } = useQuery(
    'market-sentiment-history',
    async () => {
      try {
        const result = await getMarketSentimentHistory(30);
        logger.success('getMarketSentimentHistory', result, { days: 30 });
        return result;
      } catch (err) {
        logger.error('getMarketSentimentHistory', err, { days: 30 });
        throw err;
      }
    },
    { 
      enabled: tabValue === 1,
      onError: (err) => logger.queryError('market-sentiment-history', err)
    }
  )

  const { data: sectorData, isLoading: sectorLoading } = useQuery(
    'market-sector-performance',
    async () => {
      try {
        const result = await getMarketSectorPerformance();
        logger.success('getMarketSectorPerformance', result);
        return result;
      } catch (err) {
        logger.error('getMarketSectorPerformance', err);
        throw err;
      }
    },
    { 
      enabled: tabValue === 2,
      onError: (err) => logger.queryError('market-sector-performance', err)
    }
  )

  const { data: breadthData, isLoading: breadthLoading } = useQuery(
    'market-breadth',
    async () => {
      try {
        const result = await getMarketBreadth();
        logger.success('getMarketBreadth', result);
        return result;
      } catch (err) {
        logger.error('getMarketBreadth', err);
        throw err;
      }
    },
    { 
      enabled: tabValue === 3,
      onError: (err) => logger.queryError('market-breadth', err)
    }
  )

  const { data: economicData, isLoading: economicLoading } = useQuery(
    'economic-indicators',
    async () => {
      try {
        const result = await getEconomicIndicators(90);
        logger.success('getEconomicIndicators', result, { days: 90 });
        return result;
      } catch (err) {
        logger.error('getEconomicIndicators', err, { days: 90 });
        throw err;
      }
    },
    { 
      enabled: tabValue === 4,
      onError: (err) => logger.queryError('economic-indicators', err)
    }
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
          <br /><small>Check the API debug endpoint at: <code>{import.meta.env.VITE_API_URL || ''}/market/debug</code> for table status</small>
        </Alert>
      </Box>
    )
  }

  // Extract data from the new market API structure
  const sentimentIndicators = marketData?.data?.sentiment_indicators || {}
  const marketBreadth = marketData?.data?.market_breadth || {}
  const marketCap = marketData?.data?.market_cap || {}
  const economicIndicators = marketData?.data?.economic_indicators || []
  
  const sectors = sectorData?.data?.sectors || []
  const breadthInfo = breadthData?.data || {}
  const sentimentHistory = sentimentData?.data || {}

  // Prepare chart data for sectors
  const sectorChartData = sectors.slice(0, 8).map(sector => ({
    name: sector.sector?.substring(0, 15) || 'Other',
    performance: parseFloat(sector.avg_change_percent) || 0,
    marketCap: parseFloat(sector.sector_market_cap) || 0,
    stocks: parseInt(sector.stock_count) || 0,
    advanceDeclineRatio: parseFloat(sector.advance_decline_ratio) || 0
  }))

  // Prepare sentiment chart data for all indicators
  const fearGreedHistory = sentimentHistory.fear_greed_history || [];
  const naaimHistory = sentimentHistory.naaim_history || [];
  const aaiiHistory = sentimentHistory.aaii_history || [];

  // Merge by date for multi-line chart (assume all have 'date' or 'timestamp')
  const dateMap = {};
  fearGreedHistory.forEach(item => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].fear_greed = item.value;
    dateMap[date].fear_greed_text = item.value_text;
  });
  naaimHistory.forEach(item => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].naaim = item.mean_exposure || item.average;
  });
  aaiiHistory.forEach(item => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].aaii_bullish = item.bullish;
    dateMap[date].aaii_bearish = item.bearish;
    dateMap[date].aaii_neutral = item.neutral;
  });
  const sentimentChartData = Object.values(dateMap)
    .sort((a, b) => new Date(a.date) - new Date(b.date))
    .slice(-30);

  // Latest stats for summary cards
  const latestFG = fearGreedHistory[0] || {};
  const latestNAAIM = naaimHistory[0] || {};
  const latestAAII = aaiiHistory[0] || {};

  // --- Sentiment History Tab ---
  const SentimentHistoryPanel = () => (
    <Box>
      <Grid container spacing={2} mb={2}>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary">Fear & Greed Index</Typography>
              <Typography variant="h5" fontWeight={700} color={getChangeColor(latestFG.value)}>
                {latestFG.value ?? 'N/A'}
              </Typography>
              <Typography variant="body2">{latestFG.value_text || ''}</Typography>
              <Typography variant="caption" color="text.secondary">Measures market sentiment (0=Extreme Fear, 100=Extreme Greed)</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary">NAAIM Exposure</Typography>
              <Typography variant="h5" fontWeight={700} color={getChangeColor(latestNAAIM.mean_exposure)}>
                {latestNAAIM.mean_exposure ?? latestNAAIM.average ?? 'N/A'}
              </Typography>
              <Typography variant="body2">Active manager equity exposure</Typography>
              <Typography variant="caption" color="text.secondary">0 = fully out, 100 = fully in</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary">AAII Sentiment</Typography>
              <Typography variant="body2">Bullish: <b style={{color:'#10B981'}}>{latestAAII.bullish ?? 'N/A'}%</b> | Neutral: <b style={{color:'#8884d8'}}>{latestAAII.neutral ?? 'N/A'}%</b> | Bearish: <b style={{color:'#DC2626'}}>{latestAAII.bearish ?? 'N/A'}%</b></Typography>
              <Typography variant="caption" color="text.secondary">% of retail investors bullish, neutral, or bearish</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      <Card>
        <CardContent>
          <Typography variant="h6" mb={2}>Sentiment History (Last 30 Days)</Typography>
          <ResponsiveContainer width="100%" height={350}>
            <LineChart data={sentimentChartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} />
              <YAxis yAxisId="left" label={{ value: 'FG/NAAIM', angle: -90, position: 'insideLeft', fontSize: 12 }} />
              <YAxis yAxisId="right" orientation="right" label={{ value: 'AAII %', angle: 90, position: 'insideRight', fontSize: 12 }} />
              <Tooltip formatter={(value, name) => [`${value}`, name]} />
              <Legend verticalAlign="top" height={36} />
              <Line yAxisId="left" type="monotone" dataKey="fear_greed" name="Fear & Greed" stroke="#FF8042" strokeWidth={2} dot={false} />
              <Line yAxisId="left" type="monotone" dataKey="naaim" name="NAAIM Exposure" stroke="#0088FE" strokeWidth={2} dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="aaii_bullish" name="AAII Bullish" stroke="#10B981" strokeWidth={2} dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="aaii_bearish" name="AAII Bearish" stroke="#DC2626" strokeWidth={2} dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="aaii_neutral" name="AAII Neutral" stroke="#8884d8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </Box>
  );

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
        Market Overview
      </Typography>

      {marketLoading && <LinearProgress sx={{ mb: 2 }} />}

      {/* Market Sentiment Indicators */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Fear & Greed Index
              </Typography>
              {sentimentIndicators.fear_greed ? (
                <Box>
                  <Typography variant="h3" color="primary" sx={{ mb: 1 }}>
                    {sentimentIndicators.fear_greed.value}
                  </Typography>
                  <Chip 
                    label={sentimentIndicators.fear_greed.value_text} 
                    color={
                      sentimentIndicators.fear_greed.value > 75 ? 'error' :
                      sentimentIndicators.fear_greed.value > 55 ? 'warning' :
                      sentimentIndicators.fear_greed.value > 45 ? 'info' :
                      sentimentIndicators.fear_greed.value > 25 ? 'warning' : 'error'
                    }
                    sx={{ mb: 1 }}
                  />
                  <Typography variant="body2" color="text.secondary">
                    Last updated: {sentimentIndicators.fear_greed.timestamp ? new Date(sentimentIndicators.fear_greed.timestamp).toLocaleDateString() : 'N/A'}
                  </Typography>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                AAII Investor Sentiment
              </Typography>
              {sentimentIndicators.aaii ? (
                <Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Bullish:</Typography>
                    <Typography variant="body2" color="success.main">
                      {sentimentIndicators.aaii.bullish !== undefined ? (sentimentIndicators.aaii.bullish * 100).toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Neutral:</Typography>
                    <Typography variant="body2" color="info.main">
                      {sentimentIndicators.aaii.neutral !== undefined ? (sentimentIndicators.aaii.neutral * 100).toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Bearish:</Typography>
                    <Typography variant="body2" color="error.main">
                      {sentimentIndicators.aaii.bearish !== undefined ? (sentimentIndicators.aaii.bearish * 100).toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    Week ending: {sentimentIndicators.aaii.date ? new Date(sentimentIndicators.aaii.date).toLocaleDateString() : 'N/A'}
                  </Typography>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">No data available</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                NAAIM Exposure Index
              </Typography>
              {sentimentIndicators.naaim ? (
                <Box>
                  <Typography variant="h3" color="primary" sx={{ mb: 1 }}>
                    {sentimentIndicators.naaim.average !== undefined ? sentimentIndicators.naaim.average.toFixed(1) + '%' : 'N/A'}
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Bullish:</Typography>
                    <Typography variant="body2" color="success.main">
                      {sentimentIndicators.naaim.bullish_8100 !== undefined ? sentimentIndicators.naaim.bullish_8100.toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Bearish:</Typography>
                    <Typography variant="body2" color="error.main">
                      {sentimentIndicators.naaim.bearish !== undefined ? sentimentIndicators.naaim.bearish.toFixed(1) + '%' : 'N/A'}
                    </Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary">
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

      {/* Market Breadth */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Breadth
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'success.light', borderRadius: 1 }}>
                    <Typography variant="h4" color="success.contrastText">
                      {marketBreadth.advancing !== undefined ? marketBreadth.advancing : 'N/A'}
                    </Typography>
                    <Typography variant="body2" color="success.contrastText">
                      Advancing
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box sx={{ textAlign: 'center', p: 2, backgroundColor: 'error.light', borderRadius: 1 }}>
                    <Typography variant="h4" color="error.contrastText">
                      {marketBreadth.declining !== undefined ? marketBreadth.declining : 'N/A'}
                    </Typography>
                    <Typography variant="body2" color="error.contrastText">
                      Declining
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12}>
                  <Box sx={{ textAlign: 'center', mt: 2 }}>
                    <Typography variant="body2" color="text.secondary">
                      Advance/Decline Ratio: {marketBreadth.advance_decline_ratio !== undefined ? marketBreadth.advance_decline_ratio : 'N/A'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Average Change: {marketBreadth.average_change_percent !== undefined ? marketBreadth.average_change_percent : 'N/A'}%
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Statistics
              </Typography>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="body2">Total Stocks:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {marketBreadth.total_stocks !== undefined ? marketBreadth.total_stocks.toLocaleString() : 'N/A'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="body2">Total Market Cap:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {marketCap.total !== undefined ? formatCurrency(marketCap.total) : 'N/A'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="body2">Unchanged:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {marketBreadth.unchanged !== undefined ? marketBreadth.unchanged : 'N/A'}
                </Typography>
              </Box>            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs for different market data */}
      <Card>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={handleTabChange} aria-label="market data tabs">
            <Tab label="Market Overview" />
            <Tab label="Sentiment History" />
            <Tab label="Sector Performance" />
            <Tab label="Market Breadth" />
            <Tab label="Economic Indicators" />
          </Tabs>
        </Box>

        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Market Cap Distribution
                  </Typography>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Large Cap:</Typography>
                    <Typography variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.large_cap)}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Mid Cap:</Typography>
                    <Typography variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.mid_cap)}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Small Cap:</Typography>
                    <Typography variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.small_cap)}
                    </Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="body2">Total:</Typography>
                    <Typography variant="body2" fontWeight="600">
                      {formatCurrency(marketCap.total)}
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                    Latest Economic Indicators
                  </Typography>
                  {economicIndicators.slice(0, 5).map((indicator, index) => (
                    <Box key={index} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2">{indicator.name}:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {indicator.value} {indicator.unit}
                      </Typography>
                    </Box>
                  ))}
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {sentimentLoading ? (
            <LinearProgress />
          ) : (
            <Card>
              <CardContent>
                <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                  Fear & Greed Index History (30 Days)
                </Typography>
                <ResponsiveContainer width="100%" height={400}>
                  <LineChart data={sentimentChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis domain={[0, 100]} />
                    <Tooltip 
                      formatter={(value, name, props) => [
                        `${value} (${props.payload.text})`,
                        'Fear & Greed Index'
                      ]}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="value" 
                      stroke="#8884d8" 
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          {sectorLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Sector Performance
                    </Typography>
                    <ResponsiveContainer width="100%" height={400}>
                      <BarChart data={sectorChartData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="name" 
                          angle={-45}
                          textAnchor="end"
                          height={80}
                        />
                        <YAxis />
                        <Tooltip 
                          formatter={(value, name) => [
                            `${value.toFixed(2)}%`,
                            'Performance'
                          ]}
                        />
                        <Bar dataKey="performance" fill="#8884d8" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={4}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Sector Details
                    </Typography>
                    <TableContainer>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Sector</TableCell>
                            <TableCell align="right">Change %</TableCell>
                            <TableCell align="right">Stocks</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {sectors.slice(0, 8).map((sector, index) => (
                            <TableRow key={index}>
                              <TableCell>{sector.sector?.substring(0, 12) || 'N/A'}</TableCell>
                              <TableCell 
                                align="right"
                                sx={{ 
                                  color: getChangeColor(parseFloat(sector.avg_change_percent) || 0),
                                  fontWeight: 600
                                }}
                              >
                                {formatPercentage(parseFloat(sector.avg_change_percent) || 0)}
                              </TableCell>
                              <TableCell align="right">
                                {sector.stock_count || 0}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          {breadthLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Market Breadth Details
                    </Typography>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="body2">Advancing Stocks:</Typography>
                      <Typography variant="body2" color="success.main" fontWeight="600">
                        {breadthInfo.advancing || 0}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="body2">Declining Stocks:</Typography>
                      <Typography variant="body2" color="error.main" fontWeight="600">
                        {breadthInfo.declining || 0}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="body2">Unchanged:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {breadthInfo.unchanged || 0}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="body2">A/D Ratio:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {breadthInfo.advance_decline_ratio || 'N/A'}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                      <Typography variant="body2">Average Change:</Typography>
                      <Typography 
                        variant="body2" 
                        fontWeight="600"
                        sx={{ color: getChangeColor(parseFloat(breadthInfo.average_change_percent) || 0) }}
                      >
                        {formatPercentage(parseFloat(breadthInfo.average_change_percent) || 0)}
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Breadth Visualization
                    </Typography>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={[
                            { name: 'Advancing', value: breadthInfo.advancing || 0, color: '#4CAF50' },
                            { name: 'Declining', value: breadthInfo.declining || 0, color: '#F44336' },
                            { name: 'Unchanged', value: breadthInfo.unchanged || 0, color: '#9E9E9E' }
                          ]}
                          cx="50%"
                          cy="50%"
                          outerRadius={80}
                          dataKey="value"
                          label={({ name, value }) => `${name}: ${value}`}
                        >
                          <Cell fill="#4CAF50" />
                          <Cell fill="#F44336" />
                          <Cell fill="#9E9E9E" />
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={4}>
          {economicLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Economic Indicators (Last 90 Days)
                    </Typography>
                    <TableContainer>
                      <Table>
                        <TableHead>
                          <TableRow sx={{ backgroundColor: 'grey.50' }}>
                            <TableCell sx={{ fontWeight: 600 }}>Indicator</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>Current Value</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>Previous Value</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>Change</TableCell>
                            <TableCell align="right" sx={{ fontWeight: 600 }}>Date</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {economicData?.data?.slice(0, 10).map((indicator, index) => (
                            <TableRow key={index} hover>
                              <TableCell>{indicator.name || 'N/A'}</TableCell>
                              <TableCell align="right">
                                {indicator.value} {indicator.unit}
                              </TableCell>
                              <TableCell align="right">
                                {indicator.previous_value || 'N/A'} {indicator.unit}
                              </TableCell>
                              <TableCell 
                                align="right"
                                sx={{ 
                                  color: getChangeColor(parseFloat(indicator.change_percent) || 0),
                                  fontWeight: 600
                                }}
                              >
                                {indicator.change_percent ? formatPercentage(parseFloat(indicator.change_percent)) : 'N/A'}
                              </TableCell>
                              <TableCell align="right">
                                {indicator.timestamp ? new Date(indicator.timestamp).toLocaleDateString() : 'N/A'}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}
        </TabPanel>
      </Card>
    </Box>
  )
}

export default MarketOverview
