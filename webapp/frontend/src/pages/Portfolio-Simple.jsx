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
  ExclamationTriangleIcon
} from '@heroicons/react/24/outline';
import { PageLayout, CardLayout, GridLayout } from '../components/ui/layout';
import { DataNotAvailable, LoadingFallback } from '../components/fallbacks/DataNotAvailable';
import RequiresApiKeys from '../components/RequiresApiKeys';

function Portfolio() {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('holdings');
  const [portfolio, setPortfolio] = useState({
    totalValue: 0,
    totalGain: 0,
    totalGainPercent: 0,
    holdings: [],
    performance: {}
  });

  useEffect(() => {
    // Simulate data loading
    const timer = setTimeout(() => {
      setPortfolio({
        totalValue: 125420.50,
        totalGain: 8247.25,
        totalGainPercent: 7.02,
        holdings: [
          {
            symbol: 'AAPL',
            shares: 100,
            currentPrice: 175.43,
            avgCost: 145.20,
            totalValue: 17543.00,
            gain: 3023.00,
            gainPercent: 20.82
          },
          {
            symbol: 'GOOGL', 
            shares: 25,
            currentPrice: 2431.20,
            avgCost: 2280.50,
            totalValue: 60780.00,
            gain: 3767.50,
            gainPercent: 6.61
          },
          {
            symbol: 'MSFT',
            shares: 150,
            currentPrice: 295.37,
            avgCost: 268.90,
            totalValue: 44305.50,
            gain: 3970.50,
            gainPercent: 9.84
          }
        ],
        performance: {
          dayChange: 547.82,
          dayChangePercent: 0.44
        }
      });
      setLoading(false);
    }, 1000);

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

  const PortfolioSummary = () => (
    <GridLayout cols={4} gap={6}>
      <CardLayout>
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Total Value</p>
              <p className="text-2xl font-bold text-gray-900">
                ${portfolio.totalValue.toLocaleString()}
              </p>
            </div>
            <CurrencyDollarIcon className="h-8 w-8 text-blue-500" />
          </div>
        </div>
      </CardLayout>

      <CardLayout>
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Total Gain/Loss</p>
              <p className={`text-2xl font-bold ${portfolio.totalGain >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {portfolio.totalGain >= 0 ? '+' : ''}${portfolio.totalGain.toLocaleString()}
              </p>
            </div>
            {portfolio.totalGain >= 0 ? (
              <ArrowTrendingUpIcon className="h-8 w-8 text-green-500" />
            ) : (
              <ArrowTrendingDownIcon className="h-8 w-8 text-red-500" />
            )}
          </div>
        </div>
      </CardLayout>

      <CardLayout>
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Total Return</p>
              <p className={`text-2xl font-bold ${portfolio.totalGainPercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {portfolio.totalGainPercent >= 0 ? '+' : ''}{portfolio.totalGainPercent}%
              </p>
            </div>
            <ChartBarIcon className="h-8 w-8 text-blue-500" />
          </div>
        </div>
      </CardLayout>

      <CardLayout>
        <div className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600">Day Change</p>
              <p className={`text-2xl font-bold ${portfolio.performance.dayChange >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {portfolio.performance.dayChange >= 0 ? '+' : ''}${portfolio.performance.dayChange.toLocaleString()}
              </p>
            </div>
            {portfolio.performance.dayChange >= 0 ? (
              <ArrowTrendingUpIcon className="h-8 w-8 text-green-500" />
            ) : (
              <ArrowTrendingDownIcon className="h-8 w-8 text-red-500" />
            )}
          </div>
        </div>
      </CardLayout>
    </GridLayout>
  );

  const HoldingsTable = () => (
    <CardLayout title="Holdings" subtitle="Your current positions">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Symbol</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Shares</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Current Price</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Avg Cost</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Total Value</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Gain/Loss</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {portfolio.holdings.map((holding) => (
              <tr key={holding.symbol} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm font-medium text-gray-900">{holding.symbol}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm text-gray-900">{holding.shares}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm text-gray-900">${holding.currentPrice}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm text-gray-900">${holding.avgCost}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="text-sm font-medium text-gray-900">${holding.totalValue.toLocaleString()}</div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className={`text-sm font-medium ${holding.gain >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {holding.gain >= 0 ? '+' : ''}${holding.gain.toLocaleString()} ({holding.gainPercent}%)
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  <div className="flex space-x-2">
                    <button className="text-blue-600 hover:text-blue-900">
                      <PencilIcon className="h-4 w-4" />
                    </button>
                    <button className="text-red-600 hover:text-red-900">
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </CardLayout>
  );

  const TabNavigation = () => (
    <div className="border-b border-gray-200">
      <nav className="-mb-px flex space-x-8">
        {[
          { id: 'holdings', label: 'Holdings' },
          { id: 'performance', label: 'Performance' },
          { id: 'allocation', label: 'Allocation' },
          { id: 'analysis', label: 'Analysis' }
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === tab.id
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 'holdings':
        return <HoldingsTable />;
      case 'performance':
        return (
          <CardLayout title="Performance Analysis">
            <DataNotAvailable 
              message="Performance charts coming soon" 
              suggestion="Check back for detailed performance analytics and charts"
              type="chart"
            />
          </CardLayout>
        );
      case 'allocation':
        return (
          <CardLayout title="Portfolio Allocation">
            <DataNotAvailable 
              message="Allocation analysis coming soon" 
              suggestion="Portfolio allocation charts and sector breakdown will be available here"
              type="chart"
            />
          </CardLayout>
        );
      case 'analysis':
        return (
          <CardLayout title="Portfolio Analysis">
            <DataNotAvailable 
              message="Advanced analysis coming soon" 
              suggestion="Risk metrics, factor analysis, and optimization tools will be available here"
              type="chart"
            />
          </CardLayout>
        );
      default:
        return <HoldingsTable />;
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