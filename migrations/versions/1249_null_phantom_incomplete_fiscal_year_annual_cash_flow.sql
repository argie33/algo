-- Migration 1249: same bug class as 1248, applied to annual_cash_flow.
--
-- Root cause (goal session 2026-08-29, composite-score validation against real data): the same
-- "current, still-in-progress fiscal year's annual row is actually just Q1's figures" pattern
-- fixed for annual_income_statement in migration 1248 also affects annual_cash_flow - cash flow
-- is a duration concept (operating_cash_flow/capex/free_cash_flow accumulate over a period),
-- going through the same get_cash_flow()/_aggregate_concepts() extraction path in
-- utils/external/sec_statements.py as income statement, not the instant/point-in-time balance
-- sheet case that 1248's own comment deliberately excluded (a real balance IS legitimately "as
-- of" a date, so a March/April-fiscal-year-end company's true year-end balance can coincide with
-- what's labeled Q1 - no such ambiguity exists for a cash-flow DURATION total: a real full year's
-- cash flow can never legitimately equal a real single quarter's for a continuing company).
--
-- Live-confirmed across real, active, well-known companies (not just illiquid micro-caps) - a
-- random sample: ECL (Ecolab) FY2026 annual_cash_flow.operating_cash_flow=$445,900,000 and
-- capex=$348,500,000, both EXACT-to-the-dollar matches to ECL's own quarterly_cash_flow
-- (fiscal_year=2026, fiscal_quarter=1) row; same exact-match pattern independently confirmed for
-- AVX, INBX, SWMR, UPST, ENPH, DYAI, REAL. Downstream impact: load_sec_valuations.py's fcf_yield
-- and DCF intrinsic-value calculations (both read annual_cash_flow with
-- "data_unavailable IS NOT TRUE" - see that file's own line ~1070) were using one quarter's cash
-- flow as if it were the full year's, understating FCF yield for every affected symbol's most
-- recent (most-heavily-weighted) data point - a real Value-pillar distortion, not just Growth.
--
-- Scope: fiscal_year=2026 only, same reasoning as 1248 - the current, unambiguously-still-in-
-- progress fiscal year for the overwhelming majority of the (calendar-year-filer) universe.
-- Older fiscal years were deliberately NOT swept here for the same stub-period caution 1248
-- documents.

UPDATE annual_cash_flow acf
   SET data_unavailable = TRUE,
       reason = 'incomplete_sec_filing_cashflow'
  FROM quarterly_cash_flow q
 WHERE q.symbol = acf.symbol
   AND q.fiscal_year = acf.fiscal_year
   AND q.fiscal_quarter = 1
   AND acf.fiscal_year = 2026
   AND acf.data_unavailable = FALSE
   AND acf.operating_cash_flow IS NOT NULL AND acf.operating_cash_flow != 0
   AND q.operating_cash_flow IS NOT NULL AND q.operating_cash_flow != 0
   AND abs(acf.operating_cash_flow - q.operating_cash_flow) / abs(q.operating_cash_flow) < 0.01;
