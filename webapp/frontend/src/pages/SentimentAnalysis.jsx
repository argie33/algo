import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { AlertTriangle, TrendingUp, TrendingDown, Users, MessageSquare, Globe } from 'lucide-react';

const SentimentAnalysis = () => {
  const [sentimentData, setSentimentData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedTimeframe, setSelectedTimeframe] = useState('1D');

  useEffect(() => {
    fetchSentimentData();
  }, [selectedTimeframe]);

  const fetchSentimentData = async () => {
    try {
      setLoading(true);
      // This would connect to your actual sentiment API endpoints
      const response = await fetch(`/api/sentiment/comprehensive?timeframe=${selectedTimeframe}`);
      const data = await response.json();
      setSentimentData(data);
    } catch (error) {
      console.error('Failed to fetch sentiment data:', error);
      // Mock data for development
      setSentimentData(mockSentimentData);
    } finally {
      setLoading(false);
    }
  };

  const getSentimentColor = (score) => {
    if (score >= 70) return 'text-green-600 bg-green-50';
    if (score >= 40) return 'text-yellow-600 bg-yellow-50';
    return 'text-red-600 bg-red-50';
  };

  const getSentimentIcon = (score) => {
    if (score >= 60) return <TrendingUp className="w-4 h-4" />;
    if (score >= 40) return <AlertTriangle className="w-4 h-4" />;
    return <TrendingDown className="w-4 h-4" />;
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardContent className="h-48 bg-gray-100 rounded-lg"></CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Market Sentiment Analysis</h1>
        <p className="text-gray-600">Comprehensive sentiment tracking across multiple data sources</p>
      </div>

      {/* Timeframe Selector */}
      <div className="mb-6">
        <div className="flex space-x-2">
          {['1D', '1W', '1M', '3M', '6M'].map((timeframe) => (
            <button
              key={timeframe}
              onClick={() => setSelectedTimeframe(timeframe)}
              className={`px-3 py-1 rounded text-sm font-medium ${
                selectedTimeframe === timeframe
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {timeframe}
            </button>
          ))}
        </div>
      </div>

      {/* Overall Sentiment Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Overall Sentiment</p>
                <p className="text-2xl font-bold text-gray-900">{sentimentData?.overall.score}</p>
              </div>
              <div className={`p-2 rounded-lg ${getSentimentColor(sentimentData?.overall.score)}`}>
                {getSentimentIcon(sentimentData?.overall.score)}
              </div>
            </div>
            <Progress value={sentimentData?.overall.score} className="mt-2" />
          </CardContent>
        </Card>

        {['analyst', 'social', 'news'].map((type) => (
          <Card key={type}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-gray-600 capitalize">{type} Sentiment</p>
                  <p className="text-2xl font-bold text-gray-900">{sentimentData?.[type].score}</p>
                </div>
                <div className={`p-2 rounded-lg ${getSentimentColor(sentimentData?.[type].score)}`}>
                  {type === 'analyst' && <Users className="w-4 h-4" />}
                  {type === 'social' && <MessageSquare className="w-4 h-4" />}
                  {type === 'news' && <Globe className="w-4 h-4" />}
                </div>
              </div>
              <p className="text-xs text-gray-500 mt-1">{sentimentData?.[type].change}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="analyst">Analyst Sentiment</TabsTrigger>
          <TabsTrigger value="social">Social Media</TabsTrigger>
          <TabsTrigger value="news">News Sentiment</TabsTrigger>
          <TabsTrigger value="market">Market Signals</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Sentiment Trend Chart */}
            <Card>
              <CardHeader>
                <CardTitle>Sentiment Trend</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-64 flex items-center justify-center bg-gray-50 rounded">
                  {/* This would be a real chart component */}
                  <p className="text-gray-500">Sentiment trend chart would go here</p>
                </div>
              </CardContent>
            </Card>

            {/* Sentiment Distribution */}
            <Card>
              <CardHeader>
                <CardTitle>Sentiment Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {sentimentData?.distribution.map((item, index) => (
                    <div key={index} className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <Badge variant={item.sentiment === 'Bullish' ? 'default' : item.sentiment === 'Bearish' ? 'destructive' : 'secondary'}>
                          {item.sentiment}
                        </Badge>
                        <span className="text-sm text-gray-600">{item.percentage}%</span>
                      </div>
                      <Progress value={item.percentage} className="w-24" />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Key Insights */}
          <Card>
            <CardHeader>
              <CardTitle>Key Insights</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {sentimentData?.insights.map((insight, index) => (
                  <div key={index} className="p-4 rounded-lg border border-gray-200">
                    <div className="flex items-center space-x-2 mb-2">
                      <div className={`w-2 h-2 rounded-full ${insight.type === 'positive' ? 'bg-green-500' : insight.type === 'negative' ? 'bg-red-500' : 'bg-yellow-500'}`}></div>
                      <h4 className="font-medium text-gray-900">{insight.title}</h4>
                    </div>
                    <p className="text-sm text-gray-600">{insight.description}</p>
                    <p className="text-xs text-gray-500 mt-1">{insight.timestamp}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="analyst" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Analyst Recommendations</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {sentimentData?.analyst.recommendations.map((rec, index) => (
                    <div key={index} className="flex items-center justify-between p-3 rounded-lg border">
                      <div>
                        <p className="font-medium">{rec.firm}</p>
                        <p className="text-sm text-gray-600">{rec.symbol}</p>
                      </div>
                      <div className="text-right">
                        <Badge variant={rec.rating === 'Buy' ? 'default' : rec.rating === 'Sell' ? 'destructive' : 'secondary'}>
                          {rec.rating}
                        </Badge>
                        <p className="text-sm text-gray-500">{rec.target}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Earnings Revisions</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {sentimentData?.analyst.revisions.map((revision, index) => (
                    <div key={index} className="flex items-center justify-between p-3 rounded-lg border">
                      <div>
                        <p className="font-medium">{revision.symbol}</p>
                        <p className="text-sm text-gray-600">{revision.period}</p>
                      </div>
                      <div className="text-right">
                        <p className={`font-medium ${revision.change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {revision.change > 0 ? '+' : ''}{revision.change}%
                        </p>
                        <p className="text-sm text-gray-500">{revision.estimates} estimates</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="social" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Social Media Buzz</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {sentimentData?.social.trending.map((trend, index) => (
                    <div key={index} className="flex items-center justify-between p-3 rounded-lg border">
                      <div>
                        <p className="font-medium">{trend.symbol}</p>
                        <p className="text-sm text-gray-600">{trend.mentions} mentions</p>
                      </div>
                      <div className="text-right">
                        <Badge variant={trend.sentiment === 'Positive' ? 'default' : trend.sentiment === 'Negative' ? 'destructive' : 'secondary'}>
                          {trend.sentiment}
                        </Badge>
                        <p className="text-sm text-gray-500">{trend.change}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Reddit Sentiment</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {sentimentData?.social.reddit.map((post, index) => (
                    <div key={index} className="p-3 rounded-lg border">
                      <div className="flex items-center justify-between mb-2">
                        <Badge variant="outline">{post.subreddit}</Badge>
                        <span className="text-sm text-gray-500">{post.score} points</span>
                      </div>
                      <p className="text-sm font-medium">{post.title}</p>
                      <p className="text-xs text-gray-500 mt-1">{post.timestamp}</p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="news" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Financial News Sentiment</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {sentimentData?.news.articles.map((article, index) => (
                  <div key={index} className="p-4 rounded-lg border">
                    <div className="flex items-center justify-between mb-2">
                      <Badge variant={article.sentiment === 'Positive' ? 'default' : article.sentiment === 'Negative' ? 'destructive' : 'secondary'}>
                        {article.sentiment}
                      </Badge>
                      <span className="text-sm text-gray-500">{article.source}</span>
                    </div>
                    <h4 className="font-medium mb-2">{article.title}</h4>
                    <p className="text-sm text-gray-600 mb-2">{article.summary}</p>
                    <p className="text-xs text-gray-500">{article.timestamp}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="market" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Fear & Greed Index</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center">
                  <div className="text-4xl font-bold text-gray-900 mb-2">{sentimentData?.market.fearGreed.value}</div>
                  <div className={`text-lg font-medium mb-4 ${getSentimentColor(sentimentData?.market.fearGreed.value)}`}>
                    {sentimentData?.market.fearGreed.label}
                  </div>
                  <Progress value={sentimentData?.market.fearGreed.value} className="mb-4" />
                  <p className="text-sm text-gray-600">{sentimentData?.market.fearGreed.description}</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Market Indicators</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {sentimentData?.market.indicators.map((indicator, index) => (
                    <div key={index} className="flex items-center justify-between p-3 rounded-lg border">
                      <div>
                        <p className="font-medium">{indicator.name}</p>
                        <p className="text-sm text-gray-600">{indicator.description}</p>
                      </div>
                      <div className="text-right">
                        <p className="font-medium">{indicator.value}</p>
                        <Badge variant={indicator.signal === 'Bullish' ? 'default' : indicator.signal === 'Bearish' ? 'destructive' : 'secondary'}>
                          {indicator.signal}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

// Mock data for development
const mockSentimentData = {
  overall: { score: 65 },
  analyst: { 
    score: 72, 
    change: '+5% this week',
    recommendations: [
      { firm: 'Goldman Sachs', symbol: 'AAPL', rating: 'Buy', target: '$200' },
      { firm: 'Morgan Stanley', symbol: 'TSLA', rating: 'Hold', target: '$250' },
      { firm: 'JP Morgan', symbol: 'NVDA', rating: 'Buy', target: '$900' }
    ],
    revisions: [
      { symbol: 'AAPL', period: 'Q1 2024', change: 5.2, estimates: 12 },
      { symbol: 'MSFT', period: 'Q1 2024', change: -2.1, estimates: 15 },
      { symbol: 'GOOGL', period: 'Q1 2024', change: 3.7, estimates: 10 }
    ]
  },
  social: { 
    score: 58, 
    change: '-2% today',
    trending: [
      { symbol: 'TSLA', mentions: 15420, sentiment: 'Positive', change: '+25%' },
      { symbol: 'AAPL', mentions: 12350, sentiment: 'Neutral', change: '+5%' },
      { symbol: 'AMC', mentions: 8970, sentiment: 'Negative', change: '-15%' }
    ],
    reddit: [
      {
        subreddit: 'r/stocks',
        title: 'Tesla showing strong momentum after delivery numbers',
        score: 1250,
        timestamp: '3 hours ago'
      },
      {
        subreddit: 'r/investing',
        title: 'Market outlook for 2024 - what are your thoughts?',
        score: 890,
        timestamp: '5 hours ago'
      }
    ]
  },
  news: { 
    score: 70, 
    change: '+8% this week',
    articles: [
      {
        title: 'Tech stocks rally on strong earnings expectations',
        summary: 'Major technology companies showing positive momentum ahead of Q1 earnings season',
        sentiment: 'Positive',
        source: 'Reuters',
        timestamp: '1 hour ago'
      },
      {
        title: 'Federal Reserve signals potential rate cuts',
        summary: 'Fed officials hint at possible monetary policy adjustments based on economic data',
        sentiment: 'Positive',
        source: 'Bloomberg',
        timestamp: '3 hours ago'
      }
    ]
  },
  distribution: [
    { sentiment: 'Bullish', percentage: 45 },
    { sentiment: 'Neutral', percentage: 35 },
    { sentiment: 'Bearish', percentage: 20 }
  ],
  insights: [
    {
      type: 'positive',
      title: 'Analyst Upgrade Momentum',
      description: 'Multiple upgrades in tech sector driving positive sentiment',
      timestamp: '2 hours ago'
    },
    {
      type: 'negative',
      title: 'Social Media Concerns',
      description: 'Increased discussion around inflation concerns',
      timestamp: '4 hours ago'
    },
    {
      type: 'neutral',
      title: 'Mixed Earnings Results',
      description: 'Q4 earnings showing mixed results across sectors',
      timestamp: '6 hours ago'
    }
  ],
  market: {
    fearGreed: {
      value: 65,
      label: 'Greed',
      description: 'Market showing signs of optimism with some caution remaining'
    },
    indicators: [
      {
        name: 'VIX',
        description: 'Volatility Index',
        value: '18.5',
        signal: 'Neutral'
      },
      {
        name: 'Put/Call Ratio',
        description: 'Options sentiment',
        value: '0.85',
        signal: 'Bullish'
      },
      {
        name: 'High/Low Index',
        description: 'Market breadth',
        value: '75%',
        signal: 'Bullish'
      }
    ]
  }
};

export default SentimentAnalysis;