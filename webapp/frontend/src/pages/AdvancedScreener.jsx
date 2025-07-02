import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Search, Filter, Download, Save, Star, TrendingUp, TrendingDown } from 'lucide-react';

const AdvancedScreener = () => {
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
  const [activeTab, setActiveTab] = useState('criteria');

  useEffect(() => {
    loadSavedScreens();
  }, []);

  const loadSavedScreens = async () => {
    try {
      const response = await fetch('/api/screener/saved');
      const data = await response.json();
      setSavedScreens(data);
    } catch (error) {
      console.error('Failed to load saved screens:', error);
    }
  };

  const runScreen = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/screener/advanced', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ criteria: screenCriteria })
      });
      const data = await response.json();
      setResults(data.results || mockResults);
      setActiveTab('results');
    } catch (error) {
      console.error('Failed to run screen:', error);
      setResults(mockResults);
      setActiveTab('results');
    } finally {
      setLoading(false);
    }
  };

  const saveScreen = async () => {
    const name = prompt('Enter a name for this screen:');
    if (!name) return;

    try {
      await fetch('/api/screener/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, criteria: screenCriteria })
      });
      loadSavedScreens();
    } catch (error) {
      console.error('Failed to save screen:', error);
    }
  };

  const loadScreen = (criteria) => {
    setScreenCriteria(criteria);
    setActiveTab('criteria');
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
    if (score >= 80) return 'text-green-600 bg-green-50';
    if (score >= 60) return 'text-blue-600 bg-blue-50';
    if (score >= 40) return 'text-yellow-600 bg-yellow-50';
    return 'text-red-600 bg-red-50';
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Advanced Stock Screener</h1>
        <p className="text-gray-600">Filter stocks using institutional-grade scoring methodology</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="criteria">Screen Criteria</TabsTrigger>
          <TabsTrigger value="results">Results ({results.length})</TabsTrigger>
          <TabsTrigger value="saved">Saved Screens</TabsTrigger>
          <TabsTrigger value="presets">Presets</TabsTrigger>
        </TabsList>

        <TabsContent value="criteria" className="space-y-6">
          {/* Score-Based Filters */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Filter className="w-5 h-5" />
                <span>Scoring Criteria</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Quality Score */}
              <div>
                <label className="text-sm font-medium text-gray-700 mb-2 block">
                  Quality Score: {screenCriteria.quality[0]} - {screenCriteria.quality[1]}
                </label>
                <Slider
                  value={screenCriteria.quality}
                  onValueChange={(value) => setScreenCriteria({...screenCriteria, quality: value})}
                  max={100}
                  step={1}
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">Earnings quality, balance sheet strength, profitability, management effectiveness</p>
              </div>

              {/* Growth Score */}
              <div>
                <label className="text-sm font-medium text-gray-700 mb-2 block">
                  Growth Score: {screenCriteria.growth[0]} - {screenCriteria.growth[1]}
                </label>
                <Slider
                  value={screenCriteria.growth}
                  onValueChange={(value) => setScreenCriteria({...screenCriteria, growth: value})}
                  max={100}
                  step={1}
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">Revenue growth, earnings growth, fundamental growth drivers</p>
              </div>

              {/* Value Score */}
              <div>
                <label className="text-sm font-medium text-gray-700 mb-2 block">
                  Value Score: {screenCriteria.value[0]} - {screenCriteria.value[1]}
                </label>
                <Slider
                  value={screenCriteria.value}
                  onValueChange={(value) => setScreenCriteria({...screenCriteria, value: value})}
                  max={100}
                  step={1}
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">Traditional multiples, DCF analysis, relative valuation</p>
              </div>

              {/* Momentum Score */}
              <div>
                <label className="text-sm font-medium text-gray-700 mb-2 block">
                  Momentum Score: {screenCriteria.momentum[0]} - {screenCriteria.momentum[1]}
                </label>
                <Slider
                  value={screenCriteria.momentum}
                  onValueChange={(value) => setScreenCriteria({...screenCriteria, momentum: value})}
                  max={100}
                  step={1}
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">Price momentum, fundamental momentum, technical indicators</p>
              </div>

              {/* Sentiment Score */}
              <div>
                <label className="text-sm font-medium text-gray-700 mb-2 block">
                  Sentiment Score: {screenCriteria.sentiment[0]} - {screenCriteria.sentiment[1]}
                </label>
                <Slider
                  value={screenCriteria.sentiment}
                  onValueChange={(value) => setScreenCriteria({...screenCriteria, sentiment: value})}
                  max={100}
                  step={1}
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">Analyst sentiment, social sentiment, news sentiment</p>
              </div>

              {/* Positioning Score */}
              <div>
                <label className="text-sm font-medium text-gray-700 mb-2 block">
                  Positioning Score: {screenCriteria.positioning[0]} - {screenCriteria.positioning[1]}
                </label>
                <Slider
                  value={screenCriteria.positioning}
                  onValueChange={(value) => setScreenCriteria({...screenCriteria, positioning: value})}
                  max={100}
                  step={1}
                  className="w-full"
                />
                <p className="text-xs text-gray-500 mt-1">Institutional holdings, insider activity, short interest</p>
              </div>
            </CardContent>
          </Card>

          {/* Traditional Filters */}
          <Card>
            <CardHeader>
              <CardTitle>Traditional Filters</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-700 mb-2 block">Market Cap</label>
                <Select value={screenCriteria.marketCap} onValueChange={(value) => setScreenCriteria({...screenCriteria, marketCap: value})}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any</SelectItem>
                    <SelectItem value="mega">Mega (>$200B)</SelectItem>
                    <SelectItem value="large">Large ($10B-$200B)</SelectItem>
                    <SelectItem value="mid">Mid ($2B-$10B)</SelectItem>
                    <SelectItem value="small">Small ($300M-$2B)</SelectItem>
                    <SelectItem value="micro">Micro (&lt;$300M)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 mb-2 block">Sector</label>
                <Select value={screenCriteria.sector} onValueChange={(value) => setScreenCriteria({...screenCriteria, sector: value})}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any Sector</SelectItem>
                    <SelectItem value="technology">Technology</SelectItem>
                    <SelectItem value="healthcare">Healthcare</SelectItem>
                    <SelectItem value="financials">Financials</SelectItem>
                    <SelectItem value="energy">Energy</SelectItem>
                    <SelectItem value="industrials">Industrials</SelectItem>
                    <SelectItem value="consumer_discretionary">Consumer Discretionary</SelectItem>
                    <SelectItem value="consumer_staples">Consumer Staples</SelectItem>
                    <SelectItem value="utilities">Utilities</SelectItem>
                    <SelectItem value="real_estate">Real Estate</SelectItem>
                    <SelectItem value="materials">Materials</SelectItem>
                    <SelectItem value="communication">Communication</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div>
                <label className="text-sm font-medium text-gray-700 mb-2 block">Exchange</label>
                <Select value={screenCriteria.exchange} onValueChange={(value) => setScreenCriteria({...screenCriteria, exchange: value})}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any Exchange</SelectItem>
                    <SelectItem value="NYSE">NYSE</SelectItem>
                    <SelectItem value="NASDAQ">NASDAQ</SelectItem>
                    <SelectItem value="AMEX">AMEX</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Action Buttons */}
          <div className="flex space-x-4">
            <Button onClick={runScreen} disabled={loading} className="flex items-center space-x-2">
              {loading ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
              ) : (
                <Search className="w-4 h-4" />
              )}
              <span>{loading ? 'Screening...' : 'Run Screen'}</span>
            </Button>
            <Button variant="outline" onClick={saveScreen} className="flex items-center space-x-2">
              <Save className="w-4 h-4" />
              <span>Save Screen</span>
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="results" className="space-y-6">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">Screen Results ({results.length} stocks)</h3>
            <Button variant="outline" onClick={exportResults} className="flex items-center space-x-2">
              <Download className="w-4 h-4" />
              <span>Export CSV</span>
            </Button>
          </div>

          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="text-left p-4 font-medium text-gray-900">Stock</th>
                      <th className="text-center p-4 font-medium text-gray-900">Quality</th>
                      <th className="text-center p-4 font-medium text-gray-900">Growth</th>
                      <th className="text-center p-4 font-medium text-gray-900">Value</th>
                      <th className="text-center p-4 font-medium text-gray-900">Momentum</th>
                      <th className="text-center p-4 font-medium text-gray-900">Sentiment</th>
                      <th className="text-center p-4 font-medium text-gray-900">Positioning</th>
                      <th className="text-center p-4 font-medium text-gray-900">Composite</th>
                      <th className="text-right p-4 font-medium text-gray-900">Price</th>
                      <th className="text-right p-4 font-medium text-gray-900">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map((stock, index) => (
                      <tr key={index} className="border-b hover:bg-gray-50">
                        <td className="p-4">
                          <div>
                            <div className="font-medium text-gray-900">{stock.symbol}</div>
                            <div className="text-sm text-gray-500">{stock.company}</div>
                            <div className="text-xs text-gray-400">{stock.sector}</div>
                          </div>
                        </td>
                        <td className="text-center p-4">
                          <Badge className={getScoreColor(stock.scores.quality)}>
                            {stock.scores.quality}
                          </Badge>
                        </td>
                        <td className="text-center p-4">
                          <Badge className={getScoreColor(stock.scores.growth)}>
                            {stock.scores.growth}
                          </Badge>
                        </td>
                        <td className="text-center p-4">
                          <Badge className={getScoreColor(stock.scores.value)}>
                            {stock.scores.value}
                          </Badge>
                        </td>
                        <td className="text-center p-4">
                          <Badge className={getScoreColor(stock.scores.momentum)}>
                            {stock.scores.momentum}
                          </Badge>
                        </td>
                        <td className="text-center p-4">
                          <Badge className={getScoreColor(stock.scores.sentiment)}>
                            {stock.scores.sentiment}
                          </Badge>
                        </td>
                        <td className="text-center p-4">
                          <Badge className={getScoreColor(stock.scores.positioning)}>
                            {stock.scores.positioning}
                          </Badge>
                        </td>
                        <td className="text-center p-4">
                          <Badge className={`${getScoreColor(stock.scores.composite)} font-bold`}>
                            {stock.scores.composite}
                          </Badge>
                        </td>
                        <td className="text-right p-4">
                          <div className="font-medium">${stock.price}</div>
                          <div className={`text-sm flex items-center justify-end ${stock.change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                            {stock.change >= 0 ? <TrendingUp className="w-3 h-3 mr-1" /> : <TrendingDown className="w-3 h-3 mr-1" />}
                            {stock.change >= 0 ? '+' : ''}{stock.change}%
                          </div>
                        </td>
                        <td className="text-right p-4">
                          <Button variant="outline" size="sm" className="flex items-center space-x-1">
                            <Star className="w-3 h-3" />
                            <span>Watch</span>
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="saved" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Saved Screens</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {savedScreens.map((screen, index) => (
                  <div key={index} className="p-4 border rounded-lg hover:bg-gray-50 cursor-pointer"
                       onClick={() => loadScreen(screen.criteria)}>
                    <h4 className="font-medium text-gray-900">{screen.name}</h4>
                    <p className="text-sm text-gray-600 mt-1">{screen.description}</p>
                    <p className="text-xs text-gray-500 mt-2">Last run: {screen.lastRun}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="presets" className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {presetScreens.map((preset, index) => (
              <Card key={index} className="cursor-pointer hover:shadow-md transition-shadow"
                    onClick={() => loadScreen(preset.criteria)}>
                <CardHeader>
                  <CardTitle className="text-lg">{preset.name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-gray-600 mb-4">{preset.description}</p>
                  <div className="space-y-2">
                    {Object.entries(preset.highlights).map(([key, value]) => (
                      <div key={key} className="flex justify-between text-sm">
                        <span className="text-gray-600 capitalize">{key}:</span>
                        <span className="font-medium">{value}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

// Mock data for development
const mockResults = [
  {
    symbol: 'AAPL',
    company: 'Apple Inc.',
    sector: 'Technology',
    scores: { quality: 92, growth: 78, value: 65, momentum: 84, sentiment: 88, positioning: 91, composite: 83 },
    price: 185.25,
    change: 2.4
  },
  {
    symbol: 'MSFT',
    company: 'Microsoft Corporation',
    sector: 'Technology',
    scores: { quality: 89, growth: 82, value: 72, momentum: 76, sentiment: 85, positioning: 88, composite: 82 },
    price: 378.50,
    change: 1.8
  },
  {
    symbol: 'GOOGL',
    company: 'Alphabet Inc.',
    sector: 'Technology',
    scores: { quality: 87, growth: 85, value: 78, momentum: 71, sentiment: 79, positioning: 84, composite: 81 },
    price: 142.75,
    change: -0.5
  }
];

const presetScreens = [
  {
    name: 'Quality Value',
    description: 'High-quality companies trading at attractive valuations',
    criteria: { quality: [80, 100], value: [70, 100], growth: [0, 100], momentum: [0, 100], sentiment: [0, 100], positioning: [0, 100] },
    highlights: { 'Quality Score': '80+', 'Value Score': '70+', 'Focus': 'Buffett-style investing' }
  },
  {
    name: 'Growth Momentum',
    description: 'Fast-growing companies with strong price momentum',
    criteria: { growth: [80, 100], momentum: [70, 100], quality: [0, 100], value: [0, 100], sentiment: [0, 100], positioning: [0, 100] },
    highlights: { 'Growth Score': '80+', 'Momentum Score': '70+', 'Focus': 'Growth investing' }
  },
  {
    name: 'Sentiment Leaders',
    description: 'Stocks with excellent sentiment and institutional backing',
    criteria: { sentiment: [80, 100], positioning: [70, 100], quality: [0, 100], growth: [0, 100], value: [0, 100], momentum: [0, 100] },
    highlights: { 'Sentiment Score': '80+', 'Positioning Score': '70+', 'Focus': 'Smart money following' }
  },
  {
    name: 'All-Around Champions',
    description: 'Stocks scoring well across all categories',
    criteria: { quality: [70, 100], growth: [70, 100], value: [70, 100], momentum: [70, 100], sentiment: [70, 100], positioning: [70, 100] },
    highlights: { 'All Scores': '70+', 'Focus': 'Balanced excellence' }
  },
  {
    name: 'Value Contrarian',
    description: 'Undervalued stocks with improving sentiment',
    criteria: { value: [80, 100], sentiment: [60, 100], quality: [50, 100], growth: [0, 100], momentum: [0, 100], positioning: [0, 100] },
    highlights: { 'Value Score': '80+', 'Improving Sentiment': '60+', 'Focus': 'Contrarian value' }
  },
  {
    name: 'Technical Breakouts',
    description: 'Stocks with strong technical momentum and quality fundamentals',
    criteria: { momentum: [80, 100], quality: [60, 100], growth: [0, 100], value: [0, 100], sentiment: [0, 100], positioning: [0, 100] },
    highlights: { 'Momentum Score': '80+', 'Quality Score': '60+', 'Focus': 'Technical analysis' }
  }
];

export default AdvancedScreener;