import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { createComponentLogger } from '../utils/errorLogger'
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TextField,
  Button,
  Chip,
  CircularProgress,
  Alert,
  Divider,
  ToggleButton,
  ToggleButtonGroup,
  Autocomplete
} from '@mui/material'
import {
  AccountBalance,
  Analytics,
  Timeline,
  TrendingUp,
  TrendingDown,
  HorizontalRule,
  Search,
  BusinessCenter,
  ShowChart
} from '@mui/icons-material'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar
} from 'recharts'

// Use centralized error logging (logger will be defined in component)

import {
  getBalanceSheet,
  getIncomeStatement,
  getCashFlowStatement,
  getFinancialStatements,
  getKeyMetrics,
  getTickerEarningsEstimates,
  getTickerRevenueEstimates,
  getTickerEarningsHistory,
  getTickerEpsRevisions,
  getTickerEpsTrend,
  getTickerGrowthEstimates,
  getStocks
} from '../services/api'
import { formatCurrency, formatPercentage, formatNumber } from '../utils/formatters'

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`financial-tabpanel-${index}`}
      aria-labelledby={`financial-tab-${index}`}
      {...other}
    >
      {value === index && (
        <div  sx={{ py: 3 }}>
          {children}
        </div>
      )}
    </div>
  )
}

