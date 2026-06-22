# Error Boundary Architecture

This document outlines the error boundary strategy for the Algo Trading Dashboard to ensure all failures are visible and recoverable.

## Architecture

### 1. Global ErrorBoundary (App.jsx wrapper)

- **Location:** Wraps entire app in `main.jsx`
- **Catches:** React rendering errors, unhandled promise rejections, window errors
- **Display:** Full-page error UI with error ID for support
- **Recovery:** Page reload or navigation to home

### 2. Route-Level ErrorBoundaries

- **Location:** Each route in `App.jsx`
- **Catches:** Errors during page render, lazy-loaded component failures
- **Display:** Page-level error UI
- **Recovery:** Try again, go home, or retry from error

### 3. Data Section ErrorBoundary

- **Component:** `DataSectionErrorBoundary.jsx`
- **Use:** Wrap individual data panels/sections that fetch or render data
- **Catches:** Errors in charts, tables, specific data visualizations
- **Display:** Card-level error with section name and retry
- **Recovery:** Retry just that section without full page reload

### 4. API Error Banner

- **Location:** Top of layout in `AppLayout.jsx`
- **Catches:** Global API errors from auth, config, or major endpoints
- **Display:** Alert banner with error context
- **Recovery:** Retry/dismiss

### 5. Query Error Boundary

- **Component:** `QueryErrorBoundary.jsx` / `QuerySection`
- **Use:** Wrap individual `useApiQuery` hooks
- **Catches:** Individual query failures
- **Display:** Inline error message with retry button
- **Recovery:** Retry the specific query

## When to Use Each

| Situation             | Boundary                 | Example                                               |
| --------------------- | ------------------------ | ----------------------------------------------------- |
| Page component fails  | Route-level + Global     | `MarketsHealth` page error → shows error page         |
| Chart fails to render | DataSectionErrorBoundary | Chart with malformed data → shows inline error        |
| API query fails       | QuerySection             | Fetching market data → shows "failed to load" message |
| Auth/config fails     | APIErrorBanner           | Cognito token expired → shows auth error              |
| Promise rejection     | Window handler           | Async operation fails silently → logs to console      |
| Synchronous JS error  | ErrorBoundary            | Accessing undefined property → shows error UI         |

## Implementation Checklist

- [x] Global error handler for window errors
- [x] Global unhandledrejection handler
- [x] Route-level ErrorBoundaries
- [x] ErrorBoundary component with full error details in dev
- [x] QueryErrorBoundary for individual queries
- [x] APIErrorBanner for global API errors
- [x] DataSectionErrorBoundary for data panels
- [ ] Add DataSectionErrorBoundary to high-risk pages (charts, tables)
- [ ] Document error boundary usage in each page
- [ ] Add error logging integration (Sentry/LogRocket)

## Adding Error Boundaries to New Pages

1. **Import the boundary:**

   ```jsx
   import DataSectionErrorBoundary from "../components/DataSectionErrorBoundary";
   ```

2. **Wrap data sections:**

   ```jsx
   <DataSectionErrorBoundary section="Market Data" onRetry={() => refetch()}>
     <Chart data={data} />
   </DataSectionErrorBoundary>
   ```

3. **For queries:**
   ```jsx
   <QuerySection
     loading={isLoading}
     error={error}
     isEmpty={!data?.length}
     section="Positions"
   >
     <PositionsTable data={data} />
   </QuerySection>
   ```

## Testing Error Boundaries

### Throw an error in development:

```jsx
if (process.env.NODE_ENV === "development" && Math.random() < 0.1) {
  throw new Error("Test error boundary");
}
```

### Check console:

- Errors should appear in browser DevTools console
- Should see error ID and context
- Should see component stack in dev mode

### Visual verification:

- Error UI should appear instead of blank/broken component
- Retry button should work
- Error should be recoverable without page reload

## Error Logging Integration

Once integrated with error tracking service (Sentry, LogRocket, Bugsnag):

```jsx
import { captureException } from "@sentry/react";

// In ErrorBoundary.componentDidCatch():
if (!isDev) {
  captureException(error, {
    contexts: {
      react: {
        componentStack: errorInfo.componentStack,
      },
    },
    tags: {
      errorBoundary: "route" | "section" | "query",
    },
  });
}
```

## Monitoring

Check error logs regularly for:

1. Common error types (null reference, 404, timeout)
2. Affected pages/sections
3. User impact (how many times did error occur?)
4. Error trends (increasing/decreasing?)

## FAQ

**Q: Why multiple error boundaries?**
A: Different errors need different recovery strategies. A full-page error needs reload, but a chart error just needs retry.

**Q: What about loading states?**
A: Use `<QuerySection loading={...}>` or custom loading component. Error boundary is only for unexpected errors.

**Q: Can I suppress errors?**
A: No. Always show errors to users. Suppressing leads to silent failures and confused users.

**Q: How do I test error boundaries?**
A: Throw errors in development or modify data to cause errors (null data, wrong types).
