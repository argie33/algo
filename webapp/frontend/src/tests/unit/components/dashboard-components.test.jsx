/**
 * Dashboard Components Unit Tests
 * Comprehensive testing of all real dashboard components
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Real Dashboard Components - Import actual production components
import { DashboardLayout } from '../../../components/dashboard/DashboardLayout';
import { DashboardHeader } from '../../../components/dashboard/DashboardHeader';
import { WidgetContainer } from '../../../components/dashboard/WidgetContainer';
import { MetricsOverview } from '../../../components/dashboard/MetricsOverview';

describe('📱 Dashboard Components', () => {
  const mockUser = {
    id: 'user_123',
    firstName: 'John',
    lastName: 'Doe',
    email: 'john@example.com'
  };

  const mockDashboardData = {
    portfolioValue: 125000,
    dayChange: 2500,
    dayChangePercent: 2.04,
    marketStatus: 'open',
    alertCount: 3
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('DashboardLayout Component', () => {
    it('should render dashboard layout correctly', () => {
      render(
        <DashboardLayout user={mockUser}>
          <div>Dashboard Content</div>
        </DashboardLayout>
      );

      expect(screen.getByTestId('dashboard-layout')).toBeInTheDocument();
      expect(screen.getByText('Dashboard Content')).toBeInTheDocument();
    });

    it('should handle theme switching', async () => {
      const user = userEvent.setup();
      const onThemeChange = vi.fn();

      render(
        <DashboardLayout 
          user={mockUser} 
          onThemeChange={onThemeChange}
        >
          <div>Content</div>
        </DashboardLayout>
      );

      const themeToggle = screen.getByRole('button', { name: /theme/i });
      await user.click(themeToggle);

      expect(onThemeChange).toHaveBeenCalledWith('dark');
    });
  });

  describe('DashboardHeader Component', () => {
    it('should render header with user info', () => {
      render(<DashboardHeader user={mockUser} data={mockDashboardData} />);

      expect(screen.getByText('Welcome back, John')).toBeInTheDocument();
      expect(screen.getByText('$125,000')).toBeInTheDocument();
      expect(screen.getByText('+$2,500')).toBeInTheDocument();
    });

    it('should show market status indicator', () => {
      render(<DashboardHeader user={mockUser} data={mockDashboardData} />);

      const marketStatus = screen.getByTestId('market-status');
      expect(marketStatus).toHaveClass('open');
      expect(screen.getByText('Market Open')).toBeInTheDocument();
    });

    it('should display notification badge', () => {
      render(<DashboardHeader user={mockUser} data={mockDashboardData} />);

      const notificationBadge = screen.getByTestId('notification-badge');
      expect(notificationBadge).toHaveTextContent('3');
    });
  });

  describe('WidgetContainer Component', () => {
    const mockWidget = {
      id: 'portfolio',
      type: 'portfolio_summary',
      title: 'Portfolio Overview',
      data: { totalValue: 125000 },
      isVisible: true
    };

    it('should render widget container correctly', () => {
      render(<WidgetContainer widget={mockWidget} />);

      expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      expect(screen.getByTestId('widget-container')).toHaveClass('portfolio_summary');
    });

    it('should handle widget settings', async () => {
      const user = userEvent.setup();
      const onSettings = vi.fn();

      render(<WidgetContainer widget={mockWidget} onSettings={onSettings} />);

      const settingsButton = screen.getByRole('button', { name: /settings/i });
      await user.click(settingsButton);

      expect(onSettings).toHaveBeenCalledWith(mockWidget.id);
    });

    it('should show loading state', () => {
      const loadingWidget = { ...mockWidget, isLoading: true };

      render(<WidgetContainer widget={loadingWidget} />);

      expect(screen.getByTestId('widget-loading')).toBeInTheDocument();
    });

    it('should show error state', () => {
      const errorWidget = { ...mockWidget, error: 'Failed to load data' };

      render(<WidgetContainer widget={errorWidget} />);

      expect(screen.getByText('Failed to load data')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });

  describe('MetricsOverview Component', () => {
    const mockMetrics = {
      totalValue: 125000,
      dayChange: 2500,
      dayChangePercent: 2.04,
      weekChange: 3750,
      weekChangePercent: 3.09
    };

    it('should render metrics overview correctly', () => {
      render(<MetricsOverview metrics={mockMetrics} />);

      expect(screen.getByText('Portfolio Metrics')).toBeInTheDocument();
      expect(screen.getByText('$125,000')).toBeInTheDocument();
      expect(screen.getByText('+$2,500')).toBeInTheDocument();
      expect(screen.getByText('+2.04%')).toBeInTheDocument();
    });

    it('should switch between time periods', async () => {
      const user = userEvent.setup();

      render(<MetricsOverview metrics={mockMetrics} />);

      const weekTab = screen.getByRole('button', { name: /1w/i });
      await user.click(weekTab);

      expect(screen.getByText('+$3,750')).toBeInTheDocument();
      expect(screen.getByText('+3.09%')).toBeInTheDocument();
    });

    it('should show negative changes correctly', () => {
      const negativeMetrics = {
        ...mockMetrics,
        dayChange: -1500,
        dayChangePercent: -1.18
      };

      render(<MetricsOverview metrics={negativeMetrics} />);

      expect(screen.getByText('-$1,500')).toBeInTheDocument();
      expect(screen.getByText('-1.18%')).toBeInTheDocument();
    });
  });

  describe('Dashboard Performance', () => {
    it('should render dashboard efficiently', () => {
      const startTime = performance.now();
      
      render(
        <DashboardLayout user={mockUser}>
          <DashboardHeader user={mockUser} data={mockDashboardData} />
        </DashboardLayout>
      );
      
      const renderTime = performance.now() - startTime;
      expect(renderTime).toBeLessThan(100); // Should render within 100ms
    });
  });
});