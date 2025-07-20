import React, { useState, useEffect, useMemo, useCallback } from 'react';
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
  EyeIcon,
  ArrowsUpDownIcon,
  FunnelIcon,
  CloudArrowDownIcon,
  CloudArrowUpIcon,
  CogIcon,
  ChartPieIcon,
  DocumentChartBarIcon,
  BanknotesIcon,
  ScaleIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XMarkIcon,
  MagnifyingGlassIcon,
  AdjustmentsHorizontalIcon,
  ArrowPathIcon,
  ShareIcon,
  PrinterIcon,
  SunIcon,
  MoonIcon,
  BeakerIcon,
  GlobeAltIcon,
  SparklesIcon,
  RocketLaunchIcon,
  ShieldCheckIcon,
  LightBulbIcon,
  BoltIcon,
  FireIcon,
  StarIcon,
  HeartIcon,
  CubeIcon,
  CommandLineIcon,
  ChartBarSquareIcon,
  PresentationChartLineIcon,
  CalculatorIcon,
  ClipboardDocumentListIcon,
  ArrowDownTrayIcon,
  ArrowUpTrayIcon
} from '@heroicons/react/24/outline';
import { PageLayout, CardLayout, GridLayout } from '../components/ui/layout';
import { DataNotAvailable, LoadingFallback } from '../components/fallbacks/DataNotAvailable';
import RequiresApiKeys from '../components/RequiresApiKeys';
import { 
  PieChart, 
  Pie, 
  Cell, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  LineChart,
  Line,
  Area,
  AreaChart,
  ScatterChart,
  Scatter,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Treemap,
  ComposedChart
} from 'recharts';