function FinancialData() {
  console.log('🚀 FinancialData: Component rendering...');
  
  const logger = createComponentLogger('FinancialData');
  
  const [ticker, setTicker] = useState('AAPL')
  const [searchTicker, setSearchTicker] = useState('AAPL')
  const [tabValue, setTabValue] = useState(0)
  const [period, setPeriod] = useState('annual')

  // Get list of companies for dropdown
  const { data: companiesData } = useQuery({
    queryKey: ['companies'],
    queryFn: () => getStocks({ limit: 1000, sortBy: 'ticker' }),
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => console.log('✅ FinancialData: Companies data loaded:', data),
    onError: (error) => console.error('❌ FinancialData: Companies data error:', error)
  });

  const companies = companiesData?.data?.data ?? companiesData?.data ?? companiesData ?? [];
  console.log('📊 FinancialData: Companies data:', { 
    hasData: !!companiesData, 
    companiesLength: companies.length,
    sampleCompany: companies[0] 
  });

  // Defensive: ensure companies is always an array before using .find
  const safeCompanies = Array.isArray(companies) ? companies : [];

  const handleTabChange = (event, newValue) => {
    console.log('🔄 FinancialData: Tab changed to:', newValue);
    setTabValue(newValue)
  }

  const handleSearch = () => {
    if (searchTicker.trim()) {
      console.log('🔍 FinancialData: Searching for ticker:', searchTicker.trim().toUpperCase());
      setTicker(searchTicker.trim().toUpperCase())
    }
  }

  const handlePeriodChange = (event, newPeriod) => {
    if (newPeriod !== null) {
      console.log('📅 FinancialData: Period changed to:', newPeriod);
      setPeriod(newPeriod)
    }
  }
  
  // Comprehensive financial data queries
  const { data: balanceSheet, isLoading: balanceSheetLoading, error: balanceSheetError } = useQuery({
    queryKey: ['balanceSheet', ticker, period],
    queryFn: () => getBalanceSheet(ticker, period),
    enabled: !!ticker && tabValue === 0,
    onSuccess: (data) => console.log('✅ FinancialData: Balance sheet loaded:', data),
    onError: (error) => {
      console.error('❌ FinancialData: Balance sheet error:', error);
      logger.queryError('balanceSheet', error, { ticker, period });
    }
  })

  const { data: incomeStatement, isLoading: incomeStatementLoading, error: incomeStatementError } = useQuery({
    queryKey: ['incomeStatement', ticker, period],
    queryFn: () => getIncomeStatement(ticker, period),
    enabled: !!ticker && tabValue === 1,
    onSuccess: (data) => console.log('✅ FinancialData: Income statement loaded:', data),
    onError: (error) => {
      console.error('❌ FinancialData: Income statement error:', error);
      logger.queryError('incomeStatement', error, { ticker, period });
    }
  })
  
  const { data: cashFlowStatement, isLoading: cashFlowLoading, error: cashFlowError } = useQuery({
    queryKey: ['cashFlowStatement', ticker, period],
    queryFn: () => getCashFlowStatement(ticker, period),
    enabled: !!ticker && tabValue === 2,
    onSuccess: (data) => console.log('✅ FinancialData: Cash flow statement loaded:', data),
    onError: (error) => {
      console.error('❌ FinancialData: Cash flow statement error:', error);
      logger.queryError('cashFlowStatement', error, { ticker, period });
    }
  })

  console.log('📊 FinancialData: Data summary:', {
    ticker,
    period,
    tabValue,
    balanceSheet: { hasData: !!balanceSheet, isLoading: balanceSheetLoading, hasError: !!balanceSheetError },
    incomeStatement: { hasData: !!incomeStatement, isLoading: incomeStatementLoading, hasError: !!incomeStatementError },
    cashFlowStatement: { hasData: !!cashFlowStatement, isLoading: cashFlowLoading, hasError: !!cashFlowError }
  });

  const { data: keyMetrics, isLoading: keyMetricsLoading, error: keyMetricsError } = useQuery({
    queryKey: ['keyMetrics', ticker],
    queryFn: () => getKeyMetrics(ticker),
    enabled: !!ticker && tabValue === 3,
    onError: (error) => logger.queryError('keyMetrics', error, { ticker })
  })
  const renderKeyMetrics = (data) => {
    // Handle error response
    if (data?.error) {
      return (
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
              <ShowChart />
              <div  sx={{ ml: 1 }}>Key Metrics</div>
            </div>
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Error loading key metrics: {data.error}</div>
          </div>
        </div>
      )
    }
    
    // Access data from the { data: {...} } structure returned by API
    const metricsData = data?.data || data
    
    if (!metricsData) {
      return (
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
              <ShowChart />
              <div  sx={{ ml: 1 }}>Key Metrics</div>
            </div>
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">No key metrics data available for {ticker}</div>
          </div>
        </div>
      )
    }

    // The API returns organized categories, render each category as a separate card
    return (
      <div>
        <div  variant="h5" gutterBottom sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
          <ShowChart />
          <div  sx={{ ml: 1 }}>Key Metrics - {ticker}</div>
        </div>
        
        <div className="grid" container spacing={3}>
          {Object.entries(metricsData).map(([categoryKey, category]) => (
            <div className="grid" item xs={12} md={6} lg={4} key={categoryKey}>
              <div className="bg-white shadow-md rounded-lg">
                <div className="bg-white shadow-md rounded-lg"Content>
                  <div  variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
                    {/* We can add icons based on category later */}
                    <div  sx={{ ml: 0 }}>{category.title}</div>
                  </div>
                  <hr className="border-gray-200" sx={{ mb: 2 }} />
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                        {Object.entries(category.metrics).map(([metricName, value]) => (
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={metricName}>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row" sx={{ py: 1, fontSize: '0.875rem' }}>
                              {metricName}
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ py: 1, fontSize: '0.875rem', fontWeight: 'medium' }}>
                              {value !== null && value !== undefined ? (
                                typeof value === 'number' ? (
                                  metricName.includes('%') || metricName.includes('Margin') || 
                                  metricName.includes('Growth') || metricName.includes('Yield') || 
                                  metricName.includes('Return') ? 
                                    formatPercentage(value) :
                                  metricName.includes('$') || metricName.includes('Revenue') || 
                                  metricName.includes('Income') || metricName.includes('Cash') || 
                                  metricName.includes('Value') || metricName.includes('Debt') ? 
                                    formatCurrency(value) :
                                    formatNumber(value)
                                ) : value
                              ) : 'N/A'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }
  const renderFinancialTable = (data, title, icon) => {
    // Handle error response
    if (data?.error) {
      return (
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
              {icon}
              <div  sx={{ ml: 1 }}>{title}</div>
            </div>
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Error loading {title.toLowerCase()}: {data.error}</div>
          </div>
        </div>
      )
    }
    
    // Access data from the { data: [...] } structure returned by API
    let actualData = data?.data || data;
    
    // If the data is wrapped in a 'success' or 'metadata' object, unwrap it
    if (actualData && typeof actualData === 'object' && !Array.isArray(actualData)) {
      if ('data' in actualData) actualData = actualData.data;
    }
    if (!actualData || !Array.isArray(actualData) || actualData.length === 0) {
      return (
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
              {icon}
              <div  sx={{ ml: 1 }}>{title}</div>
            </div>
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">No {title.toLowerCase()} data available for {ticker}</div>
          </div>
        </div>
      )
    }

    // Handle the new normalized table structure (symbol, date, item_name, value)
    const isNormalizedStructure = actualData.length > 0 && actualData[0].item_name !== undefined;
    
    if (isNormalizedStructure) {
      // Group by date for the new structure
      const groupedByDate = {};
      actualData.forEach(item => {
        if (!groupedByDate[item.date]) {
          groupedByDate[item.date] = [];
        }
        groupedByDate[item.date].push(item);
      });

      const periods = Object.entries(groupedByDate).map(([date, items]) => ({
        date,
        items: items.reduce((acc, item) => {
          acc[item.item_name] = item.value;
          return acc;
        }, {})
      }));

      return (
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
              {icon}
              <div  sx={{ ml: 1 }}>{title} - {ticker}</div>
            </div>
            <hr className="border-gray-200" sx={{ mb: 2 }} />
            <div className="grid" container spacing={3}>
              {periods.slice(0, 5).map((period, index) => (
                <div className="grid" item xs={12} md={6} lg={4} key={period.date || index}>
                  <div className="bg-white shadow-md rounded-lg" variant="outlined">
                    <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 2 }}>
                      <div  variant="subtitle1" sx={{ fontWeight: 'bold', mb: 2 }}>
                        {period.date ? new Date(period.date).getFullYear() : 'N/A'}
                      </div>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                            {period.items && Object.entries(period.items)
                              .slice(0, 10)
                              .map(([key, value]) => (
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={key}>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell sx={{ py: 0.5, fontSize: '0.875rem', border: 'none' }}>
                                    {key.replace(/([A-Z])/g, ' $1').trim()}
                                  </td>
                                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ py: 0.5, fontSize: '0.875rem', fontWeight: 'bold', border: 'none' }}>
                                    {value || value === 0 ? formatCurrency(value, 0) : 'N/A'}
                                  </td>
                                </tr>
                              ))}
                            {!period.items && (
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell colSpan={2} sx={{ py: 1, fontSize: '0.875rem', border: 'none', textAlign: 'center', color: 'text.secondary' }}>
                                  No financial data available for this period
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {/* Trend Chart */}
            <div  sx={{ mt: 4 }}>
              <div  variant="h6" gutterBottom>Trend Analysis</div>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={
                  periods.slice(0, 5).reverse().map(period => {
                    const items = period.items
                    const firstItem = items && Object.keys(items).length > 0 ? Object.entries(items)[0] : null
                    return {
                      year: period.date ? new Date(period.date).getFullYear() : 'N/A',
                      value: firstItem ? firstItem[1] : 0,
                      name: firstItem ? firstItem[0] : 'N/A'
                    }
                  })
                }>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="year" />
                  <YAxis tickFormatter={(value) => formatCurrency(value, 0)} />
                  <div  
                    formatter={(value, name) => [formatCurrency(value, 0), 'Value']}
                    labelFormatter={(year) => `Year: ${year}`}
                  />
                  <Line type="monotone" dataKey="value" stroke="#1976d2" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )
    }

    // Handle the old structure (periods with items)
    return (
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
            {icon}
            <div  sx={{ ml: 1 }}>{title} - {ticker}</div>
          </div>
          <hr className="border-gray-200" sx={{ mb: 2 }} />
          <div className="grid" container spacing={3}>
            {actualData.slice(0, 5).map((period, index) => (
              <div className="grid" item xs={12} md={6} lg={4} key={period.date || index}>
                <div className="bg-white shadow-md rounded-lg" variant="outlined">
                  <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 2 }}>
                    <div  variant="subtitle1" sx={{ fontWeight: 'bold', mb: 2 }}>
                      {period.date ? new Date(period.date).getFullYear() : 'N/A'}
                    </div>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          {period.items && Object.entries(period.items)
                            .slice(0, 10)
                            .map(([key, value]) => (
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={key}>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell sx={{ py: 0.5, fontSize: '0.875rem', border: 'none' }}>
                                  {key.replace(/([A-Z])/g, ' $1').trim()}
                                </td>
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ py: 0.5, fontSize: '0.875rem', fontWeight: 'bold', border: 'none' }}>
                                  {value || value === 0 ? formatCurrency(value, 0) : 'N/A'}
                                </td>
                              </tr>
                            ))}
                          {!period.items && (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell colSpan={2} sx={{ py: 1, fontSize: '0.875rem', border: 'none', textAlign: 'center', color: 'text.secondary' }}>
                                No financial data available for this period
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
          {/* Trend Chart */}
          <div  sx={{ mt: 4 }}>
            <div  variant="h6" gutterBottom>Trend Analysis</div>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={
                actualData.slice(0, 5).reverse().map(period => {
                  const items = period.items
                  const firstItem = items && Object.keys(items).length > 0 ? Object.entries(items)[0] : null
                  return {
                    year: period.date ? new Date(period.date).getFullYear() : 'N/A',
                    value: firstItem ? firstItem[1] : 0,
                    name: firstItem ? firstItem[0] : 'N/A'
                  }
                })
              }>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="year" />
                <YAxis tickFormatter={(value) => formatCurrency(value, 0)} />
                <div  
                  formatter={(value, name) => [formatCurrency(value, 0), 'Value']}
                  labelFormatter={(year) => `Year: ${year}`}
                />
                <Line type="monotone" dataKey="value" stroke="#1976d2" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    )
  }
  return (
    <div className="container mx-auto" maxWidth="xl">
      <div  sx={{ py: 3 }}>
        {/* Enhanced Header */}
        <div  sx={{ mb: 4 }}>
          <div  variant="h3" component="h1" gutterBottom sx={{ fontWeight: 700, color: 'primary.main' }}>
            📊 Financial Data Analysis
          </div>
          <div  variant="subtitle1" color="text.secondary" sx={{ mb: 3 }}>
            Comprehensive financial statements, earnings data, and institutional-grade fundamental analysis
          </div>
        </div>
        
        {/* Search Section */}
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div className="grid" container spacing={2} alignItems="center">
                <div className="grid" item xs={12} md={4}>
                <Autocomplete
                  options={safeCompanies}
                  getOptionLabel={(option) => `${option.ticker} - ${option.short_name || option.ticker}`}
                  value={safeCompanies.find(c => c.ticker === ticker) || null}
                  onChange={(event, newValue) => {
                    if (newValue) {
                      setTicker(newValue.ticker);
                    }
                  }}
                  renderInput={(params) => (
                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      {...params}
                      label="Select Company"
                      placeholder="Search companies..."
                      InputProps={{
                        ...params.InputProps,
                        startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />
                      }}
                    />
                  )}
                  renderOption={(props, option) => (
                    <div  component="li" {...props}>
                      <div>
                        <div  variant="body2" sx={{ fontWeight: 'bold' }}>
                          {option.ticker}
                        </div>
                        <div  variant="caption" color="text.secondary">
                          {option.short_name}
                        </div>
                      </div>
                    </div>
                  )}
                />
              </div>
              <div className="grid" item xs={12} md={4}>
                <ToggleButtonGroup
                  value={period}
                  exclusive
                  onChange={handlePeriodChange}
                  size="small"
                >
                  <ToggleButton value="annual">Annual</ToggleButton>
                  <ToggleButton value="quarterly">Quarterly</ToggleButton>
                  <ToggleButton value="ttm">TTM</ToggleButton>                </ToggleButtonGroup>
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}        <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
          <div className="border-b border-gray-200" value={tabValue} onChange={handleTabChange}>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Balance Sheet" icon={<AccountBalance />} />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Income Statement" icon={<Analytics />} />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Cash Flow" icon={<Timeline />} />
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Key Metrics" icon={<ShowChart />} />
          </div>
        </div>

        {/* Tab Panels */}
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={0}>
          {balanceSheetLoading ? (
            <div  display="flex" justifyContent="center" p={4}>
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
            </div>
          ) : balanceSheetError ? (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Failed to load balance sheet: {balanceSheetError.message}</div>
          ) : (
            renderFinancialTable(balanceSheet, 'Balance Sheet', <AccountBalance />)
          )}
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={1}>
          {incomeStatementLoading ? (
            <div  display="flex" justifyContent="center" p={4}>
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
            </div>
          ) : incomeStatementError ? (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Failed to load income statement: {incomeStatementError.message}</div>
          ) : (
            renderFinancialTable(incomeStatement, 'Income Statement', <Analytics />)
          )}
        </div>

        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={2}>
          {cashFlowLoading ? (
            <div  display="flex" justifyContent="center" p={4}>
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
            </div>
          ) : cashFlowError ? (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Failed to load cash flow: {cashFlowError.message}</div>          ) : (
            renderFinancialTable(cashFlowStatement, 'Cash Flow Statement', <Timeline />)
          )}
        </div>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={3}>
          {keyMetricsLoading ? (
            <div  display="flex" justifyContent="center" p={4}>
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
            </div>
          ) : keyMetricsError ? (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Failed to load key metrics: {keyMetricsError.message}</div>
          ) : (
            renderKeyMetrics(keyMetrics)
          )}
        </div>
      </div>
    </div>
  )
}

export default FinancialData
