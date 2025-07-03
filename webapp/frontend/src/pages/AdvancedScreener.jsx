import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Tabs,
  Tab,
  Slider,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
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
  TextField,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Badge,
  Tooltip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TablePagination
} from '@mui/material';
import {
  Search,
  FilterList,
  Download,
  Save,
  Star,
  TrendingUp,
  TrendingDown,
  ExpandMore,
  Refresh,
  Analytics,
  Assessment,
  Clear,
  ShowChart
} from '@mui/icons-material';
import { getApiConfig } from '../services/api';
import { formatCurrency, formatPercentage, formatNumber } from '../utils/formatters';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`screener-tabpanel-${index}`}
      aria-labelledby={`screener-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const AdvancedScreener = () => {
  const { apiUrl: API_BASE } = getApiConfig();
  
  const [screenCriteria, setScreenCriteria] = useState({
    quality: [0, 100],
    growth: [0, 100],
    value: [0, 100],
    momentum: [0, 100],
    sentiment: [0, 100],
    positioning: [0, 100],
    marketCap: 'any',
    sector: 'any',
    exchange: 'any',
    dividendYield: [0, 20],
    pe: [0, 50],
    pb: [0, 10],
    roe: [0, 50],
    debt: [0, 5]
  });

  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [savedScreens, setSavedScreens] = useState([]);
  const [activeTab, setActiveTab] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [screenName, setScreenName] = useState('');
  const [sectors, setSectors] = useState([]);
  const [screenStats, setScreenStats] = useState(null);
  const [error, setError] = useState(null);

  // Mock data for demonstration
  const mockResults = [
    {
      symbol: 'AAPL',
      company: 'Apple Inc.',
      scores: {
        quality: 85,
        growth: 75,
        value: 60,
        momentum: 80,
        sentiment: 90,
        positioning: 70,
        composite: 77
      },
      price: 175.43,
      marketCap: 2.8e12,
      sector: 'Technology',
      exchange: 'NASDAQ'
    },
    {
      symbol: 'MSFT',
      company: 'Microsoft Corporation',
      scores: {
        quality: 90,
        growth: 80,
        value: 65,
        momentum: 75,
        sentiment: 85,
        positioning: 80,
        composite: 79
      },
      price: 342.56,
      marketCap: 2.5e12,
      sector: 'Technology',
      exchange: 'NASDAQ'
    },
    {
      symbol: 'GOOGL',
      company: 'Alphabet Inc.',
      scores: {
        quality: 88,
        growth: 70,
        value: 70,
        momentum: 65,
        sentiment: 80,
        positioning: 75,
        composite: 75
      },
      price: 138.45,
      marketCap: 1.7e12,
      sector: 'Technology',
      exchange: 'NASDAQ'
    }
  ];

  useEffect(() => {
    loadSavedScreens();
    loadSectors();
    loadScreenStats();
  }, []);

  const loadSavedScreens = async () => {
    try {
      // Mock saved screens for now - would integrate with backend later
      setSavedScreens([
        { id: 1, name: 'High Quality Growth', criteria: screenCriteria },
        { id: 2, name: 'Value Opportunities', criteria: { ...screenCriteria, value: [70, 100] } },
        { id: 3, name: 'Momentum Plays', criteria: { ...screenCriteria, momentum: [80, 100] } }
      ]);
    } catch (error) {
      console.error('Failed to load saved screens:', error);
    }
  };

  const loadSectors = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/stocks/sectors`);
      if (response.ok) {
        const data = await response.json();
        setSectors(data.sectors || []);
      }
    } catch (error) {
      console.error('Failed to load sectors:', error);
    }
  };

  const loadScreenStats = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/stocks/screen/stats`);
      if (response.ok) {
        const data = await response.json();
        setScreenStats(data);
      }
    } catch (error) {
      console.error('Failed to load screen stats:', error);
    }
  };

  const runScreen = async () => {
    setLoading(true);
    setError(null);
    try {
      // Build query parameters for enhanced screening API
      const params = new URLSearchParams({
        limit: 200,
        sortBy: 'composite_score',
        sortOrder: 'desc'
      });

      // Add criteria filters
      const { quality, growth, value, momentum, sentiment, positioning, marketCap, sector, exchange, pe, pb, roe, dividendYield } = screenCriteria;
      
      // Score filters (convert 0-100 to 0-1 for backend)
      if (quality[0] > 0) params.append('minQuality', quality[0] / 100);
      if (quality[1] < 100) params.append('maxQuality', quality[1] / 100);
      if (growth[0] > 0) params.append('minGrowth', growth[0] / 100);
      if (growth[1] < 100) params.append('maxGrowth', growth[1] / 100);
      if (value[0] > 0) params.append('minValue', value[0] / 100);
      if (value[1] < 100) params.append('maxValue', value[1] / 100);
      if (momentum[0] > 0) params.append('minMomentum', momentum[0] / 100);
      if (momentum[1] < 100) params.append('maxMomentum', momentum[1] / 100);
      if (sentiment[0] > 0) params.append('minSentiment', sentiment[0] / 100);
      if (sentiment[1] < 100) params.append('maxSentiment', sentiment[1] / 100);
      if (positioning[0] > 0) params.append('minPositioning', positioning[0] / 100);
      if (positioning[1] < 100) params.append('maxPositioning', positioning[1] / 100);
      
      // Financial metrics filters
      if (pe[0] > 0) params.append('minPE', pe[0]);
      if (pe[1] < 50) params.append('maxPE', pe[1]);
      if (pb[0] > 0) params.append('minPB', pb[0]);
      if (pb[1] < 10) params.append('maxPB', pb[1]);
      if (roe[0] > 0) params.append('minROE', roe[0] / 100);
      if (roe[1] < 50) params.append('maxROE', roe[1] / 100);
      if (dividendYield[0] > 0) params.append('minDividendYield', dividendYield[0] / 100);
      if (dividendYield[1] < 20) params.append('maxDividendYield', dividendYield[1] / 100);
      
      // Category filters
      if (marketCap !== 'any') params.append('marketCapTier', marketCap);
      if (sector !== 'any') params.append('sector', sector);
      if (exchange !== 'any') params.append('exchange', exchange);

      const response = await fetch(`${API_BASE}/api/stocks/screen?${params}`);
      
      if (response.ok) {
        const data = await response.json();
        const stocks = data.stocks || [];
        
        // Transform API data to match component structure
        const transformedResults = stocks.map(stock => ({
          symbol: stock.symbol,
          company: stock.company_name || stock.security_name || `${stock.symbol} Corp`,
          scores: {
            quality: Math.round((stock.quality_score || 0) * 100),
            growth: Math.round((stock.growth_score || 0) * 100),
            value: Math.round((stock.value_score || 0) * 100),
            momentum: Math.round((stock.momentum_score || 0) * 100),
            sentiment: Math.round((stock.sentiment_score || 0) * 100),
            positioning: Math.round((stock.positioning_score || 0) * 100),
            composite: Math.round((stock.composite_score || 0) * 100)
          },
          price: stock.current_price || 0,
          marketCap: stock.market_cap || 0,
          sector: stock.sector || 'Unknown',
          exchange: stock.exchange || 'Unknown',
          pe: stock.pe_ratio,
          pb: stock.pb_ratio,
          roe: stock.roe,
          dividendYield: stock.dividend_yield
        }));

        setResults(transformedResults);
        setActiveTab(1);
      } else {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to run screen');
      }
    } catch (error) {
      console.error('Failed to run screen:', error);
      setError(error.message || 'Failed to run screen. Please try again.');
      // Fallback to mock data
      setResults(mockResults);
      setActiveTab(1);
    } finally {
      setLoading(false);
    }
  };

  const saveScreen = async () => {
    if (!screenName.trim()) return;

    try {
      const newScreen = {
        id: Date.now(),
        name: screenName.trim(),
        criteria: screenCriteria
      };
      setSavedScreens(prev => [...prev, newScreen]);
      setSaveDialogOpen(false);
      setScreenName('');
    } catch (error) {
      console.error('Failed to save screen:', error);
    }
  };

  const loadScreen = (criteria) => {
    setScreenCriteria(criteria);
    setActiveTab(0);
  };

  const exportResults = () => {
    const csv = [
      ['Symbol', 'Company', 'Quality', 'Growth', 'Value', 'Momentum', 'Sentiment', 'Positioning', 'Composite', 'Price', 'P/E', 'P/B', 'ROE', 'Dividend Yield', 'Market Cap', 'Sector'],
      ...results.map(stock => [
        stock.symbol,
        stock.company,
        stock.scores.quality,
        stock.scores.growth,
        stock.scores.value,
        stock.scores.momentum,
        stock.scores.sentiment,
        stock.scores.positioning,
        stock.scores.composite,
        stock.price,
        stock.pe || '',
        stock.pb || '',
        stock.roe || '',
        stock.dividendYield || '',
        stock.marketCap,
        stock.sector
      ])
    ].map(row => row.join(',')).join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'screener_results.csv';
    a.click();
  };

  const getScoreColor = (score) => {
    if (score >= 80) return 'success';
    if (score >= 60) return 'warning';
    return 'error';
  };

  const getScoreIcon = (score) => {
    if (score >= 80) return <TrendingUp />;
    if (score >= 60) return <ShowChart />;
    return <TrendingDown />;
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h4" gutterBottom sx={{ fontWeight: 700, display: 'flex', alignItems: 'center' }}>
          <Analytics sx={{ mr: 2, color: 'primary.main' }} />
          Advanced Stock Screener
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Screen stocks using comprehensive scoring metrics including quality, growth, value, momentum, sentiment, and positioning.
        </Typography>
      </Box>

      <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 3 }}>
        <Tab label="Screening Criteria" icon={<FilterList />} />
        <Tab label={`Results (${results.length})`} icon={<Assessment />} />
        <Tab label="Saved Screens" icon={<Save />} />
      </Tabs>

      <TabPanel value={activeTab} index={0}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Score Criteria
                </Typography>
                
                <Grid container spacing={3}>
                  {Object.entries(screenCriteria).filter(([key]) => 
                    ['quality', 'growth', 'value', 'momentum', 'sentiment', 'positioning'].includes(key)
                  ).map(([key, value]) => (
                    <Grid item xs={12} sm={6} key={key}>
                      <Typography variant="body2" sx={{ mb: 1, textTransform: 'capitalize' }}>
                        {key} Score: {value[0]} - {value[1]}
                      </Typography>
                      <Slider
                        value={value}
                        onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, [key]: newValue }))}
                        valueLabelDisplay="auto"
                        min={0}
                        max={100}
                        color="primary"
                        sx={{ mb: 2 }}
                      />
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>

            <Card sx={{ mt: 3 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Financial Metrics
                </Typography>
                
                <Grid container spacing={3}>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      Dividend Yield: {screenCriteria.dividendYield[0]}% - {screenCriteria.dividendYield[1]}%
                    </Typography>
                    <Slider
                      value={screenCriteria.dividendYield}
                      onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, dividendYield: newValue }))}
                      valueLabelDisplay="auto"
                      min={0}
                      max={20}
                      step={0.1}
                      color="secondary"
                      sx={{ mb: 2 }}
                    />
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      P/E Ratio: {screenCriteria.pe[0]} - {screenCriteria.pe[1]}
                    </Typography>
                    <Slider
                      value={screenCriteria.pe}
                      onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, pe: newValue }))}
                      valueLabelDisplay="auto"
                      min={0}
                      max={50}
                      color="secondary"
                      sx={{ mb: 2 }}
                    />
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      P/B Ratio: {screenCriteria.pb[0]} - {screenCriteria.pb[1]}
                    </Typography>
                    <Slider
                      value={screenCriteria.pb}
                      onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, pb: newValue }))}
                      valueLabelDisplay="auto"
                      min={0}
                      max={10}
                      step={0.1}
                      color="secondary"
                      sx={{ mb: 2 }}
                    />
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      ROE: {screenCriteria.roe[0]}% - {screenCriteria.roe[1]}%
                    </Typography>
                    <Slider
                      value={screenCriteria.roe}
                      onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, roe: newValue }))}
                      valueLabelDisplay="auto"
                      min={0}
                      max={50}
                      step={1}
                      color="secondary"
                      sx={{ mb: 2 }}
                    />
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Market Filters
                </Typography>
                
                <FormControl fullWidth sx={{ mb: 2 }}>
                  <InputLabel>Market Cap</InputLabel>
                  <Select
                    value={screenCriteria.marketCap}
                    onChange={(e) => setScreenCriteria(prev => ({ ...prev, marketCap: e.target.value }))}
                  >
                    <MenuItem value="any">Any</MenuItem>
                    <MenuItem value="mega_cap">Mega Cap (&gt;$200B)</MenuItem>
                    <MenuItem value="large_cap">Large Cap ($10B-$200B)</MenuItem>
                    <MenuItem value="mid_cap">Mid Cap ($2B-$10B)</MenuItem>
                    <MenuItem value="small_cap">Small Cap ($300M-$2B)</MenuItem>
                    <MenuItem value="micro_cap">Micro Cap (&lt;$300M)</MenuItem>
                  </Select>
                </FormControl>

                <FormControl fullWidth sx={{ mb: 2 }}>
                  <InputLabel>Sector</InputLabel>
                  <Select
                    value={screenCriteria.sector}
                    onChange={(e) => setScreenCriteria(prev => ({ ...prev, sector: e.target.value }))}
                  >
                    <MenuItem value="any">Any Sector</MenuItem>
                    {sectors.map((sector) => (
                      <MenuItem key={sector.sector} value={sector.sector}>
                        {sector.sector} ({sector.count} stocks)
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <FormControl fullWidth sx={{ mb: 3 }}>
                  <InputLabel>Exchange</InputLabel>
                  <Select
                    value={screenCriteria.exchange}
                    onChange={(e) => setScreenCriteria(prev => ({ ...prev, exchange: e.target.value }))}
                  >
                    <MenuItem value="any">Any Exchange</MenuItem>
                    <MenuItem value="NYSE">NYSE</MenuItem>
                    <MenuItem value="NASDAQ">NASDAQ</MenuItem>
                  </Select>
                </FormControl>

                <Button
                  variant="contained"
                  color="primary"
                  fullWidth
                  size="large"
                  onClick={runScreen}
                  disabled={loading}
                  startIcon={loading ? <CircularProgress size={20} /> : <Search />}
                  sx={{ mb: 2 }}
                >
                  {loading ? 'Screening...' : 'Run Screen'}
                </Button>

                <Button
                  variant="outlined"
                  fullWidth
                  onClick={() => setSaveDialogOpen(true)}
                  startIcon={<Save />}
                  sx={{ mb: 1 }}
                >
                  Save Screen
                </Button>

                <Button
                  variant="outlined"
                  fullWidth
                  onClick={() => setScreenCriteria({
                    quality: [0, 100],
                    growth: [0, 100],
                    value: [0, 100],
                    momentum: [0, 100],
                    sentiment: [0, 100],
                    positioning: [0, 100],
                    marketCap: 'any',
                    sector: 'any',
                    exchange: 'any',
                    dividendYield: [0, 20],
                    pe: [0, 50],
                    pb: [0, 10],
                    roe: [0, 50],
                    debt: [0, 5]
                  })}
                  startIcon={<Clear />}
                >
                  Clear Filters
                </Button>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h6">
            Screening Results ({results.length} stocks found)
          </Typography>
          {results.length > 0 && (
            <Button
              variant="outlined"
              startIcon={<Download />}
              onClick={exportResults}
            >
              Export CSV
            </Button>
          )}
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {results.length === 0 && !error ? (
          <Alert severity="info">
            No results to display. Run a screen to see matching stocks.
          </Alert>
        ) : !error && (
          <Card>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Company</TableCell>
                    <TableCell align="center">Quality</TableCell>
                    <TableCell align="center">Growth</TableCell>
                    <TableCell align="center">Value</TableCell>
                    <TableCell align="center">Momentum</TableCell>
                    <TableCell align="center">Sentiment</TableCell>
                    <TableCell align="center">Composite</TableCell>
                    <TableCell align="right">Price</TableCell>
                    <TableCell align="right">P/E</TableCell>
                    <TableCell align="right">P/B</TableCell>
                    <TableCell align="right">Market Cap</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {results
                    .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                    .map((stock) => (
                    <TableRow key={stock.symbol} hover>
                      <TableCell>
                        <Typography variant="body2" fontWeight="bold">
                          {stock.symbol}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {stock.company}
                        </Typography>
                      </TableCell>
                      {['quality', 'growth', 'value', 'momentum', 'sentiment'].map((metric) => (
                        <TableCell key={metric} align="center">
                          <Chip
                            label={stock.scores[metric]}
                            color={getScoreColor(stock.scores[metric])}
                            size="small"
                            icon={getScoreIcon(stock.scores[metric])}
                          />
                        </TableCell>
                      ))}
                      <TableCell align="center">
                        <Chip
                          label={stock.scores.composite}
                          color={getScoreColor(stock.scores.composite)}
                          variant="filled"
                        />
                      </TableCell>
                      <TableCell align="right">
                        {formatCurrency(stock.price)}
                      </TableCell>
                      <TableCell align="right">
                        {stock.pe ? formatNumber(stock.pe) : 'N/A'}
                      </TableCell>
                      <TableCell align="right">
                        {stock.pb ? formatNumber(stock.pb) : 'N/A'}
                      </TableCell>
                      <TableCell align="right">
                        {formatCurrency(stock.marketCap, 0)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              component="div"
              count={results.length}
              page={page}
              onPageChange={(e, newPage) => setPage(newPage)}
              rowsPerPage={rowsPerPage}
              onRowsPerPageChange={(e) => {
                setRowsPerPage(parseInt(e.target.value));
                setPage(0);
              }}
            />
          </Card>
        )}
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        <Typography variant="h6" gutterBottom>
          Saved Screening Strategies
        </Typography>
        
        <Grid container spacing={2}>
          {savedScreens.map((screen) => (
            <Grid item xs={12} sm={6} md={4} key={screen.id}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    {screen.name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Quality: {screen.criteria.quality[0]}-{screen.criteria.quality[1]}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Growth: {screen.criteria.growth[0]}-{screen.criteria.growth[1]}
                  </Typography>
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => loadScreen(screen.criteria)}
                    sx={{ mt: 1 }}
                  >
                    Load Screen
                  </Button>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      {/* Save Screen Dialog */}
      <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)}>
        <DialogTitle>Save Screening Strategy</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Screen Name"
            fullWidth
            variant="outlined"
            value={screenName}
            onChange={(e) => setScreenName(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSaveDialogOpen(false)}>Cancel</Button>
          <Button onClick={saveScreen} variant="contained">Save</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default AdvancedScreener;