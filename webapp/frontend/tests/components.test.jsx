import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import Dashboard from '../src/pages/Dashboard'
import theme from '../src/theme'

// Mock the API module
vi.mock('../src/services/api', () => ({
  default: {
    getMarketOverview: vi.fn(),
    getStocks: vi.fn(),
    getSectors: vi.fn(),
  }
}))

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return ({ children }) => (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider theme={theme}>
          {children}
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

describe('Dashboard Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders dashboard title', async () => {
    const { default: api } = await import('../src/services/api')
    
    api.getMarketOverview.mockResolvedValue({
      data: {
        totalStocks: 100,
        avgMarketCap: 50000000000,
        sectorPerformance: []
      }
    })

    render(<Dashboard />, { wrapper: createWrapper() })
    
    expect(screen.getByText('Market Dashboard')).toBeInTheDocument()
  })

  it('shows loading state initially', () => {
    render(<Dashboard />, { wrapper: createWrapper() })
    
    expect(screen.getByRole('progressbar')).toBeInTheDocument()  })
})

describe('API Service', () => {
  it('constructs query parameters correctly', async () => {
    const { default: api } = await import('../src/services/api')
    
    // Mock the axios instance
    api.get = vi.fn().mockResolvedValue({ data: {} })
    
    await api.getStocks({ search: 'AAPL', sector: 'Technology' })
    
    expect(api.get).toHaveBeenCalledWith('/stocks?search=AAPL&sector=Technology')
  })
})

describe('Utility Functions', () => {
  it('formats currency correctly', async () => {
    const { formatCurrency } = await import('../src/utils/formatters')
    
    expect(formatCurrency(1000)).toBe('$1,000.00')
    expect(formatCurrency(1000000)).toBe('$1,000,000.00')
    expect(formatCurrency(null)).toBe('N/A')
  })

  it('formats percentage correctly', async () => {    const { formatPercentage } = await import('../src/utils/formatters')
    
    expect(formatPercentage(0.15)).toBe('15.00%')
    expect(formatPercentage(-0.05)).toBe('-5.00%')
    expect(formatPercentage(null)).toBe('N/A')
  })

  it('formats numbers correctly', async () => {
    const { formatNumber } = await import('../src/utils/formatters')
    
    expect(formatNumber(1234.567, 2)).toBe('1,234.57')
    expect(formatNumber(1000000, 0)).toBe('1,000,000')
    expect(formatNumber(null)).toBe('N/A')
  })
})
