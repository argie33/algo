import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import muiTheme from '../../theme/muiTheme'

// Create a new QueryClient for each test to ensure isolation
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false, // Disable retries in tests
        gcTime: Infinity, // Keep data in cache during tests
        staleTime: Infinity, // Prevent automatic refetching
      },
      mutations: {
        retry: false,
      },
    },
    logger: {
      log: console.log,
      warn: console.warn,
      error: process.env.NODE_ENV === 'test' ? () => {} : console.error,
    },
  })
}

// Test wrapper with all necessary providers
function TestWrapper({ children, queryClient }) {
  const testQueryClient = queryClient || createTestQueryClient()
  
  return (
    <QueryClientProvider client={testQueryClient}>
      <BrowserRouter>
        <ThemeProvider theme={muiTheme}>
          {children}
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

// Enhanced render function with React Query support
export function renderWithProviders(ui, options = {}) {
  const { queryClient, ...renderOptions } = options
  
  const Wrapper = ({ children }) => (
    <TestWrapper queryClient={queryClient}>
      {children}
    </TestWrapper>
  )
  
  return {
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
    queryClient: queryClient || createTestQueryClient(),
  }
}

// Hook testing utility for React Query hooks
export function renderHook(hook, options = {}) {
  const { queryClient, initialProps, ...renderOptions } = options
  const testQueryClient = queryClient || createTestQueryClient()
  
  // Create a test component that calls the hook
  function TestComponent(props) {
    const hookResult = hook(props)
    TestComponent.hookResult = hookResult
    return null
  }
  
  const wrapper = ({ children }) => (
    <TestWrapper queryClient={testQueryClient}>
      {children}
    </TestWrapper>
  )
  
  const renderResult = render(<TestComponent {...initialProps} />, { 
    wrapper,
    ...renderOptions 
  })
  
  return {
    result: {
      get current() {
        return TestComponent.hookResult
      }
    },
    queryClient: testQueryClient,
    rerender: (newProps) => {
      renderResult.rerender(<TestComponent {...newProps} />)
    },
    unmount: renderResult.unmount,
  }
}

// Mock API response helpers
export function createMockApiResponse(data, options = {}) {
  const { delay = 0, shouldError = false, errorMessage = 'API Error' } = options
  
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (shouldError) {
        reject(new Error(errorMessage))
      } else {
        resolve({ data, success: true })
      }
    }, delay)
  })
}

// Mock fetch for API testing
export function mockFetch(responses = {}) {
  global.fetch = jest.fn((url) => {
    const response = responses[url] || responses.default
    
    if (!response) {
      return Promise.reject(new Error(`No mock response for ${url}`))
    }
    
    if (response instanceof Error) {
      return Promise.reject(response)
    }
    
    return Promise.resolve({
      ok: true,
      status: 200,
      headers: new Map([['content-type', 'application/json']]),
      json: () => Promise.resolve(response),
      text: () => Promise.resolve(JSON.stringify(response)),
    })
  })
}

// Clean up mocks
export function cleanupMocks() {
  if (global.fetch && global.fetch.mockRestore) {
    global.fetch.mockRestore()
  }
}

// Test data factories
export const testData = {
  marketOverview: {
    indices: [
      { symbol: 'SPY', price: 450.50, change: 2.30, changePercent: 0.51 },
      { symbol: 'QQQ', price: 380.75, change: -1.25, changePercent: -0.33 }
    ],
    lastUpdated: new Date().toISOString()
  },
  
  stockPrices: {
    AAPL: {
      symbol: 'AAPL',
      price: 175.50,
      change: 2.30,
      changePercent: 1.33,
      volume: 50000000
    }
  },
  
  portfolioData: {
    value: 125000,
    dayChange: 1250,
    dayChangePercent: 1.01,
    positions: [
      { symbol: 'AAPL', shares: 100, value: 17550 },
      { symbol: 'GOOGL', shares: 50, value: 13000 }
    ]
  },
  
  tradingSignals: [
    {
      id: 1,
      symbol: 'AAPL',
      signal: 'BUY',
      confidence: 0.85,
      timestamp: new Date().toISOString()
    },
    {
      id: 2,
      symbol: 'MSFT',
      signal: 'HOLD',
      confidence: 0.60,
      timestamp: new Date().toISOString()
    }
  ]
}

export default renderWithProviders