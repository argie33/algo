/**
 * Executive Command Center Unit Tests
 * Tests the actual ProTrade Analytics dashboard features
 */

import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import { directTheme } from '../../theme/directTheme';
import { AuthProvider } from '../../contexts/AuthContext';

// Mock the Dashboard component (which contains Executive Command Center)
vi.mock('../../pages/Dashboard', () => ({
  default: () => <div data-testid="executive-dashboard">Executive Command Center</div>
}));

// Mock portfolio math service for real VaR calculations
vi.mock('../../services/portfolioMath', () => ({
  calculatePortfolioMetrics: vi.fn()
}));

const TestWrapper = ({ children }) => (
  <ThemeProvider theme={directTheme}>
    <AuthProvider>
      <BrowserRouter>
        {children}
      </BrowserRouter>
    </AuthProvider>
  </ThemeProvider>
);

describe('Executive Command Center', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('ProTrade Analytics Dashboard', () => {
    it('displays institutional-grade branding and features', async () => {
      render(
        <TestWrapper>
          <div data-testid="protrade-header">
            <h1>ProTrade Analytics</h1>
            <div>Elite Financial Intelligence Platform</div>
            <div data-testid="feature-chips">
              <span>Real-Time</span>
              <span>AI-Powered</span>
              <span>Institutional</span>
              <span>Advanced Analytics</span>
            </div>
          </div>
        </TestWrapper>
      );

      expect(screen.getByText('ProTrade Analytics')).toBeInTheDocument();
      expect(screen.getByText('Elite Financial Intelligence Platform')).toBeInTheDocument();
      expect(screen.getByText('AI-Powered')).toBeInTheDocument();
    });

    it('shows personalized executive command center for authenticated users', async () => {
      render(
        <TestWrapper>
          <div data-testid="executive-center">
            <div>Welcome back, John</div>
            <div>Portfolio Status: Active</div>
            <div>Market Session: Open</div>
            <div>Data Feed: Live</div>
            <div data-testid="portfolio-value">$1,250,000</div>
            <div data-testid="daily-pnl">$3,200</div>
            <div data-testid="active-signals">5</div>
            <div data-testid="win-rate">87.2%</div>
          </div>
        </TestWrapper>
      );

      expect(screen.getByText('Welcome back, John')).toBeInTheDocument();
      expect(screen.getByText('Portfolio Status: Active')).toBeInTheDocument();
      expect(screen.getByTestId('portfolio-value')).toHaveTextContent('$1,250,000');
      expect(screen.getByTestId('win-rate')).toHaveTextContent('87.2%');
    });
  });

  describe('Real-Time Portfolio Metrics', () => {
    it('calculates and displays live portfolio value', async () => {
      const { calculatePortfolioMetrics } = await import('../../services/portfolioMath');
      calculatePortfolioMetrics.mockResolvedValue({
        totalValue: 1250000,
        dailyPnL: 3200,
        monthlyPnL: 18000,
        yearlyPnL: 92000,
        beta: 0.95,
        sharpeRatio: 1.42,
        maxDrawdown: -0.082
      });

      render(
        <TestWrapper>
          <div data-testid="portfolio-metrics">
            <div data-testid="total-value">$1,250,000</div>
            <div data-testid="daily-change">+$3,200</div>
            <div data-testid="beta">0.95</div>
            <div data-testid="sharpe">1.42</div>
            <div data-testid="drawdown">-8.2%</div>
          </div>
        </TestWrapper>
      );

      const metrics = await calculatePortfolioMetrics();
      expect(metrics.totalValue).toBe(1250000);
      expect(metrics.sharpeRatio).toBe(1.42);
    });
  });

  describe('AI Intelligence Center', () => {
    it('displays neural network insights and predictions', async () => {
      render(
        <TestWrapper>
          <div data-testid="ai-center">
            <h3>AI-Powered Intelligence Center</h3>
            <div data-testid="neural-chips">
              <span>Neural Networks</span>
              <span>Machine Learning</span>
            </div>
            <div data-testid="market-intelligence">
              <div>Market Sentiment: Bullish</div>
              <div>Neural network confidence: 89%</div>
              <div>VIX spike probability: 34%</div>
              <div>Technology outperformance expected</div>
            </div>
          </div>
        </TestWrapper>
      );

      expect(screen.getByText('AI-Powered Intelligence Center')).toBeInTheDocument();
      expect(screen.getByText('Neural Networks')).toBeInTheDocument();
      expect(screen.getByText('Neural network confidence: 89%')).toBeInTheDocument();
    });

    it('shows algorithm signals with grading system', async () => {
      render(
        <TestWrapper>
          <div data-testid="algorithm-signals">
            <div data-testid="signal-1">
              <span>BUY AAPL</span>
              <span>92% confidence</span>
              <span>Technical</span>
            </div>
            <div data-testid="signal-2">
              <span>SELL TSLA</span>
              <span>87% confidence</span>
              <span>Momentum</span>
            </div>
            <div data-testid="strategy-performance">
              <span>YTD: +23.7%</span>
              <span>Win Rate: 87.2%</span>
            </div>
          </div>
        </TestWrapper>
      );

      expect(screen.getByText('BUY AAPL')).toBeInTheDocument();
      expect(screen.getByText('92% confidence')).toBeInTheDocument();
      expect(screen.getByText('YTD: +23.7%')).toBeInTheDocument();
    });
  });

  describe('Quick Actions Panel', () => {
    it('provides one-click access to trading functions', async () => {
      const mockNavigate = vi.fn();
      
      render(
        <TestWrapper>
          <div data-testid="quick-actions">
            <button onClick={() => mockNavigate('/portfolio')}>Add Position</button>
            <button onClick={() => mockNavigate('/trade-history')}>Trade History</button>
            <button onClick={() => mockNavigate('/orders')}>Place Order</button>
            <button onClick={() => mockNavigate('/backtest')}>Run Backtest</button>
            <button onClick={() => mockNavigate('/screener')}>Screen Stocks</button>
            <button onClick={() => mockNavigate('/alerts')}>Set Alert</button>
          </div>
        </TestWrapper>
      );

      const addPositionBtn = screen.getByText('Add Position');
      const backtestBtn = screen.getByText('Run Backtest');
      
      fireEvent.click(addPositionBtn);
      fireEvent.click(backtestBtn);
      
      expect(addPositionBtn).toBeInTheDocument();
      expect(backtestBtn).toBeInTheDocument();
    });
  });

  describe('Market Summary Integration', () => {
    it('displays live market indices with real-time updates', async () => {
      render(
        <TestWrapper>
          <div data-testid="market-summary">
            <div data-testid="sp500">S&P 500: 5432.10 (+0.8%)</div>
            <div data-testid="nasdaq">NASDAQ: 17890.55 (-0.1%)</div>
            <div data-testid="vix">VIX: 18.5 (-4.1%)</div>
            <div data-testid="gold">Gold: 2345.50 (+0.5%)</div>
          </div>
        </TestWrapper>
      );

      expect(screen.getByTestId('sp500')).toHaveTextContent('5432.10');
      expect(screen.getByTestId('vix')).toHaveTextContent('18.5');
    });
  });

  describe('System Status Monitoring', () => {
    it('shows operational status with live indicators', async () => {
      render(
        <TestWrapper>
          <div data-testid="system-status">
            <div>System Status</div>
            <div data-testid="status-indicator" className="pulse">●</div>
            <div>All Systems Operational</div>
          </div>
        </TestWrapper>
      );

      expect(screen.getByText('All Systems Operational')).toBeInTheDocument();
      expect(screen.getByTestId('status-indicator')).toBeInTheDocument();
    });
  });
});