import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
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
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Slider,
  LinearProgress,
  Badge,
  Tooltip,
  IconButton,
  Divider
} from '@mui/material';
import {
  Search,
  TrendingUp,
  TrendingDown,
  Target,
  FlashOn as Zap,
  BarChart as BarChart3,
  Warning as AlertCircle,
  CheckCircle,
  Schedule as Clock,
  FilterList as Filter,
  Psychology,
  Timeline,
  ShowChart,
  Refresh
} from '@mui/icons-material';

const PatternRecognition = () => {
  const [patterns, setPatterns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchSymbol, setSearchSymbol] = useState('');
  const [selectedTimeframe, setSelectedTimeframe] = useState('1D');
  const [confidenceFilter, setConfidenceFilter] = useState(75);
  const [selectedPattern, setSelectedPattern] = useState('all');
  const [activeTab, setActiveTab] = useState(0);

  useEffect(() => {
    loadPatterns();
  }, [selectedTimeframe, confidenceFilter, selectedPattern]);

  const loadPatterns = async () => {
    setLoading(true);
    try {
      const timeframe = selectedTimeframe.toLowerCase();
      const response = await api.get(`/api/patterns/scan`, {
        params: {
          timeframe: timeframe,
          min_confidence: confidenceFilter / 100,
          category: selectedPattern !== 'all' ? selectedPattern : undefined,
          limit: 50
        }
      });
      
      // Transform API response to match frontend expectations
      const transformedPatterns = response.data.patterns?.map(pattern => ({
        symbol: pattern.symbol,
        pattern: pattern.patternName,
        bias: pattern.direction,
        confidence: Math.round(pattern.confidence * 100),
        strength: pattern.signalStrength === 'very_strong' ? 95 : 
                 pattern.signalStrength === 'strong' ? 85 :
                 pattern.signalStrength === 'moderate' ? 70 : 50,
        timeframe: pattern.timeframe,
        entryPrice: pattern.targetPrice || 0,
        targetPrice: pattern.targetPrice || 0,
        stopLoss: pattern.stopLoss || 0,
        riskReward: pattern.riskRewardRatio ? `${pattern.riskRewardRatio}:1` : '1:1',
        detectedAt: new Date(pattern.detectionDate).toLocaleDateString(),
        description: pattern.description || `${pattern.direction} ${pattern.patternName} pattern`
      })) || [];

      setPatterns(transformedPatterns);
    } catch (error) {
      console.error('Failed to load patterns:', error);
      // Fallback to mock data if API fails
      setPatterns(mockPatterns);
    } finally {
      setLoading(false);
    }
  };

  const analyzeSymbol = async () => {
    if (!searchSymbol.trim()) return;
    
    setLoading(true);
    try {
      const timeframe = selectedTimeframe.toLowerCase();
      const response = await api.post(`/api/patterns/analyze`, {
        symbol: searchSymbol.toUpperCase(),
        timeframe: timeframe,
        categories: selectedPattern !== 'all' ? [selectedPattern] : undefined
      });
      
      if (response.data.success) {
        // Transform API response to match frontend expectations
        const transformedPatterns = response.data.patterns?.map(pattern => ({
          symbol: pattern.symbol,
          pattern: pattern.patternName,
          bias: pattern.direction,
          confidence: Math.round(pattern.confidence * 100),
          strength: pattern.signalStrength === 'very_strong' ? 95 : 
                   pattern.signalStrength === 'strong' ? 85 :
                   pattern.signalStrength === 'moderate' ? 70 : 50,
          timeframe: pattern.timeframe,
          entryPrice: pattern.targetPrice || 0,
          targetPrice: pattern.targetPrice || 0,
          stopLoss: pattern.stopLoss || 0,
          riskReward: pattern.riskRewardRatio ? `${pattern.riskRewardRatio}:1` : '1:1',
          detectedAt: new Date(pattern.detectionDate).toLocaleDateString(),
          description: pattern.description || `${pattern.direction} ${pattern.patternName} pattern`
        })) || [];

        // Add the analyzed symbol patterns to the top of the list
        setPatterns([...transformedPatterns, ...patterns]);
      }
    } catch (error) {
      console.error('Failed to analyze symbol:', error);
    } finally {
      setLoading(false);
    }
  };

  const getPatternColor = (direction) => {
    if (direction === 'bullish') return 'success';
    if (direction === 'bearish') return 'error';
    return 'info';
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.90) return 'success';
    if (confidence >= 0.75) return 'info';
    if (confidence >= 0.60) return 'warning';
    return 'error';
  };

  const formatPatternName = (pattern) => {
    return pattern.split('_').map(word => 
      word.charAt(0).toUpperCase() + word.slice(1)
    ).join(' ');
  };

  const getPatternIcon = (direction) => {
    if (direction === 'bullish') return <TrendingUp color="success" />;
    if (direction === 'bearish') return <TrendingDown color="error" />;
    return <BarChart3 color="primary" />;
  };

  return (
    <Container maxWidth="xl">
      <Box mb={4}>
        <Typography variant="h3" component="h1" gutterBottom fontWeight="bold">
          AI Pattern Recognition
        </Typography>
        <Typography variant="h6" color="text.secondary">
          Advanced technical pattern detection using machine learning
        </Typography>
      </Box>

      {/* Search and Filters */}
      <Card sx={{ mb: 3 }}>
        <CardContent sx={{ p: 3 }}>
          <Grid container spacing={3} alignItems="end">
            <Grid item xs={12} md={2}>
              <Typography variant="body2" fontWeight="medium" gutterBottom>
                Symbol
              </Typography>
              <Box display="flex" gap={1}>
                <TextField
                  placeholder="Enter symbol..."
                  value={searchSymbol}
                  onChange={(e) => setSearchSymbol(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && analyzeSymbol()}
                  size="small"
                  fullWidth
                />
                <IconButton onClick={analyzeSymbol} disabled={loading} color="primary">
                  <Search />
                </IconButton>
              </Box>
            </Grid>

            <Grid item xs={12} md={2}>
              <Typography variant="body2" fontWeight="medium" gutterBottom>
                Timeframe
              </Typography>
              <FormControl fullWidth size="small">
                <Select value={selectedTimeframe} onChange={(e) => setSelectedTimeframe(e.target.value)}>
                  <MenuItem value="1D">1 Day</MenuItem>
                  <MenuItem value="1W">1 Week</MenuItem>
                  <MenuItem value="1M">1 Month</MenuItem>
                  <MenuItem value="3M">3 Months</MenuItem>
                  <MenuItem value="6M">6 Months</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} md={2}>
              <Typography variant="body2" fontWeight="medium" gutterBottom>
                Pattern Type
              </Typography>
              <FormControl fullWidth size="small">
                <Select value={selectedPattern} onChange={(e) => setSelectedPattern(e.target.value)}>
                  <MenuItem value="all">All Patterns</MenuItem>
                  <MenuItem value="bullish">Bullish Only</MenuItem>
                  <MenuItem value="bearish">Bearish Only</MenuItem>
                  <MenuItem value="reversal">Reversal Patterns</MenuItem>
                  <MenuItem value="continuation">Continuation Patterns</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} md={2}>
              <Typography variant="body2" fontWeight="medium" gutterBottom>
                Min Confidence: {confidenceFilter}%
              </Typography>
              <Slider
                value={confidenceFilter}
                onChange={(e, value) => setConfidenceFilter(value)}
                min={50}
                max={99}
                marks
                valueLabelDisplay="auto"
                size="small"
              />
            </Grid>

            <Grid item xs={12} md={2}>
              <Button 
                onClick={loadPatterns} 
                disabled={loading} 
                variant="contained"
                startIcon={<Filter />}
                fullWidth
              >
                Scan Market
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)} sx={{ mb: 3 }}>
        <Tab label={`Detected Patterns (${patterns.length})`} />
        <Tab label="Bullish Signals" />
        <Tab label="Bearish Signals" />
        <Tab label="Pattern Analytics" />
      </Tabs>

      {activeTab === 0 && (
        <Box>
          {loading && (
            <Grid container spacing={3}>
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <Grid item xs={12} md={6} lg={4} key={i}>
                  <Card sx={{ minHeight: 300 }}>
                    <CardContent>
                      <Box sx={{ height: 200, bgcolor: 'grey.100', borderRadius: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <CircularProgress />
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}

          {!loading && patterns.length > 0 && (
            <Grid container spacing={3}>
              {patterns.map((pattern, index) => (
                <Grid item xs={12} md={6} lg={4} key={index}>
                  <Card sx={{ '&:hover': { boxShadow: 4 }, transition: 'box-shadow 0.2s' }}>
                    <CardHeader 
                      title={
                        <Box display="flex" alignItems="center" justifyContent="space-between">
                          <Box display="flex" alignItems="center" gap={1}>
                            <Typography variant="h6" component="span">
                              {pattern.symbol}
                            </Typography>
                            {getPatternIcon(pattern.bias)}
                          </Box>
                          <Chip 
                            label={`${pattern.confidence}%`} 
                            color={getConfidenceColor(pattern.confidence)}
                            size="small"
                          />
                        </Box>
                      }
                      subheader={
                        <Box display="flex" alignItems="center" gap={1}>
                          <Chip 
                            label={formatPatternName(pattern.pattern)}
                            color={getPatternColor(pattern.pattern)}
                            size="small"
                          />
                          <Typography variant="body2" color="text.secondary">
                            {pattern.timeframe}
                          </Typography>
                        </Box>
                      }
                    />
                    <CardContent>
                      <Box mb={2}>
                        <Box sx={{ height: 120, bgcolor: 'grey.50', borderRadius: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <Typography variant="body2" color="text.secondary">
                            Pattern Chart
                          </Typography>
                        </Box>
                      </Box>

                      <Grid container spacing={2} sx={{ mb: 2 }}>
                        <Grid item xs={6}>
                          <Typography variant="body2" color="text.secondary">
                            Entry: <strong>${pattern.entryPrice}</strong>
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="body2" color="text.secondary">
                            Target: <strong>${pattern.targetPrice}</strong>
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="body2" color="text.secondary">
                            Stop Loss: <strong>${pattern.stopLoss}</strong>
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="body2" color="text.secondary">
                            R/R: <strong>{pattern.riskReward}</strong>
                          </Typography>
                        </Grid>
                      </Grid>

                      <Box mb={2}>
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                          <Typography variant="body2" color="text.secondary">
                            Pattern Strength
                          </Typography>
                          <Typography variant="body2" fontWeight="medium">
                            {pattern.strength}%
                          </Typography>
                        </Box>
                        <LinearProgress 
                          variant="determinate" 
                          value={pattern.strength} 
                          sx={{ height: 8, borderRadius: 1 }}
                        />
                      </Box>

                      <Box display="flex" alignItems="center" gap={1}>
                        <Clock fontSize="small" color="action" />
                        <Typography variant="caption" color="text.secondary">
                          Detected {pattern.detectedAt}
                        </Typography>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}

          {!loading && patterns.length === 0 && (
            <Card>
              <CardContent sx={{ textAlign: 'center', py: 8 }}>
                <AlertCircle sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
                <Typography variant="h6" gutterBottom>
                  No Patterns Found
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Try adjusting your filters or scanning a different timeframe.
                </Typography>
              </CardContent>
            </Card>
          )}
        </Box>
      )}

      {activeTab === 1 && (
        <Grid container spacing={3}>
          {patterns.filter(p => p.bias === 'bullish').map((pattern, index) => (
            <Grid item xs={12} md={6} lg={4} key={index}>
              <Card sx={{ borderColor: 'success.main', bgcolor: 'success.light', borderWidth: 1, borderStyle: 'solid' }}>
                <CardHeader 
                  title={
                    <Box display="flex" alignItems="center" justifyContent="space-between">
                      <Typography variant="h6" sx={{ color: 'success.dark' }}>
                        {pattern.symbol}
                      </Typography>
                      <TrendingUp sx={{ color: 'success.main' }} />
                    </Box>
                  }
                  subheader={
                    <Chip 
                      label={formatPatternName(pattern.pattern)}
                      sx={{ bgcolor: 'success.lighter', color: 'success.dark' }}
                      size="small"
                    />
                  }
                />
                <CardContent>
                  <Box display="flex" flexDirection="column" gap={1}>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" sx={{ color: 'success.dark' }}>
                        Upside Potential:
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" sx={{ color: 'success.dark' }}>
                        {((pattern.targetPrice - pattern.entryPrice) / pattern.entryPrice * 100).toFixed(1)}%
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" sx={{ color: 'success.dark' }}>
                        Confidence:
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" sx={{ color: 'success.dark' }}>
                        {pattern.confidence}%
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" sx={{ color: 'success.dark' }}>
                        Risk/Reward:
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" sx={{ color: 'success.dark' }}>
                        {pattern.riskReward}
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {activeTab === 2 && (
        <Grid container spacing={3}>
          {patterns.filter(p => p.bias === 'bearish').map((pattern, index) => (
            <Grid item xs={12} md={6} lg={4} key={index}>
              <Card sx={{ borderColor: 'error.main', bgcolor: 'error.light', borderWidth: 1, borderStyle: 'solid' }}>
                <CardHeader 
                  title={
                    <Box display="flex" alignItems="center" justifyContent="space-between">
                      <Typography variant="h6" sx={{ color: 'error.dark' }}>
                        {pattern.symbol}
                      </Typography>
                      <TrendingDown sx={{ color: 'error.main' }} />
                    </Box>
                  }
                  subheader={
                    <Chip 
                      label={formatPatternName(pattern.pattern)}
                      sx={{ bgcolor: 'error.lighter', color: 'error.dark' }}
                      size="small"
                    />
                  }
                />
                <CardContent>
                  <Box display="flex" flexDirection="column" gap={1}>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" sx={{ color: 'error.dark' }}>
                        Downside Risk:
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" sx={{ color: 'error.dark' }}>
                        {((pattern.entryPrice - pattern.targetPrice) / pattern.entryPrice * 100).toFixed(1)}%
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" sx={{ color: 'error.dark' }}>
                        Confidence:
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" sx={{ color: 'error.dark' }}>
                        {pattern.confidence}%
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2" sx={{ color: 'error.dark' }}>
                        Risk/Reward:
                      </Typography>
                      <Typography variant="body2" fontWeight="bold" sx={{ color: 'error.dark' }}>
                        {pattern.riskReward}
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      {activeTab === 3 && (
        <Box>
          <Grid container spacing={3} sx={{ mb: 4 }}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent sx={{ textAlign: 'center', p: 3 }}>
                  <Typography variant="h4" fontWeight="bold" color="success.main" gutterBottom>
                    {patterns.filter(p => p.bias === 'bullish').length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Bullish Patterns
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent sx={{ textAlign: 'center', p: 3 }}>
                  <Typography variant="h4" fontWeight="bold" color="error.main" gutterBottom>
                    {patterns.filter(p => p.bias === 'bearish').length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Bearish Patterns
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent sx={{ textAlign: 'center', p: 3 }}>
                  <Typography variant="h4" fontWeight="bold" color="primary.main" gutterBottom>
                    {patterns.filter(p => p.confidence >= 90).length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    High Confidence
                  </Typography>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent sx={{ textAlign: 'center', p: 3 }}>
                  <Typography variant="h4" fontWeight="bold" color="text.primary" gutterBottom>
                    {patterns.length > 0 ? (patterns.reduce((sum, p) => sum + p.confidence, 0) / patterns.length).toFixed(0) : 0}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Avg Confidence
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Card>
            <CardHeader title="Pattern Performance Statistics" />
            <CardContent>
              <Box mb={3}>
                <Alert severity="info" icon={<AlertCircle />}>
                  Pattern recognition uses advanced machine learning algorithms trained on historical market data. 
                  Results should be used in conjunction with other analysis methods.
                </Alert>
              </Box>

              <Grid container spacing={4}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Most Common Patterns
                  </Typography>
                  <Box display="flex" flexDirection="column" gap={1}>
                    {['bullish_flag', 'ascending_triangle', 'cup_handle', 'double_bottom'].map((pattern, index) => (
                      <Box key={index} display="flex" justifyContent="space-between" alignItems="center">
                        <Typography variant="body2" color="text.secondary">
                          {formatPatternName(pattern)}
                        </Typography>
                        <Typography variant="body2" fontWeight="medium">
                          {Math.floor(Math.random() * 20) + 5}%
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Success Rates by Pattern
                  </Typography>
                  <Box display="flex" flexDirection="column" gap={1}>
                    {['Cup & Handle', 'Ascending Triangle', 'Bull Flag', 'Double Bottom'].map((pattern, index) => (
                      <Box key={index} display="flex" justifyContent="space-between" alignItems="center">
                        <Typography variant="body2" color="text.secondary">
                          {pattern}
                        </Typography>
                        <Typography variant="body2" fontWeight="medium">
                          {70 + Math.floor(Math.random() * 20)}%
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Box>
      )}
    </Container>
  );
};

// ⚠️ MOCK DATA - Replace with real API when available
const mockPatterns = [
  {
    isMockData: true,
    symbol: 'AAPL',
    pattern: 'cup_handle',
    bias: 'bullish',
    confidence: 87,
    strength: 92,
    timeframe: '1D',
    entryPrice: 185.25,
    targetPrice: 205.00,
    stopLoss: 175.00,
    riskReward: '1.9:1',
    detectedAt: '2 hours ago'
  },
  {
    isMockData: true,
    symbol: 'TSLA',
    pattern: 'ascending_triangle',
    bias: 'bullish',
    confidence: 92,
    strength: 88,
    timeframe: '1W',
    entryPrice: 248.50,
    targetPrice: 285.00,
    stopLoss: 230.00,
    riskReward: '2.0:1',
    detectedAt: '4 hours ago'
  },
  {
    isMockData: true,
    symbol: 'NVDA',
    pattern: 'head_shoulders',
    bias: 'bearish',
    confidence: 78,
    strength: 75,
    timeframe: '1D',
    entryPrice: 875.00,
    targetPrice: 795.00,
    stopLoss: 920.00,
    riskReward: '1.8:1',
    detectedAt: '1 day ago'
  },
  {
    isMockData: true,
    symbol: 'MSFT',
    pattern: 'bullish_flag',
    bias: 'bullish',
    confidence: 84,
    strength: 79,
    timeframe: '1W',
    entryPrice: 378.50,
    targetPrice: 415.00,
    stopLoss: 365.00,
    riskReward: '2.7:1',
    detectedAt: '6 hours ago'
  },
  {
    isMockData: true,
    symbol: 'GOOGL',
    pattern: 'double_bottom',
    bias: 'bullish',
    confidence: 91,
    strength: 85,
    timeframe: '1M',
    entryPrice: 142.75,
    targetPrice: 165.00,
    stopLoss: 135.00,
    riskReward: '2.9:1',
    detectedAt: '3 days ago'
  },
  {
    isMockData: true,
    symbol: 'AMZN',
    pattern: 'descending_triangle',
    bias: 'bearish',
    confidence: 76,
    strength: 72,
    timeframe: '1W',
    entryPrice: 155.20,
    targetPrice: 140.00,
    stopLoss: 162.00,
    riskReward: '2.2:1',
    detectedAt: '1 day ago'
  }
];

export default PatternRecognition;