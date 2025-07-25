# Quick Page Update Template

## For Each Page with useSimpleFetch:

### 1. Add Imports (at top of file)
```jsx
import ApiErrorAlert from '../components/ApiErrorAlert';
import DataContainer from '../components/DataContainer';
```

### 2. Update Hook Calls (find existing patterns)
```jsx
// BEFORE:
const { data, loading, error } = useSimpleFetch(url);

// AFTER:
const { data, loading, error, refetch, showRoutingAlert } = useSimpleFetch(url);
```

### 3. Wrap Components with DataContainer
```jsx
// BEFORE:
return (
  <Container>
    {loading && <CircularProgress />}
    {error && <Alert severity="error">{error}</Alert>}
    {data && <YourComponent data={data} />}
  </Container>
);

// AFTER:
const YourComponentWrapper = ({ data, isFallbackData = false }) => (
  <YourComponent data={data} isDemoData={isFallbackData} />
);

return (
  <Container>
    <DataContainer
      loading={loading}
      error={error} 
      data={data}
      onRetry={refetch}
      fallbackDataType="[appropriate_type]"
      context="[page description]"
      showTechnicalDetails={true}
    >
      <YourComponentWrapper />
    </DataContainer>
  </Container>
);
```

### 4. Add Demo Data Labels
```jsx
// Add this to any data displays:
<Chip 
  label={isFallbackData ? "Demo Data" : "Live"} 
  color={isFallbackData ? "warning" : "success"} 
  size="small" 
/>
```

## Fallback Data Types by Page:

- **Portfolio**: `portfolio`
- **StockDetail**: `stocks` 
- **MarketOverview**: `stocks`
- **SentimentAnalysis**: `market_sentiment`
- **TradingSignals**: `trading_signals`
- **EarningsCalendar**: `calendar`
- **StockScreener**: `stocks`
- **AnalystInsights**: `stocks`
- **Backtest**: `portfolio`
- **FinancialData**: `stocks`

## Pages Updated ✅:
1. **Dashboard** - All widgets with full DataContainer integration
2. **ServiceHealth** - Added ApiErrorAlert import

## Pages Needing Updates ❌:
3. SentimentAnalysis
4. Portfolio  
5. StockDetail
6. MarketOverview
7. EarningsCalendar
8. StockScreener
9. AnalystInsights  
10. Backtest
11. FinancialData

## Quick Implementation:
1. Apply template to each file
2. Test with CloudFront routing fix
3. Verify fallback data displays during routing issues