# Frontend Migration Guide

**How to update pages to use new services and hooks**

This guide shows before/after patterns for the most common refactoring tasks.

---

## Pattern 1: Replace Manual Data Fetching with useApiCall()

### ❌ BEFORE (Old Pattern - Boilerplate)

```jsx
import { useState, useEffect } from 'react';
import { api } from '../services/api';

function MyComponent() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await api.get('/api/sectors');
        setData(response.data?.items || response.data?.data);
        setError(null);
      } catch (err) {
        setError(err.message);
        setData(null);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  return <div>{/* Use data */}</div>;
}
```

### ✅ AFTER (New Pattern - Clean)

```jsx
import { useApiCall } from '../hooks/useApiCall';
import { api } from '../services/api';
import { extractData } from '../utils/responseNormalizer';

function MyComponent() {
  const { data, loading, error } = useApiCall(async () => {
    const r = await api.get('/api/sectors');
    return extractData(r);
  });

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  return <div>{/* Use data */}</div>;
}
```

**Benefits:**
- 15 lines → 3 lines
- No try/catch boilerplate
- Automatic response extraction
- Single error state variable

---

## Pattern 2: Replace useQuery with useApiQuery()

### ❌ BEFORE (Inconsistent Response Handling)

```jsx
import { useQuery } from '@tanstack/react-query';
import { api } from '../services/api';

function ScoresPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['scores'],
    queryFn: () => api.get('/api/scores/stockscores')
      .then(r => r.data?.items || r.data?.data),  // <- Guessing response shape!
  });
}
```

### ✅ AFTER (Consistent Pattern with Extraction)

```jsx
import { useApiQuery } from '../hooks/useApiQuery';
import { api } from '../services/api';

function ScoresPage() {
  const { data, loading, error } = useApiQuery(
    ['scores'],
    () => api.get('/api/scores/stockscores')
  );
  // data is already extracted, error handling is standard
}
```

**Benefits:**
- Standardized error/loading naming across all pages
- Response extraction handled automatically
- Consistent query key structure
- Retry logic built-in

---

## Pattern 3: Use Domain-Specific Hooks

### ❌ BEFORE (Tightly Coupled to API)

```jsx
import { useQuery } from '@tanstack/react-query';
import { api } from '../services/api';

function SectorAnalysis() {
  const { data: sectors } = useQuery({
    queryKey: ['sectors', 20],
    queryFn: () => api.get('/api/sectors', { params: { limit: 20 } })
      .then(r => r.data?.items),
  });

  const { data: sentiment } = useQuery({
    queryKey: ['sentiment'],
    queryFn: () => api.get('/api/sentiment/history')
      .then(r => r.data?.data),
  });
}
```

### ✅ AFTER (Decoupled via Domain Hooks)

```jsx
import { useSectors, useMarketSentiment } from '../hooks/useDataApi';

function SectorAnalysis() {
  const { items: sectors } = useSectors({ limit: 20 });
  const { data: sentiment } = useMarketSentiment();
}
```

**Benefits:**
- Pages don't know API URLs
- Easy to change endpoints without touching pages
- Consistent error/loading handling
- Mock friendly for testing

---

## Pattern 4: Replace Inline Response Extraction

### ❌ BEFORE (Scattered Logic, Easy to Break)

```jsx
// Page A: Uses .items
const { data } = useQuery({
  queryFn: () => api.get('/api/scores')
    .then(r => r.data?.items || []),
});

// Page B: Uses .data
const { data } = useQuery({
  queryFn: () => api.get('/api/scores')
    .then(r => r.data?.data || []),
});

// Page C: Uses ???
const { data } = useQuery({
  queryFn: () => api.get('/api/scores'),
});
```

### ✅ AFTER (Single Standardized Function)

```jsx
import { extractData, extractPaginatedData } from '../utils/responseNormalizer';

// All pages use the same function
const { data } = useQuery({
  queryKey: ['scores'],
  queryFn: async () => {
    const r = await api.get('/api/scores');
    return extractData(r);  // <- Always handles all shapes
  },
});

// For paginated responses with metadata:
const { data, pagination } = useQuery({
  queryFn: async () => extractPaginatedData(
    await api.get('/api/scores?limit=20&page=1')
  ),
});
```

**Benefits:**
- One source of truth for response shapes
- Easy to update if API changes
- Clear contract: what extractData expects

---

## Pattern 5: Replace Inline Token Management

### ❌ BEFORE (Scattered Storage)

```jsx
// In AuthContext:
localStorage.setItem('accessToken', token);
localStorage.setItem('idToken', token);

// In api.js:
const token = localStorage.getItem('accessToken') || localStorage.getItem('authToken');

// In apiService.jsx:
const token = localStorage.getItem('dev_session');
```

### ✅ AFTER (Centralized)

```jsx
import { tokenManager } from '../services/tokenManager';

// Anywhere:
tokenManager.setToken(token, 'access');
tokenManager.setToken(idToken, 'id');

// API automatically injects:
const authHeader = tokenManager.getAuthHeader();  // { Authorization: 'Bearer ...' }
```

**Benefits:**
- Single place to manage token keys
- Future encryption ready
- Consistent across entire app
- No more guessing which key is used where

---

## Pattern 6: Use Theme Service

### ❌ BEFORE (Three Places Managing Theme)

```jsx
// main.jsx:
localStorage.setItem('theme', 'dark');

// AppLayout.jsx:
const [theme, setTheme] = useState(() => {
  return localStorage.getItem('theme') === 'light' ? 'light' : 'dark';
});

// algoTheme.js:
const getMode = () => localStorage.getItem('algo-theme') || 'light';
```

### ✅ AFTER (Single Source of Truth)

