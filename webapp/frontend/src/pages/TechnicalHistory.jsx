import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getPriceHistory } from '../services/api';
import {
  Container,
  Typography,
  Box,
  Card,
  CardContent,
  Button,
  Paper,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  TablePagination,
  TextField,
  CircularProgress,
  Alert,
  Chip,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Tabs,
  Tab,
  IconButton,
  Tooltip,
  Switch,
  FormControlLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Divider,
  Stack,
  InputAdornment
} from '@mui/material';
import {
  ArrowBack,
  Search,
  FilterList,
  ViewColumn,
  GetApp,
  TrendingUp,
  TrendingDown,
  ShowChart,
  TableChart,
  ViewModule,
  ExpandMore,
  Clear,
  DateRange
} from '@mui/icons-material';
import { formatNumber, formatDate, formatCurrency } from '../utils/formatters';

// Main component
function PriceHistory() {
  const { symbol } = useParams();
  const navigate = useNavigate();
  const theme = { palette: { mode: "light" } };
  
  // Core state
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [total, setTotal] = useState(0);
  
  // Pagination state
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  
  // Filter state
  const [searchTerm, setSearchTerm] = useState('');
  const [timeframe, setTimeframe] = useState('daily');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [activeTab, setActiveTab] = useState(0);
  const [viewMode, setViewMode] = useState('table'); // 'table' or 'cards'
  const [showFilters, setShowFilters] = useState(false);
  
  // Technical filters
  const [techFilters, setTechFilters] = useState({
    rsi_min: '',
    rsi_max: '',
    macd_min: '',
    macd_max: '',
    sma_min: '',
    sma_max: ''
  });
  
  // Column visibility
  const [visibleColumns, setVisibleColumns] = useState({
    date: true,
    close: true,
    volume: true,
    rsi: true,
    macd: true,
    sma_20: true,
    sma_50: true,
    ema_12: true,
    bollinger_middle: false,
    stochastic_k: false,
    adx: false,
    atr: false
  });

  // Define available columns with categories
  const columnCategories = {
    price: [
      { id: 'date', label: 'Date', format: formatDate },
      { id: 'open', label: 'Open', format: formatCurrency },
      { id: 'high', label: 'High', format: formatCurrency },
      { id: 'low', label: 'Low', format: formatCurrency },
      { id: 'close', label: 'Close', format: formatCurrency },
      { id: 'volume', label: 'Volume', format: (val) => formatNumber(val, 0) }
    ],
    momentum: [
      { id: 'rsi', label: 'RSI', format: (val) => formatNumber(val, 2) },
      { id: 'macd', label: 'MACD', format: (val) => formatNumber(val, 4) },
      { id: 'macd_signal', label: 'MACD Signal', format: (val) => formatNumber(val, 4) },
      { id: 'stochastic_k', label: 'Stoch %K', format: (val) => formatNumber(val, 2) },
      { id: 'stochastic_d', label: 'Stoch %D', format: (val) => formatNumber(val, 2) },
      { id: 'williams_r', label: 'Williams %R', format: (val) => formatNumber(val, 2) },
      { id: 'cci', label: 'CCI', format: (val) => formatNumber(val, 2) },
      { id: 'momentum', label: 'Momentum', format: (val) => formatNumber(val, 2) },
      { id: 'roc', label: 'ROC', format: (val) => formatNumber(val, 2) }
    ],
    trend: [
      { id: 'sma_20', label: 'SMA 20', format: formatCurrency },
      { id: 'sma_50', label: 'SMA 50', format: formatCurrency },
      { id: 'ema_12', label: 'EMA 12', format: formatCurrency },
      { id: 'ema_26', label: 'EMA 26', format: formatCurrency },
      { id: 'adx', label: 'ADX', format: (val) => formatNumber(val, 2) }
    ],
    volatility: [
      { id: 'bollinger_upper', label: 'BB Upper', format: formatCurrency },
      { id: 'bollinger_middle', label: 'BB Middle', format: formatCurrency },
      { id: 'bollinger_lower', label: 'BB Lower', format: formatCurrency },
      { id: 'atr', label: 'ATR', format: (val) => formatNumber(val, 4) }
    ],
    volume: [
      { id: 'obv', label: 'OBV', format: (val) => formatNumber(val, 0) },
      { id: 'mfi', label: 'MFI', format: (val) => formatNumber(val, 2) },
      { id: 'ad', label: 'A/D', format: (val) => formatNumber(val, 0) },
      { id: 'cmf', label: 'CMF', format: (val) => formatNumber(val, 4) }
    ]
  };

  // Get all available columns
  const allColumns = Object.values(columnCategories).flat();
  
  // Get visible columns for display
  const displayColumns = useMemo(() => {
    return allColumns.filter(col => visibleColumns[col.id]);
  }, [visibleColumns]);

  // Fetch data function
  const fetchData = async () => {
    if (!symbol) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const params = {
        symbol: symbol.toUpperCase(),
        page: page + 1,
        limit: rowsPerPage,
        start_date: dateFrom || undefined,
        end_date: dateTo || undefined,
        ...Object.fromEntries(
          Object.entries(priceFilters).filter(([_, value]) => value !== '')
        )
      };

      console.log('🔍 Fetching price history:', { timeframe, params });
      const result = await getPriceHistory(timeframe, params);
      
      if (result && result.data) {
        setData(result.data);
        setTotal(result.pagination?.total || 0);
      } else {
        setData([]);
        setTotal(0);
      }
    } catch (err) {
      console.error('❌ Error fetching price history:', err);
      setError(err.message || 'Failed to load price history');
      setData([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  // Effects
  useEffect(() => {
    fetchData();
  }, [symbol, timeframe, page, rowsPerPage, dateFrom, dateTo, priceFilters]);

  // Filter data based on search term
  const filteredData = useMemo(() => {
    if (!searchTerm) return data;
    return data.filter(row => 
      Object.values(row).some(value => 
        String(value).toLowerCase().includes(searchTerm.toLowerCase())
      )
    );
  }, [data, searchTerm]);

  // Event handlers
  const handlePageChange = (event, newPage) => setPage(newPage);
  const handleRowsPerPageChange = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const handleTimeframeChange = (event) => {
    setTimeframe(event.target.value);
    setPage(0);
  };

  const handlePriceFilterChange = (field, value) => {
    setPriceFilters(prev => ({
      ...prev,
      [field]: value
    }));
    setPage(0);
  };

  const clearFilters = () => {
    setDateFrom('');
    setDateTo('');
    setSearchTerm('');
    setPriceFilters({
      price_min: '',
      price_max: '',
      volume_min: '',
      volume_max: ''
    });
    setPage(0);
  };

  const toggleColumn = (columnId) => {
    setVisibleColumns(prev => ({
      ...prev,
      [columnId]: !prev[columnId]
    }));
  };

  const exportData = () => {
    if (!filteredData.length) return;
    
    const headers = displayColumns.map(col => col.label).join(',');
    const rows = filteredData.map(row => 
      displayColumns.map(col => {
        const value = row[col.id];
        return col.format ? col.format(value) : (value || '');
      }).join(',')
    ).join('\n');
    
    const csv = `${headers}\n${rows}`;
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${symbol}_${timeframe}_price_history.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };


  // Render summary stats
  const renderSummaryStats = () => {
    if (!data.length) return null;
    
    const latest = data[0];
    const dayChange = data.length > 1 ? latest.close - data[1].close : 0;
    const dayChangePercent = data.length > 1 ? (dayChange / data[1].close) * 100 : 0;
    
    const stats = [
      { label: 'Latest Close', value: formatCurrency(latest.close), color: 'primary' },
      { label: 'Day Change', value: `${dayChange >= 0 ? '+' : ''}${formatCurrency(dayChange)}`, color: dayChange >= 0 ? 'success' : 'error' },
      { label: 'Day Change %', value: `${dayChangePercent >= 0 ? '+' : ''}${dayChangePercent.toFixed(2)}%`, color: dayChangePercent >= 0 ? 'success' : 'error' },
      { label: 'Volume', value: formatNumber(latest.volume, 0), color: 'info' }
    ];

    return (
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Latest Data ({formatDate(latest.date)})
          </div>
          <div className="grid" container spacing={2}>
            {stats.map((stat, index) => (
              <div className="grid" item xs={6} sm={3} key={index}>
                <div  textAlign="center">
                  <div  variant="h6" color={`${stat.color}.main`}>
                    {stat.value}
                  </div>
                  <div  variant="body2" color="text.secondary">
                    {stat.label}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  // Render table view
  const renderTableView = () => (
    <div className="bg-white shadow-md rounded-lg p-4" sx={{ width: '100%', overflow: 'hidden' }}>
      <div  sx={{ overflowX: 'auto' }}>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
              {displayColumns.map(column => (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell key={column.id} sx={{ fontWeight: 'bold', minWidth: 100 }}>
                  {column.label}
                </td>
              ))}
            </tr>
          </thead>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
            {filteredData.map((row, index) => (
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow hover key={`${row.date}-${index}`}>
                {displayColumns.map(column => {
                  const value = row[column.id];
                  
                  return (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell 
                      key={column.id} 
                      align={typeof value === 'number' ? 'right' : 'left'}
                    >
                      {column.format ? column.format(value) : (value || 'N/A')}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"lePagination
        component="div"
        count={total}
        page={page}
        onPageChange={handlePageChange}
        rowsPerPage={rowsPerPage}
        onRowsPerPageChange={handleRowsPerPageChange}
        rowsPerPageOptions={[10, 25, 50, 100]}
      />
    </div>
  );

  // Render card view
  const renderCardView = () => (
    <div>
      <div className="grid" container spacing={2}>
        {filteredData.map((row, index) => (
          <div className="grid" item xs={12} sm={6} md={4} key={`${row.date}-${index}`}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="h6" gutterBottom>
                  {formatDate(row.date)}
                </div>
                <div className="flex flex-col space-y-2" spacing={1}>
                  <div  display="flex" justifyContent="space-between">
                    <div  variant="body2">Close:</div>
                    <div  variant="body2" fontWeight="bold">
                      {formatCurrency(row.close)}
                    </div>
                  </div>
                  <div  display="flex" justifyContent="space-between">
                    <div  variant="body2">Volume:</div>
                    <div  variant="body2">
                      {formatNumber(row.volume, 0)}
                    </div>
                  </div>
                  <div  display="flex" justifyContent="space-between">
                    <div  variant="body2">Open:</div>
                    <div  variant="body2">
                      {formatCurrency(row.open)}
                    </div>
                  </div>
                  <div  display="flex" justifyContent="space-between">
                    <div  variant="body2">High:</div>
                    <div  variant="body2" color="success.main">
                      {formatCurrency(row.high)}
                    </div>
                  </div>
                  <div  display="flex" justifyContent="space-between">
                    <div  variant="body2">Low:</div>
                    <div  variant="body2" color="error.main">
                      {formatCurrency(row.low)}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
      <div  display="flex" justifyContent="center" mt={3}>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"lePagination
          component="div"
          count={total}
          page={page}
          onPageChange={handlePageChange}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={handleRowsPerPageChange}
          rowsPerPageOptions={[6, 12, 24, 48]}
        />
      </div>
    </div>
  );

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 3 }}>
      {/* Header */}
      <div  display="flex" alignItems="center" justifyContent="space-between" mb={3}>
        <div  display="flex" alignItems="center" gap={2}>
          <button className="p-2 rounded-full hover:bg-gray-100" onClick={() => navigate(-1)}>
            <ArrowBack />
          </button>
          <div  variant="h4">
            Price History - {symbol}
          </div>
        </div>
        
        <div  display="flex" gap={1}>
          <div  title="Export Data">
            <button className="p-2 rounded-full hover:bg-gray-100" onClick={exportData} disabled={!data.length}>
              <GetApp />
            </button>
          </div>
          <div  title="Toggle View">
            <button className="p-2 rounded-full hover:bg-gray-100" onClick={() => setViewMode(viewMode === 'table' ? 'cards' : 'table')}>
              {viewMode === 'table' ? <ViewModule /> : <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leChart />}
            </button>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="grid" container spacing={2} alignItems="center">
            <div className="grid" item xs={12} sm={6} md={3}>
              <div className="mb-4" fullWidth size="small">
                <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" value={timeframe} onChange={handleTimeframeChange}>
                  <option  value="daily">Daily</option>
                  <option  value="weekly">Weekly</option>
                  <option  value="monthly">Monthly</option>
                </select>
              </div>
            </div>
            
            <div className="grid" item xs={12} sm={6} md={3}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                size="small"
                label="Search"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  ),
                  endAdornment: searchTerm && (
                    <InputAdornment position="end">
                      <button className="p-2 rounded-full hover:bg-gray-100" size="small" onClick={() => setSearchTerm('')}>
                        <Clear />
                      </button>
                    </InputAdornment>
                  )
                }}
              />
            </div>
            
            <div className="grid" item xs={12} sm={6} md={2}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                size="small"
                type="date"
                label="From Date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </div>
            
            <div className="grid" item xs={12} sm={6} md={2}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                size="small"
                type="date"
                label="To Date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                InputLabelProps={{ shrink: true }}
              />
            </div>
            
            <div className="grid" item xs={12} md={2}>
              <div  display="flex" gap={1}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined"
                  startIcon={<FilterList />}
                  onClick={() => setShowFilters(!showFilters)}
                  size="small"
                >
                  Filters
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined"
                  startIcon={<Clear />}
                  onClick={clearFilters}
                  size="small"
                >
                  Clear
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Advanced Filters */}
      {showFilters && (
        <Accordion expanded={showFilters}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <div>Advanced Filters & Column Selection</div>
          </AccordionSummary>
          <AccordionDetails>
            <div className="grid" container spacing={3}>
              {/* Price & Volume Filters */}
              <div className="grid" item xs={12} md={6}>
                <div  variant="h6" gutterBottom>Price & Volume Filters</div>
                <div className="grid" container spacing={2}>
                  <div className="grid" item xs={6}>
                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      fullWidth
                      size="small"
                      label="Min Price"
                      type="number"
                      step="0.01"
                      value={priceFilters.price_min}
                      onChange={(e) => handlePriceFilterChange('price_min', e.target.value)}
                    />
                  </div>
                  <div className="grid" item xs={6}>
                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      fullWidth
                      size="small"
                      label="Max Price"
                      type="number"
                      step="0.01"
                      value={priceFilters.price_max}
                      onChange={(e) => handlePriceFilterChange('price_max', e.target.value)}
                    />
                  </div>
                  <div className="grid" item xs={6}>
                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      fullWidth
                      size="small"
                      label="Min Volume"
                      type="number"
                      value={priceFilters.volume_min}
                      onChange={(e) => handlePriceFilterChange('volume_min', e.target.value)}
                    />
                  </div>
                  <div className="grid" item xs={6}>
                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      fullWidth
                      size="small"
                      label="Max Volume"
                      type="number"
                      value={priceFilters.volume_max}
                      onChange={(e) => handlePriceFilterChange('volume_max', e.target.value)}
                    />
                  </div>
                </div>
              </div>

              {/* Column Selection */}
              <div className="grid" item xs={12} md={6}>
                <div  variant="h6" gutterBottom>Visible Columns</div>
                <div className="border-b border-gray-200" value={activeTab} onChange={handleTabChange} variant="scrollable">
                  {Object.keys(columnCategories).map((category, index) => (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" key={category} label={category.charAt(0).toUpperCase() + category.slice(1)} />
                  ))}
                </div>
                <div  sx={{ mt: 2, maxHeight: 200, overflow: 'auto' }}>
                  {Object.entries(columnCategories).map(([category, columns], categoryIndex) => (
                    activeTab === categoryIndex && (
                      <div className="grid" container spacing={1} key={category}>
                        {columns.map(column => (
                          <div className="grid" item xs={6} key={column.id}>
                            <div className="mb-4"Label
                              control={
                                <input type="checkbox" className="toggle"
                                  checked={visibleColumns[column.id] || false}
                                  onChange={() => toggleColumn(column.id)}
                                  size="small"
                                />
                              }
                              label={column.label}
                            />
                          </div>
                        ))}
                      </div>
                    )
                  ))}
                </div>
              </div>
            </div>
          </AccordionDetails>
        </Accordion>
      )}

      {/* Summary Stats */}
      {renderSummaryStats()}

      {/* Main Content */}
      {loading ? (
        <div  display="flex" justifyContent="center" alignItems="center" minHeight={400}>
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={60} />
        </div>
      ) : error ? (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }}>
          {error}
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={fetchData} sx={{ ml: 2 }}>
            Retry
          </button>
        </div>
      ) : !data.length ? (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
          No technical data found for {symbol} in the {timeframe} timeframe.
        </div>
      ) : (
        <>
          <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Showing {filteredData.length} of {total} records
          </div>
          {viewMode === 'table' ? renderTableView() : renderCardView()}
        </>
      )}
    </div>
  );
}

export default PriceHistory;