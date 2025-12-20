# Professional Chart Components System

## Overview

This is an enterprise-grade financial chart system designed for wealth management platforms. All components follow award-winning UX principles used by Bloomberg, TradingView, and institutional trading platforms.

## Components

### 1. **ProfessionalChartContainer**
High-level wrapper for all charts with consistent styling, headers, and metadata.

```jsx
import ProfessionalChartContainer from './ProfessionalChartContainer';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis } from 'recharts';

<ProfessionalChartContainer
  title="Portfolio Performance"
  subtitle="12-month rolling returns"
  lastUpdated={new Date()}
  dataQuality="real-time"
  footer="Data updated every minute"
>
  <ResponsiveContainer width="100%" height={400}>
    <LineChart data={data}>
      {/* chart content */}
    </LineChart>
  </ResponsiveContainer>
</ProfessionalChartContainer>
```

**Props:**
- `title` (string): Chart title
- `subtitle` (string): Optional subtitle for context
- `children` (ReactNode): Chart content (Recharts component)
- `isLoading` (boolean): Show loading state
- `lastUpdated` (Date): Display "updated X minutes ago"
- `height` (number): Container min height in pixels
- `footer` (string): Additional context text
- `actions` (ReactNode): Action buttons/chips on header
- `dataQuality` (enum): 'real-time' | 'delayed' | 'stale'

### 2. **ProfessionalTooltip**
Replaces default Recharts tooltips with elegant, informative design.

```jsx
import ProfessionalTooltip from './ProfessionalTooltip';

<LineChart data={data}>
  <Tooltip content={<ProfessionalTooltip isPercent={true} />} />
</LineChart>
```

**Props:**
- `isPercent` (boolean): Format values as percentages
- `valuePrefix` (string): Prefix for values (default: '$')
- `showTrend` (boolean): Show trend icons (↗️ ↘️)
- `custom` (function): Custom render function

### 3. **ProfessionalLegend**
Interactive legend with visibility toggling.

```jsx
import ProfessionalLegend from './ProfessionalLegend';

<ProfessionalLegend
  items={[
    { name: 'Portfolio', dataKey: 'portfolio', color: '#3B82F6' },
    { name: 'Benchmark', dataKey: 'benchmark', color: '#10B981' }
  ]}
  orientation="horizontal"
  columns={2}
/>
```

**Props:**
- `items` (array): Legend items with `name`, `dataKey`, `color`
- `orientation` (enum): 'horizontal' | 'vertical'
- `columns` (number): Grid columns for vertical layout
- `onItemToggle` (function): Callback when item visibility changes

## Design System: Colors

### Financial Colors
- **Bullish**: `#10B981` (Emerald green) - Gains, buy signals
- **Bearish**: `#EF4444` (Red) - Losses, sell signals
- **Neutral**: `#6B7280` (Gray) - Hold, wait
- **Primary**: `#3B82F6` (Blue) - Main data
- **Secondary**: `#8B5CF6` (Purple) - Supporting metrics
- **Accent**: `#F59E0B` (Amber) - Warnings, alerts

### Color Usage
```javascript
import { FINANCIAL_COLORS } from '../../theme/chartTheme';

// Use in charts
<Bar dataKey="returns" fill={FINANCIAL_COLORS.bullish.primary} />
```

## Complete Example: Redesigned Portfolio Chart

