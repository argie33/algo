# DevTools Console Warnings Fix Guide

## Issue Summary
The application displays 15+ warnings on initial load in Chrome DevTools:
```
The width(-1) and height(-1) of chart should be greater than 0
```

## Root Cause
Recharts `ResponsiveContainer` components render before their parent containers are sized, resulting in ResizeObserver detecting negative dimensions. This occurs because:

1. **Chart containers lack `minWidth: 0`** - In flex/grid layouts, child elements inherit `min-width: auto` by default, which prevents them from sizing below their content width. Adding `minWidth: 0` allows proper flex sizing.

2. **Parent containers don't have explicit sizing** - Some chart wrappers rely on implicit sizing that hasn't computed yet when ResponsiveContainer renders.

3. **Tabs render conditionally** - Charts in hidden tabs (like PerformanceTab, RiskTab) render with measured dimensions even though they're not visible.

## Solution Overview

Add `minWidth: 0` to all parent `<div>` and `<Box>` elements that directly contain `ResponsiveContainer`.

### Pattern 1: Styled divs (MarketsHealth.jsx, PerformanceTab.jsx)
```jsx
// BEFORE
<div style={{ height: 220 }}>
  <ResponsiveContainer width="100%" height="100%">
```

// AFTER
<div style={{ height: 220, minWidth: 0 }}>
  <ResponsiveContainer width="100%" height="100%">
```

### Pattern 2: MUI Box components (MarketInternals.jsx, PETrendChart.jsx, McClellanOscillatorChart.jsx, MarketVolatility.jsx)
```jsx
// BEFORE
<Box sx={{ height: 300, width: "100%" }}>
  <ResponsiveContainer width="100%" height="100%">

// AFTER
<Box sx={{ height: 300, width: "100%", minWidth: 0 }}>
  <ResponsiveContainer width="100%" height="100%">
```

## Files Requiring Fixes

### High Priority (Most warnings come from these)
1. **src/pages/MarketsHealth.jsx** (10+ ResponsiveContainer instances)
   - Sparkline chart container (line ~407)
   - Exposure composite (line ~605)
   - Breadth bar chart (line ~652)
   - New highs/lows chart (line ~711)
   - AAII sentiment (line ~763)
   - McClellan oscillator (line ~884)
   - Monthly returns (line ~1001)
   - Yield curve (line ~1381)
   - Defensive/cyclical strength (line ~1277)
   - Sector rotation scatter (line ~1191)

2. **src/pages/components/PerformanceTab.jsx** (2 charts)
   - Equity curve chart (line ~74)
   - Drawdown chart (line ~101)

3. **src/pages/components/RiskTab.jsx** (check for similar patterns)

### Medium Priority (Supporting components)
4. **src/components/MarketInternals.jsx**
   - Breadth chart (line ~196)
   - MA analysis chart (line ~261)

5. **src/components/PETrendChart.jsx**
   - Price trend chart (line ~41) - needs Box wrapper

6. **src/components/McClellanOscillatorChart.jsx**
   - Oscillator chart (line ~124) - already has Box, add minWidth

7. **src/components/HistoricalPriceChart.jsx**
   - Price chart (line ~103) - needs Box wrapper
   - Volume chart (line ~139) - needs Box wrapper

8. **src/components/MarketVolatility.jsx**
   - Volatility metrics chart (line ~149)

## Verification

After applying fixes, run:
```bash
node capture-browser-logs.mjs
```

Expected outcome:
- Chart sizing warnings reduced to 0 or minimal (may have 1-2 during initial render)
- "AMPLIFY: Configured with fallback values" warning remains (expected behavior)
- No page errors or network failures
- All charts render correctly and responsively

## Additional Improvements (Optional)

### 1. Prevent Rendering of Hidden Tab Charts
Wrap charts in `useEffect` that only renders when visible:
```jsx
const [isVisible, setIsVisible] = useState(false);
useEffect(() => { setIsVisible(true); }, []);

{isVisible && <PerformanceTab ... />}
```

### 2. Use ResizeObserver Wrapper
Create a higher-order component that waits for parent sizing:
```jsx
function ResponsiveChartWrapper({ children }) {
  const [ready, setReady] = useState(false);
  const ref = useRef();
  
  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      if (entries[0].contentRect.width > 0) {
        setReady(true);
        observer.disconnect();
      }
    });
    observer.observe(ref.current);
  }, []);
  
  return (
    <div ref={ref}>
      {ready && children}
    </div>
  );
}
```

### 3. Add Width Constraint
For Paper/Card components, add explicit width:
```jsx
<Paper sx={{ width: "100%", p: 2 }}>
  <Box sx={{ width: "100%", height: 300, minWidth: 0 }}>
    <ResponsiveContainer width="100%" height="100%">
```

## Why This Works

CSS Flexbox/Grid have a default `min-width: auto` on flex items. This prevents them from shrinking below their content width. When you set `minWidth: 0`, it overrides this default, allowing the element to shrink to fit the available space.

When ResponsiveContainer renders before the parent has calculated its width, it reads width=0 from the DOM, then applies the percentage (100% of 0 = 0), which ResizeObserver reports as negative after removing padding/margins.

Setting `minWidth: 0` ensures the parent properly sizes itself before ResponsiveContainer computes its dimensions.

## References
- [Recharts docs on ResponsiveContainer](https://recharts.org/api/ResponsiveContainer)
- [CSS Flexbox minWidth behavior](https://developer.mozilla.org/en-US/docs/Web/CSS/min-width)
- [ResizeObserver API](https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver)
