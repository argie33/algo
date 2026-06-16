# Error Boundary Architecture & Implementation

**Goal:** Ensure all errors (network, rendering, async) are visible and actionable to users and developers

## Overview

This system ensures that no error silently fails. Every error is:
1. **Caught** at the appropriate level (global, route, section, or query)
2. **Visible** to users and developers (error panels, UI feedback, console logs)
3. **Recoverable** without full page reload (retry, navigate, or reload specific section)
4. **Logged** for debugging and monitoring

## Architecture

### Layer 1: Global Error Handlers (main.jsx)

**Purpose:** Catch unhandled JavaScript errors and promise rejections that would crash the app

**Implementation:**
- `window.addEventListener('error')` → catches sync JavaScript errors
- `window.addEventListener('unhandledrejection')` → catches unhandled promise rejections
- Global console error/warn suppression for benign third-party warnings (ResizeObserver, Recharts dimensions)

**Visible to Users:**
- Unhandled errors show error banner
- Config/startup failures show friendly error page before app loads

**Example Errors Caught:**
- Accessing properties on null/undefined
- Calling functions that don't exist
- Async operations that fail without `.catch()` or `try/catch`
- Module loading failures

### Layer 2: React ErrorBoundary (App.jsx)

**Purpose:** Catch React rendering errors and component lifecycle errors

**Implementation:**
- Wraps entire app in `<ErrorBoundary>`
- Uses React class component lifecycle hooks (`getDerivedStateFromError`, `componentDidCatch`)
- Shows full-page error UI with:
  - Error summary (dev shows full error, prod shows user-friendly message)
  - Error ID for support tickets
  - Try Again button (resets state and reloads page)
  - Go Home button (navigates to home)
  - Contact support link

**Visible to Users:** Full-page error card when a page crashes

**Example Errors Caught:**
- Errors during component render
- Errors in component lifecycle methods
- Errors in event handlers (if using Error Boundary events)

### Layer 3: Route-Level ErrorBoundaries (App.jsx routes)

**Purpose:** Isolate page-level errors so one broken page doesn't crash entire app

**Implementation:**
- Each route wrapped in `<ErrorBoundary>`
- Separate error boundary for each lazy-loaded page component
- Allows user to navigate to different pages even if one is broken

**Visible to Users:** Page shows error UI, but sidebar and navigation still work

**Example Errors Caught:**
- Errors in page components (MarketsHealth, TradeTracker, etc.)
- Errors during page render
- Errors in page-specific hooks

### Layer 4: Data Section ErrorBoundary (DataSectionErrorBoundary.jsx)

**Purpose:** Isolate errors in specific data panels/charts so one broken chart doesn't break entire page

**Implementation:**
- New component `DataSectionErrorBoundary` for wrapping data sections
- Shows inline error card for that section
- Retry button resets state and optionally calls onRetry callback
- Dev mode shows full error details, prod mode shows friendly message

**Visible to Users:** Individual card shows error, rest of page continues to work

**Example Usage:**
```jsx
<DataSectionErrorBoundary section="Market Data" onRetry={() => refetch()}>
  <MarketChart data={data} />
</DataSectionErrorBoundary>
```

**Example Errors Caught:**
- Chart rendering errors (Recharts, custom charts)
- Errors in data transformations
- Errors in event handlers within chart
- Errors from null/undefined data

### Layer 5: Query Error Handling (QuerySection component)

**Purpose:** Show user-friendly error messages for individual API query failures

**Implementation:**
- `<QuerySection>` component wraps `useApiQuery` calls
- Shows loading state, error message, or content
- Error message includes status code and message
- Retry button resets query state

**Visible to Users:** Inline error card with "Retry" button

**Example Usage:**
```jsx
<QuerySection 
  loading={isLoading} 
  error={error} 
  isEmpty={!data?.length} 
  section="Positions"
  onRetry={refetch}
>
  <PositionsTable data={data} />
</QuerySection>
```

### Layer 6: API Error Banner (ApiErrorBanner.jsx)

**Purpose:** Show global API errors from auth failures, config issues, or rate limiting

**Implementation:**
- Watches for global API errors from `api.js`
- Shows banner at top of page
- Includes error type, message, and optional actions

