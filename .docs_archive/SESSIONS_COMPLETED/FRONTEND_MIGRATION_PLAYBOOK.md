# Frontend Migration Playbook - EXECUTABLE

**Status: Production-Ready Infrastructure + 2 Pages Migrated** ✅

This playbook is ready to be executed for ALL remaining pages.

---

## Quick Summary: What We've Done

✅ **Phase 1: Infrastructure (15/15)** - All services created, tested, building
✅ **Phase 2: Abstraction Layer (6/6)** - Domain hooks created
✅ **Phase 3 In Progress: Page Migrations**
   - ✅ Commodities page - MIGRATED
   - ✅ StockDetail page - MIGRATED  
   - 🔄 Sentiment page - IN PROGRESS (just needs query updates)
   - 📋 13+ more pages ready for migration

---

## The Migration Pattern (Copy-Paste Template)

### **Step 1: Update Imports**

Replace this:
```jsx
import { useQuery } from '@tanstack/react-query';
import { api } from '../services/api';
```

With this:
```jsx
import { useApiQuery } from '../hooks/useApiQuery';
import { useSectors, useStockScores, useSignals, // ... other domain hooks
} from '../hooks/useDataApi';
import { extractData } from '../utils/responseNormalizer';
import { api } from '../services/api';
```

### **Step 2: Replace useQuery Calls**

#### Pattern A: Simple List Fetch

❌ **Before:**
```jsx
const { data, isLoading } = useQuery({
  queryKey: ['sectors'],
  queryFn: () => api.get('/api/sectors')
    .then(r => r.data?.items || r.data?.data || []),
});
```

✅ **After (Use Domain Hook):**
```jsx
const { items: data, loading: isLoading } = useSectors();
```

---

#### Pattern B: Fetches with Parameters

❌ **Before:**
```jsx
const { data, isLoading } = useQuery({
  queryKey: ['scores', limit],
  queryFn: () => api.get(`/api/scores/stockscores?limit=${limit}`)
    .then(r => r.data?.items || []),
});
```

✅ **After (Use Domain Hook with Params):**
```jsx
const { items: data, loading: isLoading } = useStockScores({ limit });
```

---

#### Pattern C: Complex Custom Queries

❌ **Before:**
```jsx
const { data, isLoading, error } = useQuery({
  queryKey: ['custom-data'],
  queryFn: () => api.get('/api/custom')
    .then(r => r.data?.items || r.data?.data || r.data || []),
});
```

✅ **After (Use useApiQuery):**
```jsx
const { data, loading: isLoading, error } = useApiQuery(
  ['custom-data'],
  () => api.get('/api/custom')
);
```

---

#### Pattern D: Conditional Fetches

❌ **Before:**
```jsx
const { data, isLoading } = useQuery({
  queryKey: ['symbol-data', symbol],
  queryFn: () => api.get(`/api/prices/history/${symbol}`),
  enabled: !!symbol,
});
```

✅ **After:**
```jsx
const { data, loading: isLoading } = useApiQuery(
  ['symbol-data', symbol],
  () => api.get(`/api/prices/history/${symbol}`),
  { enabled: !!symbol }
);
```

---

### **Step 3: Update State References**

Replace:
- `.isLoading` → `.loading`
- `.isFetching` → `.isFetching` (stays same)
- `.error` → `.error` (stays same)
- `.data` → `.data` (stays same)

For paginated responses:
```jsx
// Before:
const { data, isLoading } = useQuery({
  queryFn: () => api.get('/api/sectors')
    .then(r => ({ items: r.data?.items, total: r.data?.total }))
});

// After:
const { items, pagination, loading } = useApiPaginatedQuery(
  ['sectors'],
  () => api.get('/api/sectors')
);
```

---

### **Step 4: Test & Build**

```bash
npm run build
```

If build passes: ✅ Done! Page is migrated.

---

## Pages Ready for Migration

### **Tier 1: Simple (15-30 mins each)**
- [ ] Industries
- [ ] Commodities ✅ DONE
- [ ] Economic
- [ ] Backtests

### **Tier 2: Moderate (30-45 mins each)**
- [ ] StockDetail ✅ DONE
- [ ] PortfolioDashboard
- [ ] ScoresDashboard
- [ ] TradingSignals

### **Tier 3: Complex (45-90 mins each)**
- [ ] Sentiment (in progress)
- [ ] SectorAnalysis (1491 lines)
- [ ] MarketOverview (2118 lines)
- [ ] MarketsHealth (1765 lines)

---

## Critical Path: Get to MVP

To get the site fully migrated quickly:

### **Day 1: Tier 1 Pages (Simple Fetches)**
**Estimated: 2-3 hours for all 4 pages**

1. **Industries** (~100 lines, 1 query)
   - Replace: `useQuery → useIndustries()`
   - Time: 10 mins

2. **Economic** (~150 lines, 1-2 queries)
   - Replace: `useQuery → useEconomicData()`
   - Time: 15 mins

3. **Backtests** (~100 lines, 1 query)
   - Custom: `useApiQuery(['backtests'], () => api.get('/api/research/backtests'))`
   - Time: 15 mins

All should pass build immediately.