```jsx
import { theme } from '../services/theme';

// Get current theme:
const currentTheme = theme.getTheme();  // 'dark' or 'light'

// Set theme:
theme.setTheme('light');

// Toggle:
theme.toggleTheme();

// Subscribe to changes:
useEffect(() => {
  return theme.subscribe((newTheme) => {
    console.log('Theme changed to:', newTheme);
  });
}, []);
```

**Benefits:**
- Single source of truth
- Observer pattern enables reactive updates
- Dark is default (no flash of light)
- Encapsulated localStorage logic

---

## Pattern 7: Use Centralized Logger

### ❌ BEFORE (Scattered Logging)

```jsx
// Component A:
const logger = createComponentLogger('ComponentA');
logger.info('Loading');

// Component B:
console.log('Loading');

// Component C:
const _logger = { log: (...args) => console.log(...args) };
```

### ✅ AFTER (Consistent Pattern)

```jsx
import { getLogger } from '../services/logger';

const logger = getLogger('MyComponent');

logger.debug('Detailed debugging info');
logger.info('User action occurred');
logger.warn('Potential issue');
logger.error('Something failed', error, { context });

// Control logging app-wide:
import { setLogLevel } from '../services/logger';
setLogLevel('warn');  // Only show warnings and errors
```

**Benefits:**
- Consistent format across app
- Global log level control
- No console.log scattered everywhere
- Easy to redirect logs to service

---

## Pattern 8: Use Storage Manager

### ❌ BEFORE (Direct localStorage Calls)

```jsx
localStorage.setItem('authToken', token);
localStorage.removeItem('authToken');
const token = localStorage.getItem('authToken');

localStorage.setItem('theme', 'dark');
localStorage.setItem('rememberMe', JSON.stringify(true));
```

### ✅ AFTER (Organized Manager)

```jsx
import { storageToken, storageTheme, storagePreferences } from '../services/storage';

// Tokens:
storageToken.set(token, 'access');
storageToken.clear('access');
const token = storageToken.get('access');

// Theme:
storageTheme.set('dark');
const theme = storageTheme.get();

// Preferences:
storagePreferences.setRememberMe(true);
const remember = storagePreferences.getRememberMe();

// Clear everything:
import { clearAllStorage } from '../services/storage';
clearAllStorage();
```

**Benefits:**
- Organized by category
- Foundation for encryption
- Easy to add validation
- Single place to manage persistence

---

## Migration Checklist

For each page, apply these patterns in order:

- [ ] Replace `useState` data/loading/error with `useApiCall()` or `useApiQuery()`
- [ ] Replace direct `api.get()` calls with domain hooks (`useSectors()`, etc.)
- [ ] Replace inline response extraction with `extractData()`
- [ ] Remove inline `console.log()`, use `getLogger()`
- [ ] Replace inline `localStorage` calls with `storageToken`/`storageTheme`
- [ ] Test that page still works after refactoring
- [ ] Verify no console errors or warnings

---

## Examples by Page Type

### Simple Data List Page (e.g., Industries, Commodities)

```jsx
// After migration:
import { useQuery } from '@tanstack/react-query';
import { useIndustries } from '../hooks/useDataApi';
import { getLogger } from '../services/logger';

const logger = getLogger('IndustriesPage');

export default function IndustriesPage() {
  const { data: industries, loading, error } = useIndustries({ limit: 500 });

  if (loading) return <LoadingState />;
  if (error) return <ErrorState error={error} />;

  return (
    <div>
      {industries.map(ind => (
        <IndustryCard key={ind.id} industry={ind} />
      ))}
    </div>
  );
}
```

### Multi-Data Page (e.g., SectorAnalysis, Dashboard)

```jsx
// After migration:
import { useSectors, useSectorTrend, useMarketSentiment } from '../hooks/useDataApi';
import { getLogger } from '../services/logger';

const logger = getLogger('SectorAnalysis');

export default function SectorAnalysis() {
  const { items: sectors, loading: sectorsLoading } = useSectors({ limit: 500 });
  const { data: sentiment, loading: sentimentLoading } = useMarketSentiment();

  const allLoading = sectorsLoading || sentimentLoading;

  if (allLoading) return <LoadingState />;

  return (
    <>
      <SectorGrid sectors={sectors} />
      <SentimentChart data={sentiment} />
    </>
  );
}
```

---

## FAQ

**Q: Do I need to update all pages at once?**  
A: No. Start with high-traffic pages first (Dashboard, Markets, Sectors). Low-traffic pages can wait.

**Q: Will old and new patterns work together?**  
A: Yes. You can gradually migrate. Old pages will continue to work while new ones use new patterns.

**Q: What if the API response shape doesn't match responseNormalizer?**  
A: Update `extractData()` to handle the new shape. This is actually the GOAL - discover inconsistencies and fix them once.

**Q: Can I test pages after refactoring?**  
A: Yes. Run `npm run dev` locally. The dev API on port 3001 works with all pages.

**Q: What about pages with custom logic?**  
A: Use `useApiCall()` + custom processing. Example:
```jsx
const { data, loading, error } = useApiCall(async () => {
  const r = await api.get('/api/sectors');
  const sectors = extractData(r);
  return sectors.filter(s => s.composite_score > 50);  // <- Custom filter
});
```

---

## Progress Tracking

As you migrate pages, mark them here:

- [ ] SectorAnalysis
- [ ] MarketOverview
- [ ] MarketsHealth
- [ ] Sentiment
- [ ] DeepValueStocks
- [ ] PortfolioDashboard
- [ ] ScoresDashboard
- [ ] Commodities
- [ ] Economic
- [ ] _And more..._

---

**Start with Pattern 1 + Pattern 2 for fastest wins. Domain hooks (Pattern 3) come next.**
