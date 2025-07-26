# React Migration Guide - useSimpleFetch to React Query

This guide documents the patterns for migrating from the deprecated `useSimpleFetch` to standard React Query patterns.

## Migration Status

### ✅ Completed Components
- **Dashboard** - Fully migrated to React Query hooks
- **ServiceHealth** - Uses `useServiceHealth()` 
- **FinancialData** - Uses `useFinancialData()`
- **StockDetail** - Uses `useStockDetail()`

### 🔄 In Progress (Using Compatibility Wrapper)
- MarketOverview
- SentimentAnalysis
- Commodities
- AnalystInsights
- EarningsCalendar
- StockScreener
- Backtest
- And 5 other components

## Migration Patterns

### 1. Market Data APIs

**Before:**
```javascript
import { useSimpleFetch } from '../hooks/useSimpleFetch'

function MyComponent() {
  const { data, loading, error } = useSimpleFetch('/api/market/overview')
  // ...
}
```

**After:**
```javascript
import { useMarketOverview } from '../hooks/useMarketData'

function MyComponent() {
  const { data, isLoading, error } = useMarketOverview()
  // ...
}
```

### 2. Stock-Specific Data

**Before:**
```javascript
const { data, loading } = useSimpleFetch(`/api/market/prices/${symbol}`)
const { data: metrics } = useSimpleFetch(`/api/market/metrics/${symbol}`)
```

**After:**
```javascript
import { useStockPrices, useStockMetrics } from '../hooks/useMarketData'

const { data, isLoading } = useStockPrices(symbol)
const { data: metrics } = useStockMetrics(symbol)
```

### 3. Portfolio Data

**Before:**
```javascript
const { data } = useSimpleFetch('/api/portfolio/watchlist')
const { data: activity } = useSimpleFetch('/api/portfolio/activity')
```

**After:**
```javascript
import { useWatchlist, usePortfolioActivity } from '../hooks/usePortfolioData'

const { data } = useWatchlist()
const { data: activity } = usePortfolioActivity()
```

### 4. Trading and News Data

**Before:**
```javascript
const { data } = useSimpleFetch('/api/trading/signals/daily?limit=10')
const { data: news } = useSimpleFetch('/api/news?limit=5')
```

**After:**
```javascript
import { useTradingSignals, useNews } from '../hooks/useTradingData'

const { data } = useTradingSignals(10)
const { data: news } = useNews(5)
```

### 5. Generic API Calls

**Before:**
```javascript
const { data } = useSimpleFetch('/api/custom/endpoint')
```

**After:**
```javascript
import { useApiData } from '../hooks/useApiData'

const { data } = useApiData('/api/custom/endpoint', ['custom', 'endpoint'])
```

## Available Hook Libraries

### useMarketData.js
- `useMarketOverview()` - Market overview data
- `useMarketSentiment()` - Market sentiment analysis
- `useSectorPerformance()` - Sector performance data
- `useEconomicIndicators(limit?)` - Economic indicators
- `useStockPrices(symbol)` - Real-time stock prices
- `useStockMetrics(symbol)` - Stock metrics and ratios
- `useStockScores(limit?, sortBy?, sortOrder?)` - Stock scoring data

### usePortfolioData.js
- `useWatchlist()` - User's watchlist
- `usePortfolioActivity()` - Portfolio activity feed
- `useUserProfile()` - User profile information

### useTradingData.js
- `useTradingSignals(limit?)` - Trading signals
- `useCalendarEvents()` - Economic calendar events
- `useNews(limit?)` - Market news

### useApiData.js
- `useApiData(url, queryKey, options?)` - Generic API calls
- `useServiceHealth()` - Service health monitoring
- `useFinancialData(endpoint)` - Financial data endpoints
- `useStockDetail(symbol)` - Detailed stock information
- `useEarningsCalendar()` - Earnings calendar
- `useSentimentAnalysis()` - Sentiment analysis data
- `useAnalystInsights()` - Analyst insights
- `useCommoditiesData()` - Commodities market data
- `useBacktestData(params)` - Backtesting results

## Key Differences

### API Response Format
- **Before**: `{ data, loading, error, isLoading, isError, isSuccess }`
- **After**: `{ data, isLoading, error, isError, isSuccess, refetch }`

### Property Changes
- `loading` → `isLoading`
- Enhanced error handling with React Query's built-in retry logic
- Better caching with configurable stale times

### Options Configuration
```javascript
// Before
useSimpleFetch(url, {
  retry: 3,
  staleTime: 30000,
  enabled: true
})

// After  
useMarketOverview({
  retry: 3,
  staleTime: 30000,
  enabled: true
})
```

## Migration Checklist

For each component using `useSimpleFetch`:

1. ✅ Identify the API endpoint being called
2. ✅ Choose appropriate hook from available libraries
3. ✅ Update import statement
4. ✅ Replace `useSimpleFetch` call with new hook
5. ✅ Update property names (`loading` → `isLoading`)
6. ✅ Test component functionality
7. ✅ Remove any custom error handling if using built-in React Query features

## Benefits of Migration

### Performance
- **Better Caching**: React Query's intelligent caching system
- **Background Updates**: Automatic background refetching
- **Request Deduplication**: Automatic deduplication of identical requests

### Developer Experience
- **DevTools**: React Query DevTools for debugging
- **Built-in States**: Loading, error, and success states out of the box
- **Optimistic Updates**: Easy optimistic updates for mutations

### Reliability
- **Smart Retries**: Configurable retry logic with exponential backoff
- **Error Boundaries**: Better error handling and recovery
- **Stale-While-Revalidate**: Serve stale data while fetching fresh data

## Testing

When testing components using the new hooks, use the provided test utilities:

```javascript
import { renderWithProviders } from '../tests/helpers/testUtils'

test('component with React Query hook', () => {
  const { getByText } = renderWithProviders(<MyComponent />)
  // Test assertions
})
```

## Migration Progress Tracking

The compatibility wrapper in `useSimpleFetch.js` logs deprecation warnings to help identify which components still need migration. Check the browser console for these warnings during development.

Once all components are migrated, the compatibility wrapper can be removed entirely.