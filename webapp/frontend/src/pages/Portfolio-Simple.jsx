import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { 
  CurrencyDollarIcon,
  ChartBarIcon,
  ArrowTrendingUpIcon,
  ArrowTrendingDownIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
  ExclamationTriangleIcon,
  EyeIcon,
  ArrowPathIcon,
  ShareIcon,
  ClockIcon,
  CalendarIcon,
  BanknotesIcon,
  ScaleIcon,
  TrophyIcon,
  FireIcon,
  ChartPieIcon,
  DocumentChartBarIcon,
  AdjustmentsHorizontalIcon,
  Cog8ToothIcon,
  SparklesIcon,
  BoltIcon
} from '@heroicons/react/24/outline';
import { PageLayout, CardLayout, GridLayout } from '../components/ui/layout';
import { DataNotAvailable, LoadingFallback } from '../components/fallbacks/DataNotAvailable';
import RequiresApiKeys from '../components/RequiresApiKeys';

function Portfolio() {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [refreshing, setRefreshing] = useState(false);
  const [selectedHolding, setSelectedHolding] = useState(null);
  const [showQuickActions, setShowQuickActions] = useState(false);
  const [portfolio, setPortfolio] = useState({
    totalValue: 0,
    totalGain: 0,
    totalGainPercent: 0,
    dayChange: 0,
    dayChangePercent: 0,
    holdings: [],
    performance: {},
    metrics: {},
    alerts: []
  });

  useEffect(() => {
    // Simulate data loading
    const timer = setTimeout(() => {
      setPortfolio({
        totalValue: 387542.75,
        totalGain: 67234.50,
        totalGainPercent: 21.02,
        dayChange: 2847.25,
        dayChangePercent: 0.74,
        holdings: [
          {
            id: 1,
            symbol: 'AAPL',
            name: 'Apple Inc.',
            shares: 300,
            currentPrice: 175.43,
            avgCost: 145.20,
            totalValue: 52629.00,
            gain: 9069.00,
            gainPercent: 20.82,
            dayChange: 1.25,
            dayChangePercent: 0.72,
            sector: 'Technology',
            allocation: 13.6,
            risk: 'Moderate',
            trending: 'up'
          },
          {
            id: 2,
            symbol: 'GOOGL', 
            name: 'Alphabet Inc.',
            shares: 50,
            currentPrice: 2431.20,
            avgCost: 2180.50,
            totalValue: 121560.00,
            gain: 12535.00,
            gainPercent: 11.49,
            dayChange: 15.30,
            dayChangePercent: 0.63,
            sector: 'Technology',
            allocation: 31.4,
            risk: 'Moderate',
            trending: 'up'
          },
          {
            id: 3,
            symbol: 'MSFT',
            name: 'Microsoft Corporation',
            shares: 200,
            currentPrice: 295.37,
            avgCost: 268.90,
            totalValue: 59074.00,
            gain: 5294.00,
            gainPercent: 9.84,
            dayChange: -2.15,
            dayChangePercent: -0.72,
            sector: 'Technology',
            allocation: 15.2,
            risk: 'Low',
            trending: 'down'
          },
          {
            id: 4,
            symbol: 'TSLA',
            name: 'Tesla Inc.',
            shares: 100,
            currentPrice: 245.67,
            avgCost: 198.30,
            totalValue: 24567.00,
            gain: 4737.00,
            gainPercent: 23.90,
            dayChange: -8.92,
            dayChangePercent: -3.51,
            sector: 'Consumer Discretionary',
            allocation: 6.3,
            risk: 'High',
            trending: 'down'
          },
          {
            id: 5,
            symbol: 'NVDA',
            name: 'NVIDIA Corporation',
            shares: 150,
            currentPrice: 875.25,
            avgCost: 420.80,
            totalValue: 131287.50,
            gain: 68167.50,
            gainPercent: 108.12,
            dayChange: 25.40,
            dayChangePercent: 2.99,
            sector: 'Technology',
            allocation: 33.9,
            risk: 'High',
            trending: 'up'
          }
        ],
        performance: {
          oneDay: 0.74,
          oneWeek: 2.45,
          oneMonth: 8.73,
          threeMonth: 15.42,
          oneYear: 28.91,
          ytd: 21.02
        },
        metrics: {
          sharpeRatio: 1.24,
          beta: 1.15,
          volatility: 18.5,
          maxDrawdown: -12.3,
          diversification: 'Good'
        },
        alerts: [
          { type: 'gain', message: 'NVDA up 2.99% today', timestamp: '2 hours ago' },
          { type: 'warning', message: 'Portfolio concentration risk in Tech sector', timestamp: '1 day ago' }
        ]
      });
      setLoading(false);
    }, 1200);

    return () => clearTimeout(timer);
  }, []);

  if (!isAuthenticated) {
    return <RequiresApiKeys />;
  }

  if (loading) {
    return (
      <PageLayout title="Portfolio">
        <LoadingFallback message="Loading your portfolio..." />
      </PageLayout>
    );
  }

  // Enhanced Portfolio Summary with modern design
  const PortfolioSummary = () => (
    <div className="space-y-6">
      {/* Hero Summary Card */}
      <div className="bg-gradient-to-r from-blue-600 via-purple-600 to-indigo-600 rounded-2xl shadow-xl text-white overflow-hidden">
        <div className="p-8">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <div className="flex items-center space-x-2">
                <TrophyIcon className="h-6 w-6 text-yellow-300" />
                <h2 className="text-lg font-semibold text-blue-100">Portfolio Performance</h2>
              </div>
              <p className="text-4xl font-bold">${portfolio.totalValue.toLocaleString()}</p>
              <div className="flex items-center space-x-4">
                <div className={`flex items-center space-x-1 px-3 py-1 rounded-full text-sm font-medium ${
                  portfolio.totalGain >= 0 ? 'bg-green-500/20 text-green-100' : 'bg-red-500/20 text-red-100'
                }`}>
                  {portfolio.totalGain >= 0 ? (
                    <ArrowTrendingUpIcon className="h-4 w-4" />
                  ) : (
                    <ArrowTrendingDownIcon className="h-4 w-4" />
                  )}
                  <span>
                    {portfolio.totalGain >= 0 ? '+' : ''}${portfolio.totalGain.toLocaleString()} ({portfolio.totalGainPercent}%)
                  </span>
                </div>
                <div className="flex items-center space-x-1 text-blue-100">
                  <ClockIcon className="h-4 w-4" />
                  <span className="text-sm">All Time</span>
                </div>
              </div>
            </div>
            <div className="text-right space-y-2">
              <div className="text-blue-100 text-sm">Today's Change</div>
              <div className={`text-2xl font-bold ${
                portfolio.dayChange >= 0 ? 'text-green-300' : 'text-red-300'
              }`}>
                {portfolio.dayChange >= 0 ? '+' : ''}${portfolio.dayChange.toLocaleString()}
              </div>
              <div className={`text-sm ${
                portfolio.dayChange >= 0 ? 'text-green-200' : 'text-red-200'
              }`}>
                ({portfolio.dayChangePercent >= 0 ? '+' : ''}{portfolio.dayChangePercent}%)
              </div>
            </div>
          </div>
        </div>
        
        {/* Performance Timeline */}
        <div className="bg-white/10 backdrop-blur-sm border-t border-white/20 px-8 py-4">
          <div className="grid grid-cols-6 gap-4 text-center">
            {Object.entries(portfolio.performance).map(([period, value]) => (
              <div key={period} className="space-y-1">
                <div className="text-xs text-blue-200 uppercase tracking-wide">
                  {period.replace(/([A-Z])/g, ' $1').trim()}
                </div>
                <div className={`text-sm font-semibold ${
                  value >= 0 ? 'text-green-300' : 'text-red-300'
                }`}>
                  {value >= 0 ? '+' : ''}{value}%
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Quick Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Best Performer */}
        <div className="bg-white rounded-xl shadow-lg border border-gray-100 p-6 hover:shadow-xl transition-shadow">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <div className="flex items-center space-x-2 text-green-600">
                <FireIcon className="h-5 w-5" />
                <span className="text-sm font-medium">Best Performer</span>
              </div>
              <div className="text-2xl font-bold text-gray-900">NVDA</div>
              <div className="text-green-600 font-semibold">+108.12%</div>
            </div>
            <div className="text-4xl">🚀</div>
          </div>
        </div>

        {/* Portfolio Metrics */}
        <div className="bg-white rounded-xl shadow-lg border border-gray-100 p-6 hover:shadow-xl transition-shadow">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <div className="flex items-center space-x-2 text-blue-600">
                <ScaleIcon className="h-5 w-5" />
                <span className="text-sm font-medium">Sharpe Ratio</span>
              </div>
              <div className="text-2xl font-bold text-gray-900">{portfolio.metrics.sharpeRatio}</div>
              <div className="text-blue-600 text-sm">Excellent</div>
            </div>
            <div className="text-4xl">📊</div>
          </div>
        </div>

        {/* Risk Level */}
        <div className="bg-white rounded-xl shadow-lg border border-gray-100 p-6 hover:shadow-xl transition-shadow">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <div className="flex items-center space-x-2 text-yellow-600">
                <ExclamationTriangleIcon className="h-5 w-5" />
                <span className="text-sm font-medium">Risk Level</span>
              </div>
              <div className="text-2xl font-bold text-gray-900">Moderate</div>
              <div className="text-yellow-600 text-sm">β = {portfolio.metrics.beta}</div>
            </div>
            <div className="text-4xl">⚡</div>
          </div>
        </div>

        {/* Diversification */}
        <div className="bg-white rounded-xl shadow-lg border border-gray-100 p-6 hover:shadow-xl transition-shadow">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <div className="flex items-center space-x-2 text-purple-600">
                <ChartPieIcon className="h-5 w-5" />
                <span className="text-sm font-medium">Diversification</span>
              </div>
              <div className="text-2xl font-bold text-gray-900">{portfolio.metrics.diversification}</div>
              <div className="text-purple-600 text-sm">5 Holdings</div>
            </div>
            <div className="text-4xl">🎯</div>
          </div>
        </div>
      </div>

      {/* Alerts Section */}
      {portfolio.alerts.length > 0 && (
        <div className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-xl p-6">
          <div className="flex items-center space-x-2 mb-4">
            <BoltIcon className="h-5 w-5 text-amber-600" />
            <h3 className="text-lg font-semibold text-amber-900">Portfolio Alerts</h3>
          </div>
          <div className="space-y-3">
            {portfolio.alerts.map((alert, index) => (
              <div key={index} className="flex items-center justify-between p-3 bg-white rounded-lg shadow-sm">
                <div className="flex items-center space-x-3">
                  <div className={`w-2 h-2 rounded-full ${
                    alert.type === 'gain' ? 'bg-green-500' : 'bg-amber-500'
                  }`}></div>
                  <span className="text-gray-900">{alert.message}</span>
                </div>
                <span className="text-sm text-gray-500">{alert.timestamp}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  // Enhanced Holdings Table with modern card-based design
  const HoldingsTable = () => (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-bold text-gray-900">Portfolio Holdings</h3>
          <p className="text-gray-600">{portfolio.holdings.length} positions • Updated just now</p>
        </div>
        <div className="flex space-x-3">
          <button 
            onClick={() => setRefreshing(true)}
            className={`inline-flex items-center px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors ${
              refreshing ? 'opacity-50' : ''
            }`}
          >
            <ArrowPathIcon className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <button className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
            <PlusIcon className="h-4 w-4 mr-2" />
            Add Position
          </button>
        </div>
      </div>

      {/* Holdings Grid */}
      <div className="space-y-4">
        {portfolio.holdings.map((holding) => (
          <div 
            key={holding.id} 
            className="bg-white rounded-xl shadow-sm border border-gray-200 hover:shadow-lg transition-all duration-200 cursor-pointer group"
            onClick={() => navigate(`/stocks/${holding.symbol}`)}
          >
            <div className="p-6">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
                {/* Symbol & Company Info */}
                <div className="lg:col-span-3">
                  <div className="flex items-center space-x-3">
                    <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-white font-bold text-lg ${
                      holding.trending === 'up' ? 'bg-green-500' :
                      holding.trending === 'down' ? 'bg-red-500' : 'bg-gray-500'
                    }`}>
                      {holding.symbol.charAt(0)}
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="text-lg font-bold text-gray-900">{holding.symbol}</span>
                        {holding.trending === 'up' && <ArrowTrendingUpIcon className="h-4 w-4 text-green-500" />}
                        {holding.trending === 'down' && <ArrowTrendingDownIcon className="h-4 w-4 text-red-500" />}
                      </div>
                      <div className="text-sm text-gray-600">{holding.name}</div>
                      <div className="flex items-center space-x-2 mt-1">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          holding.risk === 'Low' ? 'bg-green-100 text-green-800' :
                          holding.risk === 'Moderate' ? 'bg-yellow-100 text-yellow-800' :
                          'bg-red-100 text-red-800'
                        }`}>
                          {holding.risk} Risk
                        </span>
                        <span className="text-xs text-gray-500">{holding.sector}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Shares & Prices */}
                <div className="lg:col-span-2 text-center lg:text-left">
                  <div className="text-lg font-semibold text-gray-900">{holding.shares.toLocaleString()}</div>
                  <div className="text-sm text-gray-600">shares</div>
                </div>

                <div className="lg:col-span-2 text-center lg:text-left">
                  <div className="text-lg font-semibold text-gray-900">${holding.currentPrice}</div>
                  <div className="text-sm text-gray-600">vs ${holding.avgCost} avg</div>
                </div>

                {/* Total Value */}
                <div className="lg:col-span-2 text-center lg:text-left">
                  <div className="text-xl font-bold text-gray-900">${holding.totalValue.toLocaleString()}</div>
                  <div className="text-sm text-gray-600">{holding.allocation}% of portfolio</div>
                </div>

                {/* Performance */}
                <div className="lg:col-span-2 text-center lg:text-left">
                  <div className={`text-lg font-bold ${holding.gain >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {holding.gain >= 0 ? '+' : ''}${holding.gain.toLocaleString()}
                  </div>
                  <div className={`text-sm font-medium ${holding.gain >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    ({holding.gainPercent >= 0 ? '+' : ''}{holding.gainPercent}%)
                  </div>
                  <div className={`text-xs ${holding.dayChange >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    Today: {holding.dayChange >= 0 ? '+' : ''}${holding.dayChange} ({holding.dayChangePercent}%)
                  </div>
                </div>

                {/* Actions */}
                <div className="lg:col-span-1 flex justify-center lg:justify-end space-x-2">
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedHolding(holding);
                    }}
                    className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    title="View Details"
                  >
                    <EyeIcon className="h-5 w-5" />
                  </button>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      // Edit logic here
                    }}
                    className="p-2 text-gray-600 hover:bg-gray-50 rounded-lg transition-colors"
                    title="Edit Position"
                  >
                    <PencilIcon className="h-5 w-5" />
                  </button>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      // Delete logic here
                    }}
                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    title="Remove Position"
                  >
                    <TrashIcon className="h-5 w-5" />
                  </button>
                </div>
              </div>

              {/* Allocation Bar */}
              <div className="mt-4 pt-4 border-t border-gray-100">
                <div className="flex items-center space-x-3">
                  <span className="text-sm text-gray-600 min-w-0 flex-shrink-0">Portfolio Weight:</span>
                  <div className="flex-1 bg-gray-200 rounded-full h-2">
                    <div 
                      className={`h-2 rounded-full transition-all duration-300 ${
                        holding.trending === 'up' ? 'bg-green-500' :
                        holding.trending === 'down' ? 'bg-red-500' : 'bg-blue-500'
                      }`}
                      style={{ width: `${Math.min(holding.allocation, 100)}%` }}
                    ></div>
                  </div>
                  <span className="text-sm font-medium text-gray-900 min-w-0 flex-shrink-0">
                    {holding.allocation}%
                  </span>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  // Enhanced Tab Navigation with modern design
  const TabNavigation = () => {
    const tabs = [
      { id: 'overview', label: 'Overview', icon: ChartBarIcon, count: null },
      { id: 'holdings', label: 'Holdings', icon: DocumentChartBarIcon, count: portfolio.holdings.length },
      { id: 'performance', label: 'Performance', icon: ArrowTrendingUpIcon, count: null },
      { id: 'risk', label: 'Risk Management', icon: ExclamationTriangleIcon, count: portfolio.alerts.length },
      { id: 'factors', label: 'Factor Analysis', icon: ScaleIcon, count: null },
      { id: 'ai', label: 'AI Insights', icon: SparklesIcon, count: null },
      { id: 'optimization', label: 'Optimization', icon: AdjustmentsHorizontalIcon, count: null },
      { id: 'settings', label: 'Settings', icon: Cog8ToothIcon, count: null }
    ];

    return (
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        <div className="border-b border-gray-200">
          <nav className="flex">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 flex items-center justify-center space-x-2 py-4 px-6 text-sm font-medium transition-all duration-200 ${
                  activeTab === tab.id
                    ? 'bg-blue-50 text-blue-700 border-b-2 border-blue-500'
                    : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }`}
              >
                <tab.icon className="h-5 w-5" />
                <span>{tab.label}</span>
                {tab.count && (
                  <span className="bg-gray-100 text-gray-600 text-xs font-medium px-2 py-1 rounded-full">
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </nav>
        </div>
      </div>
    );
  };

  // Performance Tab Component
  const PerformanceTab = () => (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-xl font-bold text-gray-900 mb-6">Portfolio Performance</h3>
        
        {/* Performance Metrics Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg p-4 border border-blue-100">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-blue-600 text-sm font-medium">Sharpe Ratio</p>
                <p className="text-2xl font-bold text-blue-900">1.47</p>
                <p className="text-blue-600 text-xs">Excellent</p>
              </div>
              <TrophyIcon className="h-8 w-8 text-blue-500" />
            </div>
          </div>
          
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-lg p-4 border border-green-100">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-green-600 text-sm font-medium">Alpha vs S&P 500</p>
                <p className="text-2xl font-bold text-green-900">+3.2%</p>
                <p className="text-green-600 text-xs">Outperforming</p>
              </div>
              <ArrowTrendingUpIcon className="h-8 w-8 text-green-500" />
            </div>
          </div>
          
          <div className="bg-gradient-to-br from-purple-50 to-violet-50 rounded-lg p-4 border border-purple-100">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-purple-600 text-sm font-medium">Beta</p>
                <p className="text-2xl font-bold text-purple-900">0.89</p>
                <p className="text-purple-600 text-xs">Lower volatility</p>
              </div>
              <ScaleIcon className="h-8 w-8 text-purple-500" />
            </div>
          </div>
          
          <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-lg p-4 border border-amber-100">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-amber-600 text-sm font-medium">Max Drawdown</p>
                <p className="text-2xl font-bold text-amber-900">-12.3%</p>
                <p className="text-amber-600 text-xs">Within range</p>
              </div>
              <ExclamationTriangleIcon className="h-8 w-8 text-amber-500" />
            </div>
          </div>
        </div>

        {/* Performance Chart Placeholder */}
        <div className="bg-gray-50 rounded-lg p-8 text-center">
          <ChartBarIcon className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <h4 className="text-lg font-semibold text-gray-900 mb-2">Performance Chart</h4>
          <p className="text-gray-600 mb-4">Interactive portfolio vs benchmark performance chart</p>
          <div className="bg-white rounded p-4 border border-gray-200">
            <p className="text-sm text-gray-500">Chart implementation coming soon - will show portfolio performance vs S&P 500 benchmark with drawdown analysis</p>
          </div>
        </div>
      </div>
    </div>
  );

  // Risk Management Tab Component
  const RiskManagementTab = () => {
    const [riskSubTab, setRiskSubTab] = useState('overview');
    
    const riskTabs = [
      { id: 'overview', label: 'Risk Overview' },
      { id: 'var', label: 'Value at Risk' },
      { id: 'stress', label: 'Stress Testing' },
      { id: 'alerts', label: 'Risk Alerts' }
    ];

    const stressScenarios = [
      { name: '2008 Financial Crisis', impact: -87234, severity: 'high' },
      { name: 'COVID-19 Market Crash', impact: -52341, severity: 'medium' },
      { name: 'Tech Bubble Burst', impact: -124567, severity: 'high' },
      { name: 'Interest Rate Shock', impact: -34567, severity: 'medium' },
      { name: 'Inflation Spike', impact: -23456, severity: 'low' },
      { name: 'Geopolitical Crisis', impact: -45678, severity: 'medium' }
    ];

    return (
      <div className="space-y-6">
        {/* Risk Tab Navigation */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="border-b border-gray-200">
            <nav className="flex">
              {riskTabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setRiskSubTab(tab.id)}
                  className={`flex-1 py-3 px-4 text-sm font-medium transition-colors ${
                    riskSubTab === tab.id
                      ? 'bg-red-50 text-red-700 border-b-2 border-red-500'
                      : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>
        </div>

        {/* Risk Tab Content */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          {riskSubTab === 'overview' && (
            <div className="space-y-6">
              <h3 className="text-xl font-bold text-gray-900">Portfolio Risk Overview</h3>
              
              {/* Risk Metrics Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-gradient-to-br from-red-50 to-pink-50 rounded-lg p-4 border border-red-100">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-red-700 font-semibold">Portfolio VaR (95%)</h4>
                    <ExclamationTriangleIcon className="h-6 w-6 text-red-500" />
                  </div>
                  <p className="text-2xl font-bold text-red-900">$12,450</p>
                  <p className="text-red-600 text-sm">Maximum 1-day loss</p>
                  <div className="mt-3 bg-red-200 rounded-full h-2">
                    <div className="bg-red-500 h-2 rounded-full" style={{ width: '65%' }}></div>
                  </div>
                  <p className="text-xs text-red-600 mt-1">Moderate risk level</p>
                </div>

                <div className="bg-gradient-to-br from-yellow-50 to-amber-50 rounded-lg p-4 border border-yellow-100">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-yellow-700 font-semibold">Portfolio Beta</h4>
                    <ScaleIcon className="h-6 w-6 text-yellow-500" />
                  </div>
                  <p className="text-2xl font-bold text-yellow-900">0.89</p>
                  <p className="text-yellow-600 text-sm">vs S&P 500</p>
                  <div className="mt-3 bg-yellow-200 rounded-full h-2">
                    <div className="bg-yellow-500 h-2 rounded-full" style={{ width: '89%' }}></div>
                  </div>
                  <p className="text-xs text-yellow-600 mt-1">Lower volatility</p>
                </div>

                <div className="bg-gradient-to-br from-orange-50 to-red-50 rounded-lg p-4 border border-orange-100">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-orange-700 font-semibold">Volatility</h4>
                    <BoltIcon className="h-6 w-6 text-orange-500" />
                  </div>
                  <p className="text-2xl font-bold text-orange-900">18.7%</p>
                  <p className="text-orange-600 text-sm">Annualized</p>
                  <div className="mt-3 bg-orange-200 rounded-full h-2">
                    <div className="bg-orange-500 h-2 rounded-full" style={{ width: '75%' }}></div>
                  </div>
                  <p className="text-xs text-orange-600 mt-1">Moderate volatility</p>
                </div>
              </div>

              {/* Risk Concentration */}
              <div className="bg-gray-50 rounded-lg p-6">
                <h4 className="text-lg font-semibold text-gray-900 mb-4">Risk Concentration Analysis</h4>
                <div className="space-y-4">
                  {portfolio.holdings.slice(0, 3).map((holding) => (
                    <div key={holding.id} className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center text-white text-sm font-bold">
                          {holding.symbol.charAt(0)}
                        </div>
                        <div>
                          <p className="font-medium text-gray-900">{holding.symbol}</p>
                          <p className="text-sm text-gray-600">{holding.allocation}% allocation</p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-medium text-gray-900">Risk Score: {(Math.random() * 10).toFixed(1)}</p>
                        <p className="text-xs text-gray-500">Individual VaR: ${(Math.random() * 5000).toFixed(0)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {riskSubTab === 'var' && (
            <div className="space-y-6">
              <h3 className="text-xl font-bold text-gray-900">Value at Risk Analysis</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-red-50 rounded-lg p-6 border border-red-100">
                  <h4 className="text-lg font-semibold text-red-900 mb-4">VaR Confidence Levels</h4>
                  <div className="space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="text-red-700">95% Confidence (1-day)</span>
                      <span className="font-bold text-red-900">$12,450</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-red-700">99% Confidence (1-day)</span>
                      <span className="font-bold text-red-900">$18,750</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-red-700">95% Confidence (10-day)</span>
                      <span className="font-bold text-red-900">$39,340</span>
                    </div>
                  </div>
                </div>
                
                <div className="bg-gray-50 rounded-lg p-6">
                  <h4 className="text-lg font-semibold text-gray-900 mb-4">VaR Trend Chart</h4>
                  <div className="text-center py-8">
                    <ChartBarIcon className="h-12 w-12 text-gray-400 mx-auto mb-2" />
                    <p className="text-gray-600">Historical VaR trend analysis</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {riskSubTab === 'stress' && (
            <div className="space-y-6">
              <h3 className="text-xl font-bold text-gray-900">Stress Testing Scenarios</h3>
              <div className="space-y-4">
                {stressScenarios.map((scenario, index) => (
                  <div key={index} className="bg-gray-50 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="font-semibold text-gray-900">{scenario.name}</h4>
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                        scenario.severity === 'high' ? 'bg-red-100 text-red-800' :
                        scenario.severity === 'medium' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-green-100 text-green-800'
                      }`}>
                        {scenario.severity} impact
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <div className="flex-1 mr-4">
                        <div className="bg-gray-200 rounded-full h-3">
                          <div 
                            className={`h-3 rounded-full ${
                              scenario.severity === 'high' ? 'bg-red-500' :
                              scenario.severity === 'medium' ? 'bg-yellow-500' :
                              'bg-green-500'
                            }`}
                            style={{ width: `${Math.abs(scenario.impact) / 200000 * 100}%` }}
                          ></div>
                        </div>
                      </div>
                      <span className="font-bold text-red-600">{scenario.impact.toLocaleString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {riskSubTab === 'alerts' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <h3 className="text-xl font-bold text-gray-900">Risk Alerts & Monitoring</h3>
                <button className="bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 transition-colors">
                  Create Alert
                </button>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-4">
                  <h4 className="text-lg font-semibold text-gray-900">Active Alerts</h4>
                  <div className="space-y-3">
                    <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-medium text-red-900">High Volatility Alert</p>
                          <p className="text-sm text-red-700">AAPL volatility exceeded 25%</p>
                        </div>
                        <ExclamationTriangleIcon className="h-5 w-5 text-red-500" />
                      </div>
                    </div>
                    
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-medium text-yellow-900">Concentration Risk</p>
                          <p className="text-sm text-yellow-700">Technology sector > 50%</p>
                        </div>
                        <ExclamationTriangleIcon className="h-5 w-5 text-yellow-500" />
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="space-y-4">
                  <h4 className="text-lg font-semibold text-gray-900">Alert Settings</h4>
                  <div className="space-y-3">
                    <div className="bg-gray-50 rounded-lg p-4">
                      <div className="space-y-3">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Alert Type</label>
                          <select className="w-full border border-gray-300 rounded px-3 py-2 text-sm">
                            <option>Volatility Alert</option>
                            <option>VaR Alert</option>
                            <option>Beta Alert</option>
                            <option>Concentration Alert</option>
                          </select>
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Threshold</label>
                          <input type="number" className="w-full border border-gray-300 rounded px-3 py-2 text-sm" placeholder="25" />
                        </div>
                        <button className="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 transition-colors text-sm">
                          Create Alert
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Factor Analysis Tab Component
  const FactorAnalysisTab = () => (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h3 className="text-xl font-bold text-gray-900 mb-6">Multi-Factor Portfolio Analysis</h3>
        
        {/* Factor Exposure Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          {[
            { name: 'Quality', score: 0.73, benchmark: 0.65, color: 'blue' },
            { name: 'Growth', score: 0.82, benchmark: 0.58, color: 'green' },
            { name: 'Value', score: 0.45, benchmark: 0.72, color: 'purple' },
            { name: 'Momentum', score: 0.91, benchmark: 0.63, color: 'indigo' },
            { name: 'Sentiment', score: 0.67, benchmark: 0.55, color: 'yellow' },
            { name: 'Positioning', score: 0.34, benchmark: 0.68, color: 'red' }
          ].map((factor) => (
            <div key={factor.name} className={`bg-gradient-to-br from-${factor.color}-50 to-${factor.color}-100 rounded-lg p-4 border border-${factor.color}-200`}>
              <h4 className={`font-semibold text-${factor.color}-900 mb-2`}>{factor.name}</h4>
              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Portfolio</span>
                  <span className={`font-bold text-${factor.color}-900`}>{(factor.score * 100).toFixed(0)}%</span>
                </div>
                <div className={`bg-${factor.color}-200 rounded-full h-2`}>
                  <div className={`bg-${factor.color}-500 h-2 rounded-full`} style={{ width: `${factor.score * 100}%` }}></div>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-gray-500">vs Benchmark: {(factor.benchmark * 100).toFixed(0)}%</span>
                  <span className={factor.score > factor.benchmark ? 'text-green-600' : 'text-red-600'}>
                    {factor.score > factor.benchmark ? '↑' : '↓'} {Math.abs((factor.score - factor.benchmark) * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Factor Radar Chart Placeholder */}
        <div className="bg-gray-50 rounded-lg p-8 text-center">
          <ScaleIcon className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <h4 className="text-lg font-semibold text-gray-900 mb-2">Factor Exposure Radar Chart</h4>
          <p className="text-gray-600 mb-4">Multi-dimensional factor analysis visualization</p>
          <div className="bg-white rounded p-4 border border-gray-200">
            <p className="text-sm text-gray-500">Interactive radar chart showing portfolio factor exposures vs benchmark coming soon</p>
          </div>
        </div>
      </div>
    </div>
  );

  // AI Insights Tab Component
  const AIInsightsTab = () => (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold text-gray-900">AI-Powered Portfolio Insights</h3>
          <div className="flex items-center space-x-2">
            <SparklesIcon className="h-5 w-5 text-yellow-500" />
            <span className="text-sm font-medium text-gray-600">Confidence: 87%</span>
            <div className="flex">
              {[1,2,3,4,5].map((star) => (
                <div key={star} className={`h-4 w-4 ${star <= 4 ? 'text-yellow-400' : 'text-gray-300'}`}>★</div>
              ))}
            </div>
          </div>
        </div>

        {/* AI Analysis Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-lg p-6 border border-green-100">
            <div className="flex items-center space-x-2 mb-4">
              <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                <span className="text-white text-sm font-bold">✓</span>
              </div>
              <h4 className="text-lg font-semibold text-green-900">Portfolio Strengths</h4>
            </div>
            <ul className="space-y-2 text-green-800">
              <li className="flex items-start space-x-2">
                <span className="text-green-500 mt-1">•</span>
                <span className="text-sm">Strong diversification across sectors</span>
              </li>
              <li className="flex items-start space-x-2">
                <span className="text-green-500 mt-1">•</span>
                <span className="text-sm">Excellent risk-adjusted returns (Sharpe: 1.47)</span>
              </li>
              <li className="flex items-start space-x-2">
                <span className="text-green-500 mt-1">•</span>
                <span className="text-sm">Low correlation with market volatility</span>
              </li>
            </ul>
          </div>

          <div className="bg-gradient-to-br from-yellow-50 to-amber-50 rounded-lg p-6 border border-yellow-100">
            <div className="flex items-center space-x-2 mb-4">
              <div className="w-8 h-8 bg-yellow-500 rounded-full flex items-center justify-center">
                <span className="text-white text-sm font-bold">!</span>
              </div>
              <h4 className="text-lg font-semibold text-yellow-900">Improvement Opportunities</h4>
            </div>
            <ul className="space-y-2 text-yellow-800">
              <li className="flex items-start space-x-2">
                <span className="text-yellow-500 mt-1">•</span>
                <span className="text-sm">Consider reducing technology concentration</span>
              </li>
              <li className="flex items-start space-x-2">
                <span className="text-yellow-500 mt-1">•</span>
                <span className="text-sm">Add international exposure for diversification</span>
              </li>
              <li className="flex items-start space-x-2">
                <span className="text-yellow-500 mt-1">•</span>
                <span className="text-sm">Rebalance to target allocation bands</span>
              </li>
            </ul>
          </div>
        </div>

        {/* AI Recommendations */}
        <div className="bg-blue-50 rounded-lg p-6 border border-blue-100">
          <h4 className="text-lg font-semibold text-blue-900 mb-4">🤖 AI Recommendations</h4>
          <div className="space-y-4">
            <div className="bg-white rounded p-4 border border-blue-200">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-blue-900">Portfolio Rebalancing</span>
                <span className="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded-full">High Priority</span>
              </div>
              <p className="text-sm text-blue-800">Current technology allocation (45%) exceeds target band (35-40%). Consider trimming AAPL and GOOGL positions by $15,000 each.</p>
            </div>
            
            <div className="bg-white rounded p-4 border border-blue-200">
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium text-blue-900">Diversification Enhancement</span>
                <span className="bg-green-100 text-green-800 text-xs px-2 py-1 rounded-full">Medium Priority</span>
              </div>
              <p className="text-sm text-blue-800">Add exposure to healthcare (XLV) and international markets (VXUS) to improve risk-adjusted returns.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  // Optimization Tab Component
  const OptimizationTab = () => {
    const [optimizationMethod, setOptimizationMethod] = useState('enhanced_sharpe');
    const [riskTolerance, setRiskTolerance] = useState(5);
    
    const optimizationMethods = [
      { id: 'enhanced_sharpe', name: 'Enhanced Sharpe Ratio', description: 'Multi-factor optimization with quality, momentum, value, sentiment' },
      { id: 'black_litterman', name: 'Black-Litterman', description: 'Market equilibrium with investor views' },
      { id: 'risk_parity', name: 'Risk Parity', description: 'Equal risk contribution optimization' },
      { id: 'factor_based', name: 'Factor-Based', description: 'Quality and momentum factor emphasis' },
      { id: 'max_diversification', name: 'Maximum Diversification', description: 'Correlation-based optimization' },
      { id: 'min_correlation', name: 'Minimum Correlation', description: 'Low correlation strategy' }
    ];

    return (
      <div className="space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h3 className="text-xl font-bold text-gray-900 mb-6">Portfolio Optimization Engine</h3>
          
          {/* Optimization Method Selection */}
          <div className="mb-8">
            <h4 className="text-lg font-semibold text-gray-900 mb-4">Optimization Strategy</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {optimizationMethods.map((method) => (
                <div 
                  key={method.id}
                  onClick={() => setOptimizationMethod(method.id)}
                  className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                    optimizationMethod === method.id 
                      ? 'border-blue-500 bg-blue-50' 
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <h5 className={`font-semibold mb-2 ${
                    optimizationMethod === method.id ? 'text-blue-900' : 'text-gray-900'
                  }`}>
                    {method.name}
                  </h5>
                  <p className={`text-sm ${
                    optimizationMethod === method.id ? 'text-blue-700' : 'text-gray-600'
                  }`}>
                    {method.description}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Risk Tolerance Slider */}
          <div className="mb-8">
            <h4 className="text-lg font-semibold text-gray-900 mb-4">Risk Tolerance</h4>
            <div className="bg-gray-50 rounded-lg p-6">
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm text-gray-600">Conservative</span>
                <span className="text-sm text-gray-600">Aggressive</span>
              </div>
              <input 
                type="range" 
                min="1" 
                max="10" 
                value={riskTolerance}
                onChange={(e) => setRiskTolerance(e.target.value)}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
              />
              <div className="flex justify-center mt-2">
                <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-medium">
                  Risk Level: {riskTolerance}/10
                </span>
              </div>
            </div>
          </div>

          {/* Optimization Results */}
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-lg p-6 border border-green-100">
            <h4 className="text-lg font-semibold text-green-900 mb-4">🎯 Optimization Results</h4>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="text-center">
                <p className="text-2xl font-bold text-green-900">+2.3%</p>
                <p className="text-green-700 text-sm">Expected Return Improvement</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-green-900">-1.2%</p>
                <p className="text-green-700 text-sm">Risk Reduction</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-green-900">1.67</p>
                <p className="text-green-700 text-sm">Projected Sharpe Ratio</p>
              </div>
            </div>
            
            <div className="mt-6 pt-6 border-t border-green-200">
              <h5 className="font-semibold text-green-900 mb-3">Recommended Adjustments</h5>
              <div className="space-y-2 text-sm text-green-800">
                <div className="flex justify-between">
                  <span>Reduce AAPL position by:</span>
                  <span className="font-medium">-$12,000 (2.3%)</span>
                </div>
                <div className="flex justify-between">
                  <span>Reduce GOOGL position by:</span>
                  <span className="font-medium">-$8,000 (1.5%)</span>
                </div>
                <div className="flex justify-between">
                  <span>Add Healthcare ETF (XLV):</span>
                  <span className="font-medium">+$15,000 (2.8%)</span>
                </div>
                <div className="flex justify-between">
                  <span>Add International ETF (VXUS):</span>
                  <span className="font-medium">+$5,000 (1.0%)</span>
                </div>
              </div>
            </div>
            
            <button className="w-full mt-6 bg-green-600 text-white py-3 rounded-lg hover:bg-green-700 transition-colors font-medium">
              Implement Optimization Plan
            </button>
          </div>
        </div>
      </div>
    );
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return <PortfolioSummary />;
      
      case 'holdings':
        return <HoldingsTable />;
      
      case 'performance':
        return <PerformanceTab />;
      
      case 'risk':
        return <RiskManagementTab />;
      
      case 'factors':
        return <FactorAnalysisTab />;
      
      case 'ai':
        return <AIInsightsTab />;
      
      case 'optimization':
        return <OptimizationTab />;
      
      
      case 'settings':
        return (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
            <div className="space-y-6">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Portfolio Settings</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Benchmark
                    </label>
                    <select className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                      <option>S&P 500 (SPY)</option>
                      <option>NASDAQ 100 (QQQ)</option>
                      <option>Total Market (VTI)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Risk Tolerance
                    </label>
                    <select className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent">
                      <option>Conservative</option>
                      <option>Moderate</option>
                      <option>Aggressive</option>
                    </select>
                  </div>
                </div>
              </div>
              
              <div className="pt-4 border-t border-gray-200">
                <h4 className="text-md font-medium text-gray-900 mb-3">Notifications</h4>
                <div className="space-y-3">
                  <label className="flex items-center">
                    <input type="checkbox" className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" defaultChecked />
                    <span className="ml-3 text-sm text-gray-700">Email alerts for significant portfolio changes</span>
                  </label>
                  <label className="flex items-center">
                    <input type="checkbox" className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" defaultChecked />
                    <span className="ml-3 text-sm text-gray-700">Daily performance summary</span>
                  </label>
                  <label className="flex items-center">
                    <input type="checkbox" className="rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
                    <span className="ml-3 text-sm text-gray-700">Rebalancing recommendations</span>
                  </label>
                </div>
              </div>
            </div>
          </div>
        );
      
      default:
        return <PortfolioSummary />;
    }
  };

  return (
    <PageLayout 
      title="Portfolio Dashboard" 
      subtitle={`Manage your $${portfolio.totalValue.toLocaleString()} investment portfolio`}
      action={
        <div className="flex items-center space-x-3">
          {/* Quick Actions Dropdown */}
          <div className="relative">
            <button 
              onClick={() => setShowQuickActions(!showQuickActions)}
              className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors"
            >
              <SparklesIcon className="h-4 w-4 mr-2" />
              Quick Actions
            </button>
            {showQuickActions && (
              <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 z-10">
                <div className="py-1">
                  <button className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                    Rebalance Portfolio
                  </button>
                  <button className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                    Export Holdings
                  </button>
                  <button className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50">
                    Performance Report
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Share Button */}
          <button className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors">
            <ShareIcon className="h-4 w-4 mr-2" />
            Share
          </button>

          {/* Add Position Button */}
          <button className="inline-flex items-center px-6 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-lg hover:from-blue-700 hover:to-indigo-700 transition-all duration-200 shadow-sm">
            <PlusIcon className="h-4 w-4 mr-2" />
            Add Position
          </button>
        </div>
      }
    >
      <div className="space-y-8">
        <TabNavigation />
        <div className="min-h-screen">
          {renderTabContent()}
        </div>
      </div>

      {/* Selected Holding Modal */}
      {selectedHolding && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="flex min-h-screen items-center justify-center p-4">
            <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={() => setSelectedHolding(null)}></div>
            <div className="relative bg-white rounded-xl shadow-xl max-w-2xl w-full">
              <div className="flex items-center justify-between p-6 border-b border-gray-200">
                <div className="flex items-center space-x-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-white font-bold ${
                    selectedHolding.trending === 'up' ? 'bg-green-500' :
                    selectedHolding.trending === 'down' ? 'bg-red-500' : 'bg-gray-500'
                  }`}>
                    {selectedHolding.symbol.charAt(0)}
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900">{selectedHolding.symbol}</h3>
                    <p className="text-sm text-gray-600">{selectedHolding.name}</p>
                  </div>
                </div>
                <button
                  onClick={() => setSelectedHolding(null)}
                  className="text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <div className="p-6">
                <div className="grid grid-cols-2 gap-6">
                  <div className="space-y-4">
                    <div>
                      <label className="text-sm font-medium text-gray-600">Shares</label>
                      <p className="text-lg font-semibold text-gray-900">{selectedHolding.shares.toLocaleString()}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-600">Current Price</label>
                      <p className="text-lg font-semibold text-gray-900">${selectedHolding.currentPrice}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-600">Average Cost</label>
                      <p className="text-lg font-semibold text-gray-900">${selectedHolding.avgCost}</p>
                    </div>
                  </div>
                  <div className="space-y-4">
                    <div>
                      <label className="text-sm font-medium text-gray-600">Total Value</label>
                      <p className="text-lg font-semibold text-gray-900">${selectedHolding.totalValue.toLocaleString()}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-600">Unrealized Gain/Loss</label>
                      <p className={`text-lg font-semibold ${selectedHolding.gain >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {selectedHolding.gain >= 0 ? '+' : ''}${selectedHolding.gain.toLocaleString()} ({selectedHolding.gainPercent}%)
                      </p>
                    </div>
                    <div>
                      <label className="text-sm font-medium text-gray-600">Portfolio Allocation</label>
                      <p className="text-lg font-semibold text-gray-900">{selectedHolding.allocation}%</p>
                    </div>
                  </div>
                </div>
                
                <div className="mt-6 pt-6 border-t border-gray-200">
                  <div className="flex space-x-3">
                    <button 
                      onClick={() => navigate(`/stocks/${selectedHolding.symbol}`)}
                      className="flex-1 bg-blue-600 text-white rounded-lg py-2 hover:bg-blue-700 transition-colors"
                    >
                      View Details
                    </button>
                    <button className="flex-1 border border-gray-300 text-gray-700 rounded-lg py-2 hover:bg-gray-50 transition-colors">
                      Edit Position
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}

export default Portfolio;