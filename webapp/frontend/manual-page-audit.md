# Manual Page Audit Plan

## Pages to Test

### Marketing Pages (Public)
- [ ] Home (/) - Check hero, CTAs, formatting
- [ ] Firm (/firm) - Check dropdowns, content layout
- [ ] Contact (/contact) - Check form, submission
- [ ] About (/about) - Check content display
- [ ] Our Team (/our-team) - Check team grid/cards
- [ ] Mission & Values (/mission-values) - Check layout
- [ ] Research Insights (/research-insights) - Check article list
- [ ] Investment Tools (/investment-tools) - Check tools display
- [ ] Wealth Management (/wealth-management) - Check content
- [ ] Terms (/terms) - Check text rendering
- [ ] Privacy (/privacy) - Check text rendering

### Dashboard Pages (No Auth Required)
- [ ] Markets (/app/markets) - Check data tables, charts
- [ ] Economic (/app/economic) - Check economic indicators
- [ ] Sectors (/app/sectors) - Check sector breakdown
- [ ] Sentiment (/app/sentiment) - Check sentiment visualization
- [ ] Deep Value Stocks (/app/deep-value) - Check stock list, data
- [ ] Trading Signals (/app/trading-signals) - Check signal display
- [ ] Swing Candidates (/app/swing) - Check candidates list
- [ ] Scores (/app/scores) - Check scoring data
- [ ] Backtest (/app/backtests) - Check backtest results

### Protected Pages (Auth Required)
- [ ] Portfolio (/app/portfolio) - Check holdings, data
- [ ] Trade History (/app/trades) - Check trades table
- [ ] Performance (/app/performance) - Check performance metrics
- [ ] System Health (/app/health) - Check health status
- [ ] Audit Log (/app/audit) - Check audit entries
- [ ] Algo Dashboard (/app/algo-dashboard) - Check algo data
- [ ] Pre-Trade Simulator (/app/pre-trade-simulator) - Check simulator
- [ ] Settings (/app/settings) - Check settings form

## Audit Checklist per Page

For each page, check:
1. **Load Time** - Does it load quickly?
2. **Console Errors** - Any JS errors? (F12)
3. **Layout** - Is layout correct/responsive?
4. **Data Display** - Is all data visible? Tables filled?
5. **Text Formatting** - Consistent fonts, spacing, capitalization?
6. **Colors/Theme** - Consistent with design?
7. **Buttons/Links** - Clickable? Styled correctly?
8. **Numbers/Format** - Numbers formatted correctly (decimals, commas)?
9. **Empty States** - Graceful handling when no data?
10. **Mobile Responsiveness** - Works on smaller screens?
