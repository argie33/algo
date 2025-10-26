# Institutional Dashboard - Quick Start Guide

## Access the Dashboard

### Primary Route
```
Navigate to: /portfolio
```

This is now the **default institutional dashboard** (you can use `/portfolio/classic` for the original version if needed).

---

## Dashboard Overview

### 1️⃣ Performance Summary Header (Top)

Four key metrics that tell the story:

| Metric | What It Means | Good Range |
|--------|---------------|-----------|
| **Total Return** | Overall portfolio performance | > 10% annually |
| **YTD Return** | 2025 performance so far | > 5% year-to-date |
| **Volatility** | How much the portfolio swings | 10-20% is moderate |
| **Sharpe Ratio** | Risk-adjusted return | > 1.0 is good |

✨ **What you see**: Beautiful gradient cards with color-coded metrics

---

### 2️⃣ Main Navigation Tabs (4 Sections)

#### **Tab 1: Performance & Attribution** 📈
*Focus: How are we making money?*

Shows:
- Performance breakdown (where returns come from)
- Return metrics (best day, worst day, win rate)
- Holdings table with gains/losses

**Key insight**: Identifies your top performing and underperforming holdings

#### **Tab 2: Risk Analysis** ⚠️
*Focus: What are the risks?*

Shows:
- Maximum drawdown (worst loss ever)
- Risk-adjusted returns (Sharpe, Sortino, etc.)
- Drawdown progression over time

**Key insight**: Understand your downside risk and recovery potential

#### **Tab 3: Portfolio Allocation** 🎯
*Focus: How is the money positioned?*

Shows:
- Sector allocation heatmap
- Sector momentum (trending up/down)
- Correlation with market (diversification check)

**Key insight**: Spot concentration risks and sector imbalances

#### **Tab 4: Comparative Analytics** 📊
*Focus: How do we compare to the S&P 500?*

Shows:
- Alpha (are we beating the market?)
- Beta (how much more/less risky than market)
- Tracking error (how different from benchmark)
- Correlation (how we move together with SPY)

**Key insight**: Understand relative performance and market sensitivity

---

## Key Metrics Explained Simply

### Performance
- **Total Return**: Bottom line - how much money did we make?
- **YTD**: Performance since January 1st
- **Best/Worst Day**: Biggest single-day gain and loss

### Risk
- **Volatility**: How jumpy/stable is the portfolio? (Higher = more variation)
- **Max Drawdown**: Worst peak-to-trough loss (e.g., -18.5% from peak)
- **Beta**: Moves with market? 1.0 = same as SPY, 0.8 = less volatile than SPY

### Return Quality
- **Sharpe Ratio**: Return per unit of risk (>1.5 is professional-grade)
- **Sortino Ratio**: Return per downside-only risk (better than Sharpe for comparison)
- **Alpha**: Are you beating the benchmark? (Positive alpha = outperformance)

### Diversification
- **Effective Positions**: How "spread out" is the portfolio?
- **Top 5 Weight**: How much in top 5 holdings? (>60% = concentrated)
- **Sector Correlation**: Are sectors too similar? (>0.8 = correlated/risky)

---

## Reading the Dashboard: Examples

### Example 1: The Green Metrics Dashboard
```
✅ Sharpe Ratio: 1.85 (Green)
✅ Max Drawdown: 12.5% (Acceptable)
✅ Volatility: 14.2% (Moderate)
✅ Alpha: +2.3% (Outperforming)
```
**Interpretation**: Strong risk-adjusted returns with good diversification

### Example 2: The Risk Dashboard
```
⚠️ Max Drawdown: 28.3% (Red - High)
⚠️ Current Drawdown: -8.2% (Down from peak)
⚠️ Top 5 Weight: 72% (Red - Concentrated)
✅ Sharpe Ratio: 0.95 (Decent but not great)
```
**Interpretation**: High concentration risk, current down market, need to diversify

### Example 3: The Benchmark Dashboard
```
✅ Alpha: +3.2% (Beating SPY)
⚠️ Beta: 1.4 (More volatile than SPY)
✅ Tracking Error: 8.5% (Differentiated)
⚠️ Correlation: 0.92 (Highly correlated with SPY)
```
**Interpretation**: Outperforming but with higher risk; consider if diversified enough

---

## Color Coding Quick Reference

### Metric Cards
- **Green Border** = Positive/Good metric
- **Red Border** = Negative/Concerning metric
- **Yellow Border** = Warning/Caution needed
- **Blue Border** = Neutral/Informational

### Sector Table
- 🟢 **Green**: Good diversification (low correlation)
- 🟡 **Yellow**: Moderate diversification
- 🔴 **Red**: Concerning (high correlation/concentration)

### Text Colors
- 🟢 Green numbers = Good performance
- 🔴 Red numbers = Losses or high risk
- 🟡 Yellow numbers = Warning/moderate concern

---

## Key Actions

### 📊 Refresh Data
Click the **Refresh** button to get latest metrics (updates from API)

### 📥 Export Data
Click the **Export** button (coming soon) to download:
- PDF report (institutional quality)
- Excel spreadsheet (for analysis)
- CSV data (for other tools)

### 📱 Mobile Access
Dashboard works on:
- ✅ Desktop (full experience)
- ✅ Tablet (optimized layout)
- ✅ Mobile (stacked, scrollable)

### 🌓 Dark Mode
Switch your app theme in settings - dashboard adapts perfectly

---

## Understanding the Holdings Table

Click a row to see position detail:

| Column | Meaning |
|--------|---------|
| **Symbol** | Ticker symbol (e.g., AAPL) |
| **Sector** | Industry (Tech, Healthcare, etc.) |
| **Weight %** | % of portfolio in this holding |
| **Value** | Dollar amount invested |
| **Gain/Loss %** | Total return on position |
| **YTD Gain %** | 2025 performance of position |
| **Beta** | How volatile vs market |
| **Correlation** | Moves with SPY? (>0.8 = yes) |

