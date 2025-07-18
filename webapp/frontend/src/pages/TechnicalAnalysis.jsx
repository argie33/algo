import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { createComponentLogger } from '../utils/errorLogger';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Alert,
  TextField,
  Button,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  InputAdornment,
  TablePagination,
  Divider
} from '@mui/material';
import {
  ExpandMore,
  Search,
  FilterList,
  Clear,
  TrendingUp,
  TrendingDown,
  HorizontalRule,
  ShowChart,
  InfoOutlined
} from '@mui/icons-material';
import { formatNumber, formatDate, getTechStatus } from '../utils/formatters';
import { getTechnicalData } from '../services/api';
import { useNavigate } from 'react-router-dom';

function TechnicalAnalysis() {
  const logger = createComponentLogger('TechnicalAnalysis');
  const [timeframe, setTimeframe] = useState('daily');
  const [symbolFilter, setSymbolFilter] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [orderBy, setOrderBy] = useState('symbol');
  const [order, setOrder] = useState('asc');
  const [activeFilters, setActiveFilters] = useState(0);
  const [expandedRow, setExpandedRow] = useState(null);
  const navigate = useNavigate();
  // --- FIX: Move these above useQuery ---
  const [indicatorFilter, setIndicatorFilter] = useState('');
  const [indicatorMin, setIndicatorMin] = useState('');
  const [indicatorMax, setIndicatorMax] = useState('');

  // Fetch technical data
  const { data: technicalData, isLoading, error, refetch } = useQuery({
    queryKey: ['technicalAnalysis', timeframe, symbolFilter, indicatorFilter, indicatorMin, indicatorMax, page, rowsPerPage, orderBy, order],
    queryFn: async () => {
      // Map frontend parameters to backend parameters
      const params = {
        page: page + 1,
        limit: rowsPerPage,
        symbol: symbolFilter || undefined,
        sortBy: orderBy,
        sortOrder: order
      };
      
      // Map indicator filters to backend parameter names
      if (indicatorFilter) {
        switch (indicatorFilter) {
          case 'rsi':
            if (indicatorMin) params.rsi_min = indicatorMin;
            if (indicatorMax) params.rsi_max = indicatorMax;
            break;
          case 'macd':
            if (indicatorMin) params.macd_min = indicatorMin;
            if (indicatorMax) params.macd_max = indicatorMax;
            break;
          case 'sma_20':
            if (indicatorMin) params.sma_min = indicatorMin;
            if (indicatorMax) params.sma_max = indicatorMax;
            break;
          default:
            // For other indicators, we'll need to add specific mappings
            break;
        }
      }
      
      console.log('TechnicalAnalysis: calling getTechnicalData with params:', params);
      const result = await getTechnicalData(timeframe, params);
      console.log('TechnicalAnalysis: getTechnicalData result:', result);
      
      if (Array.isArray(result)) return { data: result };
      if (!Array.isArray(result.data)) return { ...result, data: [] };
      return result;
    },
    onError: (error) => logger.queryError('technicalAnalysis', error, { timeframe, symbolFilter, page }),
    refetchInterval: 300000,
    retry: 2,
    staleTime: 60000
  });

  useEffect(() => {
    // Count active filters (excluding default timeframe)
    setActiveFilters(symbolFilter ? 1 : 0);
  }, [symbolFilter]);

  // Update activeFilters count
  useEffect(() => {
    let count = 0;
    if (symbolFilter) count++;
    if (indicatorFilter) count++;
    if (indicatorMin || indicatorMax) count++;
    setActiveFilters(count);
  }, [symbolFilter, indicatorFilter, indicatorMin, indicatorMax]);

  // Log the technicalData and error for debugging
  useEffect(() => {
    if (technicalData) {
      // eslint-disable-next-line no-console
      console.log('TechnicalAnalysis: technicalData', technicalData);
    }
    if (error) {
      // eslint-disable-next-line no-console
      console.error('TechnicalAnalysis: error', error);
    }
  }, [technicalData, error]);

  const handleSearch = () => {
    setSymbolFilter(searchInput.trim());
    setPage(0);
  };
  const handleClearSearch = () => {
    setSearchInput('');
    setSymbolFilter('');
    setPage(0);
  };
  const handleTimeframeChange = (e) => {
    setTimeframe(e.target.value);
    setPage(0);
  };
  const handleSort = (column) => {
    const isAsc = orderBy === column && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(column);
  };
  const handlePageChange = (event, newPage) => {
    setPage(newPage);
  };
  const handleRowsPerPageChange = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  // Table columns (updated to match backend structure)
  const columns = [
    { id: 'symbol', label: 'Symbol', sortable: true },
    { id: 'date', label: 'Date', sortable: true, format: formatDate },
    { id: 'rsi', label: 'RSI', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'macd', label: 'MACD', sortable: true, format: (val) => val ? formatNumber(val, 4) : 'N/A' },
    { id: 'macd_signal', label: 'MACD Signal', sortable: true, format: (val) => val ? formatNumber(val, 4) : 'N/A' },
    { id: 'macd_hist', label: 'MACD Hist', sortable: true, format: (val) => val ? formatNumber(val, 4) : 'N/A' },
    { id: 'adx', label: 'ADX', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'atr', label: 'ATR', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'mfi', label: 'MFI', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'roc', label: 'ROC', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'mom', label: 'MOM', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'bbands_upper', label: 'BB Upper', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'bbands_middle', label: 'BB Middle', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'bbands_lower', label: 'BB Lower', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'sma_10', label: 'SMA 10', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'sma_20', label: 'SMA 20', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'sma_50', label: 'SMA 50', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'sma_150', label: 'SMA 150', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'sma_200', label: 'SMA 200', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'ema_4', label: 'EMA 4', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'ema_9', label: 'EMA 9', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'ema_21', label: 'EMA 21', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'ad', label: 'A/D', sortable: true, format: (val) => val ? formatNumber(val, 0) : 'N/A' },
    { id: 'cmf', label: 'CMF', sortable: true, format: (val) => val ? formatNumber(val, 3) : 'N/A' },
    { id: 'td_sequential', label: 'TD Seq', sortable: true, format: (val) => val ? formatNumber(val, 0) : 'N/A' },
    { id: 'td_combo', label: 'TD Combo', sortable: true, format: (val) => val ? formatNumber(val, 0) : 'N/A' },
    { id: 'marketwatch', label: 'MW', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'dm', label: 'DM', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'pivot_high', label: 'Pivot H', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'pivot_low', label: 'Pivot L', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'pivot_high_triggered', label: 'Pivot H Triggered', sortable: true, format: (val) => val ? 'Yes' : 'No' },
    { id: 'pivot_low_triggered', label: 'Pivot L Triggered', sortable: true, format: (val) => val ? 'Yes' : 'No' }
  ];

  // Helper to map icon string to MUI icon component
  const getIconComponent = (icon) => {
    switch (icon) {
      case 'up':
        return <TrendingUp fontSize="small" color="inherit" />;
      case 'down':
        return <TrendingDown fontSize="small" color="inherit" />;
      case 'flat':
        return <HorizontalRule fontSize="small" color="inherit" />;
      case 'neutral':
        return <ShowChart fontSize="small" color="inherit" />;
      case 'info':
      default:
        return <InfoOutlined fontSize="small" color="inherit" />;
    }
  };

  // --- Accordion rendering for each row (fixed syntax, requirements met) ---
  // Simplified data access: API always returns { success: true, data: [...] }
  const technicalList = technicalData?.data || [];
  
  // Debug logging
  console.log('TechnicalAnalysis data structure:', {
    hasTechnicalData: !!technicalData,
    success: technicalData?.success,
    dataIsArray: Array.isArray(technicalData?.data),
    dataLength: technicalData?.data?.length || 0,
    pagination: technicalData?.pagination,
    metadata: technicalData?.metadata,
    firstItem: technicalData?.data?.[0]
  });

  const renderAccordionTable = () => (
    <div  sx={{ width: '100%' }}>
      {technicalList.map((row, idx) => (
        <Accordion
          key={row.symbol + '-' + row.date + '-' + idx}
          expanded={expandedRow === idx}
          onChange={() => setExpandedRow(expandedRow === idx ? null : idx)}
          sx={{ mb: 1, borderLeft: 4, borderColor: row.rsi > 70 ? 'error.main' : row.rsi < 30 ? 'primary.main' : 'grey.300', boxShadow: expandedRow === idx ? 6 : 1 }}
        >
          <AccordionSummary expandIcon={<ExpandMore />} sx={{ backgroundColor: expandedRow === idx ? 'grey.100' : 'grey.50', '&:hover': { backgroundColor: 'grey.200' } }}>
            <div className="grid" container alignItems="center" spacing={2}>
              <div className="grid" item xs={2}>
                <div  variant="h6" fontWeight="bold">{row.symbol}</div>
                {row.company_name && (
                  <div  variant="body2" color="text.secondary">{row.company_name}</div>
                )}
                <div  variant="caption" color="text.secondary">{formatDate(row.date)}</div>
              </div>
              <div className="grid" item xs={2}>
                <div  display="flex" alignItems="center" gap={1}>
                  {getIconComponent(getTechStatus('rsi', row.rsi).icon)}
                  <div  variant="body2" color={getTechStatus('rsi', row.rsi).color} fontWeight="bold">
                    RSI: {formatNumber(row.rsi)}
                  </div>
                </div>
              </div>
              <div className="grid" item xs={2}>
                <div  display="flex" alignItems="center" gap={1}>
                  {getIconComponent(getTechStatus('macd', row.macd).icon)}
                  <div  variant="body2" color={getTechStatus('macd', row.macd).color} fontWeight="bold">
                    MACD: {formatNumber(row.macd)}
                  </div>
                </div>
              </div>
              <div className="grid" item xs={2}>
                <div  display="flex" alignItems="center" gap={1}>
                  {getIconComponent(getTechStatus('adx', row.adx).icon)}
                  <div  variant="body2" color={getTechStatus('adx', row.adx).color} fontWeight="bold">
                    ADX: {formatNumber(row.adx)}
                  </div>
                </div>
              </div>
              <div className="grid" item xs={2}>
                <div  display="flex" alignItems="center" gap={1}>
                  {getIconComponent(getTechStatus('atr', row.atr).icon)}
                  <div  variant="body2" color={getTechStatus('atr', row.atr).color} fontWeight="bold">
                    ATR: {formatNumber(row.atr)}
                  </div>
                </div>
              </div>
              <div className="grid" item xs={2}>
                <div  display="flex" alignItems="center" gap={1}>
                  {getIconComponent(getTechStatus('mfi', row.mfi).icon)}
                  <div  variant="body2" color={getTechStatus('mfi', row.mfi).color} fontWeight="bold">
                    MFI: {formatNumber(row.mfi)}
                  </div>
                </div>
              </div>
              <div className="grid" item xs={12}>
                <hr className="border-gray-200" sx={{ my: 1 }} />
                <div className="grid" container spacing={2}>
                  <div className="grid" item xs={2}>
                    <div  display="flex" alignItems="center" gap={1}>
                      <div  variant="body2" color="text.secondary">Price:</div>
                      <div  variant="body2" fontWeight="bold">
                        ${row.current_price ? formatNumber(row.current_price, 2) : 'N/A'}
                      </div>
                    </div>
                  </div>
                  <div className="grid" item xs={2}>
                    <div  display="flex" alignItems="center" gap={1}>
                      {row.price_direction && (
                        getIconComponent(row.price_direction)
                      )}
                      <div  
                        variant="body2" 
                        color={row.price_direction === 'up' ? 'success.main' : row.price_direction === 'down' ? 'error.main' : 'text.secondary'}
                        fontWeight="bold"
                      >
                        {row.price_change_percent ? `${row.price_change_percent > 0 ? '+' : ''}${formatNumber(row.price_change_percent, 2)}%` : 'N/A'}
                      </div>
                    </div>
                  </div>
                  <div className="grid" item xs={2}>
                    <div  display="flex" alignItems="center" gap={1}>
                      <div  variant="body2" color="text.secondary">Range:</div>
                      <div  variant="body2" fontWeight="bold">
                        {row.high_price && row.low_price ? `${formatNumber(row.low_price, 2)} - ${formatNumber(row.high_price, 2)}` : 'N/A'}
                      </div>
                    </div>
                  </div>
                  <div className="grid" item xs={2}>
                    <div  display="flex" alignItems="center" gap={1}>
                      <div  variant="body2" color="text.secondary">Volume:</div>
                      <div  variant="body2" fontWeight="bold">
                        {row.volume ? formatNumber(row.volume) : 'N/A'}
                      </div>
                    </div>
                  </div>
                  <div className="grid" item xs={2}>
                    <div  display="flex" alignItems="center" gap={1}>
                      <div  variant="body2" color="text.secondary">Open:</div>
                      <div  variant="body2" fontWeight="bold">
                        ${row.open_price ? formatNumber(row.open_price, 2) : 'N/A'}
                      </div>
                    </div>
                  </div>
                  <div className="grid" item xs={2}>
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" size="small" onClick={(e) => { e.stopPropagation(); navigate(`/technical-history/${row.symbol}`); }}>
                      View History
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </AccordionSummary>
          <AccordionDetails>
            <div className="grid" container spacing={2}>
              {columns.filter(col => col.id !== 'symbol' && col.id !== 'date').map((col) => (
                <div className="grid" item xs={12} sm={6} md={3} key={col.id}>
                  <div className="bg-white shadow-md rounded-lg" variant="outlined" sx={{ height: '100%' }}>
                    <div className="bg-white shadow-md rounded-lg"Content>
                      <div  display="flex" alignItems="center" gap={1}>
                        {getIconComponent(getTechStatus(col.id, row[col.id]).icon)}
                        <div  variant="subtitle2">{col.label}</div>
                      </div>
                      <div  variant="h6" color={getTechStatus(col.id, row[col.id]).color} fontWeight="bold">
                        {col.format ? col.format(row[col.id]) : (row[col.id] !== undefined && row[col.id] !== null ? formatNumber(row[col.id]) : 'N/A')}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </AccordionDetails>
        </Accordion>
      ))}
    </div>
  );

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      <div  display="flex" alignItems="flex-start" gap={4}>
        {/* Left filter/search panel */}
        <div  minWidth={260} maxWidth={320}>
          <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>Filter Technicals</div>
              <div className="mb-4" fullWidth size="small" sx={{ mb: 2 }}>
                <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" value={timeframe} label="Timeframe" onChange={handleTimeframeChange}>
                  <option  value="daily">Daily</option>
                  <option  value="weekly">Weekly</option>
                  <option  value="monthly">Monthly</option>
                </select>
              </div>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                label="Search Symbol"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                size="small"
                fullWidth
                sx={{ mb: 2 }}
                placeholder="e.g., AAPL"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  )
                }}
              />
              <div className="mb-4" fullWidth size="small" sx={{ mb: 2 }}>
                <label className="block text-sm font-medium text-gray-700 mb-1">Indicator</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" value={indicatorFilter} label="Indicator" onChange={e => setIndicatorFilter(e.target.value)}>
                  <option  value="">All</option>
                  <option  value="rsi">RSI</option>
                  <option  value="macd">MACD</option>
                  <option  value="adx">ADX</option>
                  <option  value="atr">ATR</option>
                  <option  value="mfi">MFI</option>
                  <option  value="roc">ROC</option>
                  <option  value="mom">MOM</option>
                  <option  value="bbands_upper">BB Upper</option>
                  <option  value="bbands_middle">BB Middle</option>
                  <option  value="bbands_lower">BB Lower</option>
                  <option  value="sma_10">SMA 10</option>
                  <option  value="sma_20">SMA 20</option>
                  <option  value="sma_50">SMA 50</option>
                  <option  value="sma_150">SMA 150</option>
                  <option  value="sma_200">SMA 200</option>
                  <option  value="ema_4">EMA 4</option>
                  <option  value="ema_9">EMA 9</option>
                  <option  value="ema_21">EMA 21</option>
                  <option  value="ad">A/D</option>
                  <option  value="cmf">CMF</option>
                  <option  value="td_sequential">TD Seq</option>
                  <option  value="td_combo">TD Combo</option>
                  <option  value="marketwatch">MW</option>
                  <option  value="dm">DM</option>
                  <option  value="pivot_high">Pivot H</option>
                  <option  value="pivot_low">Pivot L</option>
                  <option  value="pivot_high_triggered">Pivot H Triggered</option>
                  <option  value="pivot_low_triggered">Pivot L Triggered</option>
                </select>
              </div>
              <div  display="flex" gap={1} mb={2}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  label="Min Value"
                  type="number"
                  value={indicatorMin}
                  onChange={e => setIndicatorMin(e.target.value)}
                  size="small"
                  fullWidth
                  disabled={!indicatorFilter}
                />
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  label="Max Value"
                  type="number"
                  value={indicatorMax}
                  onChange={e => setIndicatorMax(e.target.value)}
                  size="small"
                  fullWidth
                  disabled={!indicatorFilter}
                />
              </div>
              <div  display="flex" gap={1} mb={2}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" onClick={handleSearch} startIcon={<Search />} disabled={isLoading}>
                  {symbolFilter ? 'Search' : 'Filter'}
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" startIcon={<Clear />} onClick={handleClearSearch} disabled={isLoading || !symbolFilter}>
                  Clear
                </button>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={`${activeFilters} Filters`} color={activeFilters > 0 ? 'primary' : 'default'} icon={<FilterList />} />
              </div>
            </div>
          </div>
        </div>
        {/* Main content: overview + table */}
        <div  flex={1}>
          <div  variant="h4" gutterBottom sx={{ mb: 2, mt: 1, textAlign: 'left' }}>Technical Analysis</div>
          <hr className="border-gray-200" sx={{ mb: 2 }} />
          {/* Error/Loading/Empty states */}
          {error && (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>Error loading technical data: {error.message}</div>
          )}
          {isLoading ? (
            <div  display="flex" flexDirection="column" alignItems="center" p={4}>
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" sx={{ mb: 2 }} />
              <div  variant="body2" color="text.secondary">Loading technical data...</div>
            </div>
          ) : (
            <>
              {technicalList.length === 0 ? (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning" sx={{ mb: 2 }}>No technical data found.</div>
              ) : (
                renderAccordionTable()
              )}
              {/* Pagination */}
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"lePagination
                component="div"
                count={technicalData?.pagination?.total || 0}
                page={page}
                onPageChange={handlePageChange}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={handleRowsPerPageChange}
                rowsPerPageOptions={[10, 25, 50, 100]}
                sx={{ mt: 2 }}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default TechnicalAnalysis;