### **Day 2: Tier 2 Pages (Moderate Complexity)**
**Estimated: 3-4 hours for all 4 pages**

1. **PortfolioDashboard** (~200 lines, 3-4 queries)
   - Use hooks for different data sources
   - Time: 30 mins

2. **ScoresDashboard** (~250 lines, 2-3 queries)
   - Use `useStockScores()` + supplementary hooks
   - Time: 30 mins

3. **TradingSignals** (~300 lines, 2 queries)
   - Use `useSignals()` + filters
   - Time: 30 mins

### **Day 3: Tier 3 Pages (Complex)**
**Estimated: 4-6 hours for 4 pages**

These pages have 10+ queries each. Spread across day:

1. **Sentiment** (1552 lines, 4+ queries)
   - Use `useMarketSentiment()`, `useApiQuery()` for rest
   - Time: 60 mins

2. **SectorAnalysis** (1491 lines, 6+ queries)
   - Bulk replacements + fixes
   - Time: 90 mins

3. **MarketOverview** (2118 lines, 8+ queries)
   - Largest page, multiple refactors
   - Time: 90 mins

4. **MarketsHealth** (1765 lines, 5+ queries)
   - Similar pattern to MarketOverview
   - Time: 90 mins

---

## Automated Migration Script

For developers doing migrations, here's a copy-paste automation:

### **Find & Replace #1: Simple useQuery with api.get**
Find: `const { data.*? } = useQuery({\n.*?queryKey:.*?\n.*?queryFn: \(\) => api.get\('([^']+)'\)`
Replace: `const { data, loading } = useApiQuery(['key'], () => api.get('$1')`

### **Find & Replace #2: Update isLoading**
Find: `isLoading`
Replace: `loading` (in component body only)

### **Find & Replace #3: Update useQuery import**
Find: `import { useQuery } from '@tanstack/react-query';`
Replace: `import { useApiQuery } from '../hooks/useApiQuery';`

---

## Checklist Per Page

When migrating a page:

- [ ] Read the page to identify all useQuery calls
- [ ] Check if there's a domain hook available (useSectors, useSignals, etc.)
- [ ] Update imports (useApiQuery, domain hooks, responseNormalizer)
- [ ] Replace useQuery calls with new hooks
- [ ] Update state references (isLoading → loading)
- [ ] Run `npm run build`
- [ ] Verify build passes without errors
- [ ] Mark page as done in list

---

## Estimated Total Time

| Phase | Pages | Time | Status |
|-------|-------|------|--------|
| Phase 1 | Infrastructure | 4 hours | ✅ Done |
| Phase 2 | Abstraction | 2 hours | ✅ Done |
| **Phase 3** | **Tier 1-3 Pages** | **~12-15 hours** | 🔄 In Progress |
| **Phase 4** | **Edge Cases + Polish** | **~5 hours** | ⏸️ Queue |
| **TOTAL** | **~23-26 hours** | - | - |

**Parallel Work:** Multiple developers can migrate different pages simultaneously.
**Fastest Path:** 2 developers × 12 hours = 6 wall-clock hours to complete all pages.

---

## Success Criteria

Each migrated page must:
- ✅ Pass `npm run build` without errors
- ✅ Use only `useApiQuery` or domain hooks (no direct `useQuery`)
- ✅ Use `extractData()` for response extraction (no inline guessing)
- ✅ Replace `.isLoading` with `.loading`
- ✅ No unused imports remaining

---

## Known Issues to Watch

### Issue 1: API Response Shapes
Some endpoints might return slightly different structures.
**Solution:** Update `responseNormalizer.js` to handle the shape, then all pages using that endpoint work.

### Issue 2: Missing Domain Hooks
If no domain hook exists for an endpoint, use `useApiQuery()` directly.
**Solution:** Create the domain hook once, then all pages using it benefit.

### Issue 3: Complex Query Logic
Some pages have computed queries or multi-stage fetches.
**Solution:** Use `useApiCall()` for one-off logic, or create specialized hooks if reused.

---

## After All Pages Are Migrated

Once all pages use the new patterns:

1. **Delete old useQuery imports** from pages
2. **Delete apiService.jsx** (deprecated)
3. **Run full test suite**
4. **Deploy with confidence** - All pages use consistent patterns

---

## Reference: All Domain Hooks Available

```javascript
import {
  useSectors,           // GET /api/sectors
  useStockScores,       // GET /api/scores/stockscores
  useSignals,           // GET /api/signals/list
  useMarketSentiment,   // GET /api/sentiment/history
  usePriceHistory,      // GET /api/price/history/:symbol
  usePortfolioOptimization, // POST /api/optimization/analysis
  useIndustries,        // GET /api/industries
  useSectorTrend,       // GET /api/sectors/trend/sector/:sector
  useEconomicData,      // GET /api/economic
  useCommodities,       // GET /api/commodities/prices
  useServiceHealth,     // GET /api/health
} from '../hooks/useDataApi';
```

For endpoints without domain hooks, use `useApiQuery()` directly.

---

## Go execute this playbook page-by-page!

Questions during migration? Check FRONTEND_MIGRATION_GUIDE.md for detailed patterns.

**Target: All pages migrated by EOD.** 💪
