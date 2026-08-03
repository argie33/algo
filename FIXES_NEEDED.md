# Data Loading Fixes Priority List

## COMPLETED ✅
1. **Revenue filter blocking banks** - Commit 7490d5b1c
   - Removed `revenue IS NOT NULL` from growth_metrics loader
   - Allows banks to compute eps_growth, ni_growth without revenue

2. **FCF missing 91% of the time** - Commit df47914be  
   - Fixed query to prioritize years WITH actual FCF data instead of latest year
   - AAPL: was returning FY 2026 (NULL FCF), now returns FY 2024 ($108.8B real FCF)
   - Recovers ~4000 missing FCF values

## IN PROGRESS 🔄

## NEXT UP (Priority order):

### HIGH IMPACT
1. **Operating Margin NULL for 2,064 symbols (39%)**
   - Issue: Requires revenue, which is NULL for banks
   - Fix: For banks, use operating_income/total_assets or create separate calculation
   - Impact: Recovers 2000+ op margin values

2. **EV/EBITDA missing for 3,519 symbols (72%)**
   - Issue: EBITDA not being populated when depreciation/amortization missing
   - Root: SEC financial statements missing D&A data
   - Fix: Check load_financial_statements.py for D&A mapping gaps

3. **Sustainable Growth Rate NULL for 4,197 symbols (84%)**
   - Issue: Complex calc needs ROE * retention ratio
   - Fix: Improve calculation robustness

4. **Institutional Ownership NULL for 2,132 symbols (47%)**
   - Issue: No 13F institutional holdings data
   - Fix: Check if 13F loader exists, or disable this metric

### MEDIUM IMPACT
5. **Forward P/E missing for 4,209 symbols (82%)**
   - Issue: Requires external analyst estimates (not SEC)
   - Fix: Accept this gap or add external data source

6. **PB Ratio missing for 1,508 symbols (29%)**
   - Issue: Book value NULL
   - Fix: Use balance sheet data if available

7. **PS Ratio missing for 1,374 symbols (27%)**
   - Issue: Revenue NULL (already partially fixed with bank revenue)
   - Fix: Use after bank revenue fix is applied

## TESTING APPROACH
For each fix:
1. Run comprehensive_data_loading_audit.py BEFORE
2. Apply fix  
3. Test on AAPL or FNWB specifically
4. Run comprehensive_data_loading_audit.py AFTER
5. Verify improvement in NULL counts
6. Commit with impact numbers

## UTILITY SCRIPTS
- `comprehensive_data_loading_audit.py` - Full system audit
- `trace_fcf_flow.py` - Debug flow for AAPL (example)
- `check_fcf_source.py` - Check source data availability
