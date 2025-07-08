import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Alert,
  LinearProgress,
  useTheme,
  alpha,
  Tooltip,
  ButtonGroup,
  Button,
  Stack,
  Divider
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  Agriculture,
  LocalGasStation,
  Diamond,
  Construction,
  Thermostat,
  Cloud,
  Assessment,
  Timeline,
  BarChart,
  PieChart,
  TableChart,
  Refresh,
  Info,
  Warning,
  CheckCircle
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, AreaChart, Area, BarChart as RechartsBarChart, Bar, PieChart as RechartsPieChart, Cell } from 'recharts';

// Commodity categories and their symbols
const COMMODITY_CATEGORIES = {
  energy: {
    name: 'Energy',
    icon: LocalGasStation,
    color: '#f44336',
    commodities: ['CL', 'NG', 'HO', 'RB']
  },
  metals: {
    name: 'Precious Metals',
    icon: Diamond,
    color: '#ff9800',
    commodities: ['GC', 'SI', 'PL', 'PA']
  },
  industrial: {
    name: 'Industrial Metals',
    icon: Construction,
    color: '#607d8b',
    commodities: ['HG', 'ALI', 'ZN', 'NI']
  },
  agriculture: {
    name: 'Agriculture',
    icon: Agriculture,
    color: '#4caf50',
    commodities: ['C', 'W', 'S', 'SB', 'KC', 'CC']
  },
  livestock: {
    name: 'Livestock',
    icon: Agriculture,
    color: '#795548',
    commodities: ['LC', 'LH', 'FC']
  }
};

// Mock data - in production, this would come from real APIs
const mockCommodityData = {
  CL: { name: 'Crude Oil WTI', price: 78.45, change: 1.23, changePercent: 1.59, category: 'energy' },
  NG: { name: 'Natural Gas', price: 2.847, change: -0.045, changePercent: -1.56, category: 'energy' },
  GC: { name: 'Gold', price: 2045.50, change: 12.30, changePercent: 0.61, category: 'metals' },
  SI: { name: 'Silver', price: 24.87, change: -0.32, changePercent: -1.27, category: 'metals' },
  HG: { name: 'Copper', price: 3.847, change: 0.023, changePercent: 0.60, category: 'industrial' },
  C: { name: 'Corn', price: 4.82, change: 0.07, changePercent: 1.47, category: 'agriculture' },
  W: { name: 'Wheat', price: 6.23, change: -0.12, changePercent: -1.89, category: 'agriculture' },
  S: { name: 'Soybeans', price: 12.45, change: 0.18, changePercent: 1.47, category: 'agriculture' }
};

// Mock COT data
const mockCOTData = [
  { week: '2024-01-01', commercial: 45000, nonCommercial: -42000, nonReportable: -3000 },
  { week: '2024-01-08', commercial: 47000, nonCommercial: -44000, nonReportable: -3000 },
  { week: '2024-01-15', commercial: 43000, nonCommercial: -40000, nonReportable: -3000 },
  { week: '2024-01-22', commercial: 49000, nonCommercial: -46000, nonReportable: -3000 },
  { week: '2024-01-29', commercial: 51000, nonCommercial: -48000, nonReportable: -3000 }
];