// Advanced Tailwind Modal Component
const Modal = ({ isOpen, onClose, title, children, size = 'md' }) => {
  const sizeClasses = {
    sm: 'max-w-md',
    md: 'max-w-lg',
    lg: 'max-w-4xl',
    xl: 'max-w-6xl',
    full: 'max-w-7xl'
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-4">
        <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={onClose}></div>
        <div className={`relative bg-white rounded-lg shadow-xl ${sizeClasses[size]} w-full max-h-[90vh] overflow-hidden`}>
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <XMarkIcon className="h-6 w-6" />
            </button>
          </div>
          <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
};

// Advanced Data Table Component
const DataTable = ({ 
  data, 
  columns, 
  sortable = true, 
  filterable = true, 
  pagination = true,
  onRowClick,
  rowsPerPage = 10
}) => {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });
  const [filterText, setFilterText] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  const filteredData = useMemo(() => {
    if (!filterText) return data;
    return data.filter(row =>
      Object.values(row).some(value =>
        value.toString().toLowerCase().includes(filterText.toLowerCase())
      )
    );
  }, [data, filterText]);

  const sortedData = useMemo(() => {
    if (!sortConfig.key) return filteredData;
    
    return [...filteredData].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];
      
      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [filteredData, sortConfig]);

  const paginatedData = useMemo(() => {
    if (!pagination) return sortedData;
    const startIndex = (currentPage - 1) * rowsPerPage;
    return sortedData.slice(startIndex, startIndex + rowsPerPage);
  }, [sortedData, currentPage, rowsPerPage, pagination]);

  const totalPages = Math.ceil(sortedData.length / rowsPerPage);

  const handleSort = (key) => {
    if (!sortable) return;
    setSortConfig({
      key,
      direction: sortConfig.key === key && sortConfig.direction === 'asc' ? 'desc' : 'asc'
    });
  };

  return (
    <div className="space-y-4">
      {filterable && (
        <div className="flex items-center space-x-4">
          <div className="relative flex-1 max-w-sm">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Filter data..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>
      )}

      <div className="overflow-x-auto border border-gray-200 rounded-lg">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  onClick={() => handleSort(column.key)}
                  className={`px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider ${
                    sortable ? 'cursor-pointer hover:bg-gray-100' : ''
                  }`}
                >
                  <div className="flex items-center space-x-1">
                    <span>{column.label}</span>
                    {sortable && (
                      <ArrowsUpDownIcon className="h-4 w-4" />
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {paginatedData.map((row, index) => (
              <tr
                key={index}
                onClick={() => onRowClick?.(row)}
                className={`${onRowClick ? 'cursor-pointer hover:bg-gray-50' : ''} transition-colors`}
              >
                {columns.map((column) => (
                  <td key={column.key} className="px-6 py-4 whitespace-nowrap">
                    {column.render ? column.render(row[column.key], row) : row[column.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pagination && totalPages > 1 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-700">
            Showing {(currentPage - 1) * rowsPerPage + 1} to {Math.min(currentPage * rowsPerPage, sortedData.length)} of {sortedData.length} results
          </div>
          <div className="flex space-x-2">
            <button
              onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
              disabled={currentPage === 1}
              className="px-3 py-1 border border-gray-300 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              Previous
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
              <button
                key={page}
                onClick={() => setCurrentPage(page)}
                className={`px-3 py-1 border rounded ${
                  currentPage === page
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'border-gray-300 hover:bg-gray-50'
                }`}
              >
                {page}
              </button>
            ))}
            <button
              onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
              disabled={currentPage === totalPages}
              className="px-3 py-1 border border-gray-300 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// Advanced Tab System
const TabSystem = ({ tabs, activeTab, onTabChange, children }) => (
  <div className="bg-white shadow rounded-lg overflow-hidden">
    <div className="border-b border-gray-200">
      <nav className="flex space-x-8 px-6">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === tab.id
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <div className="flex items-center space-x-2">
              {tab.icon && <tab.icon className="h-4 w-4" />}
              <span>{tab.label}</span>
              {tab.badge && (
                <span className="bg-blue-100 text-blue-800 text-xs font-medium px-2 py-1 rounded-full">
                  {tab.badge}
                </span>
              )}
            </div>
          </button>
        ))}
      </nav>
    </div>
    <div className="p-6">
      {children}
    </div>
  </div>
);

function Portfolio() {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedHolding, setSelectedHolding] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [showAnalyticsModal, setShowAnalyticsModal] = useState(false);
  const [showOptimizationModal, setShowOptimizationModal] = useState(false);
  const [showScreenerModal, setShowScreenerModal] = useState(false);
  const [realTimeData, setRealTimeData] = useState(true);
  
  // Enhanced feature states
  const [darkMode, setDarkMode] = useState(false);
  const [showESGModal, setShowESGModal] = useState(false);
  const [showAIInsightsModal, setShowAIInsightsModal] = useState(false);
  const [showComparisonModal, setShowComparisonModal] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [showRiskMonteCarloModal, setShowRiskMonteCarloModal] = useState(false);
  const [showRealTimeMonitorModal, setShowRealTimeMonitorModal] = useState(false);
  const [portfolioAlerts, setPortfolioAlerts] = useState([]);
  const [realTimeUpdates, setRealTimeUpdates] = useState(true);
  const [monteCarloScenarios, setMonteCarloScenarios] = useState(1000);
  const [riskTolerance, setRiskTolerance] = useState('moderate');
  const [selectedTimeframe, setSelectedTimeframe] = useState('1M');
  const [benchmark, setBenchmark] = useState('SPY');
  
  // Complex portfolio state
  const [portfolio, setPortfolio] = useState({
    summary: {
      totalValue: 0,
      totalGain: 0,
      totalGainPercent: 0,
      dayChange: 0,
      dayChangePercent: 0,
      totalCost: 0,
      availableCash: 0,
      marginUsed: 0,
      buyingPower: 0
    },
    holdings: [],
    performance: {
      historical: [],
      benchmarks: [],
      metrics: {}
    },
    allocation: {
      sectors: [],
      assetTypes: [],
      geography: [],
      marketCap: [],
      style: []
    },
    risk: {
      beta: 0,
      sharpe: 0,
      volatility: 0,
      var95: 0,
      maxDrawdown: 0,
      expectedShortfall: 0,
      trackingError: 0,
      informationRatio: 0,
      treynorRatio: 0,
      calmarRatio: 0
    },
    factors: {
      size: 0,
      value: 0,
      momentum: 0,
      quality: 0,
      lowVol: 0,
      profitability: 0
    },
    attribution: {
      allocation: 0,
      selection: 0,
      interaction: 0,
      total: 0
    },
    optimization: {
      currentEfficiency: 0,
      recommendedChanges: [],
      riskContribution: [],
      concentration: 0
    }
  });

  // Advanced filters and settings
  const [filters, setFilters] = useState({
    sector: 'all',
    minValue: 0,
    maxValue: 0,
    gainLossFilter: 'all'
  });

  useEffect(() => {
    // Simulate complex data loading
    const timer = setTimeout(() => {
      setPortfolio({
        summary: {
          totalValue: 847291.50,
          totalGain: 127458.92,
          totalGainPercent: 17.72,
          dayChange: -2547.83,
          dayChangePercent: -0.30,
          totalCost: 719832.58,
          availableCash: 15420.30,
          marginUsed: 0,
          buyingPower: 62841.20
        },
        holdings: [
          {
            id: 1,
            symbol: 'AAPL',
            name: 'Apple Inc.',
            shares: 500,
            currentPrice: 175.43,
            avgCost: 145.20,
            totalValue: 87715.00,
            gain: 15115.00,
            gainPercent: 20.82,
            dayChange: -2.15,
            dayChangePercent: -1.21,
            sector: 'Technology',
            beta: 1.24,
            dividendYield: 0.52,
            allocation: 10.35
          },
          {
            id: 2,
            symbol: 'GOOGL',
            name: 'Alphabet Inc.',
            shares: 75,
            currentPrice: 2431.20,
            avgCost: 2280.50,
            totalValue: 182340.00,
            gain: 11302.50,
            gainPercent: 6.61,
            dayChange: 15.30,
            dayChangePercent: 0.63,
            sector: 'Technology',
            beta: 1.05,
            dividendYield: 0.00,
            allocation: 21.52
          },
          {
            id: 3,
            symbol: 'MSFT',
            name: 'Microsoft Corporation',
            shares: 300,
            currentPrice: 295.37,
            avgCost: 268.90,
            totalValue: 88611.00,
            gain: 7941.00,
            gainPercent: 9.84,
            dayChange: -3.42,
            dayChangePercent: -1.14,
            sector: 'Technology',
            beta: 0.91,
            dividendYield: 0.72,
            allocation: 10.46
          },
          {
            id: 4,
            symbol: 'TSLA',
            name: 'Tesla Inc.',
            shares: 200,
            currentPrice: 245.67,
            avgCost: 198.30,
            totalValue: 49134.00,
            gain: 9474.00,
            gainPercent: 23.90,
            dayChange: -8.92,
            dayChangePercent: -3.51,
            sector: 'Consumer Discretionary',
            beta: 2.11,
            dividendYield: 0.00,
            allocation: 5.80
          }
        ],
        performance: {
          historical: Array.from({ length: 30 }, (_, i) => ({
            date: new Date(Date.now() - (29 - i) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
            value: 800000 + Math.random() * 100000,
            sp500: 4100 + Math.random() * 200
          })),
          metrics: {
            totalReturn: 17.72,
            annualizedReturn: 12.45,
            volatility: 18.23,
            sharpeRatio: 0.68,
            maxDrawdown: -8.45,
            beta: 1.12,
            alpha: 2.34
          }
        },
        allocation: {
          sectors: [
            { name: 'Technology', value: 42.33, color: '#3B82F6' },
            { name: 'Healthcare', value: 18.75, color: '#10B981' },
            { name: 'Financials', value: 15.20, color: '#F59E0B' },
            { name: 'Consumer Discretionary', value: 12.40, color: '#EF4444' },
            { name: 'Energy', value: 8.15, color: '#8B5CF6' },
            { name: 'Other', value: 3.17, color: '#6B7280' }
          ],
          assetTypes: [
            { name: 'Stocks', value: 87.50, color: '#3B82F6' },
            { name: 'ETFs', value: 8.20, color: '#10B981' },
            { name: 'Cash', value: 4.30, color: '#F59E0B' }
          ],
          marketCap: [
            { name: 'Large Cap', value: 65.2, color: '#3B82F6' },
            { name: 'Mid Cap', value: 22.1, color: '#10B981' },
            { name: 'Small Cap', value: 12.7, color: '#F59E0B' }
          ],
          style: [
            { name: 'Growth', value: 58.3, color: '#8B5CF6' },
            { name: 'Value', value: 31.2, color: '#EF4444' },
            { name: 'Blend', value: 10.5, color: '#6B7280' }
          ]
        },
        factors: {
          size: -0.15,
          value: 0.23,
          momentum: 0.08,
          quality: 0.41,
          lowVol: -0.12,
          profitability: 0.31
        },
        attribution: {
          allocation: 1.23,
          selection: 2.14,
          interaction: -0.15,
          total: 3.22
        },
        optimization: {
          currentEfficiency: 0.78,
          recommendedChanges: [
            { action: 'Reduce', symbol: 'AAPL', amount: 5000, reason: 'Overweight tech exposure' },
            { action: 'Add', symbol: 'VTI', amount: 3000, reason: 'Improve diversification' },
            { action: 'Rebalance', symbol: 'GOOGL', amount: -2000, reason: 'Sector concentration' }
          ],
          riskContribution: [
            { symbol: 'AAPL', contribution: 28.5 },
            { symbol: 'GOOGL', contribution: 22.1 },
            { symbol: 'MSFT', contribution: 19.3 },
            { symbol: 'TSLA', contribution: 30.1 }
          ],
          concentration: 82.4
        }
      });
      setLoading(false);
    }, 1500);

    return () => clearTimeout(timer);
  }, []);

  // Enhanced tab configuration with new features
  const tabs = [
    { id: 'overview', label: 'Overview', icon: ChartBarIcon, badge: null },
    { id: 'holdings', label: 'Holdings', icon: DocumentChartBarIcon, badge: portfolio.holdings.length },
    { id: 'performance', label: 'Performance', icon: ArrowTrendingUpIcon, badge: null },
    { id: 'allocation', label: 'Allocation', icon: ChartPieIcon, badge: null },
    { id: 'analytics', label: 'Analytics', icon: ScaleIcon, badge: null },
    { id: 'risk', label: 'Risk Analysis', icon: ExclamationTriangleIcon, badge: null },
    { id: 'optimization', label: 'Optimization', icon: CogIcon, badge: portfolio.optimization?.recommendedChanges?.length || 0 },
    { id: 'factors', label: 'Factor Analysis', icon: AdjustmentsHorizontalIcon, badge: null },
    { id: 'esg', label: 'ESG Scoring', icon: GlobeAltIcon, badge: 'NEW' },
    { id: 'ai-insights', label: 'AI Insights', icon: SparklesIcon, badge: 'BETA' },
    { id: 'monitoring', label: 'Real-time Monitor', icon: BoltIcon, badge: portfolioAlerts.length || null },
    { id: 'comparison', label: 'Portfolio Compare', icon: ChartBarSquareIcon, badge: null },
    { id: 'monte-carlo', label: 'Monte Carlo Risk', icon: BeakerIcon, badge: 'PRO' }
  ];

  // Holdings table columns
  const holdingsColumns = [
    {
      key: 'symbol',
      label: 'Symbol',
      render: (value, row) => (
        <div>
          <div className="font-medium text-gray-900">{value}</div>
          <div className="text-sm text-gray-500">{row.name}</div>
        </div>
      )
    },
    {
      key: 'shares',
      label: 'Shares',
      render: (value) => <span className="font-medium">{value.toLocaleString()}</span>
    },
    {
      key: 'currentPrice',
      label: 'Price',
      render: (value) => <span>${value.toFixed(2)}</span>
    },
    {
      key: 'avgCost',
      label: 'Avg Cost',
      render: (value) => <span>${value.toFixed(2)}</span>
    },
    {
      key: 'totalValue',
      label: 'Market Value',
      render: (value) => <span className="font-medium">${value.toLocaleString()}</span>
    },
    {
      key: 'gain',
      label: 'Gain/Loss',
      render: (value, row) => (
        <div className={value >= 0 ? 'text-green-600' : 'text-red-600'}>
          <div className="font-medium">
            {value >= 0 ? '+' : ''}${value.toLocaleString()}
          </div>
          <div className="text-sm">
            ({row.gainPercent >= 0 ? '+' : ''}{row.gainPercent.toFixed(2)}%)
          </div>
        </div>
      )
    },
    {
      key: 'dayChange',
      label: 'Day Change',
      render: (value, row) => (
        <div className={value >= 0 ? 'text-green-600' : 'text-red-600'}>
          <div>{value >= 0 ? '+' : ''}${value.toFixed(2)}</div>
          <div className="text-sm">
            ({row.dayChangePercent >= 0 ? '+' : ''}{row.dayChangePercent.toFixed(2)}%)
          </div>
        </div>
      )
    },
    {
      key: 'allocation',
      label: 'Allocation',
      render: (value) => (
        <div className="flex items-center space-x-2">
          <div className="flex-1 bg-gray-200 rounded-full h-2">
            <div 
              className="bg-blue-600 h-2 rounded-full"
              style={{ width: `${Math.min(value, 100)}%` }}
            ></div>
          </div>
          <span className="text-sm font-medium">{value.toFixed(1)}%</span>
        </div>
      )
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (_, row) => (
        <div className="flex space-x-2">
          <button 
            onClick={(e) => {
              e.stopPropagation();
              setSelectedHolding(row);
            }}
            className="text-blue-600 hover:text-blue-900"
          >
            <EyeIcon className="h-4 w-4" />
          </button>
          <button 
            onClick={(e) => {
              e.stopPropagation();
              // Edit holding
            }}
            className="text-green-600 hover:text-green-900"
          >
            <PencilIcon className="h-4 w-4" />
          </button>
          <button 
            onClick={(e) => {
              e.stopPropagation();
              // Delete holding
            }}
            className="text-red-600 hover:text-red-900"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      )
    }
  ];

  if (!isAuthenticated) {
    return <RequiresApiKeys />;
  }

  if (loading) {
    return (
      <PageLayout title="Portfolio">
        <LoadingFallback message="Loading your advanced portfolio analytics..." />
      </PageLayout>
    );
  }

  // Portfolio Overview Cards
  const PortfolioOverview = () => (
    <div className="space-y-6">
      {/* Summary Cards */}
      <GridLayout cols={4} gap={6}>
        <CardLayout className="bg-gradient-to-r from-blue-500 to-blue-600 text-white">
          <div className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-blue-100">Total Portfolio Value</p>
                <p className="text-3xl font-bold">${portfolio.summary.totalValue.toLocaleString()}</p>
                <div className="flex items-center mt-2">
                  {portfolio.summary.dayChange >= 0 ? (
                    <ArrowTrendingUpIcon className="h-4 w-4 mr-1" />
                  ) : (
                    <ArrowTrendingDownIcon className="h-4 w-4 mr-1" />
                  )}
                  <span className="text-sm">
                    {portfolio.summary.dayChange >= 0 ? '+' : ''}${portfolio.summary.dayChange.toLocaleString()} ({portfolio.summary.dayChangePercent}%) today
                  </span>
                </div>
              </div>
              <CurrencyDollarIcon className="h-12 w-12 text-blue-200" />
            </div>
          </div>
        </CardLayout>

        <CardLayout className="bg-gradient-to-r from-green-500 to-green-600 text-white">
          <div className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-green-100">Total Gains</p>
                <p className="text-3xl font-bold">${portfolio.summary.totalGain.toLocaleString()}</p>
                <p className="text-sm text-green-100 mt-2">
                  {portfolio.summary.totalGainPercent}% return
                </p>
              </div>
              <ArrowTrendingUpIcon className="h-12 w-12 text-green-200" />
            </div>
          </div>
        </CardLayout>

        <CardLayout>
          <div className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Available Cash</p>
                <p className="text-2xl font-bold text-gray-900">${portfolio.summary.availableCash.toLocaleString()}</p>
                <p className="text-sm text-gray-500 mt-2">Ready to invest</p>
              </div>
              <BanknotesIcon className="h-8 w-8 text-green-500" />
            </div>
          </div>
        </CardLayout>

        <CardLayout>
          <div className="p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-600">Buying Power</p>
                <p className="text-2xl font-bold text-gray-900">${portfolio.summary.buyingPower.toLocaleString()}</p>
                <p className="text-sm text-gray-500 mt-2">Including margin</p>
              </div>
              <ScaleIcon className="h-8 w-8 text-blue-500" />
            </div>
          </div>
        </CardLayout>
      </GridLayout>

      {/* Performance Chart */}
      <CardLayout title="Portfolio Performance" subtitle="30-day performance vs S&P 500">
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={portfolio.performance.historical}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" />
              <YAxis />
              <Tooltip 
                formatter={(value, name) => [
                  `$${Number(value).toLocaleString()}`,
                  name === 'value' ? 'Portfolio' : 'S&P 500'
                ]}
              />
              <Line 
                type="monotone" 
                dataKey="value" 
                stroke="#3B82F6" 
                strokeWidth={3}
                dot={false}
              />
              <Line 
                type="monotone" 
                dataKey="sp500" 
                stroke="#10B981" 
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardLayout>

      {/* Allocation Charts */}
      <GridLayout cols={2} gap={6}>
        <CardLayout title="Sector Allocation">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={portfolio.allocation.sectors}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value }) => `${name}: ${value}%`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {portfolio.allocation.sectors.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </CardLayout>

        <CardLayout title="Asset Type Allocation">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={portfolio.allocation.assetTypes}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip formatter={(value) => [`${value}%`, 'Allocation']} />
                <Bar dataKey="value" fill="#3B82F6" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardLayout>
      </GridLayout>
    </div>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return <PortfolioOverview />;
      
      case 'holdings':
        return (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-medium text-gray-900">Portfolio Holdings</h3>
                <p className="text-sm text-gray-500">{portfolio.holdings.length} positions</p>
              </div>
              <div className="flex space-x-3">
                <button
                  onClick={() => setShowImportModal(true)}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
                >
                  <CloudArrowDownIcon className="h-4 w-4 mr-2" />
                  Import from Broker
                </button>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
                >
                  <PlusIcon className="h-4 w-4 mr-2" />
                  Add Position
                </button>
              </div>
            </div>
            
            <DataTable
              data={portfolio.holdings}
              columns={holdingsColumns}
              onRowClick={(holding) => navigate(`/stocks/${holding.symbol}`)}
              sortable={true}
              filterable={true}
              pagination={true}
              rowsPerPage={10}
            />
          </div>
        );
      
      case 'performance':
        return (
          <div className="space-y-6">
            <GridLayout cols={3} gap={6}>
              {Object.entries(portfolio.performance.metrics).map(([key, value]) => (
                <CardLayout key={key}>
                  <div className="p-6 text-center">
                    <p className="text-sm font-medium text-gray-600 capitalize">
                      {key.replace(/([A-Z])/g, ' $1').trim()}
                    </p>
                    <p className="text-2xl font-bold text-gray-900 mt-2">
                      {typeof value === 'number' ? `${value.toFixed(2)}${key.includes('Return') || key.includes('Ratio') ? '%' : ''}` : value}
                    </p>
                  </div>
                </CardLayout>
              ))}
            </GridLayout>
            
            <CardLayout title="Detailed Performance Analysis">
              <DataNotAvailable 
                message="Advanced performance analytics coming soon" 
                suggestion="Detailed attribution analysis, factor decomposition, and risk-adjusted returns will be available here"
                type="chart"
              />
            </CardLayout>
          </div>
        );
      
      case 'allocation':
        return (
          <div className="space-y-6">
            <GridLayout cols={2} gap={6}>
              <CardLayout title="Current Allocation">
                <div className="space-y-4">
                  {portfolio.allocation.sectors.map((sector) => (
                    <div key={sector.name} className="flex items-center space-x-3">
                      <div 
                        className="w-4 h-4 rounded"
                        style={{ backgroundColor: sector.color }}
                      ></div>
                      <div className="flex-1">
                        <div className="flex justify-between items-center">
                          <span className="text-sm font-medium">{sector.name}</span>
                          <span className="text-sm text-gray-500">{sector.value}%</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2 mt-1">
                          <div 
                            className="h-2 rounded-full"
                            style={{ 
                              width: `${sector.value}%`,
                              backgroundColor: sector.color 
                            }}
                          ></div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardLayout>
              
              <CardLayout title="Rebalancing Recommendations">
                <DataNotAvailable 
                  message="Rebalancing analysis coming soon" 
                  suggestion="AI-powered allocation recommendations and rebalancing suggestions will be available here"
                  type="chart"
                />
              </CardLayout>
            </GridLayout>
          </div>
        );
      
      case 'analytics':
        return (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-medium text-gray-900">Advanced Analytics</h3>
              <div className="flex space-x-3">
                <button
                  onClick={() => setShowScreenerModal(true)}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
                >
                  <FunnelIcon className="h-4 w-4 mr-2" />
                  Screen Holdings
                </button>
                <button
                  onClick={() => setShowAnalyticsModal(true)}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
                >
                  <AdjustmentsHorizontalIcon className="h-4 w-4 mr-2" />
                  Configure Analytics
                </button>
              </div>
            </div>
            
            <GridLayout cols={2} gap={6}>
              <CardLayout title="Performance Attribution">
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="text-center p-4 bg-blue-50 rounded-lg">
                      <p className="text-sm font-medium text-gray-600">Allocation Effect</p>
                      <p className="text-xl font-bold text-blue-600">{portfolio.attribution.allocation}%</p>
                    </div>
                    <div className="text-center p-4 bg-green-50 rounded-lg">
                      <p className="text-sm font-medium text-gray-600">Selection Effect</p>
                      <p className="text-xl font-bold text-green-600">{portfolio.attribution.selection}%</p>
                    </div>
                  </div>
                  <div className="text-center p-4 bg-gray-50 rounded-lg">
                    <p className="text-sm font-medium text-gray-600">Total Attribution</p>
                    <p className="text-2xl font-bold text-gray-900">{portfolio.attribution.total}%</p>
                  </div>
                </div>
              </CardLayout>
              
              <CardLayout title="Risk Contribution">
                <div className="space-y-3">
                  {portfolio.optimization.riskContribution.map((item, index) => (
                    <div key={index} className="flex justify-between items-center">
                      <span className="text-sm font-medium">{item.symbol}</span>
                      <div className="flex items-center space-x-2">
                        <div className="w-24 bg-gray-200 rounded-full h-2">
                          <div 
                            className="bg-red-500 h-2 rounded-full"
                            style={{ width: `${(item.contribution / 35) * 100}%` }}
                          ></div>
                        </div>
                        <span className="text-sm text-gray-600">{item.contribution}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardLayout>
            </GridLayout>
            
            <GridLayout cols={3} gap={6}>
              <CardLayout title="Portfolio Concentration">
                <div className="text-center">
                  <div className="relative w-24 h-24 mx-auto mb-4">
                    <svg className="w-24 h-24 transform -rotate-90" viewBox="0 0 100 100">
                      <circle cx="50" cy="50" r="40" fill="transparent" stroke="#e5e7eb" strokeWidth="8"/>
                      <circle 
                        cx="50" 
                        cy="50" 
                        r="40" 
                        fill="transparent" 
                        stroke={portfolio.optimization.concentration > 80 ? '#ef4444' : '#3b82f6'}
                        strokeWidth="8"
                        strokeDasharray={`${(portfolio.optimization.concentration / 100) * 251.2} 251.2`}
                      />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className="text-xl font-bold">{portfolio.optimization.concentration}%</span>
                    </div>
                  </div>
                  <p className="text-sm text-gray-600">Concentration Risk</p>
                </div>
              </CardLayout>
              
              <CardLayout title="Efficiency Score">
                <div className="text-center">
                  <div className="text-3xl font-bold text-blue-600 mb-2">
                    {(portfolio.optimization.currentEfficiency * 100).toFixed(0)}%
                  </div>
                  <p className="text-sm text-gray-600">Portfolio Efficiency</p>
                  <div className="mt-4 w-full bg-gray-200 rounded-full h-2">
                    <div 
                      className="bg-blue-600 h-2 rounded-full"
                      style={{ width: `${portfolio.optimization.currentEfficiency * 100}%` }}
                    ></div>
                  </div>
                </div>
              </CardLayout>
              
              <CardLayout title="Diversification Score">
                <div className="text-center">
                  <div className="text-3xl font-bold text-green-600 mb-2">B+</div>
                  <p className="text-sm text-gray-600">Diversification Grade</p>
                  <div className="mt-4 space-y-2 text-xs text-gray-500">
                    <div>Sectors: 6/11</div>
                    <div>Geography: Limited</div>
                    <div>Asset Classes: 3</div>
                  </div>
                </div>
              </CardLayout>
            </GridLayout>
          </div>
        );
      
      case 'risk':
        return (
          <div className="space-y-6">
            <CardLayout title="Risk Metrics Dashboard">
              <GridLayout cols={3} gap={6}>
                <div className="text-center p-4 bg-yellow-50 rounded-lg">
                  <ExclamationTriangleIcon className="h-8 w-8 text-yellow-500 mx-auto mb-2" />
                  <p className="text-sm font-medium text-gray-600">Portfolio Beta</p>
                  <p className="text-xl font-bold text-gray-900">{portfolio.risk.beta || '1.12'}</p>
                </div>
                <div className="text-center p-4 bg-red-50 rounded-lg">
                  <ArrowTrendingDownIcon className="h-8 w-8 text-red-500 mx-auto mb-2" />
                  <p className="text-sm font-medium text-gray-600">Max Drawdown</p>
                  <p className="text-xl font-bold text-gray-900">-8.45%</p>
                </div>
                <div className="text-center p-4 bg-green-50 rounded-lg">
                  <CheckCircleIcon className="h-8 w-8 text-green-500 mx-auto mb-2" />
                  <p className="text-sm font-medium text-gray-600">Sharpe Ratio</p>
                  <p className="text-xl font-bold text-gray-900">0.68</p>
                </div>
              </GridLayout>
            </CardLayout>
            
            <CardLayout title="Value at Risk Analysis">
              <DataNotAvailable 
                message="VaR analysis coming soon" 
                suggestion="Monte Carlo simulations and stress testing scenarios will be available here"
                type="chart"
              />
            </CardLayout>
          </div>
        );
      
      case 'optimization':
        return (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-medium text-gray-900">Portfolio Optimization</h3>
              <button
                onClick={() => setShowOptimizationModal(true)}
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
              >
                <CogIcon className="h-4 w-4 mr-2" />
                Run Optimization
              </button>
            </div>
            
            <CardLayout title="Recommended Changes">
              <div className="space-y-4">
                {portfolio.optimization.recommendedChanges.map((change, index) => (
                  <div key={index} className="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
                    <div className="flex items-center space-x-4">
                      <div className={`p-2 rounded-full ${
                        change.action === 'Add' ? 'bg-green-100 text-green-600' :
                        change.action === 'Reduce' ? 'bg-red-100 text-red-600' :
                        'bg-blue-100 text-blue-600'
                      }`}>
                        {change.action === 'Add' ? (
                          <PlusIcon className="h-4 w-4" />
                        ) : change.action === 'Reduce' ? (
                          <ArrowTrendingDownIcon className="h-4 w-4" />
                        ) : (
                          <ArrowPathIcon className="h-4 w-4" />
                        )}
                      </div>
                      <div>
                        <p className="font-medium">{change.action} {change.symbol}</p>
                        <p className="text-sm text-gray-500">{change.reason}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-medium">${Math.abs(change.amount).toLocaleString()}</p>
                      <p className="text-sm text-gray-500">
                        {change.amount > 0 ? 'Buy' : 'Sell'}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </CardLayout>
            
            <GridLayout cols={2} gap={6}>
              <CardLayout title="Efficient Frontier">
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis 
                        dataKey="risk" 
                        domain={[0, 25]}
                        label={{ value: 'Risk (%)', position: 'insideBottom', offset: -5 }}
                      />
                      <YAxis 
                        dataKey="return"
                        domain={[0, 20]}
                        label={{ value: 'Return (%)', angle: -90, position: 'insideLeft' }}
                      />
                      <Tooltip formatter={(value, name) => [`${value}%`, name === 'risk' ? 'Risk' : 'Return']} />
                      <Scatter 
                        data={[
                          { risk: 15.2, return: 12.4, name: 'Current Portfolio' },
                          { risk: 12.8, return: 11.1, name: 'Optimized Portfolio' },
                          { risk: 10.5, return: 8.9, name: 'Conservative' },
                          { risk: 18.7, return: 14.2, name: 'Aggressive' }
                        ]}
                        fill="#3B82F6"
                      />
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              </CardLayout>
              
              <CardLayout title="Asset Allocation Targets">
                <div className="space-y-4">
                  {[
                    { name: 'US Large Cap', current: 65, target: 60, color: '#3B82F6' },
                    { name: 'US Small Cap', current: 13, target: 15, color: '#10B981' },
                    { name: 'International', current: 8, target: 15, color: '#F59E0B' },
                    { name: 'Bonds', current: 4, target: 10, color: '#EF4444' },
                    { name: 'Cash', current: 10, target: 0, color: '#6B7280' }
                  ].map((asset, index) => (
                    <div key={index} className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-medium">{asset.name}</span>
                        <span className="text-sm text-gray-500">Current: {asset.current}% → Target: {asset.target}%</span>
                      </div>
                      <div className="flex space-x-2">
                        <div className="flex-1 bg-gray-200 rounded-full h-2">
                          <div 
                            className="h-2 rounded-full"
                            style={{ 
                              width: `${asset.current}%`,
                              backgroundColor: asset.color,
                              opacity: 0.7
                            }}
                          ></div>
                        </div>
                        <div className="flex-1 bg-gray-200 rounded-full h-2">
                          <div 
                            className="h-2 rounded-full"
                            style={{ 
                              width: `${asset.target}%`,
                              backgroundColor: asset.color
                            }}
                          ></div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardLayout>
            </GridLayout>
          </div>
        );
      
      case 'factors':
        return (
          <div className="space-y-6">
            <CardLayout title="Factor Exposure Analysis">
              <div className="grid grid-cols-2 gap-6">
                <div>
                  <h4 className="font-medium text-gray-900 mb-4">Style Factors</h4>
                  <div className="space-y-4">
                    {Object.entries(portfolio.factors).map(([factor, value]) => (
                      <div key={factor} className="flex items-center justify-between">
                        <span className="text-sm font-medium capitalize">
                          {factor === 'lowVol' ? 'Low Volatility' : factor}
                        </span>
                        <div className="flex items-center space-x-2">
                          <div className="w-32 bg-gray-200 rounded-full h-2 relative">
                            <div className="absolute left-1/2 w-px h-4 bg-gray-400 -top-1"></div>
                            <div 
                              className={`h-2 rounded-full ${
                                value >= 0 ? 'bg-green-500' : 'bg-red-500'
                              }`}
                              style={{ 
                                width: `${Math.abs(value) * 100}%`,
                                marginLeft: value >= 0 ? '50%' : `${50 + (value * 100)}%`
                              }}
                            ></div>
                          </div>
                          <span className={`text-sm font-medium ${
                            value >= 0 ? 'text-green-600' : 'text-red-600'
                          }`}>
                            {value >= 0 ? '+' : ''}{(value * 100).toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div>
                  <h4 className="font-medium text-gray-900 mb-4">Factor Returns (1Y)</h4>
                  <div className="h-48">
                    <ResponsiveContainer width="100%" height="100%">
                      <RadarChart data={[
                        { factor: 'Size', exposure: portfolio.factors.size * 100, return: -2.1 },
                        { factor: 'Value', exposure: portfolio.factors.value * 100, return: 8.4 },
                        { factor: 'Momentum', exposure: portfolio.factors.momentum * 100, return: 12.7 },
                        { factor: 'Quality', exposure: portfolio.factors.quality * 100, return: 15.2 },
                        { factor: 'Low Vol', exposure: portfolio.factors.lowVol * 100, return: 6.8 },
                        { factor: 'Profitability', exposure: portfolio.factors.profitability * 100, return: 11.3 }
                      ]}>
                        <PolarGrid />
                        <PolarAngleAxis dataKey="factor" />
                        <PolarRadiusAxis domain={[-50, 50]} />
                        <Radar dataKey="exposure" stroke="#3B82F6" fill="#3B82F6" fillOpacity={0.3} />
                        <Tooltip />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </CardLayout>
            
            <GridLayout cols={3} gap={6}>
              <CardLayout title="Factor Concentration">
                <div className="text-center">
                  <div className="text-2xl font-bold text-blue-600 mb-2">Moderate</div>
                  <p className="text-sm text-gray-600">Factor Diversification</p>
                  <div className="mt-4 space-y-2 text-xs text-gray-500">
                    <div>Growth Tilt: Strong</div>
                    <div>Quality Bias: High</div>
                    <div>Size Exposure: Large</div>
                  </div>
                </div>
              </CardLayout>
              
              <CardLayout title="Style Drift">
                <div className="text-center">
                  <div className="text-2xl font-bold text-yellow-600 mb-2">Low</div>
                  <p className="text-sm text-gray-600">Style Consistency</p>
                  <div className="mt-4 w-full bg-gray-200 rounded-full h-2">
                    <div className="bg-yellow-500 h-2 rounded-full" style={{ width: '25%' }}></div>
                  </div>
                </div>
              </CardLayout>
              
              <CardLayout title="Factor Momentum">
                <div className="text-center">
                  <div className="text-2xl font-bold text-green-600 mb-2">Positive</div>
                  <p className="text-sm text-gray-600">3M Trend</p>
                  <div className="mt-4 flex justify-center">
                    <ArrowTrendingUpIcon className="h-8 w-8 text-green-500" />
                  </div>
                </div>
              </CardLayout>
            </GridLayout>
          </div>
        );
      
      default:
        return <PortfolioOverview />;
    }
  };

  return (
    <PageLayout 
      title="Advanced Portfolio Management" 
      subtitle="Comprehensive portfolio analytics and management tools"
      action={
        <div className="flex space-x-3">
          {/* Dark Mode Toggle */}
          <button 
            onClick={() => setDarkMode(!darkMode)}
            className={`inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md transition-colors ${
              darkMode 
                ? 'text-yellow-600 bg-yellow-50 border-yellow-200 hover:bg-yellow-100' 
                : 'text-gray-700 bg-white hover:bg-gray-50'
            }`}
            title={darkMode ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          >
            {darkMode ? <SunIcon className="h-4 w-4" /> : <MoonIcon className="h-4 w-4" />}
          </button>

          {/* Real-time Monitor Toggle */}
          <button 
            onClick={() => setShowRealTimeMonitorModal(true)}
            className={`inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md transition-colors ${
              realTimeUpdates 
                ? 'text-green-600 bg-green-50 border-green-200 hover:bg-green-100' 
                : 'text-gray-700 bg-white hover:bg-gray-50'
            }`}
            title="Real-time Portfolio Monitor"
          >
            <BoltIcon className="h-4 w-4" />
            {portfolioAlerts.length > 0 && (
              <span className="ml-1 bg-red-500 text-white text-xs rounded-full px-1.5 py-0.5">
                {portfolioAlerts.length}
              </span>
            )}
          </button>

          {/* AI Insights */}
          <button 
            onClick={() => setShowAIInsightsModal(true)}
            className="inline-flex items-center px-4 py-2 border border-purple-300 text-sm font-medium rounded-md text-purple-700 bg-purple-50 hover:bg-purple-100 transition-colors"
            title="AI-Powered Portfolio Insights"
          >
            <SparklesIcon className="h-4 w-4 mr-2" />
            AI Insights
            <span className="ml-2 bg-purple-100 text-purple-800 text-xs font-medium px-2 py-1 rounded-full">
              BETA
            </span>
          </button>

          {/* Enhanced Export */}
          <button 
            onClick={() => setShowExportModal(true)}
            className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50"
          >
            <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
            Export
          </button>

          {/* Share */}
          <button className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50">
            <ShareIcon className="h-4 w-4 mr-2" />
            Share
          </button>

          {/* Enhanced Refresh with Real-time Data */}
          <button 
            className={`inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white transition-colors ${
              realTimeUpdates 
                ? 'bg-green-600 hover:bg-green-700' 
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            <ArrowPathIcon className={`h-4 w-4 mr-2 ${realTimeUpdates ? 'animate-spin' : ''}`} />
            {realTimeUpdates ? 'Live Data' : 'Refresh Data'}
          </button>
        </div>
      }
    >
      <div className="space-y-6">
        <TabSystem 
          tabs={tabs} 
          activeTab={activeTab} 
          onTabChange={setActiveTab}
        >
          {renderTabContent()}
        </TabSystem>
      </div>

      {/* Modals */}
      <Modal 
        isOpen={showAddModal} 
        onClose={() => setShowAddModal(false)} 
        title="Add New Position"
        size="lg"
      >
        <div className="space-y-4">
          <p className="text-gray-600">Add a new position to your portfolio manually.</p>
          <DataNotAvailable 
            message="Position entry form coming soon" 
            suggestion="Complete form with symbol, shares, cost basis, and purchase date"
            showIcon={false}
          />
        </div>
      </Modal>

      <Modal 
        isOpen={showImportModal} 
        onClose={() => setShowImportModal(false)} 
        title="Import from Broker"
        size="lg"
      >
        <div className="space-y-4">
          <p className="text-gray-600">Import your holdings directly from your broker account.</p>
          <DataNotAvailable 
            message="Broker integration coming soon" 
            suggestion="Connect with popular brokers like Schwab, Fidelity, E*TRADE, and more"
            showIcon={false}
          />
        </div>
      </Modal>

      <Modal 
        isOpen={showAnalyticsModal} 
        onClose={() => setShowAnalyticsModal(false)} 
        title="Configure Analytics"
        size="lg"
      >
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Benchmark</label>
              <select 
                value={benchmark}
                onChange={(e) => setBenchmark(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="SPY">S&P 500 (SPY)</option>
                <option value="QQQ">NASDAQ 100 (QQQ)</option>
                <option value="VTI">Total Stock Market (VTI)</option>
                <option value="ACWI">All Country World (ACWI)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Time Frame</label>
              <select 
                value={selectedTimeframe}
                onChange={(e) => setSelectedTimeframe(e.target.value)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="1W">1 Week</option>
                <option value="1M">1 Month</option>
                <option value="3M">3 Months</option>
                <option value="6M">6 Months</option>
                <option value="1Y">1 Year</option>
                <option value="3Y">3 Years</option>
              </select>
            </div>
          </div>
          
          <div>
            <label className="flex items-center">
              <input 
                type="checkbox" 
                checked={realTimeData}
                onChange={(e) => setRealTimeData(e.target.checked)}
                className="mr-2"
              />
              <span className="text-sm text-gray-700">Enable real-time data updates</span>
            </label>
          </div>
          
          <div className="pt-4 border-t">
            <h4 className="font-medium text-gray-900 mb-3">Risk Preferences</h4>
            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-700 mb-1">Risk Tolerance</label>
                <input type="range" min="1" max="10" defaultValue="6" className="w-full" />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>Conservative</span>
                  <span>Aggressive</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Modal>
      
      <Modal 
        isOpen={showOptimizationModal} 
        onClose={() => setShowOptimizationModal(false)} 
        title="Portfolio Optimization Settings"
        size="xl"
      >
        <div className="space-y-6">
          <div className="grid grid-cols-3 gap-6">
            <div className="p-4 border border-gray-200 rounded-lg">
              <h4 className="font-medium mb-2">Conservative</h4>
              <p className="text-sm text-gray-600 mb-3">Focus on capital preservation</p>
              <div className="space-y-2 text-xs">
                <div>• Lower volatility</div>
                <div>• Higher bond allocation</div>
                <div>• Target Sharpe: 0.8+</div>
              </div>
            </div>
            <div className="p-4 border-2 border-blue-500 rounded-lg bg-blue-50">
              <h4 className="font-medium mb-2">Balanced</h4>
              <p className="text-sm text-gray-600 mb-3">Optimize risk-adjusted returns</p>
              <div className="space-y-2 text-xs">
                <div>• Moderate risk</div>
                <div>• Diversified allocation</div>
                <div>• Target Sharpe: 1.0+</div>
              </div>
            </div>
            <div className="p-4 border border-gray-200 rounded-lg">
              <h4 className="font-medium mb-2">Growth</h4>
              <p className="text-sm text-gray-600 mb-3">Maximize long-term growth</p>
              <div className="space-y-2 text-xs">
                <div>• Higher equity exposure</div>
                <div>• Growth-oriented</div>
                <div>• Target Return: 12%+</div>
              </div>
            </div>
          </div>
          
          <div className="flex justify-end space-x-3">
            <button 
              onClick={() => setShowOptimizationModal(false)}
              className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
              Run Optimization
            </button>
          </div>
        </div>
      </Modal>
      
      <Modal 
        isOpen={showScreenerModal} 
        onClose={() => setShowScreenerModal(false)} 
        title="Holdings Screener"
        size="lg"
      >
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Sector</label>
              <select className="w-full border border-gray-300 rounded-md px-3 py-2">
                <option value="all">All Sectors</option>
                <option value="technology">Technology</option>
                <option value="healthcare">Healthcare</option>
                <option value="financials">Financials</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Market Cap</label>
              <select className="w-full border border-gray-300 rounded-md px-3 py-2">
                <option value="all">All Sizes</option>
                <option value="large">Large Cap</option>
                <option value="mid">Mid Cap</option>
                <option value="small">Small Cap</option>
              </select>
            </div>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Performance Filter</label>
            <div className="flex space-x-4">
              <label className="flex items-center">
                <input type="radio" name="performance" value="all" className="mr-2" defaultChecked />
                All Holdings
              </label>
              <label className="flex items-center">
                <input type="radio" name="performance" value="winners" className="mr-2" />
                Winners Only
              </label>
              <label className="flex items-center">
                <input type="radio" name="performance" value="losers" className="mr-2" />
                Losers Only
              </label>
            </div>
          </div>
        </div>
      </Modal>

      {selectedHolding && (
        <Modal 
          isOpen={!!selectedHolding} 
          onClose={() => setSelectedHolding(null)} 
          title={`${selectedHolding.symbol} - Position Details`}
          size="xl"
        >
          <div className="space-y-6">
            <GridLayout cols={2} gap={6}>
              <div>
                <h4 className="font-medium text-gray-900 mb-4">Position Summary</h4>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Shares:</span>
                    <span className="font-medium">{selectedHolding.shares.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Current Price:</span>
                    <span className="font-medium">${selectedHolding.currentPrice}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Average Cost:</span>
                    <span className="font-medium">${selectedHolding.avgCost}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Total Value:</span>
                    <span className="font-medium">${selectedHolding.totalValue.toLocaleString()}</span>
                  </div>
                </div>
              </div>
              <div>
                <h4 className="font-medium text-gray-900 mb-4">Performance</h4>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Unrealized Gain/Loss:</span>
                    <span className={`font-medium ${selectedHolding.gain >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      ${selectedHolding.gain.toLocaleString()} ({selectedHolding.gainPercent}%)
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Day Change:</span>
                    <span className={`font-medium ${selectedHolding.dayChange >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      ${selectedHolding.dayChange} ({selectedHolding.dayChangePercent}%)
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Portfolio Allocation:</span>
                    <span className="font-medium">{selectedHolding.allocation}%</span>
                  </div>
                </div>
              </div>
            </GridLayout>
            <div className="pt-4 border-t">
              <DataNotAvailable 
                message="Detailed position analytics coming soon" 
                suggestion="Historical performance, technical indicators, and position-specific risk metrics"
                showIcon={false}
              />
            </div>
          </div>
        </Modal>
      )}
    </PageLayout>
  );
}

export default Portfolio;