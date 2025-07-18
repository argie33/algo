import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
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
  CircularProgress,
  Alert,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemIcon
} from '@mui/material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  ComposedChart,
  ScatterChart,
  Scatter,
  PieChart,
  Pie,
  Cell
} from 'recharts';
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Assessment,
  Timeline,
  PieChart as PieChartIcon,
  ShowChart,
  AccountBalance,
  Warning,
  CheckCircle,
  Info,
  Star,
  StarBorder
} from '@mui/icons-material';
import { getPortfolioPerformance, getPortfolioAnalytics, getBenchmarkData } from '../services/api';
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

const PortfolioPerformance = () => {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeframe, setTimeframe] = useState('1Y');
  const [showBenchmark, setShowBenchmark] = useState(true);
  const [performanceData, setPerformanceData] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [attributionData, setAttributionData] = useState(null);
  const [riskMetrics, setRiskMetrics] = useState(null);

  // Performance metrics
  const [metrics, setMetrics] = useState({
    totalReturn: 0,
    annualizedReturn: 0,
    volatility: 0,
    sharpeRatio: 0,
    maxDrawdown: 0,
    beta: 0,
    alpha: 0,
    informationRatio: 0,
    calmarRatio: 0,
    sortinoRatio: 0
  });


  useEffect(() => {
    fetchPerformanceData();
  }, [timeframe]);

  const fetchPerformanceData = async () => {
    try {
      setLoading(true);
      setError(null); // Clear any previous errors
      
      // Add timeout handling for API calls
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('API call timeout')), 5000)
      );
      
      // Fetch portfolio performance data with better error handling
      const performanceResponse = await Promise.race([
        getPortfolioPerformance(timeframe),
        timeoutPromise
      ]);
      const perfData = performanceResponse?.data || performanceResponse;
      
      if (perfData) {
        // Transform performance data - handle new API structure
        const transformedData = perfData.performanceData || perfData.performance || perfData.data || [];
        console.log('Performance data structure:', { perfData, transformedData });
        setPerformanceData(Array.isArray(transformedData) ? transformedData : []);
        
        // Extract or use default metrics
        const responseMetrics = perfData.metrics || {};
        setMetrics({
          totalReturn: responseMetrics.totalReturn || responseMetrics.totalReturnPercent || 0,
          annualizedReturn: responseMetrics.annualizedReturn || 0,
          volatility: responseMetrics.volatility || 0,
          sharpeRatio: responseMetrics.sharpeRatio || 0,
          maxDrawdown: responseMetrics.maxDrawdown || 0,
          beta: responseMetrics.beta || 1,
          alpha: responseMetrics.alpha || 0,
          informationRatio: responseMetrics.informationRatio || 0,
          calmarRatio: responseMetrics.calmarRatio || 0,
          sortinoRatio: responseMetrics.sortinoRatio || 0
        });
      }

      // Fetch analytics
      try {
        const analyticsTimeoutPromise = new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Analytics API timeout')), 5000)
        );
        
        const analyticsResponse = await Promise.race([
          getPortfolioAnalytics(timeframe),
          analyticsTimeoutPromise
        ]);
        const analyticsData = analyticsResponse?.data || analyticsResponse;
        
        if (analyticsData) {
          setAnalytics(analyticsData.analytics || analyticsData);
          setAttributionData(analyticsData.attribution);
          setRiskMetrics(analyticsData.risk);
        }
      } catch (analyticsError) {
        console.error('Analytics fetch failed:', analyticsError.message);
        setAnalytics(null);
        setAttributionData(null);
        setRiskMetrics(null);
        setError('Failed to load portfolio analytics');
      }
    } catch (err) {
      console.error('Portfolio performance API failed:', err);
      setPerformanceData([]);
      setError('Failed to load portfolio performance data');
      setLoading(false);
    } finally {
      setLoading(false);
    }
  };

  const formatPercentage = (value) => {
    const color = value >= 0 ? 'success.main' : 'error.main';
    const sign = value >= 0 ? '+' : '';
    return {
      text: `${sign}${value.toFixed(2)}%`,
      color
    };
  };

  const formatCurrency = (value) => {
    return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, border: 1, borderColor: 'divider' }}>
          <div  variant="body2" sx={{ mb: 1 }}>
            {label}
          </div>
          {payload.map((entry, index) => (
            <div 
              key={index}
              variant="body2"
              sx={{ color: entry.color }}
            >
              {entry.name}: {entry.name.includes('%') ? `${entry.value.toFixed(2)}%` : formatCurrency(entry.value)}
            </div>
          ))}
        </div>
      );
    }
    return null;
  };

  const TabPanel = ({ children, value, index, ...other }) => (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`performance-tabpanel-${index}`}
      aria-labelledby={`performance-tab-${index}`}
      {...other}
    >
      {value === index && <div  sx={{ pt: 3 }}>{children}</div>}
    </div>
  );


  if (loading) {
    return (
      <div className="container mx-auto" maxWidth="xl">
        <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
        </div>
      </div>
    );
  }

  // Add error boundary
  if (error && !performanceData) {
    return (
      <div className="container mx-auto" maxWidth="xl">
        <div  sx={{ py: 4 }}>
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">
            <div  variant="h6">Error Loading Portfolio Performance</div>
            <div>{String(error)}</div>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={fetchPerformanceData} sx={{ mt: 2 }}>Retry</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="xl">
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" gutterBottom>
          Portfolio Performance Analysis
        </div>
        <div  variant="body1" color="text.secondary">
          Comprehensive performance analytics with attribution analysis
        </div>
      </div>

      {/* API Key Status */}
      <div  sx={{ mb: 3 }}>
        <ApiKeyStatusIndicator 
          showSetupDialog={true}
          onStatusChange={(status) => {
            console.log('Portfolio Performance - API Key Status:', status);
          }}
        />
      </div>

      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {String(error)}
        </div>
      )}

      {/* Controls */}
      <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <div className="mb-4" sx={{ minWidth: 120 }}>
          <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
          <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={timeframe}
            label="Timeframe"
            onChange={(e) => setTimeframe(e.target.value)}
          >
            <option  value="1M">1 Month</option>
            <option  value="3M">3 Months</option>
            <option  value="6M">6 Months</option>
            <option  value="1Y">1 Year</option>
            <option  value="2Y">2 Years</option>
            <option  value="3Y">3 Years</option>
            <option  value="5Y">5 Years</option>
            <option  value="MAX">All Time</option>
          </select>
        </div>
        <div className="mb-4"Label
          control={
            <input type="checkbox" className="toggle"
              checked={showBenchmark}
              onChange={(e) => setShowBenchmark(e.target.checked)}
            />
          }
          label="Show Benchmark"
        />
      </div>

      {/* Performance Metrics Cards */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  color="text.secondary" gutterBottom>
                Total Return
              </div>
              <div  variant="h5" sx={{ color: formatPercentage(metrics.totalReturn).color }}>
                {formatPercentage(metrics.totalReturn).text}
              </div>
              <div  variant="body2" color="text.secondary">
                Since inception
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  color="text.secondary" gutterBottom>
                Annualized Return
              </div>
              <div  variant="h5" sx={{ color: formatPercentage(metrics.annualizedReturn).color }}>
                {formatPercentage(metrics.annualizedReturn).text}
              </div>
              <div  variant="body2" color="text.secondary">
                Geometric mean
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  color="text.secondary" gutterBottom>
                Sharpe Ratio
              </div>
              <div  variant="h5">
                {metrics.sharpeRatio.toFixed(2)}
              </div>
              <div  variant="body2" color="text.secondary">
                Risk-adjusted return
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} sm={6} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  color="text.secondary" gutterBottom>
                Max Drawdown
              </div>
              <div  variant="h5" color="error.main">
                {formatPercentage(metrics.maxDrawdown).text}
              </div>
              <div  variant="body2" color="text.secondary">
                Worst decline
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs for different analysis views */}
      <div className="bg-white shadow-md rounded-lg">
        <div  sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <div className="border-b border-gray-200" value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)}>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Performance Chart" icon={<ShowChart />} />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Attribution Analysis" icon={<PieChartIcon />} />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Risk Metrics" icon={<Warning />} />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Sector Performance" icon={<Analytics />} />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Holdings Analysis" icon={<Assessment />} />
          </div>
        </div>

        {/* Performance Chart Tab */}
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={0}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Portfolio Performance vs Benchmark
            </div>
            {/* Only render chart if we have valid data */}
            {performanceData && Array.isArray(performanceData) && performanceData.length > 0 ? (
              <ResponsiveContainer width="100%" height={400}>
                <ComposedChart data={performanceData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="portfolioValue"
                    stroke="#2196F3"
                    fill="#2196F3"
                    fillOpacity={0.1}
                    name="Portfolio Value"
                  />
                  {showBenchmark && (
                    <Line
                      type="monotone"
                      dataKey="benchmarkValue"
                      stroke="#FF9800"
                      strokeWidth={2}
                      dot={false}
                      name="S&P 500"
                    />
                  )}
                  <Bar
                    dataKey="dailyReturn"
                    fill="#4CAF50"
                    name="Daily Return %"
                    yAxisId="right"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div  
                display="flex" 
                justifyContent="center" 
                alignItems="center" 
                height={400}
                sx={{ bgcolor: 'grey.50', borderRadius: 1 }}
              >
                <div  variant="body1" color="text.secondary">
                  {error ? 'Error loading performance data' : 'No performance data available'}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Attribution Analysis Tab */}
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={1}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Performance Attribution Analysis
            </div>
            {attributionData ? (
              <div className="grid" container spacing={3}>
                <div className="grid" item xs={12} md={6}>
                  <div  variant="subtitle1" gutterBottom>
                    Sector Attribution
                  </div>
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={attributionData.sectorAttribution}
                        cx="50%"
                        cy="50%"
                        outerRadius={100}
                        fill="#8884d8"
                        dataKey="contribution"
                        label={({ name, contribution }) => `${name}: ${contribution.toFixed(2)}%`}
                      >
                        {attributionData.sectorAttribution.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.contribution >= 0 ? '#4CAF50' : '#F44336'} />
                        ))}
                      </Pie>
                      <RechartsTooltip formatter={(value) => [`${value.toFixed(2)}%`, 'Contribution']} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="grid" item xs={12} md={6}>
                  <div  variant="subtitle1" gutterBottom>
                    Stock Attribution
                  </div>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Stock</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Weight</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Return</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Contribution</td>
                        </tr>
                      </thead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                        {attributionData.stockAttribution?.slice(0, 10).map((stock) => (
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={stock.symbol}>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{stock.symbol}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{stock.weight.toFixed(2)}%</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell 
                              align="right"
                              sx={{ color: stock.return >= 0 ? 'success.main' : 'error.main' }}
                            >
                              {formatPercentage(stock.return).text}
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell 
                              align="right"
                              sx={{ color: stock.contribution >= 0 ? 'success.main' : 'error.main' }}
                            >
                              {formatPercentage(stock.contribution).text}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : (
              <div  color="text.secondary">No attribution data available</div>
            )}
          </div>
        </div>

        {/* Risk Metrics Tab */}
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={2}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Risk Analysis
            </div>
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={12} md={6}>
                <div  variant="subtitle1" gutterBottom>
                  Risk Metrics
                </div>
                <List>
                  <ListItem>
                    <ListItemIcon>
                      <Analytics />
                    </ListItemIcon>
                    <ListItemText
                      primary="Volatility (Annualized)"
                      secondary={`${metrics.volatility.toFixed(2)}%`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <TrendingUp />
                    </ListItemIcon>
                    <ListItemText
                      primary="Beta (vs S&P 500)"
                      secondary={metrics.beta.toFixed(2)}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <Star />
                    </ListItemIcon>
                    <ListItemText
                      primary="Alpha (Annualized)"
                      secondary={`${metrics.alpha.toFixed(2)}%`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <Assessment />
                    </ListItemIcon>
                    <ListItemText
                      primary="Information Ratio"
                      secondary={metrics.informationRatio.toFixed(2)}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <CheckCircle />
                    </ListItemIcon>
                    <ListItemText
                      primary="Sortino Ratio"
                      secondary={metrics.sortinoRatio.toFixed(2)}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon>
                      <Warning />
                    </ListItemIcon>
                    <ListItemText
                      primary="Calmar Ratio"
                      secondary={metrics.calmarRatio.toFixed(2)}
                    />
                  </ListItem>
                </List>
              </div>
              <div className="grid" item xs={12} md={6}>
                <div  variant="subtitle1" gutterBottom>
                  Rolling Volatility
                </div>
                {riskMetrics?.rollingVolatility && (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={riskMetrics.rollingVolatility}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <RechartsTooltip content={<CustomTooltip />} />
                      <Line
                        type="monotone"
                        dataKey="volatility"
                        stroke="#FF5722"
                        strokeWidth={2}
                        dot={false}
                        name="30-Day Volatility %"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Sector Performance Tab */}
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={3}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Sector Performance Analysis
            </div>
            {analytics?.sectorPerformance && (
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={analytics.sectorPerformance}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="sector" angle={-45} textAnchor="end" height={100} />
                  <YAxis />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Bar dataKey="return" name="Return %" fill="#2196F3" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Holdings Analysis Tab */}
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={4}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Top Holdings Performance
            </div>
            {analytics?.holdingsPerformance && (
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Name</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Weight</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Return</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Contribution</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volatility</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Rating</td>
                    </tr>
                  </thead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                    {analytics.holdingsPerformance.map((holding) => (
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={holding.symbol}>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" fontWeight="bold">
                            {holding.symbol}
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{holding.name}</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{holding.weight.toFixed(2)}%</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell 
                          align="right"
                          sx={{ color: holding.return >= 0 ? 'success.main' : 'error.main' }}
                        >
                          {formatPercentage(holding.return).text}
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell 
                          align="right"
                          sx={{ color: holding.contribution >= 0 ? 'success.main' : 'error.main' }}
                        >
                          {formatPercentage(holding.contribution).text}
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{holding.volatility.toFixed(2)}%</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  sx={{ display: 'flex', alignItems: 'center' }}>
                            {[1, 2, 3, 4, 5].map((star) => (
                              star <= holding.rating ? 
                                <Star key={star} sx={{ color: '#FFD700', fontSize: 16 }} /> :
                                <StarBorder key={star} sx={{ color: '#FFD700', fontSize: 16 }} />
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default PortfolioPerformance;