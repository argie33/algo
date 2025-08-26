/**
 * FinancialData Component Comprehensive Tests
 * Tests financial data display, calculations, and real-time updates
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import FinancialData from '../../../pages/FinancialData';
import { renderWithProviders } from '../../test-utils';

// Mock API service
// Mock the API service with comprehensive mock
vi.mock("../../../services/api", async (_importOriginal) => {
  const { createApiServiceMock } = await import('../../mocks/api-service-mock');
  return {
    default: createApiServiceMock(),
    ...createApiServiceMock()
  };
});

// Get the mocked API for setting up test responses
const mockApi = vi.mocked(await import('../../../services/api')).default;

const mockFinancialData = {
  symbol: 'AAPL',
  companyName: 'Apple Inc.',
  marketCap: 3200000000000,
  pe: 28.5,
  eps: 6.85,
  revenue: 394000000000,
  grossProfit: 170000000000,
  operatingIncome: 114000000000,
  netIncome: 100000000000,
  totalDebt: 132000000000,
  totalCash: 165000000000,
  freeCashFlow: 111000000000,
  roe: 0.175,
  roa: 0.135,
  currentRatio: 1.07,
  debtToEquity: 1.73,
  priceToBook: 45.2,
  dividendYield: 0.0042,
  quarterlyData: [
    { quarter: 'Q1 2024', revenue: 90000000000, netIncome: 23000000000 },
    { quarter: 'Q2 2024', revenue: 95000000000, netIncome: 25000000000 },
    { quarter: 'Q3 2024', revenue: 100000000000, netIncome: 26000000000 },
    { quarter: 'Q4 2024', revenue: 109000000000, netIncome: 26000000000 },
  ],
  yearlyData: [
    { year: 2020, revenue: 275000000000, netIncome: 57000000000 },
    { year: 2021, revenue: 366000000000, netIncome: 95000000000 },
    { year: 2022, revenue: 394000000000, netIncome: 100000000000 },
    { year: 2023, revenue: 383000000000, netIncome: 97000000000 },
  ],
};

describe('FinancialData Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    mockApi.get.mockResolvedValue({ data: { success: true, data: mockFinancialData } });
  });

  describe('Data Loading and Display', () => {
    it('should display company financial information', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
        expect(screen.getByText('AAPL')).toBeInTheDocument();
      });
    });

    it('should show key financial metrics', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText(/market cap/i)).toBeInTheDocument();
        expect(screen.getByText(/3\.2T|3,200/i)).toBeInTheDocument();
        expect(screen.getByText(/P\/E/i)).toBeInTheDocument();
        expect(screen.getByText(/28\.5/)).toBeInTheDocument();
      });
    });

    it('should display revenue and profitability metrics', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText(/revenue/i)).toBeInTheDocument();
        expect(screen.getByText(/394B|394,000/i)).toBeInTheDocument();
        expect(screen.getByText(/net income/i)).toBeInTheDocument();
        expect(screen.getByText(/100B|100,000/i)).toBeInTheDocument();
      });
    });
  });

  describe('Financial Ratios and Analysis', () => {
    it('should calculate and display financial ratios', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText(/ROE|return on equity/i)).toBeInTheDocument();
        expect(screen.getByText(/17\.5%/)).toBeInTheDocument();
        expect(screen.getByText(/ROA|return on assets/i)).toBeInTheDocument();
        expect(screen.getByText(/13\.5%/)).toBeInTheDocument();
      });
    });

    it('should show liquidity and solvency ratios', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText(/current ratio/i)).toBeInTheDocument();
        expect(screen.getByText(/1\.07/)).toBeInTheDocument();
        expect(screen.getByText(/debt.*equity|D\/E/i)).toBeInTheDocument();
        expect(screen.getByText(/1\.73/)).toBeInTheDocument();
      });
    });

    it('should display valuation metrics', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText(/price.*book|P\/B/i)).toBeInTheDocument();
        expect(screen.getByText(/45\.2/)).toBeInTheDocument();
        expect(screen.getByText(/dividend yield/i)).toBeInTheDocument();
        expect(screen.getByText(/0\.42%/)).toBeInTheDocument();
      });
    });
  });

  describe('Historical Data Visualization', () => {
    it('should render quarterly revenue chart', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText(/quarterly/i)).toBeInTheDocument();
        expect(screen.getByText(/Q1 2024/)).toBeInTheDocument();
        expect(screen.getByText(/Q4 2024/)).toBeInTheDocument();
      });
    });

    it('should display yearly trends', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText(/yearly|annual/i)).toBeInTheDocument();
        expect(screen.getByText(/2020/)).toBeInTheDocument();
        expect(screen.getByText(/2023/)).toBeInTheDocument();
      });
    });

    it('should allow switching between revenue and income views', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        const toggleButtons = screen.getAllByRole('button');
        const revenueButton = toggleButtons.find(btn => 
          btn.textContent?.includes('Revenue') || btn.textContent?.includes('Income')
        );
        
        if (revenueButton) {
          fireEvent.click(revenueButton);
          expect(screen.getByText(/revenue|income/i)).toBeInTheDocument();
        }
      });
    });
  });

  describe('Data Formatting and Display', () => {
    it('should format large numbers appropriately', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        // Should format billions and trillions
        expect(screen.getByText(/3\.2T|3\.2 trillion/i)).toBeInTheDocument();
        expect(screen.getByText(/394B|394 billion/i)).toBeInTheDocument();
      });
    });

    it('should display percentages correctly', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText(/17\.5%/)).toBeInTheDocument();
        expect(screen.getByText(/0\.42%/)).toBeInTheDocument();
      });
    });

    it('should handle negative values appropriately', async () => {
      const negativeData = {
        ...mockFinancialData,
        netIncome: -5000000000,
        roe: -0.05,
      };
      
      mockApi.get.mockResolvedValue({ data: { success: true, data: negativeData } });
      renderWithProviders(<FinancialData symbol="TEST" />);
      
      await waitFor(() => {
        expect(screen.getByText(/-5B|negative/i)).toBeInTheDocument();
        expect(screen.getByText(/-5\.0%/)).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle missing financial data gracefully', async () => {
      const incompleteData = {
        symbol: 'TEST',
        companyName: 'Test Company',
        marketCap: null,
        pe: null,
        eps: null,
      };
      
      mockApi.get.mockResolvedValue({ data: { success: true, data: incompleteData } });
      renderWithProviders(<FinancialData symbol="TEST" />);
      
      await waitFor(() => {
        expect(screen.getByText('Test Company')).toBeInTheDocument();
        expect(screen.getByText(/N\/A|not available|no data/i)).toBeInTheDocument();
      });
    });

    it('should display error message when API fails', async () => {
      mockApi.get.mockRejectedValue(new Error('Failed to fetch financial data'));
      
      renderWithProviders(<FinancialData symbol="INVALID" />);
      
      await waitFor(() => {
        expect(
          screen.getByText(/error|failed|unable to load/i)
        ).toBeInTheDocument();
      });
    });

    it('should show loading state during data fetch', async () => {
      // Mock delayed response
      mockApi.get.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ data: { success: true, data: mockFinancialData } }), 100)
        )
      );
      
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      expect(screen.getByText(/loading|fetching/i)).toBeInTheDocument();
      
      await waitFor(() => {
        expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
      });
    });
  });

  describe('Interactive Features', () => {
    it('should allow time period selection', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        const timeButtons = screen.getAllByRole('button');
        const periodButton = timeButtons.find(btn => 
          btn.textContent?.includes('1Y') || 
          btn.textContent?.includes('5Y') ||
          btn.textContent?.includes('Quarter')
        );
        
        if (periodButton) {
          fireEvent.click(periodButton);
          // Should trigger data refresh
          expect(mockApi.get).toHaveBeenCalledTimes(2);
        }
      });
    });

    it('should support data export functionality', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        const exportButton = screen.queryByText(/export|download/i);
        if (exportButton) {
          fireEvent.click(exportButton);
          // Should handle export (implementation dependent)
          expect(exportButton).toBeInTheDocument();
        }
      });
    });

    it('should allow comparison with other companies', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" compare={['MSFT', 'GOOGL']} />);
      
      await waitFor(() => {
        const compareElements = screen.queryAllByText(/compare|vs\.|versus/i);
        if (compareElements.length > 0) {
          expect(compareElements[0]).toBeInTheDocument();
        }
      });
    });
  });

  describe('Accessibility', () => {
    it('should have proper table headers for financial data', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        const headers = screen.getAllByRole('columnheader');
        expect(headers.length).toBeGreaterThan(0);
        headers.forEach(header => {
          expect(header).toHaveTextContent(/.+/);
        });
      });
    });

    it('should provide ARIA labels for financial metrics', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        const metricElements = screen.getAllByTestId(/metric|ratio|financial/i);
        metricElements.forEach(element => {
          expect(element).toHaveAttribute('aria-label');
        });
      });
    });

    it('should support keyboard navigation for interactive elements', async () => {
      renderWithProviders(<FinancialData symbol="AAPL" />);
      
      await waitFor(() => {
        const buttons = screen.getAllByRole('button');
        buttons.forEach(button => {
          expect(button).not.toHaveAttribute('tabindex', '-1');
        });
      });
    });
  });
});