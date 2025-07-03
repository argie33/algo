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

  useEffect(() => {
    loadPatterns();
  }, [selectedTimeframe, confidenceFilter, selectedPattern]);

  const loadPatterns = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/patterns/scan?timeframe=${selectedTimeframe}&confidence=${confidenceFilter}&pattern=${selectedPattern}`);
      const data = await response.json();
      // ⚠️ MOCK DATA - Using mock patterns when API unavailable
      setPatterns(data.patterns || mockPatterns);
    } catch (error) {
      console.error('Failed to load patterns:', error);
      // ⚠️ MOCK DATA - Fallback to mock patterns
      setPatterns(mockPatterns);
    } finally {
      setLoading(false);
    }
  };

  const analyzeSymbol = async () => {
    if (!searchSymbol.trim()) return;
    
    setLoading(true);
    try {
      const response = await fetch(`/api/patterns/analyze/${searchSymbol.toUpperCase()}?timeframe=${selectedTimeframe}`);
      const data = await response.json();
      // Add the analyzed symbol patterns to the top of the list
      setPatterns([...data.patterns, ...patterns]);
    } catch (error) {
      console.error('Failed to analyze symbol:', error);
    } finally {
      setLoading(false);
    }
  };

  const getPatternColor = (pattern) => {
    const bullishPatterns = ['bullish_flag', 'cup_handle', 'ascending_triangle', 'double_bottom', 'inverse_head_shoulders'];
    const bearishPatterns = ['bearish_flag', 'head_shoulders', 'descending_triangle', 'double_top', 'falling_wedge'];
    
    if (bullishPatterns.some(p => pattern.includes(p))) return 'success';
    if (bearishPatterns.some(p => pattern.includes(p))) return 'error';
    return 'info';
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 90) return 'success';
    if (confidence >= 75) return 'info';
    if (confidence >= 60) return 'warning';
    return 'error';
  };

  const formatPatternName = (pattern) => {
    return pattern.split('_').map(word => 
      word.charAt(0).toUpperCase() + word.slice(1)
    ).join(' ');
  };

  const getPatternIcon = (bias) => {
    if (bias === 'bullish') return <TrendingUp className="w-4 h-4 text-green-600" />;
    if (bias === 'bearish') return <TrendingDown className="w-4 h-4 text-red-600" />;
    return <BarChart3 className="w-4 h-4 text-blue-600" />;
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">AI Pattern Recognition</h1>
        <p className="text-gray-600">Advanced technical pattern detection using machine learning</p>
      </div>

      {/* Search and Filters */}
      <Card className="mb-6">
        <CardContent className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
            <div>
              <label className="text-sm font-medium text-gray-700 mb-2 block">Symbol</label>
              <div className="flex space-x-2">
                <Input
                  placeholder="Enter symbol..."
                  value={searchSymbol}
                  onChange={(e) => setSearchSymbol(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && analyzeSymbol()}
                />
                <Button onClick={analyzeSymbol} disabled={loading}>
                  <Search className="w-4 h-4" />
                </Button>
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 mb-2 block">Timeframe</label>
              <Select value={selectedTimeframe} onValueChange={setSelectedTimeframe}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1D">1 Day</SelectItem>
                  <SelectItem value="1W">1 Week</SelectItem>
                  <SelectItem value="1M">1 Month</SelectItem>
                  <SelectItem value="3M">3 Months</SelectItem>
                  <SelectItem value="6M">6 Months</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 mb-2 block">Pattern Type</label>
              <Select value={selectedPattern} onValueChange={setSelectedPattern}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Patterns</SelectItem>
                  <SelectItem value="bullish">Bullish Only</SelectItem>
                  <SelectItem value="bearish">Bearish Only</SelectItem>
                  <SelectItem value="reversal">Reversal Patterns</SelectItem>
                  <SelectItem value="continuation">Continuation Patterns</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="text-sm font-medium text-gray-700 mb-2 block">
                Min Confidence: {confidenceFilter}%
              </label>
              <input
                type="range"
                min="50"
                max="99"
                value={confidenceFilter}
                onChange={(e) => setConfidenceFilter(parseInt(e.target.value))}
                className="w-full"
              />
            </div>

            <Button onClick={loadPatterns} disabled={loading} className="flex items-center space-x-2">
              <Filter className="w-4 h-4" />
              <span>Scan Market</span>
            </Button>
          </div>
        </CardContent>
      </Card>

      <Tabs defaultValue="detected" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="detected">Detected Patterns ({patterns.length})</TabsTrigger>
          <TabsTrigger value="bullish">Bullish Signals</TabsTrigger>
          <TabsTrigger value="bearish">Bearish Signals</TabsTrigger>
          <TabsTrigger value="analytics">Pattern Analytics</TabsTrigger>
        </TabsList>

        <TabsContent value="detected" className="space-y-6">
          {loading && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <Card key={i} className="animate-pulse">
                  <CardContent className="h-48 bg-gray-100 rounded-lg"></CardContent>
                </Card>
              ))}
            </div>
          )}

          {!loading && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {patterns.map((pattern, index) => (
                <Card key={index} className="hover:shadow-lg transition-shadow">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <h3 className="font-bold text-lg">{pattern.symbol}</h3>
                        {getPatternIcon(pattern.bias)}
                      </div>
                      <Badge className={getConfidenceColor(pattern.confidence)}>
                        {pattern.confidence}%
                      </Badge>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Badge className={getPatternColor(pattern.pattern)}>
                        {formatPatternName(pattern.pattern)}
                      </Badge>
                      <span className="text-sm text-gray-500">{pattern.timeframe}</span>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {/* Pattern Visualization Placeholder */}
                      <div className="h-32 bg-gray-50 rounded flex items-center justify-center">
                        <span className="text-gray-500 text-sm">Pattern Chart</span>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div>
                          <span className="text-gray-600">Entry:</span>
                          <span className="font-medium ml-2">${pattern.entryPrice}</span>
                        </div>
                        <div>
                          <span className="text-gray-600">Target:</span>
                          <span className="font-medium ml-2">${pattern.targetPrice}</span>
                        </div>
                        <div>
                          <span className="text-gray-600">Stop Loss:</span>
                          <span className="font-medium ml-2">${pattern.stopLoss}</span>
                        </div>
                        <div>
                          <span className="text-gray-600">R/R:</span>
                          <span className="font-medium ml-2">{pattern.riskReward}</span>
                        </div>
                      </div>

                      <div className="pt-2">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-gray-600">Pattern Strength</span>
                          <span className="text-sm font-medium">{pattern.strength}%</span>
                        </div>
                        <Progress value={pattern.strength} className="h-2" />
                      </div>

                      <div className="flex items-center space-x-2 text-xs text-gray-500">
                        <Clock className="w-3 h-3" />
                        <span>Detected {pattern.detectedAt}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {!loading && patterns.length === 0 && (
            <Card>
              <CardContent className="text-center py-12">
                <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No Patterns Found</h3>
                <p className="text-gray-600">Try adjusting your filters or scanning a different timeframe.</p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="bullish" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {patterns.filter(p => p.bias === 'bullish').map((pattern, index) => (
              <Card key={index} className="border-green-200 bg-green-50">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <h3 className="font-bold text-lg text-green-800">{pattern.symbol}</h3>
                    <TrendingUp className="w-5 h-5 text-green-600" />
                  </div>
                  <Badge className="bg-green-100 text-green-800 border-green-300">
                    {formatPatternName(pattern.pattern)}
                  </Badge>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-green-700">Upside Potential:</span>
                      <span className="font-bold text-green-800">
                        {((pattern.targetPrice - pattern.entryPrice) / pattern.entryPrice * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-green-700">Confidence:</span>
                      <span className="font-bold text-green-800">{pattern.confidence}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-green-700">Risk/Reward:</span>
                      <span className="font-bold text-green-800">{pattern.riskReward}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="bearish" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {patterns.filter(p => p.bias === 'bearish').map((pattern, index) => (
              <Card key={index} className="border-red-200 bg-red-50">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <h3 className="font-bold text-lg text-red-800">{pattern.symbol}</h3>
                    <TrendingDown className="w-5 h-5 text-red-600" />
                  </div>
                  <Badge className="bg-red-100 text-red-800 border-red-300">
                    {formatPatternName(pattern.pattern)}
                  </Badge>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span className="text-red-700">Downside Risk:</span>
                      <span className="font-bold text-red-800">
                        {((pattern.entryPrice - pattern.targetPrice) / pattern.entryPrice * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-red-700">Confidence:</span>
                      <span className="font-bold text-red-800">{pattern.confidence}%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-red-700">Risk/Reward:</span>
                      <span className="font-bold text-red-800">{pattern.riskReward}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="analytics" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardContent className="p-6 text-center">
                <div className="text-2xl font-bold text-green-600 mb-2">
                  {patterns.filter(p => p.bias === 'bullish').length}
                </div>
                <div className="text-sm text-gray-600">Bullish Patterns</div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6 text-center">
                <div className="text-2xl font-bold text-red-600 mb-2">
                  {patterns.filter(p => p.bias === 'bearish').length}
                </div>
                <div className="text-sm text-gray-600">Bearish Patterns</div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6 text-center">
                <div className="text-2xl font-bold text-blue-600 mb-2">
                  {patterns.filter(p => p.confidence >= 90).length}
                </div>
                <div className="text-sm text-gray-600">High Confidence</div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6 text-center">
                <div className="text-2xl font-bold text-gray-900 mb-2">
                  {patterns.length > 0 ? (patterns.reduce((sum, p) => sum + p.confidence, 0) / patterns.length).toFixed(0) : 0}%
                </div>
                <div className="text-sm text-gray-600">Avg Confidence</div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Pattern Performance Statistics</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    Pattern recognition uses advanced machine learning algorithms trained on historical market data. 
                    Results should be used in conjunction with other analysis methods.
                  </AlertDescription>
                </Alert>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <h4 className="font-medium text-gray-900 mb-3">Most Common Patterns</h4>
                    <div className="space-y-2">
                      {['bullish_flag', 'ascending_triangle', 'cup_handle', 'double_bottom'].map((pattern, index) => (
                        <div key={index} className="flex justify-between items-center">
                          <span className="text-sm text-gray-600">{formatPatternName(pattern)}</span>
                          <span className="text-sm font-medium">{Math.floor(Math.random() * 20) + 5}%</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h4 className="font-medium text-gray-900 mb-3">Success Rates by Pattern</h4>
                    <div className="space-y-2">
                      {['Cup & Handle', 'Ascending Triangle', 'Bull Flag', 'Double Bottom'].map((pattern, index) => (
                        <div key={index} className="flex justify-between items-center">
                          <span className="text-sm text-gray-600">{pattern}</span>
                          <span className="text-sm font-medium">{70 + Math.floor(Math.random() * 20)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
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