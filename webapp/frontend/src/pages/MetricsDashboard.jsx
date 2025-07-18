import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  CircularProgress,
  Alert,
  Tab,
  Tabs,
  LinearProgress,
  Tooltip,
  IconButton,
  Badge
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Info,
  Assessment,
  Speed,
  AttachMoney,
  Psychology,
  ShowChart,
  AccountBalance
} from '@mui/icons-material';
import { getApiConfig } from '../services/api';

const MetricsDashboard = () => {
  const { apiUrl: API_BASE } = getApiConfig();
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Data states
  const [stocks, setStocks] = useState([]);
  const [sectors, setSectors] = useState([]);
  const [topStocks, setTopStocks] = useState({});
  
  // Filter states
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedSector, setSelectedSector] = useState('');
  const [minMetric, setMinMetric] = useState(0);
  const [maxMetric, setMaxMetric] = useState(1);
  const [sortBy, setSortBy] = useState('composite_metric');
  const [sortOrder, setSortOrder] = useState('desc');
  
  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    fetchData();
  }, [page, searchTerm, selectedSector, minMetric, maxMetric, sortBy, sortOrder]);

  useEffect(() => {
    if (activeTab === 1) {
      fetchSectorAnalysis();
    } else if (activeTab === 2) {
      fetchTopStocks();
    }
  }, [activeTab]);

  const fetchData = async () => {
    try {
      setLoading(true);
      
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '50',
        search: searchTerm,
        sector: selectedSector,
        minMetric: minMetric.toString(),
        maxMetric: maxMetric.toString(),
        sortBy,
        sortOrder
      });

      const response = await fetch(`${API_BASE}/api/metrics?${params}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      setStocks(data.stocks || []);
      setTotalPages(data.pagination?.totalPages || 1);
      setError(null);
      
    } catch (err) {
      console.error('Error fetching metrics:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSectorAnalysis = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/metrics/sectors/analysis`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      
      const data = await response.json();
      setSectors(data.sectors || []);
      
    } catch (err) {
      console.error('Error fetching sector analysis:', err);
      setError(err.message);
    }
  };

  const fetchTopStocks = async () => {
    try {
      const categories = ['composite', 'quality', 'value'];
      const promises = categories.map(category =>
        fetch(`${API_BASE}/api/metrics/top/${category}?limit=10`)
          .then(res => res.json())
          .then(data => ({ category, data: data.topStocks || [] }))
      );
      
      const results = await Promise.all(promises);
      const topStocksData = {};
      
      results.forEach(({ category, data }) => {
        topStocksData[category] = data;
      });
      
      setTopStocks(topStocksData);
      
    } catch (err) {
      console.error('Error fetching top stocks:', err);
      setError(err.message);
    }
  };

  const getMetricColor = (metric) => {
    if (metric >= 0.8) return '#4caf50'; // Green
    if (metric >= 0.7) return '#8bc34a'; // Light green
    if (metric >= 0.6) return '#ffeb3b'; // Yellow
    if (metric >= 0.5) return '#ff9800'; // Orange
    return '#f44336'; // Red
  };

  const getMetricChip = (metric, label) => (
    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
      label={`${label}: ${metric.toFixed(3)}`}
      size="small"
      style={{
        backgroundColor: getMetricColor(metric),
        color: metric >= 0.6 ? '#000' : '#fff',
        fontWeight: 'bold',
        margin: '2px'
      }}
    />
  );

  const MetricProgressBar = ({ metric, label, icon }) => (
    <div  sx={{ mb: 2 }}>
      <div  sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
        {icon}
        <div  variant="body2" sx={{ ml: 1, flex: 1 }}>
          {label}
        </div>
        <div  variant="body2" sx={{ fontWeight: 'bold' }}>
          {metric.toFixed(3)}
        </div>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2"
        variant="determinate"
        value={metric * 100}
        sx={{
          height: 8,
          borderRadius: 4,
          '& .MuiLinearProgress-bar': {
            backgroundColor: getMetricColor(metric),
            borderRadius: 4,
          },
        }}
      />
    </div>
  );

  const MainMetricsTable = () => (
    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} sx={{ mt: 3 }}>
      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell><strong>Symbol</strong></td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell><strong>Company</strong></td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell><strong>Sector</strong></td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center"><strong>Composite Metric</strong></td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center"><strong>Quality</strong></td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center"><strong>Value</strong></td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center"><strong>Growth</strong></td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell><strong>Price</strong></td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell><strong>Market Cap</strong></td>
          </tr>
        </thead>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
          {stocks.map((stock, index) => (
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={stock.symbol} hover>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                <div  variant="subtitle2" sx={{ fontWeight: 'bold', color: '#1976d2' }}>
                  {stock.symbol}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                <div  variant="body2">
                  {stock.companyName?.substring(0, 30)}
                  {stock.companyName?.length > 30 ? '...' : ''}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label={stock.sector} 
                  size="small" 
                  variant="outlined"
                />
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <div  
                    variant="h6" 
                    sx={{ 
                      color: getMetricColor(stock.metrics.composite),
                      fontWeight: 'bold'
                    }}
                  >
                    {stock.metrics.composite.toFixed(3)}
                  </div>
                  <div  title={`Confidence: ${stock.metadata.confidence.toFixed(2)}`}>
                    <button className="p-2 rounded-full hover:bg-gray-100" size="small">
                      <Info fontSize="small" />
                    </button>
                  </div>
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                <div  sx={{ color: getMetricColor(stock.metrics.quality) }}>
                  {stock.metrics.quality.toFixed(3)}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                <div  sx={{ color: getMetricColor(stock.metrics.value) }}>
                  {stock.metrics.value.toFixed(3)}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                <div  sx={{ color: getMetricColor(stock.metrics.growth || 0) }}>
                  {(stock.metrics.growth || 0).toFixed(3)}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                ${stock.currentPrice?.toFixed(2) || 'N/A'}
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                {stock.marketCap ? `$${(stock.marketCap / 1e9).toFixed(1)}B` : 'N/A'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const SectorAnalysis = () => (
    <div className="grid" container spacing={3} sx={{ mt: 2 }}>
      {sectors.map((sector) => (
        <div className="grid" item xs={12} md={6} lg={4} key={sector.sector}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                {sector.sector}
              </div>
              <div  variant="body2" color="textSecondary" gutterBottom>
                {sector.stockCount} stocks
              </div>
              
              <MetricProgressBar 
                metric={parseFloat(sector.averageMetrics.composite)} 
                label="Composite"
                icon={<Assessment />}
              />
              <MetricProgressBar 
                metric={parseFloat(sector.averageMetrics.quality)} 
                label="Quality"
                icon={<AccountBalance />}
              />
              <MetricProgressBar 
                metric={parseFloat(sector.averageMetrics.value)} 
                label="Value"
                icon={<AttachMoney />}
              />
              <MetricProgressBar 
                metric={parseFloat(sector.averageMetrics.growth || 0)} 
                label="Growth"
                icon={<TrendingUp />}
              />
              
              <div  sx={{ mt: 2, display: 'flex', justifyContent: 'space-between' }}>
                <div  variant="caption">
                  Range: {sector.metricRange.min} - {sector.metricRange.max}
                </div>
                <div  variant="caption">
                  Vol: {sector.metricRange.volatility}
                </div>
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );

  const TopStocks = () => (
    <div className="grid" container spacing={3} sx={{ mt: 2 }}>
      {Object.entries(topStocks).map(([category, stocks]) => (
        <div className="grid" item xs={12} md={6} key={category}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom sx={{ textTransform: 'capitalize' }}>
                Top {category === 'composite' ? 'Overall' : category} Stocks
              </div>
              <div  sx={{ maxHeight: 400, overflow: 'auto' }}>
                {stocks.slice(0, 10).map((stock, index) => (
                  <div  
                    key={stock.symbol} 
                    sx={{ 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center',
                      py: 1,
                      borderBottom: index < 9 ? '1px solid #eee' : 'none'
                    }}
                  >
                    <div>
                      <div  variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                        {index + 1}. {stock.symbol}
                      </div>
                      <div  variant="caption" color="textSecondary">
                        {stock.companyName?.substring(0, 25)}
                        {stock.companyName?.length > 25 ? '...' : ''}
                      </div>
                    </div>
                    <div  sx={{ textAlign: 'right' }}>
                      <div  
                        variant="body2" 
                        sx={{ 
                          color: getMetricColor(stock.categoryMetric),
                          fontWeight: 'bold'
                        }}
                      >
                        {stock.categoryMetric.toFixed(3)}
                      </div>
                      <div  variant="caption" color="textSecondary">
                        {stock.sector}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );

  if (error) {
    return (
      <div className="container mx-auto" maxWidth="lg" sx={{ mt: 4 }}>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">
          Error loading metrics: {error}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="lg" sx={{ mt: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h3" component="h1" gutterBottom>
          Institutional-Grade Stock Metrics
        </div>
        <div  variant="subtitle1" color="textSecondary">
          Advanced multi-factor analysis based on academic research and institutional methodology
        </div>
      </div>

      {/* Navigation Tabs */}
      <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <div className="border-b border-gray-200" value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)}>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Stock Metrics" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Sector Analysis" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Top Performers" />
        </div>
      </div>

      {/* Filters for Stock Metrics Tab */}
      {activeTab === 0 && (
        <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3, mb: 3 }}>
          <div className="grid" container spacing={2} alignItems="center">
            <div className="grid" item xs={12} sm={3}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                label="Search Symbol/Company"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                size="small"
              />
            </div>
            <div className="grid" item xs={12} sm={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Sector</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={selectedSector}
                  label="Sector"
                  onChange={(e) => setSelectedSector(e.target.value)}
                >
                  <option  value="">All Sectors</option>
                  <option  value="Technology">Technology</option>
                  <option  value="Healthcare">Healthcare</option>
                  <option  value="Financial Services">Financial Services</option>
                  <option  value="Consumer Cyclical">Consumer Cyclical</option>
                  <option  value="Industrials">Industrials</option>
                  <option  value="Communication Services">Communication Services</option>
                  <option  value="Consumer Defensive">Consumer Defensive</option>
                  <option  value="Energy">Energy</option>
                  <option  value="Utilities">Utilities</option>
                  <option  value="Real Estate">Real Estate</option>
                  <option  value="Basic Materials">Basic Materials</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={12} sm={2}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                label="Min Metric"
                type="number"
                value={minMetric}
                onChange={(e) => setMinMetric(Number(e.target.value))}
                size="small"
                inputProps={{ min: 0, max: 1, step: 0.01 }}
              />
            </div>
            <div className="grid" item xs={12} sm={2}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                label="Max Metric"
                type="number"
                value={maxMetric}
                onChange={(e) => setMaxMetric(Number(e.target.value))}
                size="small"
                inputProps={{ min: 0, max: 1, step: 0.01 }}
              />
            </div>
            <div className="grid" item xs={12} sm={2}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Sort By</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={sortBy}
                  label="Sort By"
                  onChange={(e) => setSortBy(e.target.value)}
                >
                  <option  value="composite_metric">Composite Metric</option>
                  <option  value="quality_metric">Quality Metric</option>
                  <option  value="value_metric">Value Metric</option>
                  <option  value="market_cap">Market Cap</option>
                  <option  value="symbol">Symbol</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Content based on active tab */}
      {loading ? (
        <div  sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
        </div>
      ) : (
        <>
          {activeTab === 0 && <MainMetricsTable />}
          {activeTab === 1 && <SectorAnalysis />}
          {activeTab === 2 && <TopStocks />}
        </>
      )}

      {/* Pagination for Stock Metrics */}
      {activeTab === 0 && totalPages > 1 && (
        <div  sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
          <div  variant="body2" sx={{ mt: 1 }}>
            Page {page} of {totalPages}
          </div>
          {/* Add pagination controls here if needed */}
        </div>
      )}

      {/* Legend */}
      <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, mt: 4, backgroundColor: '#f5f5f5' }}>
        <div  variant="h6" gutterBottom>
          Metrics Methodology
        </div>
        <div className="grid" container spacing={2}>
          <div className="grid" item xs={12} sm={6} md={6}>
            <div  variant="subtitle2">Quality Metric</div>
            <div  variant="caption">
              Financial statement quality, balance sheet strength, profitability, management effectiveness using Piotroski F-Score, Altman Z-Score analysis
            </div>
          </div>
          <div className="grid" item xs={12} sm={6} md={6}>
            <div  variant="subtitle2">Value Metric</div>
            <div  variant="caption">
              Traditional multiples (P/E, P/B, EV/EBITDA), DCF intrinsic value, dividend discount model, and peer comparison analysis
            </div>
          </div>
          <div className="grid" item xs={12} sm={6} md={6}>
            <div  variant="subtitle2">Growth Metric</div>
            <div  variant="caption">
              Revenue growth analysis, earnings growth quality, fundamental growth drivers, and market expansion potential based on academic research
            </div>
          </div>
        </div>
        
        <div  sx={{ mt: 2 }}>
          <div  variant="subtitle2" gutterBottom>
            Metric Ranges (0-1 Scale):
          </div>
          <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {getMetricChip(0.9, 'Excellent (0.8-1.0)')}
            {getMetricChip(0.75, 'Good (0.7-0.79)')}
            {getMetricChip(0.65, 'Fair (0.6-0.69)')}
            {getMetricChip(0.55, 'Below Average (0.5-0.59)')}
            {getMetricChip(0.4, 'Poor (0.0-0.49)')}
          </div>
        </div>
      </div>
    </div>
  );
};

export default MetricsDashboard;