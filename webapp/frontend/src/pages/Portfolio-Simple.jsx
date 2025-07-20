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
      { id: 'allocation', label: 'Allocation', icon: ChartPieIcon, count: null },
      { id: 'analysis', label: 'Analysis', icon: AdjustmentsHorizontalIcon, count: null },
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

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return <PortfolioSummary />;
      
      case 'holdings':
        return <HoldingsTable />;
      
      case 'performance':
        return (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
            <DataNotAvailable 
              message="Performance charts coming soon" 
              suggestion="Advanced performance analytics with interactive charts, benchmarking, and attribution analysis"
              type="chart"
            />
          </div>
        );
      
      case 'allocation':
        return (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
            <DataNotAvailable 
              message="Allocation analysis coming soon" 
              suggestion="Interactive allocation charts, sector breakdown, and rebalancing recommendations"
              type="chart"
            />
          </div>
        );
      
      case 'analysis':
        return (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
            <DataNotAvailable 
              message="Advanced analysis coming soon" 
              suggestion="Risk metrics, factor analysis, Monte Carlo simulations, and portfolio optimization tools"
              type="chart"
            />
          </div>
        );
      
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
      title="Portfolio" 
      subtitle="Manage your investment portfolio"
      action={
        <button className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
          <PlusIcon className="h-4 w-4 mr-2" />
          Add Position
        </button>
      }
    >
      <div className="space-y-6">
        <PortfolioSummary />
        
        <div className="bg-white shadow rounded-lg">
          <TabNavigation />
          <div className="p-6">
            {renderTabContent()}
          </div>
        </div>
      </div>
    </PageLayout>
  );
}

export default Portfolio;