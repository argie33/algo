import React, { useState, useMemo } from 'react';
import {
  MagnifyingGlassIcon,
  ArrowsUpDownIcon,
  EyeIcon,
  PencilIcon,
  TrashIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  AdjustmentsHorizontalIcon,
  FunnelIcon
} from '@heroicons/react/24/outline';

const HoldingsTable = ({ 
  holdings, 
  onRowClick, 
  onEdit, 
  onDelete, 
  onViewDetails,
  showActions = true,
  compact = false 
}) => {
  const [sortConfig, setSortConfig] = useState({ key: 'totalValue', direction: 'desc' });
  const [filterText, setFilterText] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState({
    sector: 'all',
    performance: 'all',
    minValue: '',
    maxValue: ''
  });

  const rowsPerPage = compact ? 5 : 10;

  // Advanced filtering
  const filteredHoldings = useMemo(() => {
    const safeHoldings = Array.isArray(holdings) ? holdings : [];
    let filtered = safeHoldings.filter(holding => {
      const matchesText = filterText === '' || 
        holding.symbol.toLowerCase().includes(filterText.toLowerCase()) ||
        holding.name.toLowerCase().includes(filterText.toLowerCase()) ||
        holding.sector.toLowerCase().includes(filterText.toLowerCase());

      const matchesSector = filters.sector === 'all' || holding.sector === filters.sector;
      
      const matchesPerformance = filters.performance === 'all' ||
        (filters.performance === 'winners' && holding.gainPercent > 0) ||
        (filters.performance === 'losers' && holding.gainPercent < 0);

      const matchesMinValue = filters.minValue === '' || holding.totalValue >= parseFloat(filters.minValue);
      const matchesMaxValue = filters.maxValue === '' || holding.totalValue <= parseFloat(filters.maxValue);

      return matchesText && matchesSector && matchesPerformance && matchesMinValue && matchesMaxValue;
    });

    return filtered;
  }, [holdings, filterText, filters]);

  // Sorting
  const sortedHoldings = useMemo(() => {
    if (!sortConfig.key) return filteredHoldings;
    
    return [...filteredHoldings].sort((a, b) => {
      const aVal = a[sortConfig.key];
      const bVal = b[sortConfig.key];
      
      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [filteredHoldings, sortConfig]);

  // Pagination
  const paginatedHoldings = useMemo(() => {
    const startIndex = (currentPage - 1) * rowsPerPage;
    return sortedHoldings.slice(startIndex, startIndex + rowsPerPage);
  }, [sortedHoldings, currentPage, rowsPerPage]);

  const totalPages = Math.ceil(sortedHoldings.length / rowsPerPage);

  const handleSort = (key) => {
    setSortConfig({
      key,
      direction: sortConfig.key === key && sortConfig.direction === 'asc' ? 'desc' : 'asc'
    });
  };

  const getSectorIcon = (sector) => {
    const icons = {
      'Technology': '💻',
      'Healthcare': '🏥',
      'Financials': '🏦',
      'Consumer Discretionary': '🛍️',
      'Energy': '⚡',
      'Industrials': '🏭',
      'Materials': '🧱',
      'Utilities': '💡',
      'Real Estate': '🏠',
      'Consumer Staples': '🛒',
      'Communication Services': '📡'
    };
    return icons[sector] || '📊';
  };

  const SortableHeader = ({ sortKey, children, className = "" }) => (
    <th 
      onClick={() => handleSort(sortKey)}
      className={`px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100 transition-colors ${className}`}
    >
      <div className="flex items-center space-x-1 group">
        <span>{children}</span>
        <div className="flex flex-col">
          <ChevronUpIcon className={`h-3 w-3 ${
            sortConfig.key === sortKey && sortConfig.direction === 'asc' 
              ? 'text-blue-600' 
              : 'text-gray-300 group-hover:text-gray-400'
          }`} />
          <ChevronDownIcon className={`h-3 w-3 -mt-1 ${
            sortConfig.key === sortKey && sortConfig.direction === 'desc' 
              ? 'text-blue-600' 
              : 'text-gray-300 group-hover:text-gray-400'
          }`} />
        </div>
      </div>
    </th>
  );

  return (
    <div className="space-y-4">
      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-4 sm:space-y-0">
        <div className="flex items-center space-x-4">
          <div className="relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search holdings..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              className="w-64 pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`inline-flex items-center px-3 py-2 border border-gray-300 rounded-lg text-sm font-medium transition-colors ${
              showFilters ? 'bg-blue-50 text-blue-700 border-blue-200' : 'text-gray-700 hover:bg-gray-50'
            }`}
          >
            <FunnelIcon className="h-4 w-4 mr-2" />
            Filters
            {Object.values(filters).some(f => f !== 'all' && f !== '') && (
              <span className="ml-2 bg-blue-100 text-blue-800 text-xs rounded-full px-2 py-1">
                Active
              </span>
            )}
          </button>
        </div>

        <div className="text-sm text-gray-500">
          Showing {paginatedHoldings.length} of {sortedHoldings.length} holdings
        </div>
      </div>

      {/* Advanced Filters Panel */}
      {showFilters && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Sector</label>
              <select
                value={filters.sector}
                onChange={(e) => setFilters(prev => ({ ...prev, sector: e.target.value }))}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="all">All Sectors</option>
                {Array.isArray(holdings) 
                  ? [...new Set(holdings.map(h => h.sector))].map(sector => (
                      <option key={sector} value={sector}>{sector}</option>
                    ))
                  : null
                }
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Performance</label>
              <select
                value={filters.performance}
                onChange={(e) => setFilters(prev => ({ ...prev, performance: e.target.value }))}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="all">All Holdings</option>
                <option value="winners">Winners (+)</option>
                <option value="losers">Losers (-)</option>
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Min Value</label>
              <input
                type="number"
                placeholder="$0"
                value={filters.minValue}
                onChange={(e) => setFilters(prev => ({ ...prev, minValue: e.target.value }))}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Max Value</label>
              <input
                type="number"
                placeholder="No limit"
                value={filters.maxValue}
                onChange={(e) => setFilters(prev => ({ ...prev, maxValue: e.target.value }))}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
          </div>
          
          <div className="flex justify-end mt-4">
            <button
              onClick={() => setFilters({ sector: 'all', performance: 'all', minValue: '', maxValue: '' })}
              className="text-sm text-gray-600 hover:text-gray-800"
            >
              Clear Filters
            </button>
          </div>
        </div>
      )}

      {/* Holdings Table */}
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <SortableHeader sortKey="symbol">Symbol</SortableHeader>
                <SortableHeader sortKey="shares">Shares</SortableHeader>
                <SortableHeader sortKey="currentPrice">Price</SortableHeader>
                <SortableHeader sortKey="totalValue">Market Value</SortableHeader>
                <SortableHeader sortKey="gainPercent">Gain/Loss</SortableHeader>
                <SortableHeader sortKey="dayChangePercent">Day Change</SortableHeader>
                <SortableHeader sortKey="allocation">Allocation</SortableHeader>
                {showActions && <th className="px-4 py-3 text-xs font-medium text-gray-500 uppercase">Actions</th>}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {paginatedHoldings.map((holding) => (
                <tr 
                  key={holding.id}
                  onClick={() => onRowClick?.(holding)}
                  className={`${onRowClick ? 'cursor-pointer hover:bg-blue-50' : ''} transition-colors group`}
                >
                  <td className="px-4 py-4 whitespace-nowrap">
                    <div className="flex items-center space-x-3">
                      <div className="text-lg">{getSectorIcon(holding.sector)}</div>
                      <div>
                        <div className="text-sm font-bold text-gray-900">{holding.symbol}</div>
                        <div className="text-xs text-gray-500 max-w-32 truncate">{holding.name}</div>
                      </div>
                    </div>
                  </td>
                  
                  <td className="px-4 py-4 whitespace-nowrap">
                    <span className="text-sm font-medium text-gray-900">
                      {holding.shares.toLocaleString()}
                    </span>
                  </td>
                  
                  <td className="px-4 py-4 whitespace-nowrap">
                    <div className="text-sm">
                      <div className="font-medium text-gray-900">${holding.currentPrice.toFixed(2)}</div>
                      <div className="text-xs text-gray-500">Avg: ${holding.avgCost.toFixed(2)}</div>
                    </div>
                  </td>
                  
                  <td className="px-4 py-4 whitespace-nowrap">
                    <div className="text-sm font-bold text-gray-900">
                      ${holding.totalValue.toLocaleString()}
                    </div>
                  </td>
                  
                  <td className="px-4 py-4 whitespace-nowrap">
                    <div className={`text-sm ${holding.gainPercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      <div className="font-bold">
                        {holding.gainPercent >= 0 ? '+' : ''}${holding.gain.toLocaleString()}
                      </div>
                      <div className="text-xs">
                        ({holding.gainPercent >= 0 ? '+' : ''}{holding.gainPercent.toFixed(2)}%)
                      </div>
                    </div>
                  </td>
                  
                  <td className="px-4 py-4 whitespace-nowrap">
                    <div className={`text-sm ${holding.dayChangePercent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      <div className="font-medium">
                        {holding.dayChangePercent >= 0 ? '+' : ''}${holding.dayChange.toFixed(2)}
                      </div>
                      <div className="text-xs">
                        ({holding.dayChangePercent >= 0 ? '+' : ''}{holding.dayChangePercent.toFixed(2)}%)
                      </div>
                    </div>
                  </td>
                  
                  <td className="px-4 py-4 whitespace-nowrap">
                    <div className="flex items-center space-x-2">
                      <div className="flex-1 bg-gray-200 rounded-full h-2 max-w-20">
                        <div 
                          className="bg-gradient-to-r from-blue-500 to-blue-600 h-2 rounded-full transition-all duration-500"
                          style={{ width: `${Math.min(holding.allocation, 100)}%` }}
                        />
                      </div>
                      <span className="text-xs font-medium text-gray-700 min-w-12">
                        {holding.allocation.toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  
                  {showActions && (
                    <td className="px-4 py-4 whitespace-nowrap">
                      <div className="flex items-center space-x-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button 
                          onClick={(e) => {
                            e.stopPropagation();
                            onViewDetails?.(holding);
                          }}
                          className="p-1 text-blue-600 hover:text-blue-900 hover:bg-blue-100 rounded"
                          title="View Details"
                        >
                          <EyeIcon className="h-4 w-4" />
                        </button>
                        <button 
                          onClick={(e) => {
                            e.stopPropagation();
                            onEdit?.(holding);
                          }}
                          className="p-1 text-green-600 hover:text-green-900 hover:bg-green-100 rounded"
                          title="Edit Position"
                        >
                          <PencilIcon className="h-4 w-4" />
                        </button>
                        <button 
                          onClick={(e) => {
                            e.stopPropagation();
                            onDelete?.(holding);
                          }}
                          className="p-1 text-red-600 hover:text-red-900 hover:bg-red-100 rounded"
                          title="Delete Position"
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="bg-white px-4 py-3 border-t border-gray-200 sm:px-6">
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-700">
                Showing {(currentPage - 1) * rowsPerPage + 1} to {Math.min(currentPage * rowsPerPage, sortedHoldings.length)} of {sortedHoldings.length} results
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                  disabled={currentPage === 1}
                  className="px-3 py-1 border border-gray-300 rounded-md text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
                >
                  Previous
                </button>
                
                <div className="flex space-x-1">
                  {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                    let pageNum;
                    if (totalPages <= 5) {
                      pageNum = i + 1;
                    } else if (currentPage <= 3) {
                      pageNum = i + 1;
                    } else if (currentPage >= totalPages - 2) {
                      pageNum = totalPages - 4 + i;
                    } else {
                      pageNum = currentPage - 2 + i;
                    }
                    
                    return (
                      <button
                        key={pageNum}
                        onClick={() => setCurrentPage(pageNum)}
                        className={`px-3 py-1 border rounded-md text-sm ${
                          currentPage === pageNum
                            ? 'bg-blue-600 text-white border-blue-600'
                            : 'border-gray-300 hover:bg-gray-50'
                        }`}
                      >
                        {pageNum}
                      </button>
                    );
                  })}
                </div>
                
                <button
                  onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 border border-gray-300 rounded-md text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-50"
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default HoldingsTable;