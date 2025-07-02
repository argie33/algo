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

const ScoresDashboard = () => {
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
  const [minScore, setMinScore] = useState(0);
  const [maxScore, setMaxScore] = useState(100);
  const [sortBy, setSortBy] = useState('composite_score');
  const [sortOrder, setSortOrder] = useState('desc');
  
  // Pagination
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    fetchData();
  }, [page, searchTerm, selectedSector, minScore, maxScore, sortBy, sortOrder]);

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
        minScore: minScore.toString(),
        maxScore: maxScore.toString(),
        sortBy,
        sortOrder
      });

      const response = await fetch(`/api/scores?${params}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      setStocks(data.stocks || []);
      setTotalPages(data.pagination?.totalPages || 1);
      setError(null);
      
    } catch (err) {
      console.error('Error fetching scores:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSectorAnalysis = async () => {
    try {
      const response = await fetch('/api/scores/sectors/analysis');
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
      const categories = ['composite', 'quality', 'value', 'growth', 'momentum', 'sentiment'];
      const promises = categories.map(category =>
        fetch(`/api/scores/top/${category}?limit=10`)
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

  const getScoreColor = (score) => {
    if (score >= 80) return '#4caf50'; // Green
    if (score >= 70) return '#8bc34a'; // Light green
    if (score >= 60) return '#ffeb3b'; // Yellow
    if (score >= 50) return '#ff9800'; // Orange
    return '#f44336'; // Red
  };

  const getScoreChip = (score, label) => (
    <Chip
      label={`${label}: ${score.toFixed(1)}`}
      size="small"
      style={{
        backgroundColor: getScoreColor(score),
        color: score >= 60 ? '#000' : '#fff',
        fontWeight: 'bold',
        margin: '2px'
      }}
    />
  );

  const ScoreProgressBar = ({ score, label, icon }) => (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
        {icon}
        <Typography variant="body2" sx={{ ml: 1, flex: 1 }}>
          {label}
        </Typography>
        <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
          {score.toFixed(1)}
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate"
        value={score}
        sx={{
          height: 8,
          borderRadius: 4,
          '& .MuiLinearProgress-bar': {
            backgroundColor: getScoreColor(score),
            borderRadius: 4,
          },
        }}
      />
    </Box>
  );

  const MainScoresTable = () => (
    <TableContainer component={Paper} sx={{ mt: 3 }}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell><strong>Symbol</strong></TableCell>
            <TableCell><strong>Company</strong></TableCell>
            <TableCell><strong>Sector</strong></TableCell>
            <TableCell align="center"><strong>Composite Score</strong></TableCell>
            <TableCell align="center"><strong>Quality</strong></TableCell>
            <TableCell align="center"><strong>Value</strong></TableCell>
            <TableCell align="center"><strong>Growth</strong></TableCell>
            <TableCell align="center"><strong>Momentum</strong></TableCell>
            <TableCell><strong>Price</strong></TableCell>
            <TableCell><strong>Market Cap</strong></TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {stocks.map((stock, index) => (
            <TableRow key={stock.symbol} hover>
              <TableCell>
                <Typography variant="subtitle2" sx={{ fontWeight: 'bold', color: '#1976d2' }}>
                  {stock.symbol}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {stock.companyName?.substring(0, 30)}
                  {stock.companyName?.length > 30 ? '...' : ''}
                </Typography>
              </TableCell>
              <TableCell>
                <Chip 
                  label={stock.sector} 
                  size="small" 
                  variant="outlined"
                />
              </TableCell>
              <TableCell align="center">
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Typography 
                    variant="h6" 
                    sx={{ 
                      color: getScoreColor(stock.scores.composite),
                      fontWeight: 'bold'
                    }}
                  >
                    {stock.scores.composite.toFixed(1)}
                  </Typography>
                  <Tooltip title={`Percentile: ${stock.metadata.percentileRank.toFixed(1)}`}>
                    <IconButton size="small">
                      <Info fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              </TableCell>
              <TableCell align="center">
                <Typography sx={{ color: getScoreColor(stock.scores.quality) }}>
                  {stock.scores.quality.toFixed(1)}
                </Typography>
              </TableCell>
              <TableCell align="center">
                <Typography sx={{ color: getScoreColor(stock.scores.value) }}>
                  {stock.scores.value.toFixed(1)}
                </Typography>
              </TableCell>
              <TableCell align="center">
                <Typography sx={{ color: getScoreColor(stock.scores.growth) }}>
                  {stock.scores.growth.toFixed(1)}
                </Typography>
              </TableCell>
              <TableCell align="center">
                <Typography sx={{ color: getScoreColor(stock.scores.momentum) }}>
                  {stock.scores.momentum.toFixed(1)}
                </Typography>
              </TableCell>
              <TableCell>
                ${stock.currentPrice?.toFixed(2) || 'N/A'}
              </TableCell>
              <TableCell>
                {stock.marketCap ? `$${(stock.marketCap / 1e9).toFixed(1)}B` : 'N/A'}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const SectorAnalysis = () => (
    <Grid container spacing={3} sx={{ mt: 2 }}>
      {sectors.map((sector) => (
        <Grid item xs={12} md={6} lg={4} key={sector.sector}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {sector.sector}
              </Typography>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                {sector.stockCount} stocks
              </Typography>
              
              <ScoreProgressBar 
                score={parseFloat(sector.averageScores.composite)} 
                label="Composite"
                icon={<Assessment />}
              />
              <ScoreProgressBar 
                score={parseFloat(sector.averageScores.quality)} 
                label="Quality"
                icon={<AccountBalance />}
              />
              <ScoreProgressBar 
                score={parseFloat(sector.averageScores.value)} 
                label="Value"
                icon={<AttachMoney />}
              />
              <ScoreProgressBar 
                score={parseFloat(sector.averageScores.growth)} 
                label="Growth"
                icon={<TrendingUp />}
              />
              
              <Box sx={{ mt: 2, display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption">
                  Range: {sector.scoreRange.min} - {sector.scoreRange.max}
                </Typography>
                <Typography variant="caption">
                  Vol: {sector.scoreRange.volatility}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );

  const TopStocks = () => (
    <Grid container spacing={3} sx={{ mt: 2 }}>
      {Object.entries(topStocks).map(([category, stocks]) => (
        <Grid item xs={12} md={6} key={category}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom sx={{ textTransform: 'capitalize' }}>
                Top {category === 'composite' ? 'Overall' : category} Stocks
              </Typography>
              <Box sx={{ maxHeight: 400, overflow: 'auto' }}>
                {stocks.slice(0, 10).map((stock, index) => (
                  <Box 
                    key={stock.symbol} 
                    sx={{ 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center',
                      py: 1,
                      borderBottom: index < 9 ? '1px solid #eee' : 'none'
                    }}
                  >
                    <Box>
                      <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                        {index + 1}. {stock.symbol}
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        {stock.companyName?.substring(0, 25)}
                        {stock.companyName?.length > 25 ? '...' : ''}
                      </Typography>
                    </Box>
                    <Box sx={{ textAlign: 'right' }}>
                      <Typography 
                        variant="body2" 
                        sx={{ 
                          color: getScoreColor(stock.categoryScore),
                          fontWeight: 'bold'
                        }}
                      >
                        {stock.categoryScore.toFixed(1)}
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        {stock.sector}
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );

  if (error) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Alert severity="error">
          Error loading scores: {error}
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom>
          Institutional-Grade Stock Scoring
        </Typography>
        <Typography variant="subtitle1" color="textSecondary">
          Advanced multi-factor analysis based on academic research and institutional methodology
        </Typography>
      </Box>

      {/* Navigation Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)}>
          <Tab label="Stock Scores" />
          <Tab label="Sector Analysis" />
          <Tab label="Top Performers" />
        </Tabs>
      </Box>

      {/* Filters for Stock Scores Tab */}
      {activeTab === 0 && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={3}>
              <TextField
                fullWidth
                label="Search Symbol/Company"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                size="small"
              />
            </Grid>
            <Grid item xs={12} sm={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Sector</InputLabel>
                <Select
                  value={selectedSector}
                  label="Sector"
                  onChange={(e) => setSelectedSector(e.target.value)}
                >
                  <MenuItem value="">All Sectors</MenuItem>
                  <MenuItem value="Technology">Technology</MenuItem>
                  <MenuItem value="Healthcare">Healthcare</MenuItem>
                  <MenuItem value="Financial Services">Financial Services</MenuItem>
                  <MenuItem value="Consumer Cyclical">Consumer Cyclical</MenuItem>
                  <MenuItem value="Industrials">Industrials</MenuItem>
                  <MenuItem value="Communication Services">Communication Services</MenuItem>
                  <MenuItem value="Consumer Defensive">Consumer Defensive</MenuItem>
                  <MenuItem value="Energy">Energy</MenuItem>
                  <MenuItem value="Utilities">Utilities</MenuItem>
                  <MenuItem value="Real Estate">Real Estate</MenuItem>
                  <MenuItem value="Basic Materials">Basic Materials</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={2}>
              <TextField
                fullWidth
                label="Min Score"
                type="number"
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                size="small"
                inputProps={{ min: 0, max: 100 }}
              />
            </Grid>
            <Grid item xs={12} sm={2}>
              <TextField
                fullWidth
                label="Max Score"
                type="number"
                value={maxScore}
                onChange={(e) => setMaxScore(Number(e.target.value))}
                size="small"
                inputProps={{ min: 0, max: 100 }}
              />
            </Grid>
            <Grid item xs={12} sm={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Sort By</InputLabel>
                <Select
                  value={sortBy}
                  label="Sort By"
                  onChange={(e) => setSortBy(e.target.value)}
                >
                  <MenuItem value="composite_score">Composite Score</MenuItem>
                  <MenuItem value="quality_score">Quality Score</MenuItem>
                  <MenuItem value="value_score">Value Score</MenuItem>
                  <MenuItem value="growth_score">Growth Score</MenuItem>
                  <MenuItem value="momentum_score">Momentum Score</MenuItem>
                  <MenuItem value="market_cap">Market Cap</MenuItem>
                  <MenuItem value="symbol">Symbol</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* Content based on active tab */}
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <>
          {activeTab === 0 && <MainScoresTable />}
          {activeTab === 1 && <SectorAnalysis />}
          {activeTab === 2 && <TopStocks />}
        </>
      )}

      {/* Pagination for Stock Scores */}
      {activeTab === 0 && totalPages > 1 && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
          <Typography variant="body2" sx={{ mt: 1 }}>
            Page {page} of {totalPages}
          </Typography>
          {/* Add pagination controls here if needed */}
        </Box>
      )}

      {/* Legend */}
      <Paper sx={{ p: 2, mt: 4, backgroundColor: '#f5f5f5' }}>
        <Typography variant="h6" gutterBottom>
          Scoring Methodology
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={2}>
            <Typography variant="subtitle2">Quality Score</Typography>
            <Typography variant="caption">
              Financial statement quality, balance sheet strength, profitability, management effectiveness
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Typography variant="subtitle2">Value Score</Typography>
            <Typography variant="caption">
              P/E, P/B, EV/EBITDA analysis, DCF intrinsic value, peer comparison
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Typography variant="subtitle2">Growth Score</Typography>
            <Typography variant="caption">
              Revenue growth, earnings growth quality, sustainable growth analysis
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Typography variant="subtitle2">Momentum Score</Typography>
            <Typography variant="caption">
              Price trends, earnings revisions, technical indicators
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Typography variant="subtitle2">Sentiment Score</Typography>
            <Typography variant="caption">
              Analyst recommendations, social media sentiment, news analysis
            </Typography>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <Typography variant="subtitle2">Positioning Score</Typography>
            <Typography variant="caption">
              Institutional ownership, insider trading, short interest dynamics
            </Typography>
          </Grid>
        </Grid>
        
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            Score Ranges:
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {getScoreChip(90, 'Excellent (80-100)')}
            {getScoreChip(75, 'Good (70-79)')}
            {getScoreChip(65, 'Fair (60-69)')}
            {getScoreChip(55, 'Below Average (50-59)')}
            {getScoreChip(40, 'Poor (0-49)')}
          </Box>
        </Box>
      </Paper>
    </Container>
  );
};

export default ScoresDashboard;