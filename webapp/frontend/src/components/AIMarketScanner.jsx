import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box,
  Card,
  CardContent,
  Chip,
  Typography,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Alert,
  CircularProgress,
  IconButton,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Refresh,
  Star,
  StarBorder,
  Visibility,
  Speed,
  Timeline,
  ShowChart,
} from '@mui/icons-material';
import { formatCurrency, formatPercentage } from '../utils/formatters';
import realTimeDataService from '../services/realTimeDataService';

const AIMarketScanner = ({ onStockSelect }) => {
  const [scanType, setScanType] = useState('momentum');
  const [isRealTime, setIsRealTime] = useState(false);
  const [scanResults, setScanResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lastScan, setLastScan] = useState(null);
  const [selectedStock, setSelectedStock] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [watchlist, setWatchlist] = useState(new Set());

  // Real-time data subscriptions
  const [realtimeData, setRealtimeData] = useState({});
  
  // AI Scan Configurations
  const scanConfigs = {
    momentum: {
      name: 'AI Momentum Breakouts',
      description: 'Stocks breaking out with strong momentum and volume',
      icon: <TrendingUp />,
      color: 'success',
      criteria: {
        priceChange: [5, 25],
        volumeRatio: [2, 10],
        rsi: [60, 85],
        macdSignal: 'bullish'
      }
    },
    reversal: {
      name: 'Smart Reversal Plays',
      description: 'Oversold stocks with reversal indicators',
      icon: <Timeline />,
      color: 'warning',
      criteria: {
        priceChange: [-15, -5],
        rsi: [20, 40],
        bollingerPosition: 'lower',
        volumeRatio: [1.5, 5]
      }
    },
    breakout: {
      name: 'Technical Breakouts',
      description: 'Stocks breaking key resistance levels',
      icon: <ShowChart />,
      color: 'info',
      criteria: {
        priceChange: [3, 20],
        volumeRatio: [1.8, 8],
        resistance: 'broken',
        consolidation: 'emerging'
      }
    },
    unusual: {
      name: 'Unusual Activity',
      description: 'Stocks with unusual price or volume activity',
      icon: <Speed />,
      color: 'secondary',
      criteria: {
        volumeRatio: [3, 20],
        priceVolatility: [1.5, 5],
        newsScore: [0.6, 1.0]
      }
    }
  };

  // Fetch scan results
  const fetchScanResults = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/screener/ai-scan?type=${scanType}&limit=50`);
      const data = await response.json();
      
      if (data.success) {
        setScanResults(data.data.results || []);
        setLastScan(new Date());
        
        // Subscribe to real-time updates for top results
        if (isRealTime && data.data.results) {
          const topSymbols = data.data.results.slice(0, 20).map(r => r.symbol);
          topSymbols.forEach(symbol => {
            realTimeDataService.subscribe('prices', (priceData) => {
              if (priceData[symbol]) {
                setRealtimeData(prev => ({
                  ...prev,
                  [symbol]: priceData[symbol]
                }));
              }
            });
          });
        }
      }
    } catch (error) {
      console.error('Scan failed:', error);
    }
    setLoading(false);
  }, [scanType, isRealTime]);

  // Auto-refresh for real-time mode
  useEffect(() => {
    let interval;
    if (isRealTime) {
      fetchScanResults(); // Initial scan
      interval = setInterval(fetchScanResults, 30000); // Every 30 seconds
    }
    return () => clearInterval(interval);
  }, [isRealTime, fetchScanResults]);

  // Manual scan
  const handleScan = () => {
    fetchScanResults();
  };

  // Toggle watchlist
  const toggleWatchlist = (symbol) => {
    setWatchlist(prev => {
      const newWatchlist = new Set(prev);
      if (newWatchlist.has(symbol)) {
        newWatchlist.delete(symbol);
      } else {
        newWatchlist.add(symbol);
      }
      return newWatchlist;
    });
  };

  // Get AI Score based on multiple factors
  const calculateAIScore = (stock) => {
    let score = 50; // Base score
    
    // Price momentum
    if (stock.priceChange > 10) score += 20;
    else if (stock.priceChange > 5) score += 10;
    else if (stock.priceChange < -10) score -= 20;
    
    // Volume factor
    if (stock.volumeRatio > 3) score += 15;
    else if (stock.volumeRatio > 2) score += 10;
    
    // Technical indicators
    if (stock.rsi && stock.rsi > 70) score += 10;
    if (stock.rsi && stock.rsi < 30) score -= 10;
    
    // Market cap stability
    if (stock.marketCap > 10000000000) score += 5; // Large cap bonus
    
    return Math.max(0, Math.min(100, score));
  };

  // Enhanced scan results with real-time data
  const enhancedResults = useMemo(() => {
    return scanResults.map(stock => {
      const realtimePrice = realtimeData[stock.symbol];
      return {
        ...stock,
        currentPrice: realtimePrice?.price || stock.price,
        realtimeChange: realtimePrice ? 
          ((realtimePrice.price - stock.price) / stock.price * 100) : 0,
        aiScore: calculateAIScore(stock),
        isRealTime: !!realtimePrice
      };
    });
  }, [scanResults, realtimeData]);

  return (
    <Box>
      {/* Scanner Controls */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={3}>
              <FormControl fullWidth size="small">
                <InputLabel>Scan Type</InputLabel>
                <Select
                  value={scanType}
                  onChange={(e) => setScanType(e.target.value)}
                  label="Scan Type"
                >
                  {Object.entries(scanConfigs).map(([key, config]) => (
                    <MenuItem key={key} value={key}>
                      <Box display="flex" alignItems="center" gap={1}>
                        {config.icon}
                        {config.name}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={12} md={3}>
              <FormControlLabel
                control={
                  <Switch
                    checked={isRealTime}
                    onChange={(e) => setIsRealTime(e.target.checked)}
                    color="primary"
                  />
                }
                label="Real-Time Mode"
              />
            </Grid>
            
            <Grid item xs={12} md={3}>
              <Button
                variant="contained"
                onClick={handleScan}
                disabled={loading}
                startIcon={loading ? <CircularProgress size={16} /> : <Analytics />}
                fullWidth
              >
                {loading ? 'Scanning...' : 'Run AI Scan'}
              </Button>
            </Grid>
            
            <Grid item xs={12} md={3}>
              <Typography variant="caption" color="text.secondary">
                {lastScan && `Last scan: ${lastScan.toLocaleTimeString()}`}
                {isRealTime && <Chip label="LIVE" color="success" size="small" sx={{ ml: 1 }} />}
              </Typography>
            </Grid>
          </Grid>
          
          {/* Current scan description */}
          <Alert severity="info" sx={{ mt: 2 }}>
            <Typography variant="body2">
              <strong>{scanConfigs[scanType].name}:</strong> {scanConfigs[scanType].description}
            </Typography>
          </Alert>
        </CardContent>
      </Card>

      {/* Scan Results */}
      <Card>
        <CardContent>
          <Box display="flex" justifyContent="between" alignItems="center" mb={2}>
            <Typography variant="h6">
              AI Scan Results ({enhancedResults.length})
            </Typography>
            {isRealTime && (
              <Chip 
                icon={<Refresh />} 
                label="Auto-updating" 
                color="success" 
                variant="outlined" 
              />
            )}
          </Box>
          
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Price</TableCell>
                  <TableCell>Change</TableCell>
                  <TableCell>Volume</TableCell>
                  <TableCell>AI Score</TableCell>
                  <TableCell>Signals</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {enhancedResults.slice(0, 25).map((stock) => {
                  const isPositive = (stock.realtimeChange || stock.priceChange || 0) >= 0;
                  const totalChange = (stock.priceChange || 0) + (stock.realtimeChange || 0);
                  
                  return (
                    <TableRow 
                      key={stock.symbol}
                      hover
                      sx={{ 
                        backgroundColor: stock.isRealTime ? 'rgba(76, 175, 80, 0.05)' : 'inherit',
                        '&:hover': { backgroundColor: 'rgba(0, 0, 0, 0.04)' }
                      }}
                    >
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          <Typography variant="body2" fontWeight="bold">
                            {stock.symbol}
                          </Typography>
                          {stock.isRealTime && (
                            <Chip label="LIVE" size="small" color="success" />
                          )}
                        </Box>
                      </TableCell>
                      
                      <TableCell>
                        <Typography variant="body2">
                          {formatCurrency(stock.currentPrice)}
                        </Typography>
                      </TableCell>
                      
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={0.5}>
                          {isPositive ? <TrendingUp color="success" /> : <TrendingDown color="error" />}
                          <Typography 
                            variant="body2" 
                            color={isPositive ? 'success.main' : 'error.main'}
                            fontWeight="medium"
                          >
                            {formatPercentage(totalChange)}
                          </Typography>
                        </Box>
                      </TableCell>
                      
                      <TableCell>
                        <Typography variant="body2">
                          {stock.volumeRatio ? `${stock.volumeRatio.toFixed(1)}x` : 'N/A'}
                        </Typography>
                      </TableCell>
                      
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          <Typography 
                            variant="body2" 
                            fontWeight="bold"
                            color={stock.aiScore > 75 ? 'success.main' : stock.aiScore > 50 ? 'warning.main' : 'error.main'}
                          >
                            {stock.aiScore}
                          </Typography>
                          <Box 
                            width={30} 
                            height={6} 
                            bgcolor="grey.200" 
                            borderRadius={1}
                          >
                            <Box 
                              width={`${stock.aiScore}%`} 
                              height="100%" 
                              bgcolor={stock.aiScore > 75 ? 'success.main' : stock.aiScore > 50 ? 'warning.main' : 'error.main'}
                              borderRadius={1}
                            />
                          </Box>
                        </Box>
                      </TableCell>
                      
                      <TableCell>
                        <Box display="flex" gap={0.5}>
                          {stock.signals?.map((signal, idx) => (
                            <Chip
                              key={idx}
                              label={signal}
                              size="small"
                              variant="outlined"
                              color={signal.includes('Buy') ? 'success' : signal.includes('Sell') ? 'error' : 'default'}
                            />
                          ))}
                        </Box>
                      </TableCell>
                      
                      <TableCell>
                        <Box display="flex" gap={1}>
                          <IconButton 
                            size="small" 
                            onClick={() => toggleWatchlist(stock.symbol)}
                            color={watchlist.has(stock.symbol) ? 'warning' : 'default'}
                          >
                            {watchlist.has(stock.symbol) ? <Star /> : <StarBorder />}
                          </IconButton>
                          
                          <IconButton 
                            size="small" 
                            onClick={() => {
                              setSelectedStock(stock);
                              setDetailsOpen(true);
                            }}
                          >
                            <Visibility />
                          </IconButton>
                          
                          {onStockSelect && (
                            <Button 
                              size="small" 
                              variant="outlined"
                              onClick={() => onStockSelect(stock.symbol)}
                            >
                              Analyze
                            </Button>
                          )}
                        </Box>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
          
          {enhancedResults.length === 0 && !loading && (
            <Box textAlign="center" py={4}>
              <Typography color="text.secondary">
                No stocks found matching the current scan criteria. Try running a scan.
              </Typography>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Stock Details Dialog */}
      <Dialog 
        open={detailsOpen} 
        onClose={() => setDetailsOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          {selectedStock?.symbol} - AI Analysis Details
        </DialogTitle>
        <DialogContent>
          {selectedStock && (
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Price Action</Typography>
                <Typography>Current Price: {formatCurrency(selectedStock.currentPrice)}</Typography>
                <Typography>Daily Change: {formatPercentage(selectedStock.priceChange || 0)}</Typography>
                <Typography>Volume Ratio: {selectedStock.volumeRatio?.toFixed(1)}x</Typography>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>AI Assessment</Typography>
                <Typography>AI Score: {selectedStock.aiScore}/100</Typography>
                <Typography>Scan Type: {scanConfigs[scanType].name}</Typography>
                <Typography>Market Cap: {selectedStock.marketCap ? formatCurrency(selectedStock.marketCap) : 'N/A'}</Typography>
              </Grid>
              <Grid item xs={12}>
                <Typography variant="h6" gutterBottom>Signals</Typography>
                <Box display="flex" gap={1} flexWrap="wrap">
                  {selectedStock.signals?.map((signal, idx) => (
                    <Chip key={idx} label={signal} color="primary" />
                  ))}
                </Box>
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailsOpen(false)}>Close</Button>
          {onStockSelect && (
            <Button 
              variant="contained"
              onClick={() => {
                onStockSelect(selectedStock?.symbol);
                setDetailsOpen(false);
              }}
            >
              Full Analysis
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default AIMarketScanner;