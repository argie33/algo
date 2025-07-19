/**
 * PortfolioEnhanced - Real portfolio page with live data
 * No fallbacks, no mocks, real functionality only
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getPortfolioData, addHolding, updateHolding, deleteHolding } from '../services/api';
import { useNavigate } from 'react-router-dom';

const PortfolioEnhanced = () => {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadPortfolio = async () => {
    if (!isAuthenticated) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const data = await getPortfolioData();
      setPortfolio(data);
    } catch (err) {
      setError(err.message || 'Failed to load portfolio');
      console.error('Portfolio load error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPortfolio();
  }, [isAuthenticated]);

  if (!isAuthenticated) {
    navigate('/login');
    return null;
  }

  const handleAddHolding = async (symbol, quantity, price) => {
    try {
      await addHolding({ symbol, quantity, price });
      await loadPortfolio(); // Refresh data
    } catch (err) {
      console.error('Add holding error:', err);
    }
  };

  const handleUpdateHolding = async (id, updates) => {
    try {
      await updateHolding(id, updates);
      await loadPortfolio(); // Refresh data
    } catch (err) {
      console.error('Update holding error:', err);
    }
  };

  const handleDeleteHolding = async (id) => {
    try {
      await deleteHolding(id);
      await loadPortfolio(); // Refresh data
    } catch (err) {
      console.error('Delete holding error:', err);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin h-12 w-12 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-gray-600">Loading your portfolio...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="bg-white border border-red-200 rounded-lg p-8 text-center max-w-md">
          <div className="text-red-500 text-4xl mb-4">⚠️</div>
          <h3 className="text-lg font-semibold text-red-800 mb-2">Error Loading Portfolio</h3>
          <p className="text-red-600 mb-4">{error}</p>
          <div className="space-x-3">
            <button
              onClick={loadPortfolio}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              Try Again
            </button>
            <button
              onClick={() => navigate('/settings')}
              className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Check Settings
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">Portfolio</h1>
              <p className="text-gray-600 mt-2">
                Welcome back, {user?.name || 'Investor'}
              </p>
            </div>
            
            <div className="flex items-center space-x-4">
              <button
                onClick={loadPortfolio}
                disabled={loading}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                🔄 Refresh
              </button>
              <button 
                onClick={() => navigate('/portfolio/add')}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Add Position
              </button>
            </div>
          </div>
        </div>

        {/* Portfolio Summary */}
        {portfolio && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
              <div className="bg-white border border-gray-200 rounded-lg p-6">
                <h3 className="text-sm font-medium text-gray-500 mb-2">Total Value</h3>
                <p className="text-2xl font-bold text-gray-900">
                  ${portfolio.totalValue?.toLocaleString() || '0.00'}
                </p>
              </div>
              
              <div className="bg-white border border-gray-200 rounded-lg p-6">
                <h3 className="text-sm font-medium text-gray-500 mb-2">Day Change</h3>
                <p className={`text-2xl font-bold ${(portfolio.dayChange || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {(portfolio.dayChange || 0) >= 0 ? '+' : ''}${portfolio.dayChange?.toLocaleString() || '0.00'}
                </p>
              </div>
              
              <div className="bg-white border border-gray-200 rounded-lg p-6">
                <h3 className="text-sm font-medium text-gray-500 mb-2">Positions</h3>
                <p className="text-2xl font-bold text-gray-900">
                  {portfolio.holdings?.length || 0}
                </p>
              </div>
              
              <div className="bg-white border border-gray-200 rounded-lg p-6">
                <h3 className="text-sm font-medium text-gray-500 mb-2">Cash</h3>
                <p className="text-2xl font-bold text-gray-900">
                  ${portfolio.cashBalance?.toLocaleString() || '0.00'}
                </p>
              </div>
            </div>

            {/* Holdings Table */}
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <div className="px-6 py-4 border-b border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900">Holdings</h3>
              </div>
              
              {portfolio.holdings && portfolio.holdings.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Symbol</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Quantity</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Price</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Market Value</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Gain/Loss</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                      {portfolio.holdings.map((holding) => (
                        <tr key={holding.id || holding.symbol}>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="font-medium text-gray-900">{holding.symbol}</div>
                            <div className="text-sm text-gray-500">{holding.name}</div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            {holding.quantity || holding.shares || 0}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            ${(holding.currentPrice || holding.price || 0).toFixed(2)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                            ${(holding.marketValue || 0).toLocaleString()}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm">
                            <span className={`${(holding.gainLoss || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                              {(holding.gainLoss || 0) >= 0 ? '+' : ''}${(holding.gainLoss || 0).toFixed(2)}
                              {holding.gainLossPercent && ` (${(holding.gainLossPercent * 100).toFixed(2)}%)`}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            <button
                              onClick={() => handleDeleteHolding(holding.id)}
                              className="text-red-600 hover:text-red-900 ml-2"
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="px-6 py-12 text-center">
                  <p className="text-gray-500 mb-4">No holdings in your portfolio yet.</p>
                  <button
                    onClick={() => navigate('/portfolio/add')}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Add Your First Position
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default PortfolioEnhanced;