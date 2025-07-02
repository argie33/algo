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
  }, []);

  const loadSavedScreens = async () => {
    try {
      // Mock saved screens for now
      setSavedScreens([
        { id: 1, name: 'High Quality Growth', criteria: screenCriteria },
        { id: 2, name: 'Value Opportunities', criteria: { ...screenCriteria, value: [70, 100] } },
        { id: 3, name: 'Momentum Plays', criteria: { ...screenCriteria, momentum: [80, 100] } }
      ]);
    } catch (error) {
      console.error('Failed to load saved screens:', error);
    }
  };

  const runScreen = async () => {
    setLoading(true);
    try {
      // Build query parameters for metrics API
      const params = new URLSearchParams({
        page: 1,
        limit: 200,
        sortBy: 'composite_metric',
        sortOrder: 'desc'
      });

      // Add filters based on criteria
      if (screenCriteria.sector !== 'any') {
        params.append('sector', screenCriteria.sector);
      }

      // Convert quality score range (0-100) to metric range (0-1)
      const minComposite = screenCriteria.quality[0] / 100;
      const maxComposite = screenCriteria.quality[1] / 100;
      
      if (minComposite > 0) {
        params.append('minMetric', minComposite);
      }
      if (maxComposite < 1) {
        params.append('maxMetric', maxComposite);
      }

      const response = await fetch(`${API_BASE}/api/metrics?${params}`);
      
      if (response.ok) {
        const data = await response.json();
        const stocks = data.stocks || [];
        
        // Transform API data to match our component structure
        const transformedResults = stocks.map(stock => ({
          symbol: stock.symbol,
          company: stock.security_name || stock.short_name || `${stock.symbol} Corp`,
          scores: {
            quality: Math.round((stock.quality_metric || 0.5) * 100),
            growth: Math.round((stock.growth_metric || 0.5) * 100), 
            value: Math.round((stock.value_metric || 0.5) * 100),
            momentum: Math.round((stock.momentum_metric || 0.5) * 100),
            sentiment: Math.round((stock.sentiment_metric || 0.5) * 100),
            positioning: Math.round((stock.positioning_metric || 0.5) * 100),
            composite: Math.round((stock.composite_metric || 0.5) * 100)
          },
          price: stock.current_price || 0,
          marketCap: stock.market_cap || 0,
          sector: stock.sector || 'Unknown',
          exchange: stock.exchange || 'Unknown'
        }));

        // Apply additional client-side filters
        const filteredResults = transformedResults.filter(stock => {
          // Market cap filter
          if (screenCriteria.marketCap !== 'any') {
            const marketCap = stock.marketCap;
            if (screenCriteria.marketCap === 'large' && marketCap < 10e9) return false;
            if (screenCriteria.marketCap === 'mid' && (marketCap < 2e9 || marketCap > 10e9)) return false;
            if (screenCriteria.marketCap === 'small' && marketCap > 2e9) return false;
          }

          // Exchange filter
          if (screenCriteria.exchange !== 'any' && stock.exchange !== screenCriteria.exchange) {
            return false;
          }

          // Score filters
          const { quality, growth, value, momentum, sentiment, positioning } = screenCriteria;
          return (
            stock.scores.quality >= quality[0] && stock.scores.quality <= quality[1] &&
            stock.scores.growth >= growth[0] && stock.scores.growth <= growth[1] &&
            stock.scores.value >= value[0] && stock.scores.value <= value[1] &&
            stock.scores.momentum >= momentum[0] && stock.scores.momentum <= momentum[1] &&
            stock.scores.sentiment >= sentiment[0] && stock.scores.sentiment <= sentiment[1] &&
            stock.scores.positioning >= positioning[0] && stock.scores.positioning <= positioning[1]
          );
        });

        setResults(filteredResults);
      } else {
        console.warn('API call failed, using mock data');
        setResults(mockResults);
      }
      setActiveTab(1);
    } catch (error) {
      console.error('Failed to run screen:', error);
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
      ['Symbol', 'Company', 'Quality', 'Growth', 'Value', 'Momentum', 'Sentiment', 'Positioning', 'Composite', 'Price', 'Market Cap'],
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
        stock.marketCap
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
                    <MenuItem value="large">Large Cap (>$10B)</MenuItem>
                    <MenuItem value="mid">Mid Cap ($2B-$10B)</MenuItem>
                    <MenuItem value="small">Small Cap (<$2B)</MenuItem>
                  </Select>
                </FormControl>

                <FormControl fullWidth sx={{ mb: 2 }}>
                  <InputLabel>Sector</InputLabel>
                  <Select
                    value={screenCriteria.sector}
                    onChange={(e) => setScreenCriteria(prev => ({ ...prev, sector: e.target.value }))}
                  >
                    <MenuItem value="any">Any Sector</MenuItem>
                    <MenuItem value="Technology">Technology</MenuItem>
                    <MenuItem value="Healthcare">Healthcare</MenuItem>
                    <MenuItem value="Financials">Financials</MenuItem>
                    <MenuItem value="Consumer Discretionary">Consumer Discretionary</MenuItem>
                    <MenuItem value="Consumer Staples">Consumer Staples</MenuItem>
                    <MenuItem value="Energy">Energy</MenuItem>
                    <MenuItem value="Industrials">Industrials</MenuItem>
                    <MenuItem value="Materials">Materials</MenuItem>
                    <MenuItem value="Real Estate">Real Estate</MenuItem>
                    <MenuItem value="Utilities">Utilities</MenuItem>
                    <MenuItem value="Communication Services">Communication Services</MenuItem>
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
                >
                  Save Screen
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

        {results.length === 0 ? (
          <Alert severity="info">
            No results to display. Run a screen to see matching stocks.
          </Alert>
        ) : (
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