**Example**:
```
AAPL | Tech | 18.5% | $185K | +15.6% | +4.8% | 1.2 | 0.92
```
Interpretation: Apple is 18.5% of portfolio, up 15.6% overall, beta of 1.2 (20% more volatile than market), highly correlated with SPY

---

## Common Questions

### Q: What does "Effective Positions" mean?
**A**: If you have 25 holdings but top 5 are 70% of portfolio, effective positions might be 8. It accounts for concentration.

### Q: Is my Sharpe Ratio good?
**A**:
- < 0.5 = Poor
- 0.5-1.0 = Fair
- 1.0-1.5 = Good
- 1.5-2.0 = Very Good
- > 2.0 = Excellent (professional-grade)

### Q: What's a good correlation?
**A**:
- < 0.5 = Independent (great diversification)
- 0.5-0.8 = Some correlation (acceptable)
- > 0.8 = Highly correlated (concentration risk)

### Q: My metrics show all zeros - what's wrong?
**A**: Portfolio likely has no holdings or insufficient historical data. Add positions and wait 30+ days for metrics to calculate.

### Q: Why is my Beta 1.4 but correlation only 0.92?
**A**: You move 40% more than the market (1.4 beta) but don't move in lock-step (0.92 correlation). You have alpha - you're making different choices than the benchmark.

---

## Interpreting the 4 Tabs

### Tab 1: Ask "Are we making money the right way?"
✅ If you see:
- High Sharpe Ratio (>1.5)
- Positive top day numbers
- Good win rate (>55%)
- Concentrated gains in quality positions

❌ If you see:
- Low Sharpe Ratio (<0.7)
- Few top-performing days
- Low win rate (<50%)
- Scattered small gains

### Tab 2: Ask "Can we afford this much risk?"
✅ If you see:
- Max Drawdown < 20%
- Current Drawdown < 10%
- Sharpe + Sortino > 1.0
- Beta close to 1.0

❌ If you see:
- Max Drawdown > 30%
- Multiple 20%+ drawdowns
- Recovery time > 6 months
- High beta (>1.5)

### Tab 3: Ask "Is the portfolio properly positioned?"
✅ If you see:
- 8+ different sectors
- No sector > 30%
- Low correlation (mostly < 0.75)
- Diversification Ratio > 1.1

❌ If you see:
- Only 3-4 sectors
- Top sector > 40%
- Most sectors > 0.85 correlation
- Top 5 holdings > 60% of portfolio

### Tab 4: Ask "Are we beating the benchmark?"
✅ If you see:
- Alpha > +1.5%
- Tracking Error > 5% (active bet)
- Correlation < 0.9 (differentiated)
- Consistent outperformance

❌ If you see:
- Alpha < 0% (underperforming)
- Very high correlation (0.95+)
- Tracking Error < 3% (closet indexing)
- Underperformance vs SPY

---

## Quick Diagnostic Guide

### "My portfolio is underperforming"
1. Check Tab 1 → Sharpe Ratio (vs market it beats?)
2. Check Tab 2 → Beta (am I taking extra risk?)
3. Check Tab 4 → Alpha (am I actually underperforming?)
4. Check Holdings → Are top performers underweight?

### "I'm worried about risk"
1. Check Tab 2 → Max Drawdown (what's acceptable to you?)
2. Check Tab 2 → Downside Deviation (cushion above)
3. Check Tab 3 → Concentration (is it too narrow?)
4. Check Tab 2 → Beta (how much market risk?)

### "Portfolio seems concentrated"
1. Check Tab 3 → Top 5 Weight (is it >60%?)
2. Check Holdings → Any sectors >30%?
3. Check Tab 3 → Herfindahl Index
4. Action: Consider trimming top performers, adding quality new positions

### "Volatility is too high"
1. Check Tab 2 → Volatility (what's your target?)
2. Check Tab 2 → Beta (am I over-leveraged?)
3. Check Holdings → Add defensive positions?
4. Check Tab 3 → Correlation → Add uncorrelated assets?

---

## Professional Benchmarks

### For Individual Investors
- Target Return: 8-10% annually
- Target Sharpe: 0.8-1.2
- Target Max Drawdown: <15%
- Target Volatility: 10-15%

### For Asset Managers (Benchmark)
- Target Return: 12-15% annually
- Target Sharpe: 1.5-2.0
- Target Max Drawdown: <10%
- Target Volatility: 12-18%

### For Hedge Funds
- Target Return: 15-25% annually
- Target Sharpe: 1.8-3.0+
- Target Max Drawdown: <5-8%
- Target Volatility: 8-15%

---

## Next Steps

1. **Navigate to `/portfolio`** in your app
2. **Explore the 4 tabs** to understand your portfolio
3. **Check the bottom section** for diversification metrics
4. **Use the Holdings table** to identify concentrated positions
5. **Compare yourself to SPY** on Tab 4

---

## Support

### For questions about:
- **How to read metrics**: See "Key Metrics Explained" section above
- **What values are normal**: See "Professional Benchmarks" section
- **How to improve portfolio**: Check "Quick Diagnostic Guide"
- **Technical issues**: Contact support team

### Dashboard Version
- **Institutional**: `/portfolio` ← Default (you are here)
- **Classic**: `/portfolio/classic` (older version)
- **Optimization**: `/portfolio/optimize` (portfolio rebalancing tool)

---

**Your institutional-grade portfolio analytics dashboard is ready!** 🚀

*Dashboard updated: October 26, 2025*
*Status: Production Ready ✅*