```jsx
import ProfessionalChartContainer from './ProfessionalChartContainer';
import ProfessionalTooltip from './ProfessionalTooltip';
import ProfessionalLegend from './ProfessionalLegend';
import { FINANCIAL_COLORS, CHART_PRESETS } from '../../theme/chartTheme';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
} from 'recharts';

export default function PortfolioPerformance() {
  const data = [
    { date: 'Jan', portfolio: 100000, benchmark: 98000 },
    { date: 'Feb', portfolio: 102000, benchmark: 99500 },
    // ...
  ];

  return (
    <ProfessionalChartContainer
      title="Cumulative Performance"
      subtitle="Portfolio vs SPY benchmark, 12-month view"
      lastUpdated={new Date()}
      dataQuality="real-time"
      footer="Green area = outperformance vs benchmark"
    >
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart data={data}>
          <defs>
            <linearGradient id="gradientBullish" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={FINANCIAL_COLORS.bullish.primary} stopOpacity={0.3} />
              <stop offset="100%" stopColor={FINANCIAL_COLORS.bullish.primary} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="5 5" stroke="#E5E7EB" />
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip content={<ProfessionalTooltip valuePrefix="$" />} />
          <Line
            type="monotone"
            dataKey="portfolio"
            stroke={FINANCIAL_COLORS.primary.primary}
            strokeWidth={2.5}
            dot={false}
            name="Portfolio"
          />
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke={FINANCIAL_COLORS.secondary.primary}
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={false}
            name="SPY Benchmark"
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Custom legend below chart */}
      <ProfessionalLegend
        items={[
          { name: 'Portfolio', dataKey: 'portfolio', color: FINANCIAL_COLORS.primary.primary },
          { name: 'SPY Benchmark', dataKey: 'benchmark', color: FINANCIAL_COLORS.secondary.primary }
        ]}
        orientation="horizontal"
        sx={{ mt: 3, justifyContent: 'center' }}
      />
    </ProfessionalChartContainer>
  );
}
```

## Implementation Checklist

When converting existing charts to use the new professional system:

- [ ] Wrap chart in `ProfessionalChartContainer`
- [ ] Replace `<Tooltip />` with `<Tooltip content={<ProfessionalTooltip />} />`
- [ ] Replace `<Legend />` with `<ProfessionalLegend items={...} />`
- [ ] Update colors to use `FINANCIAL_COLORS` constants
- [ ] Add gradients using `CHART_GRADIENTS`
- [ ] Update spacing/margins using `CHART_PRESETS`
- [ ] Add `lastUpdated` timestamp
- [ ] Test in both light and dark modes
- [ ] Verify responsive behavior on mobile
- [ ] Add appropriate footer text with insights/interpretation

## Theme Integration

All components automatically adapt to Material-UI theme (light/dark mode):

```jsx
import { useTheme } from '@mui/material';

const MyChart = () => {
  const theme = useTheme();
  // Components automatically use theme colors
};
```

## Animation Presets

```javascript
import { CHART_ANIMATIONS } from '../../theme/chartTheme';

// Default: 600ms fade-in
// Fast: 300ms (for interactive updates)
// Slow: 1000ms (for emphasis)

<Line
  dataKey="value"
  isAnimationActive={true}
  animationDuration={CHART_ANIMATIONS.default.duration}
/>
```

## Typography

All charts use professional financial typography:

```javascript
import { CHART_TYPOGRAPHY } from '../../theme/chartTheme';

// Title: 18px, weight 600
// Subtitle: 13px, weight 400
// Label: 12px, weight 500
// Caption: 11px, weight 400
```

## Accessibility

- All charts use semantic HTML
- Tooltips have proper `role="tooltip"`
- Colors meet WCAG AA contrast requirements
- Legend items are keyboard accessible
- Screen reader support for all components

## Performance Optimization

- Charts use `isAnimationActive={false}` for initial render on mobile
- Lazy loading for charts below the fold
- Responsive containers prevent layout thrashing
- Memoization of expensive components

## Browser Support

- Chrome/Edge: 90+
- Firefox: 88+
- Safari: 14+
- Mobile Safari: iOS 14+

## Common Issues & Solutions

### Chart not updating?
- Ensure `data` prop changes trigger re-render
- Check that key props are unique

### Tooltip positioning wrong?
- Increase `margin` in ResponsiveContainer
- Use `wrapperStyle={{ zIndex: 100 }}` on Tooltip

### Colors not showing?
- Check that gradient IDs don't conflict
- Ensure SVG defs come before chart elements

## Related Files

- `/theme/chartTheme.js` - Color system and constants
- `/theme/chartGradients.js` - Legacy gradient system (deprecated, use chartTheme.js)

## Updates & Roadmap

- [ ] Add animated gauge charts
- [ ] Implement candlestick charts for OHLC
- [ ] Add heatmap visualization
- [ ] Create chart composition builder
- [ ] Add export to PNG/PDF functionality
