/**
 * PortfolioEnhancedIntegration - Portfolio page with full enhanced backend integration
 * Features: Real-time sync status, data source indicators, enhanced actions, performance tracking
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { getPortfolioData, addHolding, updateHolding, deleteHolding } from '../services/api';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Alert,
  Divider,
  Stack
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  AccountBalance,
  ShowChart
} from '@mui/icons-material';

// Import our new enhanced components
import PortfolioMetricsCard from '../components/portfolio/PortfolioMetricsCard';
import PortfolioSyncStatus from '../components/portfolio/PortfolioSyncStatus';
import PortfolioDataSource from '../components/portfolio/PortfolioDataSource';
import EnhancedPortfolioActions from '../components/portfolio/EnhancedPortfolioActions';
import { PortfolioPieChart } from '../components/charts/PortfolioPieChart';

const PortfolioEnhancedIntegration = () => {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  
  // Core portfolio state
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [dataSource, setDataSource] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  const loadPortfolio = useCallback(async (force = false) => {
    if (!isAuthenticated) return;
    
    setLoading(true);
    setError(null);
    
    try {
      // Call enhanced API with optional force parameter
      const response = await getPortfolioData(force ? 'paper&force=true' : 'paper');
      
      // Extract enhanced response data
      if (response.success) {
        setPortfolio(response.data);
        setDataSource({
          source: response.source,
          responseTime: response.responseTime,
          syncInfo: response.syncInfo,
          warning: response.warning,
          error: response.syncError,
          message: response.message
        });
      } else {
        setPortfolio(response);
        setDataSource(null);
      }
      
      setLastUpdate(new Date());
    } catch (err) {
      setError(err.message || 'Failed to load portfolio');
      console.error('Portfolio load error:', err);
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  const handleForceSync = useCallback((force = true) => {
    loadPortfolio(force);
  }, [loadPortfolio]);

  const handleSyncComplete = useCallback(() => {
    // Refresh portfolio data after sync completes
    loadPortfolio(false);
  }, [loadPortfolio]);

  const handleExport = () => {
    // Export portfolio data
    const dataStr = JSON.stringify(portfolio, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `portfolio-${new Date().toISOString().split('T')[0]}.json`;
    link.click();
  };

  const handleAnalyze = () => {
    navigate('/portfolio/performance');
  };

  const handleViewHistory = () => {
    navigate('/portfolio/performance');
  };

  useEffect(() => {
    loadPortfolio();
  }, [loadPortfolio]);

  if (!isAuthenticated) {
    navigate('/login');
    return null;
  }

  // Calculate portfolio metrics
  const portfolioMetrics = portfolio ? {
    totalValue: portfolio.holdings?.reduce((sum, h) => sum + (h.marketValue || 0), 0) || 0,
    totalGainLoss: portfolio.holdings?.reduce((sum, h) => sum + (h.gainLoss || 0), 0) || 0,
    positionCount: portfolio.holdings?.length || 0,
    cashBalance: portfolio.account?.cash || 0
  } : {};

  const gainLossPercent = portfolioMetrics.totalValue > 0 
    ? ((portfolioMetrics.totalGainLoss / (portfolioMetrics.totalValue - portfolioMetrics.totalGainLoss)) * 100).toFixed(2)
    : 0;

  // Prepare chart data
  const chartData = portfolio?.holdings?.map(holding => ({
    symbol: holding.symbol,
    value: holding.marketValue || 0,
    color: `hsl(${Math.random() * 360}, 70%, 50%)`
  })) || [];

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header with Enhanced Actions */}
      <Box display="flex" justifyContent="between" alignItems="center" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Portfolio Dashboard
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Welcome back, {user?.name || 'Investor'}
          </Typography>
        </Box>
        
        <EnhancedPortfolioActions
          onRefresh={() => loadPortfolio(false)}
          onForceSync={handleForceSync}
          onExport={handleExport}
          onAnalyze={handleAnalyze}
          onViewHistory={handleViewHistory}
          loading={loading}
          dataSource={dataSource}
          showDataSource={true}
        />
      </Box>

      {/* Sync Status Card */}
      <PortfolioSyncStatus 
        userId={user?.sub}
        onSyncComplete={handleSyncComplete}
      />

      {/* Data Source Information */}
      {dataSource && (
        <Box mb={3}>
          <PortfolioDataSource
            source={dataSource.source}
            responseTime={dataSource.responseTime}
            syncInfo={dataSource.syncInfo}
            warning={dataSource.warning}
            error={dataSource.error}
            compact={false}
          />
        </Box>
      )}

      {/* Error Display */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Portfolio Metrics Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} sm={6} md={3}>
          <PortfolioMetricsCard
            title="Total Value"
            value={`$${portfolioMetrics.totalValue.toLocaleString()}`}
            change={portfolioMetrics.totalGainLoss}
            changePercent={gainLossPercent}
            icon={AccountBalance}
            gradient="blue"
            trend={portfolioMetrics.totalGainLoss >= 0 ? 'up' : 'down'}
          />
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <PortfolioMetricsCard
            title="Day Change"
            value={`$${portfolioMetrics.totalGainLoss.toLocaleString()}`}
            changePercent={gainLossPercent}
            icon={portfolioMetrics.totalGainLoss >= 0 ? TrendingUp : TrendingDown}
            gradient={portfolioMetrics.totalGainLoss >= 0 ? 'green' : 'red'}
            trend={portfolioMetrics.totalGainLoss >= 0 ? 'up' : 'down'}
          />
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <PortfolioMetricsCard
            title="Positions"
            value={portfolioMetrics.positionCount}
            icon={ShowChart}
            gradient="purple"
            trend="neutral"
          />
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <PortfolioMetricsCard
            title="Cash Balance"
            value={`$${portfolioMetrics.cashBalance.toLocaleString()}`}
            icon={AccountBalance}
            gradient="orange"
            trend="neutral"
          />
        </Grid>
      </Grid>

      {/* Portfolio Content */}
      <Grid container spacing={3}>
        {/* Holdings Table */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Holdings
              </Typography>
              
              {portfolio?.holdings && portfolio.holdings.length > 0 ? (
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Symbol</TableCell>
                        <TableCell align="right">Quantity</TableCell>
                        <TableCell align="right">Price</TableCell>
                        <TableCell align="right">Market Value</TableCell>
                        <TableCell align="right">Gain/Loss</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {portfolio.holdings.map((holding) => (
                        <TableRow key={holding.symbol}>
                          <TableCell>
                            <Box>
                              <Typography variant="body2" fontWeight="medium">
                                {holding.symbol}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {holding.name || holding.company}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="right">
                            {holding.quantity || holding.shares || 0}
                          </TableCell>
                          <TableCell align="right">
                            ${(holding.currentPrice || holding.price || 0).toFixed(2)}
                          </TableCell>
                          <TableCell align="right">
                            ${(holding.marketValue || 0).toLocaleString()}
                          </TableCell>
                          <TableCell align="right">
                            <Typography
                              color={(holding.gainLoss || 0) >= 0 ? 'success.main' : 'error.main'}
                              fontWeight="medium"
                            >
                              {(holding.gainLoss || 0) >= 0 ? '+' : ''}
                              ${(holding.gainLoss || 0).toFixed(2)}
                              {holding.gainLossPercent && (
                                ` (${(holding.gainLossPercent * 100).toFixed(2)}%)`
                              )}
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Box textAlign="center" py={6}>
                  <Typography color="text.secondary">
                    No holdings in your portfolio yet.
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Portfolio Allocation Chart */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Portfolio Allocation
              </Typography>
              
              {chartData.length > 0 ? (
                <PortfolioPieChart 
                  data={chartData}
                  height={300}
                />
              ) : (
                <Box 
                  height={300} 
                  display="flex" 
                  alignItems="center" 
                  justifyContent="center"
                >
                  <Typography color="text.secondary">
                    No data to display
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Last Update Info */}
      {lastUpdate && (
        <Box mt={2} textAlign="center">
          <Typography variant="caption" color="text.secondary">
            Last updated: {lastUpdate.toLocaleString()}
          </Typography>
        </Box>
      )}
    </Container>
  );
};

export default PortfolioEnhancedIntegration;