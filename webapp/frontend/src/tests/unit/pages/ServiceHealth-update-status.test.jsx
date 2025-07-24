/**
 * ServiceHealth Update Status Functionality Tests
 * Tests the health status update button and comprehensive database analysis
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import ServiceHealth from '../../../pages/ServiceHealth';
import * as useSimpleFetchModule from '../../../hooks/useSimpleFetch.js';

// Mock the API service
const mockApi = {
  get: vi.fn(),
  post: vi.fn()
};

// Mock all the API functions
vi.mock('../../../services/api', () => ({
  healthCheck: vi.fn(),
  getTechnicalData: vi.fn(),
  getStocks: vi.fn(),
  getMarketOverview: vi.fn(),
  testApiConnection: vi.fn(),
  screenStocks: vi.fn(),
  getBuySignals: vi.fn(),
  getSellSignals: vi.fn(),
  getNaaimData: vi.fn(),
  getFearGreedData: vi.fn(),
  getApiConfig: vi.fn(() => ({ apiUrl: 'https://test-api.example.com' })),
  getDiagnosticInfo: vi.fn(),
  getCurrentBaseURL: vi.fn(),
  api: {
    get: vi.fn(),
    post: vi.fn()
  }
}));

vi.mock('../../../hooks/useSimpleFetch.js', () => ({
  useSimpleFetch: vi.fn()
}));

// Mock Material-UI components to simplify testing
vi.mock('@mui/material', () => ({
  Box: ({ children }) => <div data-testid="box">{children}</div>,
  Container: ({ children }) => <div data-testid="container">{children}</div>,
  Typography: ({ children, ...props }) => <div data-testid="typography" {...props}>{children}</div>,
  Grid: ({ children }) => <div data-testid="grid">{children}</div>,
  Card: ({ children }) => <div data-testid="card">{children}</div>,
  CardContent: ({ children }) => <div data-testid="card-content">{children}</div>,
  Alert: ({ children }) => <div data-testid="alert">{children}</div>,
  CircularProgress: () => <div data-testid="loading">Loading...</div>,
  Chip: ({ label }) => <span data-testid="chip">{label}</span>,
  Table: ({ children }) => <table data-testid="table">{children}</table>,
  TableBody: ({ children }) => <tbody data-testid="table-body">{children}</tbody>,
  TableCell: ({ children }) => <td data-testid="table-cell">{children}</td>,
  TableContainer: ({ children }) => <div data-testid="table-container">{children}</div>,
  TableHead: ({ children }) => <thead data-testid="table-head">{children}</thead>,
  TableRow: ({ children }) => <tr data-testid="table-row">{children}</tr>,
  Paper: ({ children }) => <div data-testid="paper">{children}</div>,
  Accordion: ({ children }) => <div data-testid="accordion">{children}</div>,
  AccordionSummary: ({ children }) => <div data-testid="accordion-summary">{children}</div>,
  AccordionDetails: ({ children }) => <div data-testid="accordion-details">{children}</div>,
  Divider: () => <hr data-testid="divider" />,
  Button: ({ children, onClick, disabled, ...props }) => (
    <button 
      data-testid="button" 
      onClick={onClick} 
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  ),
  IconButton: ({ children, onClick }) => (
    <button data-testid="icon-button" onClick={onClick}>{children}</button>
  ),
  Tooltip: ({ children, title }) => (
    <div data-testid="tooltip" title={title}>{children}</div>
  )
}));

// Mock Material-UI icons
vi.mock('@mui/icons-material', () => ({
  ExpandMore: () => <span data-testid="expand-more-icon">ExpandMore</span>,
  CheckCircle: () => <span data-testid="check-circle-icon">CheckCircle</span>,
  Error: () => <span data-testid="error-icon">Error</span>,
  Warning: () => <span data-testid="warning-icon">Warning</span>,
  Info: () => <span data-testid="info-icon">Info</span>,
  Refresh: () => <span data-testid="refresh-icon">Refresh</span>,
  Storage: () => <span data-testid="storage-icon">Storage</span>,
  Api: () => <span data-testid="api-icon">Api</span>,
  Cloud: () => <span data-testid="cloud-icon">Cloud</span>,
  ToggleOff: () => <span data-testid="toggle-off-icon">ToggleOff</span>,
  ToggleOn: () => <span data-testid="toggle-on-icon">ToggleOn</span>
}));

// Mock the ApiKeyStatusIndicator component
vi.mock('../../../components/ApiKeyStatusIndicator', () => ({
  default: () => <div data-testid="api-key-status-indicator">API Key Status</div>
}));

describe('ServiceHealth Update Status Functionality', () => {

  const mockHealthData = {
    status: 'connected',
    database: {
      status: 'connected',
      tables: {
        'stock_symbols': {
          status: 'healthy',
          record_count: 5000,
          last_updated: '2024-01-15T10:00:00Z',
          last_checked: '2024-01-15T12:00:00Z',
          table_category: 'symbols',
          critical_table: true,
          is_stale: false,
          missing_data_count: 0,
          error: null,
          note: 'Using pg_stat estimated counts for performance'
        },
        'portfolio_holdings': {
          status: 'healthy',
          record_count: 150,
          last_updated: '2024-01-15T11:30:00Z',
          last_checked: '2024-01-15T12:00:00Z',
          table_category: 'portfolio',
          critical_table: true,
          is_stale: false,
          missing_data_count: 0,
          error: null,
          note: 'Using pg_stat estimated counts for performance'
        },
        'health_status': {
          status: 'healthy',
          record_count: 25,
          last_updated: '2024-01-15T12:00:00Z',
          last_checked: '2024-01-15T12:00:00Z',
          table_category: 'system',
          critical_table: true,
          is_stale: false,
          missing_data_count: 0,
          error: null,
          note: 'Using pg_stat estimated counts for performance'
        }
      },
      summary: {
        total_tables: 3,
        healthy_tables: 3,
        stale_tables: 0,
        error_tables: 0,
        empty_tables: 0,
        missing_tables: 0,
        total_records: 5175,
        total_missing_data: 0
      }
    },
    timestamp: '2024-01-15T12:00:00Z',
    note: 'Analyzed 3 database tables in 150ms'
  };

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock useSimpleFetch to return database health data
    vi.spyOn(useSimpleFetchModule, 'useSimpleFetch').mockReturnValue({
      data: mockHealthData,
      loading: false,
      error: null,
      refetch: vi.fn()
    });

    // Mock console methods
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Update Status Button', () => {
    it('should render update status button', () => {
      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      expect(updateButton).toBeDefined();
    });

    it('should call correct API endpoint when update status is clicked', async () => {
      // Mock successful API response
      mockApi.post.mockResolvedValueOnce({
        data: {
          status: 'success',
          message: 'Database health status updated successfully',
          data: mockHealthData,
          timestamp: '2024-01-15T12:00:00Z'
        }
      });

      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      fireEvent.click(updateButton);

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalledWith(
          '/api/health-full/update-status',
          {},
          { timeout: 60000 }
        );
      });
    });

    it('should handle API errors gracefully during update', async () => {
      // Mock API error
      mockApi.post.mockRejectedValueOnce(new Error('Update failed'));

      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      fireEvent.click(updateButton);

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalled();
      });

      // Should not crash the component
      expect(updateButton).toBeDefined();
    });

    it('should show loading state during update', async () => {
      // Mock delayed API response
      let resolveApi;
      mockApi.post.mockImplementationOnce(() => 
        new Promise(resolve => { resolveApi = resolve; })
      );

      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      fireEvent.click(updateButton);

      // Should show loading state
      await waitFor(() => {
        expect(updateButton).toBeDisabled();
      });

      // Resolve the API call
      resolveApi({
        data: {
          status: 'success',
          data: mockHealthData
        }
      });

      // Should enable button again
      await waitFor(() => {
        expect(updateButton).not.toBeDisabled();
      });
    });
  });

  describe('Comprehensive Database Analysis Display', () => {
    it('should display table analysis results after update', () => {
      render(<ServiceHealth />);
      
      // Should display table information
      expect(screen.getByText('stock_symbols')).toBeDefined();
      expect(screen.getByText('portfolio_holdings')).toBeDefined();
      expect(screen.getByText('health_status')).toBeDefined();
    });

    it('should show table categories and critical status', () => {
      render(<ServiceHealth />);
      
      // Should show table categories
      expect(screen.getByText(/symbols/)).toBeDefined();
      expect(screen.getByText(/portfolio/)).toBeDefined();
      expect(screen.getByText(/system/)).toBeDefined();
    });

    it('should display comprehensive summary statistics', () => {
      render(<ServiceHealth />);
      
      // Should show summary information
      expect(screen.getByText(/3.*tables/i)).toBeDefined(); // Total tables
      expect(screen.getByText(/5175/)).toBeDefined(); // Total records
    });

    it('should show performance metrics from analysis', () => {
      render(<ServiceHealth />);
      
      // Should show performance information
      expect(screen.getByText(/150ms/)).toBeDefined(); // Analysis duration
    });

    it('should categorize tables correctly as per backend analysis', () => {
      const mockDataWithCategories = {
        ...mockHealthData,
        database: {
          ...mockHealthData.database,
          tables: {
            ...mockHealthData.database.tables,
            'price_daily': {
              status: 'healthy',
              record_count: 100000,
              table_category: 'prices',
              critical_table: true
            },
            'earnings_estimates': {
              status: 'healthy',
              record_count: 12000,
              table_category: 'earnings',
              critical_table: false
            }
          }
        }
      };

      vi.spyOn(useSimpleFetchModule, 'useSimpleFetch').mockReturnValue({
        data: mockDataWithCategories,
        loading: false,
        error: null,
        refetch: vi.fn()
      });

      render(<ServiceHealth />);
      
      // Should display all categories
      expect(screen.getByText(/prices/)).toBeDefined();
      expect(screen.getByText(/earnings/)).toBeDefined();
    });
  });

  describe('Error Handling', () => {
    it('should handle 404 errors gracefully', async () => {
      const error404 = new Error('Request failed with status code 404');
      error404.response = { status: 404 };
      mockApi.post.mockRejectedValueOnce(error404);

      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      fireEvent.click(updateButton);

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalled();
      });

      // Should handle error without crashing
      expect(updateButton).toBeDefined();
    });

    it('should handle network errors during update', async () => {
      const networkError = new Error('Network Error');
      mockApi.post.mockRejectedValueOnce(networkError);

      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      fireEvent.click(updateButton);

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalled();
      });

      // Should handle error gracefully
      expect(updateButton).toBeDefined();
    });

    it('should handle timeout errors during long-running analysis', async () => {
      const timeoutError = new Error('timeout exceeded');
      mockApi.post.mockRejectedValueOnce(timeoutError);

      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      fireEvent.click(updateButton);

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalled();
      });

      // Should handle timeout gracefully
      expect(updateButton).toBeDefined();
    });
  });

  describe('Data Refresh Integration', () => {
    it('should refresh health data after successful update', async () => {
      const mockRefetch = vi.fn();
      vi.spyOn(useSimpleFetchModule, 'useSimpleFetch').mockReturnValue({
        data: mockHealthData,
        loading: false,
        error: null,
        refetch: mockRefetch
      });

      mockApi.post.mockResolvedValueOnce({
        data: {
          status: 'success',
          data: mockHealthData
        }
      });

      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      fireEvent.click(updateButton);

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalled();
      });

      // Should trigger data refresh
      await waitFor(() => {
        expect(mockRefetch).toHaveBeenCalled();
      });
    });

    it('should handle refresh failures gracefully', async () => {
      const mockRefetch = vi.fn().mockRejectedValueOnce(new Error('Refresh failed'));
      vi.spyOn(useSimpleFetchModule, 'useSimpleFetch').mockReturnValue({
        data: mockHealthData,
        loading: false,
        error: null,
        refetch: mockRefetch
      });

      mockApi.post.mockResolvedValueOnce({
        data: { status: 'success', data: mockHealthData }
      });

      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      fireEvent.click(updateButton);

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalled();
      });

      // Should not crash on refresh failure
      expect(updateButton).toBeDefined();
    });
  });

  describe('Performance and User Experience', () => {
    it('should disable update button during refresh to prevent double-clicks', async () => {
      let resolveApi;
      mockApi.post.mockImplementationOnce(() => 
        new Promise(resolve => { resolveApi = resolve; })
      );

      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      
      // Button should be enabled initially
      expect(updateButton).not.toBeDisabled();
      
      fireEvent.click(updateButton);

      // Should be disabled during API call
      await waitFor(() => {
        expect(updateButton).toBeDisabled();
      });

      // Complete the API call
      resolveApi({ data: { status: 'success', data: mockHealthData } });

      // Should be enabled again
      await waitFor(() => {
        expect(updateButton).not.toBeDisabled();
      });
    });

    it('should provide visual feedback during comprehensive analysis', async () => {
      let resolveApi;
      mockApi.post.mockImplementationOnce(() => 
        new Promise(resolve => { resolveApi = resolve; })
      );

      render(<ServiceHealth />);
      
      const updateButton = screen.getByRole('button', { name: /update.*all.*tables/i });
      fireEvent.click(updateButton);

      // Should show some form of loading indication
      await waitFor(() => {
        expect(updateButton).toBeDisabled();
      });

      resolveApi({ data: { status: 'success', data: mockHealthData } });
    });
  });
});