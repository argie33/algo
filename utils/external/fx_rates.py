#!/usr/bin/env python3
"""Historical USD exchange rates for major, developed-market currencies.

FIXED 2026-08-17 (goal: "no SEC data" audit): sec_statements.py's non-USD currency
guard (added to block KRW/JPY-style filers whose raw local-currency magnitudes were
being stored as if they were USD, off by ~100-1000x) is a blanket rule that also
silently drops real, usable data for foreign issuers reporting in currencies that are
NOT wildly divergent from USD - CAD, GBP, EUR, AUD, CHF, JPY are all liquid, developed-
market currencies whose value vs USD has stayed within roughly a 2x band historically,
nothing like KRW/JPY's original ~100-1000x *magnitude* mismatch (which was really a
unit-scale confusion, not a volatility problem). Live-confirmed via DB scan: 272
symbols (CP, ASML, BBVA, BCS, BAP, BCE, AEG and more) have real revenue/net_income
sitting in their SEC filings, reported in one of these currencies, that the blanket
guard discards entirely.

This module fetches REAL historical exchange rates (never a fabricated/guessed
number) from Frankfurter (https://frankfurter.dev), a free ECB-rate mirror with no
API key, for the specific fiscal-period-end date of each filing - not a single
"current" rate applied retroactively to old filings, which would misstate periods
where the real historical rate differed meaningfully from today's. A rate lookup
failure (network error, date outside ECB's published range, currency not found) is
never treated as "assume ~1.0" or any other guess - it returns None, and the caller
must still leave that value NULL, same fail-closed discipline as the currency guard
this replaces for this specific whitelist of currencies.

FIXED 2026-08-18 (goal: "no SEC data"/loader-failure audit, follow-up to the currency-
poisoning cleanup that wiped ~428 corrupted rows for 15 KRW/CLP/COP-reporting foreign
filers): KRW moved here from the "deliberately not extended" list below. Frankfurter
does cover it (live-confirmed: `GET /2023-12-31?from=KRW&to=USD` returns a real rate,
unlike CLP/COP/TWD which 404), and it's a fully convertible, actively-traded currency
with no capital controls (South Korea is an OECD/G20 advanced economy) - not
meaningfully more volatile than JPY, already on this list, which moved ~35% (115->160)
over 2022-2024 vs KRW's ~25% move over the same window. Live-verified against 3 named
still-open symbols using each one's own real historical rate for its fact's period-end
date (never a guessed/current rate): KEP (Korea Electric Power) FY2024 revenue converts
to ~$71B, matching KEPCO's real public-reported revenue; KB (KB Financial Group) FY2023
~$12.5B and SHG (Shinhan Financial Group) FY2024 ~$50B both fall in the plausible range
for Korea's largest bank holding companies - none of the 100-1000x magnitude errors the
original blanket guard existed to catch.

FIXED 2026-08-20 (goal session: coverage root-cause audit): CNY added. Live-confirmed via
GDS (GDS Holdings, Chinese data-center operator, CIK 0001526125) - its entire us-gaap
revenue/net_income history (2016-2025) is tagged exclusively in CNY, none in USD, so the
blanket guard was dropping real data for every fiscal year going all the way back to its
2016 IPO. Frankfurter serves CNY (`GET /2025-12-31?from=USD&to=CNY` returns a real rate);
year-end CNY/USD moved at most ~7.9% year-over-year across 2018-2025 (managed-float regime,
narrower band than JPY's cited ~35% 2022-2024 swing or KRW's ~25%), so it clears the same
volatility bar KRW was added under. Converting GDS's real revenue history with each
fiscal year's own historical rate produces a smooth, monotonic $152M (FY2016) -> $1.63B
(FY2025) growth curve consistent with its known real business trajectory - no 10-100x
magnitude red flag. Before this fix, annual_income_statement rows for GDS (and any other
CNY-only filer) were marked data_unavailable/"incomplete_sec_filing_income" despite having
a complete, extractable filing - see
[[financial_statements_governance_flag_downgrade_bug_20260820]] in memory for a separate,
related bug this interacts with: rows written by a PRE-guard code version had stored the
raw, unconverted CNY figure directly (a silently ~7x-too-large "USD" value, preserved by
preserve_on_missing_fields and never overwritten because every fetch since has correctly
returned None for the un-whitelisted currency) - this fix's next real fetch produces a
genuine non-NULL converted value, which overwrites the stale wrong one normally (no COALESCE
blocking involved when the new value is real, only when it's NULL).

Deliberately NOT extended to other volatile/emerging-market currencies (ARS, BRL, MXN, TRY,
TWD, VND and similar) - those can move far more than developed-market FX pairs even within a
single fiscal year, and Frankfurter itself doesn't cover several of them at all (TWD live-
confirmed 404). Those stay behind the original blanket-reject guard, unconverted. (PEN and
COP were originally lumped into this list too, without their own live check - see this
file's 2026-09-06 "PEN"/"COP" fix entries below for why they were moved out and added via the
yfinance-only path instead.) Do not add another currency to MAJOR_CURRENCIES without the same
live-verification discipline: (1) confirm Frankfurter actually serves it, (2) sanity-check
the converted USD figure against at least one real filer's known public financials.

FIXED 2026-08-22 (goal session: "Stale fiscal data" coverage audit): ZAR added. Live-
confirmed via HMY (Harmony Gold Mining, a South African gold producer, CIK 0001023514) -
its entire ifrs-full revenue/net_income history from FY2019 onward is tagged exclusively
in ZAR (FY2016-2018 alone were USD-tagged), so the blanket guard silently dropped 7
straight fiscal years of real, current 20-F data (marked "incomplete_sec_filing_income")
despite the company continuing to file real annual reports every year. Frankfurter serves
ZAR (`GET /2025-06-30?from=USD&to=ZAR` returns a real rate); year-end ZAR/USD moved at
most ~8.6% year-over-year across 2019-2025 (2.6%-8.6% range, live-checked), comparable to
or narrower than CNY's ~7.9% bar above - clears the same volatility threshold. Converting
HMY's real FY2025 revenue (ZAR 73.896B) at its own fiscal-year-end rate produces ~$4.16B,
consistent with Harmony Gold's known real, growing revenue during 2024-2025's record gold
prices - no magnitude red flag. NOT the same case as MXN or CLP: MXN's real year-over-year
move was live-checked at up to 22.4% (2023->2024) - genuinely more volatile than CNY/ZAR's
band, so it stays excluded pending its own dedicated review; CLP still 404s on Frankfurter
entirely (BCH/Bank of Chile stays unconverted for a structural source-availability reason,
not a volatility judgment).

FIXED 2026-08-29 (goal session: "full data for scores" completeness pass, root-causing
`currency_conversion_bug_remediation_20260819` markers): INR added. Live-confirmed via IBN
(ICICI Bank Ltd, one of India's largest banks) - annual_income_statement had 3 straight
fiscal years of real revenue/net_income sitting as raw, unconverted INR (pre-guard rows,
same "stale raw local-currency value" shape as the CNY/GDS case above), plus the current
fiscal year blocked entirely by the blanket guard. Frankfurter serves INR (year-end rate
live-fetched for 2018-2025); year-over-year moves were 0.6%-5% in 6 of 8 years, with a
single 11.1% outlier (2021->2022, the year the Fed's rate-hike cycle broadly hit EM
currencies) - comparable to ZAR's 8.6% high-water mark and well inside JPY's ~35%/KRW's
~25% precedent ceiling. Converting IBN's raw revenue with each year's own year-end rate
produces a smooth $16.3B (FY2023) -> $18.8B (FY2024) -> $22.8B (FY2025) growth curve
consistent with ICICI Bank's known real, growing total income - no magnitude red flag.

Same pass live-checked BRL as a candidate (found via BAK/Braskem carrying the identical
raw-unconverted-value shape) and confirmed it does NOT clear the bar: year-over-year
moves included two years of ~28%-29% (2019->2020 COVID shock, 2023->2024), well past
MXN's already-declined 22.4% - stays excluded, same volatility judgment as MXN/CLP, not
a bug. KZT (the currency behind KSPI/Kaspi.kz's gap) was also checked and, like CLP/COP/
TWD, is not served by Frankfurter at all (`GET /2024-12-31?from=USD&to=KZT` 404s) - a
structural source-availability gap, not a volatility judgment.

FOLLOW-UP (2026-08-29, same session): confirmed KSPI's gap is fully explained by the
above, not a separate ifrs-full extraction bug as first suspected - live SEC companyfacts
JSON (CIK 0001985487) shows KSPI DOES tag both `ifrs-full:Revenue` and `ifrs-full:ProfitLoss`
every fiscal year, exclusively under unit="KZT", no USD-tagged alternative anywhere. The
guard is working exactly as designed (same as BSAC/CLP); this cannot be fixed without a
different historical-FX data source for KZT, which this module deliberately doesn't add
without live verification (see the top of this docstring).

FIXED 2026-08-31 (goal: "data loading issues/missing coverage" pass): PHP added. Found while
investigating a small cluster of "stale_fiscal_data" 20-F filers (BCH/BBAR/BBD/BMA/CCU/CEPU/
LOMA all confirmed CLP/ARS/BRL - already-excluded currencies per above, correctly unconverted)
that also turned up PHI (PLDT Inc., CIK 0000078150) reporting exclusively in PHP with no
USD-tagged alternative. Frankfurter serves PHP (live-confirmed: `GET /2024-12-31?from=USD&to=PHP`
returns a real rate); year-end PHP/USD moves were +9.05% (2021->2022), -0.28% (2022->2023),
+4.66% (2023->2024) - comparable to ZAR's 8.6% high-water mark and inside INR's 11.1% ceiling,
both already accepted, well below MXN's rejected 22.4%/BRL's rejected 28-29%. Converting PLDT's
real FY2024 revenue (PHP 216.833B) at its own fiscal-year-end rate produces ~$3.74B, matching
PLDT's known real public revenue (Philippines' largest telecom, consistently $3.5-4B/year) - no
magnitude red flag. Only 1 symbol in this repo's universe affected (PHI) - a small, single-
symbol fix, but the same live-verification discipline applies regardless of population size.

FIXED 2026-09-02 (goal: SEC/XBRL missing-data sweep): DKK added. Found via NVO (Novo Nordisk)
and GMAB (Genmab) - both real, large, actively-traded Danish 20-F filers with a stock_scores
`missing_sec_data` gap on every quality/growth ratio - live-confirmed via real companyfacts
JSON (CIK 0000353278/0001434265): both tag `ifrs-full:Revenue`/`ifrs-full:ProfitLoss` every
fiscal year, NVO exclusively under unit="DKK" (no USD-tagged alternative at all), so this
guard was silently zeroing out `get_income_statement()`'s entire return for NVO - not just
one field, every concept, since every candidate fact failed the currency check the same way.
Frankfurter serves DKK (live-confirmed: `GET /2024-12-31?from=USD&to=DKK` returns a real
rate). Year-end DKK/USD moves: +6.19% (2021->2022), -3.26% (2022->2023), +6.43% (2023->2024)
- same developed-market band as EUR/GBP/CHF (DKK is ERM II-pegged to EUR within a tight
+/-2.25% band, one of the most stable currencies in Frankfurter's coverage, arguably safer
than several currencies already on this list), well inside PHP's already-accepted ceiling.

Same pass also found ERIC (Ericsson, Swedish, reports in SEK) with the identical zeroed-
statement shape - checked SEK as a candidate and at the time it did NOT clear the bar:
year-over-year moves included -12.07% (2019->2020), +15.22% (2021->2022), a wider and higher
band than every currency already accepted here (INR's 11.1% was the prior ceiling) - a
genuine, freely-floating developed-market currency, but judged more volatile than this list's
threshold tolerated at the time. See the 2026-09-06 re-evaluation below - this rejection did
not survive the BRL policy reversal.

FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, re-evaluating the SEK
rejection above against the BRL precedent): SEK's own worst live-reconfirmed year-over-year
move (`GET /2021-12-31?from=USD&to=SEK` vs `GET /2022-12-31?from=USD&to=SEK` = +15.22%) is
LESS volatile than BRL's 28-29% swings that the 2026-09-04 policy decision explicitly chose
to accept in exchange for real coverage over permanent NULL - the volatility-threshold
rejection above predates that policy reversal and was never revisited against the new,
looser bar it established, leaving SEK excluded for a reason weaker than one already accepted
elsewhere on this list. ERIC (Ericsson, CIK 0000717826) is the live-confirmed case: real
`ifrs-full:ProfitLoss`/`ifrs-full:Revenue` tagged every fiscal year, exclusively under
unit="SEK" (SEK 28.714B FY2025 ProfitLoss, no USD-tagged alternative), silently zeroing
annual_income_statement's entire row for every recent fiscal year. Frankfurter serves SEK
(same live-reconfirmed rates above). Added.

HKD, found via TDIC (a small HK-listed 20-F filer, same zeroed-statement shape), DOES clear
the bar trivially: year-over-year moves +/-0.6% or less (2021-2024, live-checked) - Hong
Kong's currency board has pegged HKD to USD within a ~7.75-7.85 band since 1983, making it
structurally more stable than every currency already on this list, JPY/CHF included. Added.

ADDED 2026-09-04 (goal session: "SEC/XBRL missing data under 6k" sweep): BRL added, reversing
the 2026-08-29 rejection above - NOT a re-assessment of the volatility (still the same real
28-29% year-over-year swings, live-reconfirmed via `GET /2019-01-01?from=USD&to=BRL` = 3.8812
vs `GET /2024-12-31?from=USD&to=BRL` = 6.1847), but an explicit, informed product decision:
given a direct choice between "leave ~15+ real Brazilian ADRs' (ABEV/BBD/STNE/SUZ/CIG/VIV/XP/
AZUL/TIMB/PAGS/...) balance-sheet and income-statement data permanently NULL" vs "convert it
at each fact's own real historical date-of-record rate and accept that cross-year trend/growth
metrics for these symbols will show real currency-driven noise on top of real business
performance", the latter was chosen. This is real historical FX movement, not fabricated data
or a bug - a Brazilian company's USD-equivalent revenue genuinely did move with BRL/USD, same
as it does for every other currency on this list, just by a wider margin. Frankfurter serves
BRL with real historical rates (confirmed above); sanity-checked ABEV's real FY2025 total_assets
(BRL 145.087B) converts to ~$26.5B at that fiscal year-end's real rate (5.4778) - a plausible
figure for Ambev's real balance sheet, no magnitude red flag. ARS was evaluated alongside BRL
in this same session and stays excluded: Frankfurter returns `{"message":"not found"}` for ARS
(live-confirmed `GET /2024-12-31?from=USD&to=ARS`) - a structural source-availability gap like
CLP/COP/TWD/KZT above, not a volatility judgment, so no policy decision can fix it without a
different historical-FX data source for ARS.

CHECKED 2026-09-05 (goal session: "get SEC/XBRL missing data to zero" sweep) - TRY (Turkish
Lira, the currency behind TKC/Turkcell and HEPS/Hepsiburada's gaps) evaluated and REJECTED,
never previously checked in this file. Frankfurter DOES serve it (live-confirmed
`GET /2024-12-31?from=USD&to=TRY` = 35.361, so this is not a source-availability gap like
ARS/CLP/COP/TWD/KZT) - but year-end TRY/USD year-over-year moves were +24.8% (2020), +81.1%
(2021), +39.2% (2022), +57.9% (2023), +19.7% (2024), +21.5% (2025) - every single year exceeds
BRL's already-rejected ~28-29% high-water mark, with 2021's 81.1% move alone dwarfing every
currency ever accepted or rejected on this list. Converting TKC/HEPS's real TRY-denominated
financials at these rates would produce USD figures whose year-over-year swings are almost
entirely currency noise, not real business performance - clearly fails the same volatility bar
that excluded BRL/MXN/SEK, more decisively than any of them. Confirmed correct to exclude, not
an oversight - do not re-add without a materially different Turkish-lira stabilization regime.

FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): ILS (Israeli New Shekel)
added. Found via SVRE (SaverOne 2014 Ltd., CIK 0001894693) - live-confirmed real
companyfacts JSON shows `ifrs-full:Assets`/`ifrs-full:Equity` tagged every fiscal year
2024-2025, exclusively under unit="ILS", no USD-tagged alternative - the blanket guard was
silently zeroing SVRE's entire quality_metrics/growth_metrics balance-sheet row
(`no_recent_balance_sheet_data_reported`) despite complete, extractable 20-F filings on
file. Frankfurter serves ILS (live-confirmed: `GET /2024-12-31?from=USD&to=ILS` returns a
real rate); year-end USD/ILS year-over-year moves 2018-2024: -7.9%, -7.0%, -3.4%, +13.4%,
+2.8%, +0.75% - the +13.4% high-water mark (2021->2022, the same broad EM-currency-stress
year that produced INR's 11.1% and ZAR's 8.6% peaks) is comparable to INR's already-accepted
ceiling and far inside BRL/MXN's rejected 20%+ band. Israel is a developed, OECD-member
economy (joined 2010) with a freely-floating, fully convertible currency and no capital
controls - not meaningfully more volatile than KRW, already on this list. Converting SVRE's
real FY2024 total_assets (ILS 23.818M) at that fiscal year-end's real rate (0.27422)
produces ~$6.53M, a plausible total-assets figure for a real micro-cap Israeli medical-
device/tech company - no magnitude red flag.

FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, user-pushed re-investigation
of the ARS/KZT/CLP "structural source-availability gap" closed earlier this campaign): found
a second real historical-FX source - yfinance's `f"{currency}=X"` tickers (already a project
dependency, used elsewhere in this codebase) - and re-ran the SAME live-verification
discipline against it before touching MAJOR_CURRENCIES.

ARS re-checked first, NOT added: yfinance does serve real ARS/USD history, but real year-end
year-over-year moves 2019-2025 (live-computed) are +58.9%, +40.5%, +22.0%, +72.2%, **+356.9%
(2023, the Milei devaluation)**, +27.6%, +41.3% - decisively worse than TRY's already-rejected
81.1% single-year record (see above), let alone BRL's 28-29% accepted ceiling. This was never
actually a source-availability-only gap that a new source could close - Argentina's real
currency volatility fails the volatility bar on its own merits, independent of which vendor
supplies the rate. Stays excluded; do not re-add without a materially different Argentine
currency regime (a hypothetical future currency board/dollarization, not the case as of this
writing).

KZT and CLP, by contrast, ARE genuinely stable and WERE excluded purely for lack of a Frankfurter
listing (confirmed via `GET /v1/currencies` - neither appears in Frankfurter's ~30-currency
list at all) - added here via yfinance. Real year-end year-over-year moves, yfinance-computed
2019-2025: KZT +2.2%, +10.4%, +3.7%, +5.5%, -1.1%, +15.0%, -4.2% (15.0% high-water mark,
comparable to ZAR/PHP/DKK's already-accepted band); CLP +5.6%, -2.9%, +19.8%, +0.5%, +3.3%,
+12.3%, -8.0% (19.8% high-water mark, comparable to CNY/ZAR territory, well inside BRL's
ceiling). Live-verified against real filers: KSPI (Kaspi.kz, CIK 0001985487) FY2024
ifrs-full:ProfitLoss = KZT 1,056,834,000,000 converts to ~$2.02B at that fiscal year-end's
real rate (521.98) - plausible for a ~$18-20B-market-cap fintech (implied P/E ~9-10). BCH
(Bank of Chile, CIK 0001161125) FY2024 ifrs-full:ProfitLoss = CLP 1,248,476,000,000 converts
to ~$1.24B at that fiscal year-end's real rate (1004.13) - plausible for a large Chilean bank
(implied P/E ~8-10 against its real market cap). Both pass the same "no magnitude red flag"
bar as every other addition to this list.

FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, re-investigation of the "PEN"
entry in this file's own "deliberately NOT extended" list above): that listing lumped PEN in
with ARS/BRL/CLP/COP/MXN/TRY/TWD/VND without an individual live check, unlike every other
currency actually added above - re-ran the same discipline against it and it does NOT belong
with that group. Found via AUNA (AUNA S.A., a Peru/Mexico/Colombia hospital-network operator,
CIK 0001799207) and IFS (Intercorp Financial Services, CIK 0001615903): both real, current
20-F filers with ifrs-full:Revenue/ProfitLoss/Assets/Equity tagged exclusively in PEN, zero
USD-tagged alternative - the blanket guard was zeroing their entire quality_metrics/
growth_metrics balance-sheet AND income-statement rows despite complete, extractable filings.
Frankfurter doesn't list PEN (`GET /v1/currencies` 404s it, same structural gap as KZT/CLP) but
yfinance's `PEN=X` does, with a full history. Real year-end year-over-year moves, yfinance-
computed 2019-2025: -1.5%, +9.2%, +10.2%, -5.1%, -2.2%, -0.9%, -8.4% - 10.2% high-water mark,
comparable to KZT's already-accepted 15.0% and narrower than CLP's 19.8%, decisively unlike
ARS's 356.9% single-year record just above. Peru has run an inflation-targeting, freely-
floating sol since 2002 with routine BCRP smoothing intervention, not a peg or capital-control
regime - the same "managed float, not crisis-prone" profile as CNY/KZT, not ARS/TRY. Converting
AUNA's real FY2024 ifrs-full:Revenue (PEN 4,386,112,000) at that fiscal year-end's real rate
(~3.75) produces ~$1.17B, consistent with AUNA's known real hospital-network scale (a 2024
SPAC-merger IPO with public revenue guidance in the same range) - no magnitude red flag.

FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same "recheck the deliberately-
excluded bucket individually" pass as the PEN fix just above): COP (Colombian Peso) added.
Found via EC (Ecopetrol S.A., Colombia's national oil company, CIK 0001444406) - a major,
real NYSE-listed 20-F filer whose ifrs-full Revenue/ProfitLoss are tagged EXCLUSIVELY in COP,
zero USD alternative (unlike TSM/UMC/ASX/CHT, which all dual-tag TWD+USD and so were never
actually blocked - checked as TWD candidates in the same pass and found to have no real
marginal impact in this universe, so TWD stays excluded). Frankfurter doesn't list COP
(`GET /v1/currencies` 404s it, same structural gap as KZT/CLP/PEN) but yfinance's `COP=X`
does. Real year-end year-over-year moves, yfinance-computed 2019-2025: +1.2%, +4.2%, +18.9%,
+19.2%, -20.0%, +13.5%, -15.1% - the ~19-20% high-water mark is essentially identical to
CLP's already-accepted 19.8% ceiling, comfortably inside BRL's 28-29% accepted band, and
nowhere near ARS's 356.9%/TRY's 81.1% rejected tier. Converting EC's real FY2024
ifrs-full:Revenue (COP 133,330,428,000,000) at that fiscal year-end's real rate (~4,400)
produces ~$30.3B, consistent with Ecopetrol's known real, public annual revenue scale - no
magnitude red flag. Before this fix EC's entire income-statement row was blocked by the
blanket currency guard despite a complete, extractable 20-F on file every year.

FIXED 2026-09-11 (goal: "missing SEC/XBRL data under 300" push): MXN (Mexican Peso) added,
reversing the earlier exclusion recorded above ("MXN's real year-over-year move was live-
checked at up to 22.4%... stays excluded pending its own dedicated review") - that rejection
predates the 2026-09-04 BRL policy reversal (28-29% accepted) and the COP/CLP additions
(19-20%/19.8% accepted) and, like the SEK case fixed 2026-09-06, was never revisited against
the looser bar those decisions established. Live-reconfirmed MXN's own year-end year-over-year
moves 2019-2025 (Frankfurter, fresh): -3.8%, +5.3%, +2.7%, -4.3%, -13.4%, +22.4%, -9.1% - the
same 22.4% high-water mark as before, but now decisively inside BRL's accepted 28-29% ceiling
and comparable to COP/CLP's already-accepted ~20% band. Found via ASR (Grupo Aeroportuario del
Sureste, CIK 0001123452) and PAC/TBBB/TV (Grupo Aeroportuario del Pacifico/Fibra clients/Grupo
Televisa) - all real, current 20-F filers tagging ifrs-full:Revenue/ProfitLoss/Assets exclusively
under unit="MXN", zero USD-tagged alternative, so the blanket guard was zeroing their entire
quality_metrics/growth_metrics/value_metrics/sec_valuations rows despite complete, extractable
filings on file every year. Frankfurter serves MXN (live-confirmed: `GET /2024-12-31?from=USD&to=MXN`
returns a real rate). Converting ASR's real FY2024 ifrs-full:Revenue (MXN 31,332,787,000) at that
fiscal year-end's real rate (20.743) produces ~$1.51B, consistent with Grupo Aeroportuario del
Sureste's known real public revenue scale - no magnitude red flag. 4 symbols directly affected in
this universe (ASR/PAC/TBBB/TV), each blocked across multiple factor tables.

FIXED 2026-09-10 (goal: "missing SEC/XBRL data under 500" push, dcf_fcf_unavailable_reason=
'missing_cash_flow_data' investigation): SGD (Singapore Dollar) added. Found via BLIV (BeLive
Holdings, CIK 0001982448, recently-listed 20-F filer) - live-confirmed real companyfacts JSON
shows `ifrs-full:CashFlowsFromUsedInOperatingActivities` and both capex-alias concepts already
mapped in sec_cash_flow.py tagged every fiscal year 2022-2024, exclusively under unit="SGD", no
USD-tagged alternative - the blanket guard was silently blocking dcf_fcf/operating_cash_flow/
free_cash_flow despite a complete, extractable 20-F on file. Frankfurter serves SGD
(live-confirmed: `GET /2024-12-31?from=USD&to=SGD` returns a real rate); year-end SGD/USD
year-over-year moves 2019-2024 (live-computed): -1.2%, -1.7%, +2.1%, -0.6%, -1.5%, +3.2% - a
tighter band than DKK's ERM-II peg comparison and second only to HKD's currency-board peg among
every currency already on this list; the Monetary Authority of Singapore manages SGD against an
undisclosed trade-weighted basket, producing this same currency-board-adjacent stability.
Converting BLIV's real FY2024 operating cash flow (SGD -1,067,138) at that fiscal year-end's
real rate (0.73348) produces ~-$783K, plausible for a just-IPO'd micro-cap - no magnitude red
flag.
"""

