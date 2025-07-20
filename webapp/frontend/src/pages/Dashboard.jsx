import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { 
  ChartBarIcon, 
  CurrencyDollarIcon, 
  ArrowTrendingUpIcon, 
  ArrowTrendingDownIcon,
  ExclamationTriangleIcon,
  ArrowUpIcon,
  ArrowDownIcon
} from '@heroicons/react/24/outline';
import { DataNotAvailable, LoadingFallback } from '../components/fallbacks/DataNotAvailable';
import { PageLayout, CardLayout, GridLayout } from '../components/ui/layout';

// Simple dashboard using only Tailwind CSS components
function Dashboard() {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({
    portfolio: { value: 0, change: 0, changePercent: 0 },
    market: { sp500: 0, nasdaq: 0, dow: 0 },
    watchlist: [],
    recentTrades: []
  });

  useEffect(() => {
    // Simulate data loading
    const timer = setTimeout(() => {
      setData({
        portfolio: { 
          value: 125420.50, 
          change: 2847.20, 
          changePercent: 2.32 
        },
        market: { 
          sp500: 4185.47, 
          nasdaq: 12987.22, 
          dow: 33875.12 
        },
        watchlist: [
          { symbol: 'AAPL', price: 175.43, change: 2.10 },
          { symbol: 'GOOGL', price: 2431.20, change: -15.80 },
          { symbol: 'MSFT', price: 295.37, change: 5.25 },
          { symbol: 'TSLA', price: 678.90, change: -12.45 }
        ],
        recentTrades: [
          { symbol: 'AAPL', type: 'BUY', shares: 100, price: 173.33, time: '2 hours ago' },
          { symbol: 'GOOGL', type: 'SELL', shares: 25, price: 2447.00, time: '1 day ago' }
        ]
      });
      setLoading(false);
    }, 1000);

    return () => clearTimeout(timer);
  }, []);

  if (loading) {
    return (
      <PageLayout title="Dashboard">
        <LoadingFallback message="Loading your dashboard..." />
      </PageLayout>
    );
  }

  const StatCard = ({ title, value, change, changePercent, icon: Icon, color = "blue" }) => {
    const isPositive = change >= 0;
    const colorClasses = {
      blue: 'bg-blue-500',
      green: 'bg-green-500',
      red: 'bg-red-500',
      yellow: 'bg-yellow-500'
    };

    return (
      <CardLayout className="overflow-hidden">
        <div className="p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-600 truncate">{title}</p>
              <p className="text-2xl font-semibold text-gray-900">{value}</p>
            </div>
            <div className={`p-3 rounded-md ${colorClasses[color]}`}>
              <Icon className="h-6 w-6 text-white" />
            </div>
          </div>
          {(change !== undefined && changePercent !== undefined) && (
            <div className="mt-4 flex items-center">
              {isPositive ? (
                <ArrowUpIcon className="h-4 w-4 text-green-500" />
              ) : (
                <ArrowDownIcon className="h-4 w-4 text-red-500" />
              )}
              <span className={`text-sm font-medium ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
                {Math.abs(changePercent)}% ({isPositive ? '+' : ''}${change.toLocaleString()})
              </span>
            </div>
          )}
        </div>
      </CardLayout>
    );
  };

  const QuickActionButton = ({ title, icon: Icon, onClick, color = "blue" }) => {
    const colorClasses = {
      blue: 'bg-blue-600 hover:bg-blue-700',
      green: 'bg-green-600 hover:bg-green-700',
      purple: 'bg-purple-600 hover:bg-purple-700'
    };

    return (
      <button
        onClick={onClick}
        className={`flex items-center justify-center w-full p-4 ${colorClasses[color]} text-white rounded-lg transition-colors duration-200`}
      >
        <Icon className="h-5 w-5 mr-2" />
        {title}
      </button>
    );
  };

  return (
    <PageLayout 
      title="Dashboard" 
      subtitle={isAuthenticated ? `Welcome back, ${user?.name || 'User'}` : "Welcome to Financial Platform"}
    >
      <div className="space-y-6">
        {/* Portfolio Overview */}
        <GridLayout cols={4} gap={6}>
          <StatCard
            title="Portfolio Value"
            value={`$${data.portfolio.value.toLocaleString()}`}
            change={data.portfolio.change}
            changePercent={data.portfolio.changePercent}
            icon={CurrencyDollarIcon}
            color="blue"
          />
          <StatCard
            title="S&P 500"
            value={data.market.sp500.toLocaleString()}
            icon={ChartBarIcon}
            color="green"
          />
          <StatCard
            title="NASDAQ"
            value={data.market.nasdaq.toLocaleString()}
            icon={ArrowTrendingUpIcon}
            color="purple"
          />
          <StatCard
            title="Dow Jones"
            value={data.market.dow.toLocaleString()}
            icon={ChartBarIcon}
            color="yellow"
          />
        </GridLayout>

        {/* Quick Actions */}
        <CardLayout title="Quick Actions">
          <GridLayout cols={3} gap={4}>
            <QuickActionButton
              title="View Portfolio"
              icon={CurrencyDollarIcon}
              onClick={() => navigate('/portfolio')}
              color="blue"
            />
            <QuickActionButton
              title="Live Market Data"
              icon={ChartBarIcon}
              onClick={() => navigate('/live-data')}
              color="green"
            />
            <QuickActionButton
              title="Trading Signals"
              icon={ArrowTrendingUpIcon}
              onClick={() => navigate('/trading')}
              color="purple"
            />
          </GridLayout>
        </CardLayout>

        <GridLayout cols={2} gap={6}>
          {/* Watchlist */}
          <CardLayout title="Watchlist" subtitle="Your tracked stocks">
            {data.watchlist.length > 0 ? (
              <div className="space-y-3">
                {data.watchlist.map((stock) => (
                  <div key={stock.symbol} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div>
                      <p className="font-medium text-gray-900">{stock.symbol}</p>
                      <p className="text-sm text-gray-500">${stock.price}</p>
                    </div>
                    <div className={`flex items-center ${stock.change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {stock.change >= 0 ? (
                        <ArrowTrendingUpIcon className="h-4 w-4 mr-1" />
                      ) : (
                        <ArrowTrendingDownIcon className="h-4 w-4 mr-1" />
                      )}
                      <span className="text-sm font-medium">
                        {stock.change >= 0 ? '+' : ''}{stock.change}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <DataNotAvailable 
                message="No stocks in watchlist" 
                suggestion="Add stocks to track their performance"
                type="table"
              />
            )}
          </CardLayout>

          {/* Recent Trades */}
          <CardLayout title="Recent Trades" subtitle="Your latest transactions">
            {data.recentTrades.length > 0 ? (
              <div className="space-y-3">
                {data.recentTrades.map((trade, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div>
                      <p className="font-medium text-gray-900">
                        {trade.type} {trade.shares} {trade.symbol}
                      </p>
                      <p className="text-sm text-gray-500">${trade.price} • {trade.time}</p>
                    </div>
                    <div className={`px-2 py-1 rounded text-xs font-medium ${
                      trade.type === 'BUY' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                    }`}>
                      {trade.type}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <DataNotAvailable 
                message="No recent trades" 
                suggestion="Start trading to see your transaction history"
                type="table"
              />
            )}
          </CardLayout>
        </GridLayout>

        {/* Market News placeholder */}
        <CardLayout title="Market News" subtitle="Latest financial news">
          <DataNotAvailable 
            message="News service temporarily unavailable" 
            suggestion="Please check back later for the latest market news"
            type="api"
          />
        </CardLayout>
      </div>
    </PageLayout>
  );
}

export default Dashboard;