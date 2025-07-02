import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { 
  TrendingUp, 
  TrendingDown, 
  AlertTriangle, 
  Target, 
  BarChart3, 
  Activity,
  DollarSign,
  Building,
  Users,
  Zap
} from 'lucide-react';

const EconomicModeling = () => {
  const [economicData, setEconomicData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedTimeframe, setSelectedTimeframe] = useState('6M');

  useEffect(() => {
    fetchEconomicData();
  }, [selectedTimeframe]);

  const fetchEconomicData = async () => {
    try {
      setLoading(true);
      // This would connect to your actual economic modeling API
      const response = await fetch(`/api/economic/comprehensive?timeframe=${selectedTimeframe}`);
      const data = await response.json();
      setEconomicData(data);
    } catch (error) {
      console.error('Failed to fetch economic data:', error);
      // Mock data for development
      setEconomicData(mockEconomicData);
    } finally {
      setLoading(false);
    }
  };

  const getRiskColor = (level) => {
    switch (level) {
      case 'Low': return 'text-green-600 bg-green-50 border-green-200';
      case 'Medium': return 'text-yellow-600 bg-yellow-50 border-yellow-200';
      case 'High': return 'text-red-600 bg-red-50 border-red-200';
      default: return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  const getIndicatorIcon = (trend) => {
    if (trend === 'improving') return <TrendingUp className="w-4 h-4 text-green-600" />;
    if (trend === 'deteriorating') return <TrendingDown className="w-4 h-4 text-red-600" />;
    return <Activity className="w-4 h-4 text-gray-600" />;
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
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
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Economic Modeling & Analysis</h1>
        <p className="text-gray-600">Real-time economic indicators and recession probability modeling</p>
      </div>

      {/* Timeframe Selector */}
      <div className="mb-6">
        <div className="flex space-x-2">
          {['3M', '6M', '1Y', '2Y', '5Y'].map((timeframe) => (
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

      {/* Recession Alert */}
      {economicData?.recessionProbability >= 30 && (
        <Alert className="mb-6 border-yellow-200 bg-yellow-50">
          <AlertTriangle className="h-4 w-4 text-yellow-600" />
          <AlertDescription className="text-yellow-800">
            <strong>Elevated Recession Risk:</strong> Current indicators suggest a {economicData.recessionProbability}% 
            probability of recession within the next 6-12 months.
          </AlertDescription>
        </Alert>
      )}

      {/* Key Metrics Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Recession Probability</p>
                <p className="text-2xl font-bold text-gray-900">{economicData?.recessionProbability}%</p>
                <p className="text-xs text-gray-500">6-12 month horizon</p>
              </div>
              <div className={`p-2 rounded-lg ${getRiskColor(economicData?.riskLevel)}`}>
                <Target className="w-4 h-4" />
              </div>
            </div>
            <Progress value={economicData?.recessionProbability} className="mt-2" />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">GDP Growth</p>
                <p className="text-2xl font-bold text-gray-900">{economicData?.gdpGrowth}%</p>
                <p className="text-xs text-gray-500">Annualized Q/Q</p>
              </div>
              <div className="p-2 rounded-lg bg-blue-50">
                <BarChart3 className="w-4 h-4 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Unemployment</p>
                <p className="text-2xl font-bold text-gray-900">{economicData?.unemployment}%</p>
                <p className="text-xs text-gray-500">Current rate</p>
              </div>
              <div className="p-2 rounded-lg bg-green-50">
                <Users className="w-4 h-4 text-green-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Inflation (CPI)</p>
                <p className="text-2xl font-bold text-gray-900">{economicData?.inflation}%</p>
                <p className="text-xs text-gray-500">Y/Y change</p>
              </div>
              <div className="p-2 rounded-lg bg-yellow-50">
                <DollarSign className="w-4 h-4 text-yellow-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="indicators" className="w-full">
        <TabsList className="grid w-full grid-cols-5">
          <TabsTrigger value="indicators">Leading Indicators</TabsTrigger>
          <TabsTrigger value="yieldCurve">Yield Curve</TabsTrigger>
          <TabsTrigger value="credit">Credit Markets</TabsTrigger>
          <TabsTrigger value="employment">Employment</TabsTrigger>
          <TabsTrigger value="forecast">Forecast Models</TabsTrigger>
        </TabsList>

        <TabsContent value="indicators" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Leading Economic Indicators</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {economicData?.leadingIndicators.map((indicator, index) => (
                  <div key={index} className="p-4 rounded-lg border">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-medium text-gray-900 flex items-center space-x-2">
                        {getIndicatorIcon(indicator.trend)}
                        <span>{indicator.name}</span>
                      </h4>
                      <Badge variant={indicator.signal === 'Positive' ? 'default' : indicator.signal === 'Negative' ? 'destructive' : 'secondary'}>
                        {indicator.signal}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-2xl font-bold">{indicator.value}</span>
                      <span className={`text-sm ${indicator.change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {indicator.change > 0 ? '+' : ''}{indicator.change}%
                      </span>
                    </div>
                    <p className="text-sm text-gray-600 mt-2">{indicator.description}</p>
                    <div className="mt-2">
                      <Progress value={indicator.strength} className="h-2" />
                      <p className="text-xs text-gray-500 mt-1">Signal Strength: {indicator.strength}%</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Economic Calendar */}
          <Card>
            <CardHeader>
              <CardTitle>Upcoming Economic Events</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {economicData?.upcomingEvents.map((event, index) => (
                  <div key={index} className="flex items-center justify-between p-3 rounded-lg border">
                    <div>
                      <h4 className="font-medium text-gray-900">{event.event}</h4>
                      <p className="text-sm text-gray-600">{event.date} • {event.time}</p>
                    </div>
                    <div className="text-right">
                      <Badge variant={event.importance === 'High' ? 'destructive' : event.importance === 'Medium' ? 'default' : 'secondary'}>
                        {event.importance}
                      </Badge>
                      <p className="text-sm text-gray-500">Forecast: {event.forecast}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="yieldCurve" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Yield Curve Analysis</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-64 flex items-center justify-center bg-gray-50 rounded">
                  <p className="text-gray-500">Yield curve chart would go here</p>
                </div>
                <div className="mt-4 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">2Y-10Y Spread:</span>
                    <span className={`font-medium ${economicData?.yieldCurve.spread2y10y >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {economicData?.yieldCurve.spread2y10y >= 0 ? '+' : ''}{economicData?.yieldCurve.spread2y10y} bps
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">3M-10Y Spread:</span>
                    <span className={`font-medium ${economicData?.yieldCurve.spread3m10y >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {economicData?.yieldCurve.spread3m10y >= 0 ? '+' : ''}{economicData?.yieldCurve.spread3m10y} bps
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Inversion Analysis</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className={`p-4 rounded-lg border-2 ${economicData?.yieldCurve.isInverted ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50'}`}>
                    <div className="flex items-center space-x-2 mb-2">
                      {economicData?.yieldCurve.isInverted ? (
                        <AlertTriangle className="w-5 h-5 text-red-600" />
                      ) : (
                        <TrendingUp className="w-5 h-5 text-green-600" />
                      )}
                      <h4 className={`font-medium ${economicData?.yieldCurve.isInverted ? 'text-red-800' : 'text-green-800'}`}>
                        {economicData?.yieldCurve.isInverted ? 'Yield Curve Inverted' : 'Normal Yield Curve'}
                      </h4>
                    </div>
                    <p className={`text-sm ${economicData?.yieldCurve.isInverted ? 'text-red-700' : 'text-green-700'}`}>
                      {economicData?.yieldCurve.interpretation}
                    </p>
                  </div>

                  <div className="space-y-2">
                    <h5 className="font-medium text-gray-900">Historical Context</h5>
                    <p className="text-sm text-gray-600">
                      Inverted yield curves have preceded {economicData?.yieldCurve.historicalAccuracy}% of recessions 
                      since 1970, with an average lead time of {economicData?.yieldCurve.averageLeadTime} months.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="credit" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Credit Spreads</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {economicData?.creditSpreads.map((spread, index) => (
                    <div key={index} className="flex items-center justify-between p-3 rounded-lg border">
                      <div>
                        <h4 className="font-medium text-gray-900">{spread.name}</h4>
                        <p className="text-sm text-gray-600">{spread.description}</p>
                      </div>
                      <div className="text-right">
                        <span className="text-lg font-bold">{spread.value} bps</span>
                        <p className={`text-sm ${spread.change > 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {spread.change > 0 ? '+' : ''}{spread.change} bps
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Financial Stress Index</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-center mb-4">
                  <div className="text-3xl font-bold text-gray-900 mb-2">{economicData?.financialStress.index}</div>
                  <Badge className={getRiskColor(economicData?.financialStress.level)}>
                    {economicData?.financialStress.level} Stress
                  </Badge>
                </div>
                <Progress value={economicData?.financialStress.percentile} className="mb-4" />
                <p className="text-sm text-gray-600 text-center">
                  {economicData?.financialStress.interpretation}
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="employment" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Employment Indicators</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {economicData?.employment.indicators.map((indicator, index) => (
                    <div key={index} className="flex items-center justify-between p-3 rounded-lg border">
                      <div>
                        <h4 className="font-medium text-gray-900">{indicator.name}</h4>
                        <p className="text-sm text-gray-600">{indicator.period}</p>
                      </div>
                      <div className="text-right">
                        <span className="text-lg font-bold">{indicator.value}</span>
                        <p className={`text-sm ${indicator.change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {indicator.change > 0 ? '+' : ''}{indicator.change}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Sahm Rule Indicator</CardTitle>
              </CardHeader>
              <CardContent>
                <div className={`p-4 rounded-lg border-2 ${economicData?.employment.sahmRule.triggered ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50'}`}>
                  <div className="flex items-center space-x-2 mb-2">
                    {economicData?.employment.sahmRule.triggered ? (
                      <AlertTriangle className="w-5 h-5 text-red-600" />
                    ) : (
                      <TrendingUp className="w-5 h-5 text-green-600" />
                    )}
                    <h4 className={`font-medium ${economicData?.employment.sahmRule.triggered ? 'text-red-800' : 'text-green-800'}`}>
                      Sahm Rule {economicData?.employment.sahmRule.triggered ? 'Triggered' : 'Not Triggered'}
                    </h4>
                  </div>
                  <p className="text-lg font-bold mb-2">Current Value: {economicData?.employment.sahmRule.value}</p>
                  <p className={`text-sm ${economicData?.employment.sahmRule.triggered ? 'text-red-700' : 'text-green-700'}`}>
                    {economicData?.employment.sahmRule.interpretation}
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="forecast" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Economic Forecast Models</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {economicData?.forecastModels.map((model, index) => (
                  <div key={index} className="p-4 rounded-lg border">
                    <h4 className="font-medium text-gray-900 mb-2">{model.name}</h4>
                    <div className="text-center mb-3">
                      <div className="text-2xl font-bold text-gray-900">{model.probability}%</div>
                      <p className="text-sm text-gray-600">Recession Probability</p>
                    </div>
                    <Progress value={model.probability} className="mb-3" />
                    <div className="space-y-1 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-600">Confidence:</span>
                        <span className="font-medium">{model.confidence}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Time Horizon:</span>
                        <span className="font-medium">{model.timeHorizon}</span>
                      </div>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">{model.methodology}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Scenario Analysis</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {economicData?.scenarios.map((scenario, index) => (
                  <div key={index} className={`p-4 rounded-lg border-2 ${scenario.likelihood === 'Base Case' ? 'border-blue-200 bg-blue-50' : scenario.likelihood === 'Bear Case' ? 'border-red-200 bg-red-50' : 'border-green-200 bg-green-50'}`}>
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="font-medium">{scenario.name}</h4>
                      <Badge variant="outline">{scenario.probability}%</Badge>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span>GDP Growth:</span>
                        <span className="font-medium">{scenario.gdpGrowth}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Unemployment:</span>
                        <span className="font-medium">{scenario.unemployment}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Fed Funds Rate:</span>
                        <span className="font-medium">{scenario.fedRate}%</span>
                      </div>
                    </div>
                    <p className="text-xs text-gray-600 mt-2">{scenario.description}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

// Mock data for development
const mockEconomicData = {
  recessionProbability: 35,
  riskLevel: 'Medium',
  gdpGrowth: 2.1,
  unemployment: 3.7,
  inflation: 3.2,
  leadingIndicators: [
    {
      name: 'Leading Economic Index',
      value: '102.5',
      change: -0.3,
      trend: 'deteriorating',
      signal: 'Negative',
      strength: 25,
      description: 'Composite index of 10 leading indicators showing economic momentum'
    },
    {
      name: 'ISM Manufacturing PMI',
      value: '48.7',
      change: -1.2,
      trend: 'deteriorating',
      signal: 'Negative',
      strength: 35,
      description: 'Manufacturing activity index; values below 50 indicate contraction'
    },
    {
      name: 'Consumer Confidence',
      value: '115.8',
      change: 2.1,
      trend: 'improving',
      signal: 'Positive',
      strength: 75,
      description: 'Consumer assessment of current and future economic conditions'
    },
    {
      name: 'Building Permits',
      value: '1.52M',
      change: -5.2,
      trend: 'deteriorating',
      signal: 'Negative',
      strength: 40,
      description: 'Forward-looking indicator of housing construction activity'
    }
  ],
  upcomingEvents: [
    {
      event: 'Federal Reserve Meeting',
      date: 'Mar 20, 2024',
      time: '2:00 PM EST',
      importance: 'High',
      forecast: '0.25% rate cut expected'
    },
    {
      event: 'Consumer Price Index',
      date: 'Mar 12, 2024',
      time: '8:30 AM EST',
      importance: 'High',
      forecast: '3.1% Y/Y expected'
    },
    {
      event: 'Employment Report',
      date: 'Mar 8, 2024',
      time: '8:30 AM EST',
      importance: 'High',
      forecast: '200K jobs added expected'
    }
  ],
  yieldCurve: {
    spread2y10y: -45,
    spread3m10y: -62,
    isInverted: true,
    interpretation: 'The inverted yield curve suggests investor expectations of economic slowdown and potential Federal Reserve rate cuts.',
    historicalAccuracy: 85,
    averageLeadTime: 14
  },
  creditSpreads: [
    {
      name: 'High Yield Spread',
      description: 'Corporate bonds vs Treasury',
      value: 485,
      change: 15
    },
    {
      name: 'Investment Grade Spread',
      description: 'IG corporate vs Treasury',
      value: 125,
      change: 8
    },
    {
      name: 'TED Spread',
      description: '3M LIBOR vs 3M Treasury',
      value: 28,
      change: -2
    }
  ],
  financialStress: {
    index: 0.85,
    level: 'Medium',
    percentile: 65,
    interpretation: 'Financial conditions are moderately stressed but within normal ranges.'
  },
  employment: {
    indicators: [
      {
        name: 'Unemployment Rate',
        value: '3.7%',
        change: 0.1,
        period: 'February 2024'
      },
      {
        name: 'Job Openings',
        value: '9.9M',
        change: -0.3,
        period: 'January 2024'
      },
      {
        name: 'Initial Claims',
        value: '220K',
        change: 5,
        period: 'Week ending Mar 2'
      }
    ],
    sahmRule: {
      value: 0.23,
      triggered: false,
      interpretation: 'The Sahm Rule recession indicator remains below the 0.50 threshold that historically signals recession onset.'
    }
  },
  forecastModels: [
    {
      name: 'NY Fed Model',
      probability: 32,
      confidence: 78,
      timeHorizon: '12 months',
      methodology: 'Yield curve and term structure model'
    },
    {
      name: 'Goldman Sachs',
      probability: 35,
      confidence: 71,
      timeHorizon: '12 months',
      methodology: 'Multi-factor econometric model'
    },
    {
      name: 'JP Morgan',
      probability: 40,
      confidence: 68,
      timeHorizon: '18 months',
      methodology: 'Credit conditions and leading indicators'
    }
  ],
  scenarios: [
    {
      name: 'Bull Case',
      probability: 25,
      gdpGrowth: 3.2,
      unemployment: 3.4,
      fedRate: 4.5,
      description: 'Soft landing with continued growth and declining inflation'
    },
    {
      name: 'Base Case',
      probability: 50,
      gdpGrowth: 1.8,
      unemployment: 4.2,
      fedRate: 3.8,
      description: 'Mild slowdown with modest recession risk'
    },
    {
      name: 'Bear Case',
      probability: 25,
      gdpGrowth: -1.5,
      unemployment: 5.8,
      fedRate: 2.5,
      description: 'Economic recession with significant policy response'
    }
  ]
};

export default EconomicModeling;