import json
import logging
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import requests
import yfinance

logger = logging.getLogger(__name__)

FRANKFURTER_URL = "https://api.frankfurter.app"

# Currencies Frankfurter (an ECB-rate mirror) doesn't publish at all - confirmed via
# `GET /v1/currencies` - but which DO clear the same volatility bar as every currency above,
# using yfinance's `f"{currency}=X"` tickers as the real historical-rate source instead. See
# this module's 2026-09-06 docstring entries for the live verification (KSPI/BCH for KZT/CLP,
# AUNA/IFS for PEN, EC for COP) each one is based on. Kept as a separate set (not merged into
# MAJOR_CURRENCIES's own iteration order) so `_fetch_rate` knows which provider to route to
# without a second live probe per call.
_YFINANCE_ONLY_CURRENCIES = frozenset({"KZT", "CLP", "PEN", "COP"})

# Liquid, developed-market currencies only - see module docstring for why this list is
# deliberately narrow. Do not add emerging-market/volatile currencies here without the
# same live-verification discipline as the currencies already on this list.
MAJOR_CURRENCIES = frozenset(
    {
        "CAD",
        "GBP",
        "EUR",
        "AUD",
        "CHF",
        "JPY",
        "KRW",
        "CNY",
        "ZAR",
        "INR",
        "PHP",
        "DKK",
        "HKD",
        "BRL",
        "ILS",
        "SEK",
        "SGD",
        "MXN",
    }
    | _YFINANCE_ONLY_CURRENCIES
)