// Mock seasonal data
const mockSeasonalData = [
  { month: 'Jan', historical: 75.2, current: 78.4, average: 76.8 },
  { month: 'Feb', historical: 76.8, current: 79.1, average: 77.9 },
  { month: 'Mar', historical: 78.4, current: 80.2, average: 79.3 },
  { month: 'Apr', historical: 80.1, current: 82.5, average: 81.3 },
  { month: 'May', historical: 82.7, current: 84.8, average: 83.7 },
  { month: 'Jun', historical: 85.2, current: 87.1, average: 86.1 }
];

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`commodities-tabpanel-${index}`}
      aria-labelledby={`commodities-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

const Commodities = () => {
  const theme = useTheme();
  const [activeTab, setActiveTab] = useState(0);
  const [selectedCommodity, setSelectedCommodity] = useState('CL');
  const [selectedTimeframe, setSelectedTimeframe] = useState('1M');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Load initial commodity data
    setLoading(true);
    // Simulate API call
    setTimeout(() => setLoading(false), 1500);
  }, []);

  const formatCurrency = (value, symbol = '$') => {
    return `${symbol}${value?.toFixed(2)}`;
  };

  const formatPercent = (value) => {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value?.toFixed(2)}%`;
  };

  const getPriceColor = (changePercent) => {
    if (changePercent > 0) return theme.palette.success.main;
    if (changePercent < 0) return theme.palette.error.main;
    return theme.palette.text.secondary;
  };

  const renderMarketOverview = () => (
    <Grid container spacing={3}>
      {/* Market Summary Cards */}
      <Grid item xs={12}>
        <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Assessment />
          Commodities Market Overview
        </Typography>
      </Grid>
      
      {Object.entries(COMMODITY_CATEGORIES).map(([key, category]) => {
        const Icon = category.icon;
        const categoryData = Object.values(mockCommodityData).filter(c => c.category === key);
        const avgChange = categoryData.reduce((sum, c) => sum + c.changePercent, 0) / categoryData.length;
        
        return (
          <Grid item xs={12} sm={6} md={2.4} key={key}>
            <Card 
              sx={{ 
                height: '100%',
                background: `linear-gradient(135deg, ${alpha(category.color, 0.1)} 0%, ${alpha(category.color, 0.05)} 100%)`,
                border: `1px solid ${alpha(category.color, 0.2)}`
              }}
            >
              <CardContent>
                <Box display="flex" alignItems="center" justifyContent="space-between" mb={1}>
                  <Icon sx={{ color: category.color, fontSize: 28 }} />
                  <Chip 
                    label={formatPercent(avgChange)}
                    size="small"
                    sx={{ 
                      backgroundColor: getPriceColor(avgChange),
                      color: 'white',
                      fontWeight: 'bold'
                    }}
                  />
                </Box>
                <Typography variant="h6" gutterBottom>
                  {category.name}
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  {categoryData.length} commodities
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        );
      })}

      {/* Price Table */}
      <Grid item xs={12}>
        <Card>
          <CardHeader 
            title="Live Commodity Prices" 
            action={
              <IconButton onClick={() => setLoading(true)}>
                <Refresh />
              </IconButton>
            }
          />
          <CardContent>
            {loading && <LinearProgress sx={{ mb: 2 }} />}
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Commodity</TableCell>
                    <TableCell align="right">Price</TableCell>
                    <TableCell align="right">Change</TableCell>
                    <TableCell align="right">% Change</TableCell>
                    <TableCell align="center">Trend</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Object.entries(mockCommodityData).map(([symbol, data]) => (
                    <TableRow key={symbol} hover>
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          <Chip 
                            label={symbol} 
                            size="small" 
                            variant="outlined"
                            sx={{ minWidth: 40 }}
                          />
                          <Typography variant="body2">{data.name}</Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2" fontWeight="bold">
                          {formatCurrency(data.price)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography 
                          variant="body2" 
                          sx={{ color: getPriceColor(data.change) }}
                        >
                          {data.change >= 0 ? '+' : ''}{data.change.toFixed(3)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography 
                          variant="body2" 
                          sx={{ color: getPriceColor(data.changePercent) }}
                          fontWeight="bold"
                        >
                          {formatPercent(data.changePercent)}
                        </Typography>
                      </TableCell>
                      <TableCell align="center">
                        {data.changePercent > 0 ? (
                          <TrendingUp sx={{ color: theme.palette.success.main }} />
                        ) : (
                          <TrendingDown sx={{ color: theme.palette.error.main }} />
                        )}
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
  );

  const renderCOTAnalysis = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <BarChart />
          Commitment of Traders (COT) Analysis
        </Typography>
        <Alert severity="info" sx={{ mb: 3 }}>
          COT data shows the positioning of different trader categories. Commercial traders are typically the "smart money" 
          while non-commercial (speculators) often represent retail sentiment.
        </Alert>
      </Grid>

      {/* COT Chart */}
      <Grid item xs={12} md={8}>
        <Card>
          <CardHeader 
            title="Net Positions Over Time"
            subheader="Commercial vs Non-Commercial Positioning"
          />
          <CardContent>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={mockCOTData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="week" />
                <YAxis />
                <RechartsTooltip />
                <Line 
                  type="monotone" 
                  dataKey="commercial" 
                  stroke={theme.palette.success.main} 
                  strokeWidth={2}
                  name="Commercial (Smart Money)"
                />
                <Line 
                  type="monotone" 
                  dataKey="nonCommercial" 
                  stroke={theme.palette.error.main} 
                  strokeWidth={2}
                  name="Non-Commercial (Speculators)"
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>

      {/* COT Summary */}
      <Grid item xs={12} md={4}>
        <Card>
          <CardHeader title="Current COT Analysis" />
          <CardContent>
            <Stack spacing={2}>
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Commercial Net Position
                </Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <Typography variant="h6" color="success.main">
                    +51,000
                  </Typography>
                  <Chip label="Bullish" size="small" color="success" />
                </Box>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Non-Commercial Net Position
                </Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <Typography variant="h6" color="error.main">
                    -48,000
                  </Typography>
                  <Chip label="Bearish" size="small" color="error" />
                </Box>
              </Box>

              <Divider />

              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Smart Money Signal
                </Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <CheckCircle sx={{ color: 'success.main' }} />
                  <Typography variant="body2">
                    Commercial traders are net long, suggesting bullish outlook
                  </Typography>
                </Box>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderSeasonalAnalysis = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Timeline />
          Seasonal Analysis & Patterns
        </Typography>
      </Grid>

      {/* Seasonal Chart */}
      <Grid item xs={12} md={8}>
        <Card>
          <CardHeader 
            title="Seasonal Price Patterns"
            subheader="Historical vs Current Year Performance"
          />
          <CardContent>
            <ResponsiveContainer width="100%" height={400}>
              <AreaChart data={mockSeasonalData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis />
                <RechartsTooltip />
                <Area 
                  type="monotone" 
                  dataKey="historical" 
                  stroke={theme.palette.primary.main} 
                  fill={alpha(theme.palette.primary.main, 0.3)}
                  name="Historical Average"
                />
                <Area 
                  type="monotone" 
                  dataKey="current" 
                  stroke={theme.palette.secondary.main} 
                  fill={alpha(theme.palette.secondary.main, 0.3)}
                  name="Current Year"
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>

      {/* Seasonal Insights */}
      <Grid item xs={12} md={4}>
        <Card>
          <CardHeader title="Seasonal Insights" />
          <CardContent>
            <Stack spacing={2}>
              <Alert severity="success">
                <Typography variant="subtitle2">Positive Season</Typography>
                <Typography variant="body2">
                  Historically strong performance in Q2
                </Typography>
              </Alert>

              <Alert severity="warning">
                <Typography variant="subtitle2">Weather Risk</Typography>
                <Typography variant="body2">
                  Hurricane season approaching - monitor supply disruptions
                </Typography>
              </Alert>

              <Alert severity="info">
                <Typography variant="subtitle2">Inventory Cycle</Typography>
                <Typography variant="body2">
                  Weekly inventory reports every Wednesday
                </Typography>
              </Alert>
            </Stack>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderTechnicalAnalysis = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Typography variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <ShowChart />
          Technical Analysis
        </Typography>
      </Grid>

      {/* Controls */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box display="flex" gap={2} alignItems="center" flexWrap="wrap">
              <FormControl sx={{ minWidth: 120 }}>
                <InputLabel>Commodity</InputLabel>
                <Select
                  value={selectedCommodity}
                  onChange={(e) => setSelectedCommodity(e.target.value)}
                  label="Commodity"
                >
                  {Object.entries(mockCommodityData).map(([symbol, data]) => (
                    <MenuItem key={symbol} value={symbol}>
                      {symbol} - {data.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <ButtonGroup variant="outlined">
                {['1D', '1W', '1M', '3M', '1Y'].map((timeframe) => (
                  <Button
                    key={timeframe}
                    variant={selectedTimeframe === timeframe ? 'contained' : 'outlined'}
                    onClick={() => setSelectedTimeframe(timeframe)}
                  >
                    {timeframe}
                  </Button>
                ))}
              </ButtonGroup>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      {/* Technical Indicators */}
      <Grid item xs={12} md={8}>
        <Card>
          <CardHeader title={`${selectedCommodity} Technical Chart`} />
          <CardContent>
            <ResponsiveContainer width="100%" height={400}>
              <LineChart data={mockSeasonalData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis />
                <RechartsTooltip />
                <Line 
                  type="monotone" 
                  dataKey="current" 
                  stroke={theme.palette.primary.main} 
                  strokeWidth={2}
                  name="Price"
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </Grid>

      {/* Technical Indicators Summary */}
      <Grid item xs={12} md={4}>
        <Card>
          <CardHeader title="Technical Indicators" />
          <CardContent>
            <Stack spacing={2}>
              <Box>
                <Typography variant="subtitle2">RSI (14)</Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <Typography variant="h6">68.5</Typography>
                  <Chip label="Neutral" size="small" color="warning" />
                </Box>
              </Box>

              <Box>
                <Typography variant="subtitle2">MACD</Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <Typography variant="h6">+1.23</Typography>
                  <Chip label="Bullish" size="small" color="success" />
                </Box>
              </Box>

              <Box>
                <Typography variant="subtitle2">Moving Average (50)</Typography>
                <Box display="flex" alignItems="center" gap={1}>
                  <Typography variant="h6">$76.20</Typography>
                  <Chip label="Above" size="small" color="success" />
                </Box>
              </Box>

              <Box>
                <Typography variant="subtitle2">Support/Resistance</Typography>
                <Typography variant="body2" color="error.main">Support: $74.50</Typography>
                <Typography variant="body2" color="success.main">Resistance: $82.00</Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={(_, newValue) => setActiveTab(newValue)}>
          <Tab label="Market Overview" icon={<Assessment />} />
          <Tab label="COT Analysis" icon={<BarChart />} />
          <Tab label="Seasonal Patterns" icon={<Timeline />} />
          <Tab label="Technical Analysis" icon={<ShowChart />} />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0}>
        {renderMarketOverview()}
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        {renderCOTAnalysis()}
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        {renderSeasonalAnalysis()}
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        {renderTechnicalAnalysis()}
      </TabPanel>
    </Container>
  );
};

export default Commodities;