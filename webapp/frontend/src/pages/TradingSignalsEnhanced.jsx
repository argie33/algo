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
  Chip,
  CircularProgress,
  Alert,
  Button,
  TextField,
  IconButton,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Divider,
  Stack,
  Paper,
  ToggleButton,
  ToggleButtonGroup,
  alpha
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  ShowChart,
  FilterList,
  Refresh,
  ViewModule,
  ViewList,
  Search,
  Clear,
  Assessment,
  AccountBalance
} from '@mui/icons-material';
import { api } from '../utils/api';
import MarketTimingPanel from '../components/trading/MarketTimingPanel';
import PositionManager from '../components/trading/PositionManager';
import SignalCardEnhanced from '../components/trading/SignalCardEnhanced';
import ExitZoneVisualizer from '../components/trading/ExitZoneVisualizer';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`trading-tabpanel-${index}`}
      aria-labelledby={`trading-tab-${index}`}
      {...other}
    >
      {value === index && (
        <div  sx={{ py: 3 }}>
          {children}
        </div>
      )}
    </div>
  );
}

const TradingSignalsEnhanced = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [signals, setSignals] = useState([]);
  const [positions, setPositions] = useState([]);
  const [marketData, setMarketData] = useState({});
  const [filters, setFilters] = useState({
    signalType: 'all',
    minStrength: 60,
    sector: 'all',
    inBuyZone: false,
    searchTerm: ''
  });
  const [viewMode, setViewMode] = useState('cards');
  const [watchlist, setWatchlist] = useState(new Set());

  // Load trading signals with enhanced O'Neill methodology
  const loadSignals = async () => {
    setLoading(true);
    try {
      const response = await api.get('/trading/signals/enhanced');
      const signalsData = response.data?.signals || [];
      
      // Process signals to include O'Neill specific fields
      const processedSignals = signalsData.map(signal => ({
        ...signal,
        pivot_price: signal.pivot_price || signal.entry_price,
        buy_zone_start: signal.pivot_price || signal.entry_price,
        buy_zone_end: (signal.pivot_price || signal.entry_price) * 1.05,
        exit_zone_1_price: (signal.entry_price || signal.pivot_price) * 1.20,
        exit_zone_2_price: (signal.entry_price || signal.pivot_price) * 1.25,
        initial_stop: (signal.entry_price || signal.pivot_price) * 0.93,
        volume_surge_pct: ((signal.volume / signal.avg_volume_50d) - 1) * 100,
        is_in_buy_zone: signal.current_price >= signal.pivot_price && 
                       signal.current_price <= signal.pivot_price * 1.05
      }));
      
      setSignals(processedSignals);
    } catch (error) {
      console.error('Error loading signals:', error);
    } finally {
      setLoading(false);
    }
  };

  // Load active positions
  const loadPositions = async () => {
    try {
      const response = await api.get('/trading/positions/active');
      setPositions(response.data?.positions || []);
    } catch (error) {
      console.error('Error loading positions:', error);
    }
  };

  // Load market timing data
  const loadMarketData = async () => {
    try {
      const response = await api.get('/trading/market-timing');
      setMarketData(response.data || {});
    } catch (error) {
      console.error('Error loading market data:', error);
    }
  };

  useEffect(() => {
    loadSignals();
    loadPositions();
    loadMarketData();
  }, []);

  // Filter signals based on criteria
  const filteredSignals = signals.filter(signal => {
    if (filters.signalType !== 'all' && signal.signal !== filters.signalType) return false;
    if (signal.signal_strength * 100 < filters.minStrength) return false;
    if (filters.sector !== 'all' && signal.sector !== filters.sector) return false;
    if (filters.inBuyZone && !signal.is_in_buy_zone) return false;
    if (filters.searchTerm && !signal.symbol.toLowerCase().includes(filters.searchTerm.toLowerCase()) &&
        !signal.company_name?.toLowerCase().includes(filters.searchTerm.toLowerCase())) return false;
    return true;
  });

  const buySignals = filteredSignals.filter(s => s.signal === 'Buy');
  const sellSignals = filteredSignals.filter(s => s.signal === 'Sell');

  const handleUpdatePosition = (positionData) => {
    // Handle position updates
    console.log('Updating position:', positionData);
  };

  const handleClosePosition = (exitData) => {
    // Handle position closure
    console.log('Closing position:', exitData);
  };

  const handleTrade = (signal) => {
    // Handle trade execution
    console.log('Executing trade:', signal);
  };

  const toggleWatchlist = (symbol) => {
    const newWatchlist = new Set(watchlist);
    if (newWatchlist.has(symbol)) {
      newWatchlist.delete(symbol);
    } else {
      newWatchlist.add(symbol);
    }
    setWatchlist(newWatchlist);
  };

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" gutterBottom fontWeight={700}>
          Swing Trading Signals
        </div>
        <div  variant="body1" color="text.secondary">
          Professional swing trading using William O'Neill's proven methodology
        </div>
      </div>

      {/* Market Timing Panel - Always visible */}
      <div  sx={{ mb: 3 }}>
        <MarketTimingPanel marketData={marketData} />
      </div>

      {/* Main Tabs */}
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Header
          title={
            <div className="border-b border-gray-200" value={activeTab} onChange={(e, v) => setActiveTab(v)}>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Trading Signals" icon={<ShowChart />} iconPosition="start" />
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Active Positions" icon={<AccountBalance />} iconPosition="start" />
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Analytics" icon={<Assessment />} iconPosition="start" />
            </div>
          }
          action={
            <div className="flex flex-col space-y-2" direction="row" spacing={1}>
              <ToggleButtonGroup
                value={viewMode}
                exclusive
                onChange={(e, v) => v && setViewMode(v)}
                size="small"
              >
                <ToggleButton value="cards">
                  <ViewModule />
                </ToggleButton>
                <ToggleButton value="table">
                  <ViewList />
                </ToggleButton>
              </ToggleButtonGroup>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                startIcon={<Refresh />}
                onClick={() => {
                  loadSignals();
                  loadPositions();
                  loadMarketData();
                }}
              >
                Refresh
              </button>
            </div>
          }
        />
        <hr className="border-gray-200" />
        
        {/* Trading Signals Tab */}
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={0}>
          {/* Filters */}
          <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, mb: 3 }}>
            <div className="grid" container spacing={2} alignItems="center">
              <div className="grid" item xs={12} md={3}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  fullWidth
                  size="small"
                  placeholder="Search symbols..."
                  value={filters.searchTerm}
                  onChange={(e) => setFilters({ ...filters, searchTerm: e.target.value })}
                  InputProps={{
                    startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />,
                    endAdornment: filters.searchTerm && (
                      <button className="p-2 rounded-full hover:bg-gray-100" size="small" onClick={() => setFilters({ ...filters, searchTerm: '' })}>
                        <Clear />
                      </button>
                    )
                  }}
                />
              </div>
              <div className="grid" item xs={12} md={2}>
                <div className="mb-4" fullWidth size="small">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Signal Type</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={filters.signalType}
                    onChange={(e) => setFilters({ ...filters, signalType: e.target.value })}
                    label="Signal Type"
                  >
                    <option  value="all">All Signals</option>
                    <option  value="Buy">Buy Only</option>
                    <option  value="Sell">Sell Only</option>
                  </select>
                </div>
              </div>
              <div className="grid" item xs={12} md={2}>
                <div className="mb-4" fullWidth size="small">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Min Strength</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={filters.minStrength}
                    onChange={(e) => setFilters({ ...filters, minStrength: e.target.value })}
                    label="Min Strength"
                  >
                    <option  value={0}>All</option>
                    <option  value={60}>60%+</option>
                    <option  value={70}>70%+</option>
                    <option  value={80}>80%+</option>
                    <option  value={90}>90%+</option>
                  </select>
                </div>
              </div>
              <div className="grid" item xs={12} md={2}>
                <div className="mb-4" fullWidth size="small">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Sector</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={filters.sector}
                    onChange={(e) => setFilters({ ...filters, sector: e.target.value })}
                    label="Sector"
                  >
                    <option  value="all">All Sectors</option>
                    <option  value="Technology">Technology</option>
                    <option  value="Healthcare">Healthcare</option>
                    <option  value="Financial">Financial</option>
                    <option  value="Consumer">Consumer</option>
                    <option  value="Industrial">Industrial</option>
                  </select>
                </div>
              </div>
              <div className="grid" item xs={12} md={3}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  fullWidth
                  variant={filters.inBuyZone ? 'contained' : 'outlined'}
                  onClick={() => setFilters({ ...filters, inBuyZone: !filters.inBuyZone })}
                  startIcon={<FilterList />}
                >
                  In Buy Zone Only
                </button>
              </div>
            </div>
          </div>

          {/* Signal Statistics */}
          <div className="grid" container spacing={2} sx={{ mb: 3 }}>
            <div className="grid" item xs={12} sm={4}>
              <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                <div  variant="h4" fontWeight={700} color="success.main">
                  {buySignals.length}
                </div>
                <div  variant="body2" color="text.secondary">
                  Buy Signals
                </div>
              </div>
            </div>
            <div className="grid" item xs={12} sm={4}>
              <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                <div  variant="h4" fontWeight={700} color="error.main">
                  {sellSignals.length}
                </div>
                <div  variant="body2" color="text.secondary">
                  Sell Signals
                </div>
              </div>
            </div>
            <div className="grid" item xs={12} sm={4}>
              <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 2, textAlign: 'center' }}>
                <div  variant="h4" fontWeight={700} color="primary.main">
                  {buySignals.filter(s => s.is_in_buy_zone).length}
                </div>
                <div  variant="body2" color="text.secondary">
                  In Buy Zone
                </div>
              </div>
            </div>
          </div>

          {/* Signals Display */}
          {loading ? (
            <div  sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
            </div>
          ) : filteredSignals.length === 0 ? (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
              No signals match your current filters. Try adjusting the criteria.
            </div>
          ) : (
            <div className="grid" container spacing={3}>
              {viewMode === 'cards' ? (
                filteredSignals.map((signal, index) => (
                  <div className="grid" item xs={12} md={6} lg={4} key={`${signal.symbol}-${index}`}>
                    <SignalCardEnhanced
                      signal={signal}
                      onBookmark={toggleWatchlist}
                      isBookmarked={watchlist.has(signal.symbol)}
                      onTrade={handleTrade}
                    />
                  </div>
                ))
              ) : (
                <div className="grid" item xs={12}>
                  {/* Table view implementation would go here */}
                  <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">Table view coming soon</div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Active Positions Tab */}
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={1}>
          <PositionManager
            positions={positions}
            onUpdatePosition={handleUpdatePosition}
            onClosePosition={handleClosePosition}
          />
        </div>

        {/* Analytics Tab */}
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={2}>
          <div className="grid" container spacing={3}>
            <div className="grid" item xs={12}>
              <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
                Advanced analytics and backtesting coming soon. This will include:
                <ul>
                  <li>Win rate analysis by signal type and quality</li>
                  <li>Exit zone effectiveness metrics</li>
                  <li>Sector rotation analysis</li>
                  <li>Historical performance by market conditions</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TradingSignalsEnhanced;