**Visible to Users:** Alert banner below header

**Example Errors Caught:**
- Auth token expired
- CORS errors
- Rate limit exceeded
- Config file missing/failed to load

## Python Dashboard Error Boundaries

### Data Fetch Errors (error_boundary.py)

**Purpose:** Handle API fetch failures gracefully in Python terminal dashboard

**Implementation:**
- `error_summary_panel()` → Shows list of failed fetchers at top of dashboard
- `has_error()`, `get_error_message()` → Check and extract error info safely
- `safe_get()`, `safe_list()` → Access data without crashing on error
- Panel rendering wrapped in try-catch

**Visible to Users:** Red panel at top showing which data fetches failed

**Example:**
```
⚠ Data Fetch Failures (2)
  run: Fetcher run (/api/algo/last-run: Last algo run status) timed out
  pos: Timeout connecting to database - connection pool exhausted
```

### Dashboard Rendering Protection

**Implementation:**
- `run_once()` and `run_watch()` wrap `render_dashboard()` in try-catch
- If render fails, shows error panel instead of crashing
- Dashboard continues to work with last good state

**Visible to Users:** Red error panel instead of blank/corrupted terminal view

## Error Flow Diagram

```
User Action / API Response / Component Mount
     ↓
     ├─→ Promise-based error? → window.addEventListener('unhandledrejection')
     │                           ↓
     │                      [Logged + Visible]
     │
     ├─→ Sync JS error? → window.addEventListener('error')
     │                    ↓
     │                   [Logged + Visible]
     │
     ├─→ Component render error?
     │   ├─→ Page level? → Route ErrorBoundary
     │   │                 ↓
     │   │                [Page error UI]
     │   │
     │   └─→ Section level? → DataSectionErrorBoundary
     │                        ↓
     │                       [Inline card error]
     │
     └─→ API Query error?
         ├─→ Global error (auth, config)? → ApiErrorBanner
         │                                   ↓
         │                                  [Top banner]
         │
         └─→ Section query? → QuerySection
                              ↓
                             [Inline error]
```

## Error Recovery Strategy

### User Can Always...
1. **Retry a section** - Click "Try Again" button on error card
2. **Navigate away** - Use sidebar to go to different page (doesn't crash)
3. **Reload page** - Refresh browser to reset all state
4. **Go home** - Button on full-page error
5. **Contact support** - Error ID provided for support tickets

### Developer Can Always...
1. **See full error stack** - Browser DevTools console + error logging
2. **See error context** - URL, component, operation, data structures
3. **Reproduce error** - Same conditions should produce same error
4. **Debug in isolation** - Can test page/section independently
5. **Monitor errors** - Error logs/dashboard (when logging service integrated)

## Known Limitations

1. **Error Boundary can't catch...**
   - Async errors (use `.catch()` or `try/catch`)
   - Event handler errors (wrap in try-catch)
   - Server-side errors (must be communicated via API)
   - SSR errors (only applies to client-side app)

2. **Error recovery is best-effort**
   - May not fully recover state
   - User may need to refresh page
   - Some errors require backend fix

3. **Error logging requires backend**
   - Currently logs to browser console only
   - Need Sentry/LogRocket integration for production monitoring
   - Error IDs help with support but aren't automatically tracked

## Future Improvements

1. **Error Logging Backend Integration**
   - Integrate Sentry or LogRocket
   - Send all errors with error ID, context, and stack trace
   - Set up error alerts for spike detection

2. **Error Recovery Automation**
   - Auto-retry failed queries with exponential backoff
   - Auto-reload failed sections
   - Guided error recovery (suggest solutions based on error type)

3. **User-Facing Error Analytics**
   - Dashboard showing error trends
   - Most common errors by page/section
   - Error impact assessment (how many users affected?)

4. **Proactive Error Prevention**
   - Type checking (TypeScript)
   - Data validation at all boundaries
   - API response validation
   - Component prop validation

## References

- React ErrorBoundary: https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary
- Promise Error Handling: https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise#error_handling
- Error Logging Best Practices: https://www.sentry.io/blog/the-power-of-error-boundaries/
