/**
 * PortfolioEnhanced - Modern portfolio page with comprehensive error handling
 * TailwindCSS version without fallback components
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getPortfolioData } from '../services/api';
import { useApiErrorHandler } from '../error';

const fetchPortfolioData = async () => {
  try {
    const data = await getPortfolioData();
    
    // Transform API response to match expected format
    return {
      totalValue: data.totalValue || 0,
      dayChange: data.dayChange || 0,
      dayChangePercent: data.dayChangePercent || 0,
      holdings: data.holdings?.map(holding => ({
        symbol: holding.symbol,
        name: holding.name || holding.companyName || `${holding.symbol} Corp`,
        shares: holding.quantity || holding.shares || 0,
        currentPrice: holding.currentPrice || holding.price || 0,
        marketValue: holding.marketValue || (holding.currentPrice * holding.quantity) || 0,
        costBasis: holding.costBasis || (holding.averagePrice * holding.quantity) || 0,
        gainLoss: holding.gainLoss || holding.unrealizedGain || 0,
        gainLossPercent: holding.gainLossPercent || holding.unrealizedGainPercent || 0
      })) || []
    };
  } catch (error) {
    // Log actual error for debugging
    console.error('Portfolio API Error:', error);
    
    // Re-throw with user-friendly message
    if (error.message?.includes('API URL not configured')) {
      throw new Error('API configuration required - please check settings');
    } else if (error.response?.status === 401) {
      throw new Error('Authentication required - please log in');
    } else if (error.response?.status >= 500) {
      throw new Error('Portfolio service temporarily unavailable');
    } else {
      throw new Error(error.message || 'Failed to load portfolio data');
    }
  }
};

const LoadingSpinner = () => (
  <div className="flex items-center justify-center py-8">
    <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
    <span className="ml-3 text-gray-600">Loading portfolio...</span>
  </div>
);

const ErrorMessage = ({ error, onRetry }) => (
  <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
    <div className="text-red-500 text-4xl mb-4">⚠️</div>
    <h3 className="text-lg font-semibold text-red-800 mb-2">Error Loading Portfolio</h3>
    <p className="text-red-600 mb-4">{error.message}</p>
    <button
      onClick={onRetry}
      className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
    >
      Try Again
    </button>
  </div>
);

const PortfolioSummary = ({ portfolio }) => (
  <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-700 mb-2">Total Value</h3>
      <p className="text-3xl font-bold text-gray-900">
        ${portfolio.totalValue.toLocaleString()}
      </p>
      <div className={`flex items-center mt-2 ${portfolio.dayChange >= 0 ? 'text-green-600' : 'text-red-600'}`}>
        <span className="text-sm font-medium">
          {portfolio.dayChange >= 0 ? '+' : ''}${portfolio.dayChange.toLocaleString()} 
          ({portfolio.dayChange >= 0 ? '+' : ''}{portfolio.dayChangePercent}%)
        </span>
      </div>
    </div>

    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-700 mb-2">Holdings</h3>
      <p className="text-3xl font-bold text-gray-900">
        {portfolio.holdings.length}
      </p>
      <p className="text-sm text-gray-500 mt-2">
        Active positions
      </p>
    </div>

    <div className="bg-white border border-gray-200 rounded-lg p-6">
      <h3 className="text-lg font-semibold text-gray-700 mb-2">Performance</h3>
      <p className="text-3xl font-bold text-green-600">
        +12.8%
      </p>
      <p className="text-sm text-gray-500 mt-2">
        Since inception
      </p>
    </div>
  </div>
);

const HoldingsTable = ({ holdings }) => (
  <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
    <div className="px-6 py-4 border-b border-gray-200">
      <h3 className="text-lg font-semibold text-gray-900">Holdings</h3>
    </div>
    
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Symbol
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Shares
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Price
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Market Value
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Gain/Loss
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {holdings.map((holding) => (
            <tr key={holding.symbol} className="hover:bg-gray-50">
              <td className="px-6 py-4 whitespace-nowrap">
                <div>
                  <div className="text-sm font-medium text-gray-900">
                    {holding.symbol}
                  </div>
                  <div className="text-sm text-gray-500">
                    {holding.name}
                  </div>
                </div>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                {holding.shares}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                ${holding.currentPrice.toFixed(2)}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                ${holding.marketValue.toLocaleString()}
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span className={`text-sm font-medium ${
                  holding.gainLoss >= 0 ? 'text-green-600' : 'text-red-600'
                }`}>
                  {holding.gainLoss >= 0 ? '+' : ''}${holding.gainLoss.toLocaleString()}
                  ({holding.gainLoss >= 0 ? '+' : ''}{holding.gainLossPercent}%)
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

const PortfolioEnhanced = () => {
  const { isAuthenticated } = useAuth();
  const [portfolio, setPortfolio] = useState(null);
  
  // Use the enhanced error handler
  const { error, loading, execute, retry } = useApiErrorHandler({
    onSuccess: (data) => setPortfolio(data),
    onError: (error) => console.error('Portfolio load failed:', error)
  });

  const loadPortfolio = () => execute(fetchPortfolioData);

  useEffect(() => {
    if (isAuthenticated) {
      loadPortfolio();
    }
  }, [isAuthenticated]);

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white border border-gray-200 rounded-lg p-8 text-center max-w-md">
          <div className="text-4xl mb-4">🔒</div>
          <h2 className="text-xl font-semibold text-gray-700 mb-2">
            Authentication Required
          </h2>
          <p className="text-gray-500 mb-6">
            Please sign in to view your portfolio.
          </p>
          <button className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
            Sign In
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Portfolio</h1>
              <p className="text-gray-600 mt-2">
                Track your investments and performance
              </p>
            </div>
            
            <div className="flex items-center space-x-4">
              <button
                onClick={() => retry()}
                disabled={loading}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                {loading ? '⏳ Loading...' : '🔄 Refresh'}
              </button>
              <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                Add Holding
              </button>
            </div>
          </div>
        </div>

        {loading && <LoadingSpinner />}
        
        {error && <ErrorMessage error={error} onRetry={() => retry()} />}
        
        {portfolio && !loading && !error && (
          <div>
            <PortfolioSummary portfolio={portfolio} />
            <HoldingsTable holdings={portfolio.holdings} />
          </div>
        )}

        {/* Quick actions */}
        <div className="mt-8 bg-white border border-gray-200 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <button className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors text-left">
              <div className="text-lg mb-2">📊</div>
              <div className="font-medium">Performance Analysis</div>
              <div className="text-sm text-gray-500">View detailed performance metrics</div>
            </button>
            
            <button className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors text-left">
              <div className="text-lg mb-2">🎯</div>
              <div className="font-medium">Rebalance Portfolio</div>
              <div className="text-sm text-gray-500">Optimize your asset allocation</div>
            </button>
            
            <button className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors text-left">
              <div className="text-lg mb-2">📈</div>
              <div className="font-medium">Trade Suggestions</div>
              <div className="text-sm text-gray-500">Get AI-powered trade ideas</div>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PortfolioEnhanced;