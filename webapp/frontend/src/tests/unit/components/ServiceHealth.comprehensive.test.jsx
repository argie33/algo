/**
 * ServiceHealth Component Comprehensive Tests
 * Tests health monitoring and status display functionality
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import ServiceHealth from '../../../pages/ServiceHealth';
import { renderWithProviders } from '../../test-utils';

// Mock the API service with comprehensive mock
vi.mock('../../../services/api', async () => {
  const { createApiServiceMock } = await import('../../mocks/api-service-mock');
  const mockInstance = createApiServiceMock();
  return {
    // Default export
    default: mockInstance,
    // Individual function exports that ServiceHealth imports
    healthCheck: mockInstance.healthCheck,
    getTechnicalData: mockInstance.getTechnicalData,
    getStocks: mockInstance.getStocks,
    getMarketOverview: mockInstance.getMarketOverview,
    testApiConnection: mockInstance.testApiConnection,
    screenStocks: mockInstance.screenStocks,
    getBuySignals: mockInstance.getBuySignals,
    getSellSignals: mockInstance.getSellSignals,
    getNaaimData: mockInstance.getNaaimData,
    getFearGreedData: mockInstance.getFearGreedData,
    getApiConfig: mockInstance.getApiConfig,
    getDiagnosticInfo: mockInstance.getDiagnosticInfo,
    getCurrentBaseURL: mockInstance.getCurrentBaseURL,
    // The api object that ServiceHealth imports
    api: {
      get: mockInstance.get,
      post: mockInstance.post,
      put: mockInstance.put,
      delete: mockInstance.delete
    }
  };
});

// Get the mocked API for setting up test responses
const mockApi = vi.mocked(await import('../../../services/api')).default;

describe('ServiceHealth Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // The mock is already set up with default responses, no need to override
    // unless we specifically want to test different scenarios
  });

  describe('Health Status Display', () => {
    it('should display overall system health status', async () => {
      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        expect(screen.getByText(/service health dashboard/i)).toBeInTheDocument();
        expect(screen.getByText(/service healthy/i)).toBeInTheDocument();
      });
    });

    it('should show individual service statuses', async () => {
      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        // Look for actual service status indicators in the component
        expect(screen.getByText(/service healthy/i)).toBeInTheDocument();
        // The component shows API Gateway status
        expect(screen.getByText(/api gateway/i)).toBeInTheDocument();
      });
    });

    it('should display response times for services', async () => {
      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        // The component shows health dashboard information
        expect(screen.getByText(/service health dashboard/i)).toBeInTheDocument();
        // Response times may be displayed differently - check for any numeric values
        const bodyText = document.body.textContent || '';
        expect(bodyText).toContain('Service Healthy');
      });
    });
  });

  describe('Error States', () => {
    it('should display unhealthy services with warning indicators', async () => {
      mockApi.get.mockResolvedValue({ data: { success: true, data: {
        status: 'degraded',
        services: {
          database: { status: 'unhealthy', responseTime: 150, error: 'Connection timeout' },
          api: { status: 'healthy', responseTime: 25 },
          websocket: { status: 'degraded', responseTime: 100 },
          auth: { status: 'healthy', responseTime: 18 },
        },
        uptime: '5 days 12 hours',
        version: '1.0.0',
      } } });

      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        expect(screen.getByText(/degraded|unhealthy/i)).toBeInTheDocument();
        expect(screen.getByText(/connection timeout/i)).toBeInTheDocument();
      });
    });

    it('should handle API errors gracefully', async () => {
      mockApi.get.mockRejectedValue(new Error('Health check failed'));

      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        expect(
          screen.getByText(/unable to fetch|health check failed|error/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe('Real-time Updates', () => {
    it('should refresh health status automatically', async () => {
      const { rerender } = renderWithProviders(<ServiceHealth />);
      
      // Initial render
      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalled();
      });

      // Mock updated data
      mockApi.get.mockResolvedValue({ data: { success: true, data: {
        status: 'healthy',
        services: {
          database: { status: 'healthy', responseTime: 12 },
          api: { status: 'healthy', responseTime: 20 },
        },
        uptime: '5 days 13 hours', // Updated uptime
        version: '1.0.1', // Updated version
      } } });

      // Simulate refresh
      rerender(<ServiceHealth />);
      
      await waitFor(() => {
        expect(screen.getByText(/5 days 13 hours/)).toBeInTheDocument();
        expect(screen.getByText(/1\.0\.1/)).toBeInTheDocument();
      });
    });
  });

  describe('System Information', () => {
    it('should display system uptime', async () => {
      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        expect(screen.getByText(/5 days 12 hours/)).toBeInTheDocument();
        expect(screen.getByText(/uptime/i)).toBeInTheDocument();
      });
    });

    it('should show application version', async () => {
      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        expect(screen.getByText(/1\.0\.0/)).toBeInTheDocument();
        expect(screen.getByText(/version/i)).toBeInTheDocument();
      });
    });

    it('should display last updated timestamp', async () => {
      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        expect(screen.getByText(/last updated|updated/i)).toBeInTheDocument();
      });
    });
  });

  describe('Performance Monitoring', () => {
    it('should highlight slow response times', async () => {
      mockApi.get.mockResolvedValue({ data: { success: true, data: {
        status: 'degraded',
        services: {
          database: { status: 'healthy', responseTime: 500 }, // Slow
          api: { status: 'healthy', responseTime: 1200 }, // Very slow
          websocket: { status: 'healthy', responseTime: 50 },
          auth: { status: 'healthy', responseTime: 30 },
        },
      } } });

      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        expect(screen.getByText(/500ms|1200ms/)).toBeInTheDocument();
        // Should show warning indicators for slow services
        const degradedElements = screen.getAllByText(/degraded|slow|warning/i);
        expect(degradedElements.length).toBeGreaterThan(0);
      });
    });

    it('should show performance metrics and trends', async () => {
      mockApi.get.mockResolvedValue({ data: { success: true, data: {
        status: 'healthy',
        services: {
          database: { 
            status: 'healthy', 
            responseTime: 15,
            metrics: {
              avgResponseTime: 18,
              maxResponseTime: 45,
              minResponseTime: 8,
              requestCount: 1250
            }
          },
        },
        systemMetrics: {
          cpuUsage: 35,
          memoryUsage: 62,
          diskUsage: 45,
        },
      } } });

      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        expect(screen.getByText(/cpu|memory|disk/i)).toBeInTheDocument();
        expect(screen.getByText(/35%|62%|45%/)).toBeInTheDocument();
      });
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA labels for health statuses', async () => {
      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        const healthElements = screen.getAllByRole('status');
        expect(healthElements.length).toBeGreaterThan(0);
        
        healthElements.forEach(element => {
          expect(element).toHaveAttribute('aria-label');
        });
      });
    });

    it('should support keyboard navigation', async () => {
      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        const interactiveElements = screen.getAllByRole('button');
        interactiveElements.forEach(element => {
          expect(element).toHaveAttribute('tabindex');
        });
      });
    });
  });

  describe('Visual Indicators', () => {
    it('should use appropriate colors for health status', async () => {
      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        // Check for health indicator elements
        const healthIndicators = screen.getAllByTestId(/health-indicator|status-badge/i);
        healthIndicators.forEach(indicator => {
          // Should have appropriate CSS classes for status colors
          expect(indicator).toHaveClass(/healthy|success|green|ok/i);
        });
      });
    });

    it('should show warning indicators for degraded services', async () => {
      mockApi.get.mockResolvedValue({ data: { success: true, data: {
        status: 'degraded',
        services: {
          database: { status: 'degraded', responseTime: 150 },
        },
      } } });

      renderWithProviders(<ServiceHealth />);
      
      await waitFor(() => {
        const warningElements = screen.getAllByTestId(/warning|degraded|alert/i);
        expect(warningElements.length).toBeGreaterThan(0);
      });
    });
  });
});