class FxRateCache:
    """Caches (currency, date) -> USD exchange rate lookups.

    Historical rates are immutable once published (ECB doesn't revise past fixings),
    so cached entries never expire - unlike TickerCache's ticker-to-CIK mapping (which
    needs periodic refresh as new companies list), there is no staleness concept here.
    """

    def __init__(self, timeout: float = 10.0, session: requests.Session | None = None):
        self._timeout = timeout
        self._session = session or requests.Session()
        temp_dir = Path(tempfile.gettempdir())
        self._cache_file = temp_dir / "sec_fx_rate_cache.json"
        self._cache: dict[str, float | None] = {}
        self._load_from_file()

    def _load_from_file(self) -> None:
        try:
            if self._cache_file.exists():
                with open(self._cache_file) as f:
                    self._cache = json.load(f)
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.debug(f"Could not load FX rate cache file: {e}")

    def _save_to_file(self) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_file, "w") as f:
                json.dump(self._cache, f)
        except OSError as e:
            logger.debug(f"Could not save FX rate cache file: {e}")

    def get_usd_rate(self, currency: str, date_str: str) -> float | None:
        """Return how many units of `currency` equal 1 USD on `date_str` (YYYY-MM-DD).

        A caller converts a local-currency value to USD via `value / rate`. Returns
        None (never a guessed/fallback number) if the currency isn't on the major-
        currency whitelist, the date is malformed, or the live lookup fails for any
        reason (network error, date outside Frankfurter's published range, etc.).
        """
        if currency not in MAJOR_CURRENCIES:
            return None
        if len(date_str) != 10 or date_str[4] != "-" or date_str[7] != "-":
            return None

        cache_key = f"{currency}:{date_str}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        rate = self._fetch_rate(currency, date_str)
        self._cache[cache_key] = rate
        self._save_to_file()
        return rate

    def _fetch_rate(self, currency: str, date_str: str) -> float | None:
        if currency in _YFINANCE_ONLY_CURRENCIES:
            return self._fetch_rate_yfinance(currency, date_str)
        max_retries = 2
        for attempt in range(max_retries):
            try:
                resp = self._session.get(
                    f"{FRANKFURTER_URL}/{date_str}",
                    params={"from": "USD", "to": currency},
                    timeout=self._timeout,
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                logger.warning(f"FX rate fetch network error for {currency}/{date_str}: {e}")
                return None

            if resp.status_code == 404:
                # Date outside Frankfurter's published range (pre-1999, weekends land on
                # the prior business day automatically so this is a genuine gap, not a
                # transient issue) - a real "no rate available", not a retry candidate.
                return None
            if resp.status_code in (429, 502, 503, 504):
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                logger.warning(f"FX rate fetch got HTTP {resp.status_code} for {currency}/{date_str}")
                return None
            if resp.status_code != 200:
                return None

            try:
                data = resp.json()
                if "rates" not in data or currency not in data["rates"]:
                    return None
                rate = data["rates"][currency]
                return float(rate) if rate is not None else None
            except (ValueError, TypeError) as e:
                logger.warning(f"FX rate response parse failure for {currency}/{date_str}: {e}")
                return None
        return None

    def _fetch_rate_yfinance(self, currency: str, date_str: str) -> float | None:
        """Real historical USD/{currency} rate via yfinance's `f"{currency}=X"` ticker, for
        the currencies in `_YFINANCE_ONLY_CURRENCIES` that Frankfurter doesn't publish at all.

        yfinance has no single-date lookup (unlike Frankfurter's `/YYYY-MM-DD` endpoint) - it
        only serves a daily OHLC history. Fetches a small trailing window ending the day after
        `date_str` (yfinance's `end` is exclusive) and takes the LAST close on or before
        `date_str` - the same "weekends/holidays fall back to the prior business day" behavior
        Frankfurter provides natively, implemented here by hand. A window with zero rows means
        a genuine gap (date outside the ticker's published range, or too far in the future) -
        never guessed at, same fail-closed discipline as the Frankfurter path.
        """
        try:
            target = date.fromisoformat(date_str)
        except ValueError:
            return None
        # 10 calendar days covers even a long holiday cluster (e.g. Kazakh Nauryz, Chilean
        # Fiestas Patrias) while staying a cheap, bounded fetch.
        window_start = (target - timedelta(days=10)).isoformat()
        window_end = (target + timedelta(days=1)).isoformat()
        try:
            hist = yfinance.Ticker(f"{currency}=X").history(start=window_start, end=window_end)
        except Exception as e:
            logger.warning(f"yfinance FX rate fetch failed for {currency}/{date_str}: {type(e).__name__}: {e}")
            return None
        if hist.empty:
            return None
        closes = hist["Close"]
        on_or_before = closes[closes.index.date <= target]
        if on_or_before.empty:
            return None
        rate = float(on_or_before.iloc[-1])
        return rate if rate > 0 else None
