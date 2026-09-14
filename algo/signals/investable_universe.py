"""Canonical investable-universe SQL fragment, shared by every consumer that ranks or
averages across "the universe" of stocks (leaderboard, sector/industry rankings).

EXTRACTED 2026-09-13 (/goal session, Item 2 of the scores plan): this exact WHERE clause
previously lived only inline in lambda/api/routes/scores_handlers/stock_scores.py (the
leaderboard endpoint) - live-verified 2026-09-13 that loaders/load_sector_industry_daily.py's
sector_ranking/industry_ranking queries never applied it at all, just
`stock_scores.composite_score IS NOT NULL`. That let 414 symbols (~8% of the scored
universe, live-counted) - ETFs, SPAC shells, royalty trusts, structured notes, closed-end
funds with no annual report filing, and inactive/delisted symbols - into the AVG(composite_score)/
RANK()/stock_count that drives sector_ranking.avg_score, industry_ranking.avg_score, and
(via algo/signals/advanced_filters.py's _strong_sectors/_strong_industries) the
"qualifying to best" signal-quality boosters, even though none of those symbols could ever
appear on the leaderboard or get traded. Centralized here instead of copy-pasting the SQL a
second time, so a future filter addition/removal (see the individual filter comments this
module inherited from stock_scores.py's git history) can't silently drift between the two
consumers again.
"""

from __future__ import annotations


def investable_universe_conditions(scores_alias: str, symbols_alias: str) -> str:
    """AND-joined SQL conditions (no leading WHERE/AND) that define the tradeable universe:
    a real, active, non-fund, non-shell common-equity symbol with a real composite_score.

    scores_alias must reference a table with a composite_score column (stock_scores);
    symbols_alias must reference a `JOIN stock_symbols <symbols_alias> ON
    <symbols_alias>.symbol = <scores_alias>.symbol` the caller adds to its own query (needs
    stock_symbols' active/security_name columns). Requires etf_symbols and company_info_sec
    (sic_code, has_annual_report_filing) to exist in the query's scope.

    `%` is doubled (`%%`) throughout because every known caller passes this string through
    psycopg2's execute() alongside `%s` parameter placeholders elsewhere in the same query.

    Each condition's own history (all originally worked out live against
    lambda/api/routes/scores_handlers/stock_scores.py's leaderboard endpoint before this
    module existed):

    ETF FILTERING (GOVERNANCE compliance): stock_scores are for equity trading signals only
    (GOVERNANCE.md). etf_symbols is the definitive source - stock_symbols.etf is not used
    here because it doesn't exist on the joined alias in every caller.

    SPAC-SHELL/DERIVATIVE FILTERING (2026-08-03): pre-merger SPAC common shares ("...
    Acquisition Corp[oration] - Class A Ordinary Shares") and their Rights/Warrants
    derivatives have no operating business, so SEC EDGAR has no income statement/balance
    sheet for them (~5% of the universe, 279/5455 symbols, live-verified). The Rights/
    Warrants pattern is end-anchored ('...Rights?/Warrants?$') to avoid matching ADS
    boilerplate ("...American Depositary Shares (each representing the right to
    receive...)", e.g. AMX/RLX/WDH), which are real operating companies.

    SIC-CODE SPAC FILTERING (2026-08-03, follow-up): the name regex above still misses SPAC
    shells with heterogeneous naming ("General Catalyst Global Resilience Merger Corp",
    "Iron Dome Acquisition I Corp", "Yorkville International Capital Corp", ...) -
    live-verified all report SIC 6770 ("Blank Checks"), the SEC's own classification for
    pre-merger shells, while real operating companies with similar naming (AAPL, MSFT,
    FNWB, NREF, OZK) do not. REVENUE EXEMPTION ADDED 2026-09-14 (same session as the royalty-
    trust correction below, found by the same adversarial audit): a completed de-SPAC keeps
    its SIC 6770 classification too, with no code-shape name signal to catch it - live example
    INV (Innventure, Inc., completed its business combination with Learn CW Investment Corp
    October 2024, is now a real operating tech-commercialization company with $1.1M/$2.1M real
    revenue 2023/2025) was silently excluded from the entire tradeable universe by SIC alone.
    A shell-naming regex can't safely fix this the way it did for the SIC-6792 case above -
    SPACs routinely rename to the target company's brand mid-merger, before the deal actually
    closes, so a name that no longer looks like a shell doesn't reliably mean the merger is
    done (unlike royalty trusts, which don't rename). Real signal instead: has this SIC-6770
    symbol ever reported positive annual revenue - live-verified $0.00 (not merely absent) for
    confirmed still-pre-merger shells (CEPO, GIX) vs INV's real $1M+ figures, so "revenue > 0
    in any fiscal year" cleanly separates a completed, operating business from an empty shell
    without depending on naming conventions that don't hold up for this SIC code.

    SIC-CODE ROYALTY TRUST FILTERING (2026-08-03): oil/gas royalty trusts carry SIC 6792
    ("Oil Royalty Traders") - live-confirmed distinct from real producers XOM/CVX/OXY.
    CORRECTED 2026-09-14 (goal session, adversarial leaderboard audit - user pushback: "I
    would have wanted to buy TPL when it popped off last year, that doesn't seem right"): the
    original SIC-6792-alone rule was too broad, and this docstring's "nothing for SEC EDGAR to
    report" justification was itself false (live-verified `has_annual_report_filing = TRUE`
    for every SIC-6792 symbol) - this filter's real job is excluding zero-employee
    pass-through trusts whose near-zero invested-capital balance sheets mechanically produce
    meaningless ROE/ROCE/asset-turnover ratios (100-200%+), not a missing-data problem. Of the
    9 symbols carrying SIC 6792 (live-checked), 3 are NOT passive trusts at all: TPL (Texas
    Pacific Land Corp, converted from trust to corporation in 2021 - real board/management and
    a genuine, growing Water Services segment), LB (LandBridge Co LLC, $73M/$110M/$199M real
    and growing revenue 2023-2025), and EROK (EagleRock Land LLC, $17.7M/$141.4M real revenue
    2024-2025) - all real, actively-managed, execution-dependent operating businesses that
    happen to share a legacy SIC code with genuine trusts, not passive distribution
    mechanisms. SEC SIC codes are assigned once and rarely revisited, so this is a real,
    ongoing classification-lag risk, not a one-time data bug to patch upstream - a blanket
    SIC-code-alone rule will keep catching future trust-to-corporation conversions the same
    way. General, self-updating fix instead of one-off ticker carve-outs: every genuine
    passive trust in this SIC code has the literal word "Trust" in its name (CRT="Cross
    Timbers Royalty Trust", MTR="Mesa Royalty Trust", PBT="Permian Basin Royalty Trust",
    SBR="Sabine Royalty Trust", SJT="San Juan Basin Royalty Trust", NRT="North European Oil
    Royalty Trust") - none of the 3 real operating companies do. Requiring the name match
    narrows the exclusion back to the 6 genuine trusts and stays correct if a future company
    converts the same way TPL did, without needing another hand-picked exception. Excluding a
    real operating company from the entire tradeable universe over a Quality-pillar problem
    that doesn't even apply to its other pillars (Momentum/Growth/Value/Risk aren't mechanically
    gamed by a light balance sheet the way ROE/ROCE-heavy Quality is) would permanently block
    real trading opportunities for a reason that shouldn't reach that far.

    EXTENDED TO SIC 6795 (2026-09-14, same goal session - found via a live query while auditing
    whether the fix above was complete, not a bug report): SIC 6795 ("Mineral Royalty Traders")
    has the IDENTICAL mixed-population shape - MSB (Mesabi Trust, a genuine passive iron-ore
    royalty trust, live-confirmed roe=399.84% off a near-zero balance sheet the same way as the
    SIC-6792 trusts above) shares the code with RGLD (Royal Gold), SSRM (SSR Mining), SRL
    (Scully Royalty), VMET (Versamet Royalties), and TFPM (Triple Flag Precious Metals) - all
    real, actively-managed royalty/streaming/mining operating companies, none with "Trust" in
    their name. Same fix, same reasoning: SIC-6795-alone would wrongly exclude 5 real companies
    to catch 1 real trust; requiring the "Trust" name match again narrows it to exactly MSB.

    SIC-CODE STRUCTURED-NOTE FILTERING (2026-08-03): trust-preferred/structured-note
    certificates (GJH/GJO/GJP/GJR/GJS/GJT "STRATS", KTN "CorTS", PYT "PPlus Trust") have
    their own SIC 6189 ("Asset-Backed Securities"). Entergy's First Mortgage Bonds tickers
    were checked too but resolve to the parent utility's own CIK/SIC - a different,
    not-yet-understood problem, not fixed by this filter.

    HAS_ANNUAL_REPORT_FILING FILTERING (2026-08-03, migration 1193): closed-end funds (the
    largest remaining "No SEC data" bucket, ~60+ symbols - BlackRock/Eaton Vance/Gabelli/
    Invesco/Franklin CEFs) have no usable SIC signal (blank, same as real operating
    companies like OZK). Direct signal instead: whether SEC EDGAR submissions.filings.recent
    ever included a 10-K/10-K-A or 20-F/20-F-A - live-verified CEFs (BGT, GAB) file neither,
    only fund-specific forms. `= FALSE` (not `IS NOT TRUE`) deliberately includes NULL
    (unchecked symbol, or no company_info_sec row) - fail-open on unknown, matching the
    ETF/SPAC filters above.

    DEBT/PREFERRED-CERTIFICATE FILTERING (2026-08-03): subordinated debentures/mortgage
    bonds (AFGB/AFGC/AFGD/AFGE, ELC/EMP/ENJ/ENO/EAI) trade under their own ticker but share
    the parent operating company's CIK/financials, yet aren't common equity and have no
    separate balance sheet to compute ROE/margins from - live-verified the name regex
    matches exactly these 5 tickers, zero false positives. Deliberately not extended to a
    broader "Trust N" pattern - collides with real CEFs (VLT "Invesco High Income Trust
    II").

    PHYSICAL COMMODITY TRUST FILTERING (2026-08-10): grantor trusts holding physical bullion
    (GraniteShares Gold Trust "BAR") file real 10-Ks and aren't '40-Act funds, so they pass
    every filter above - ranked #1 in the universe on a live check. SIC 6221 alone isn't
    safe (also covers real operating companies AIB/ANTA/UROY), so this requires both SIC
    6221 AND a commodity-Trust name pattern together - matched only BAR live, zero false
    positives.

    ETN FILTERING (2026-08-20): GRN ("iPath Series B Carbon Exchange-Traded Notes") passed
    every filter above - not in etf_symbols (ETNs are debt notes), SIC 6029 ("Commercial
    Banks") because an ETN's SEC filer is the issuing bank, not the note's own structure.
    No usable SIC/has_annual_report_filing signal exists for this case (same root cause as
    utils/loaders/helpers.py::get_active_symbols(exclude_etfs=True)) - name-based catch,
    verified to match only GRN live.

    ACTIVE-UNIVERSE FILTER (2026-09-08): no `active` check existed anywhere - live-verified
    3 delisted/deactivated symbols (TOI, KORE, PSNYW) cleared every other filter and would
    render with a plausible composite_score, indistinguishable from a real tradeable idea.
    """
    return f"""
        {scores_alias}.composite_score > 0
        AND {symbols_alias}.active = true
        AND {symbols_alias}.symbol NOT IN (SELECT symbol FROM etf_symbols)
        AND {symbols_alias}.symbol NOT IN (SELECT symbol FROM company_info_sec WHERE sic_code = 6189)
        AND NOT (
            {symbols_alias}.symbol IN (SELECT symbol FROM company_info_sec WHERE sic_code IN (6792, 6795))
            AND {symbols_alias}.security_name ~* 'Trust'
        )
        AND NOT (
            {symbols_alias}.symbol IN (SELECT symbol FROM company_info_sec WHERE sic_code = 6770)
            AND {symbols_alias}.symbol NOT IN (
                SELECT symbol FROM annual_income_statement WHERE revenue > 0
            )
        )
        AND {symbols_alias}.symbol NOT IN (
            SELECT symbol FROM company_info_sec WHERE has_annual_report_filing = FALSE
        )
        AND NOT (
            {symbols_alias}.symbol IN (SELECT symbol FROM company_info_sec WHERE sic_code = 6221)
            AND {symbols_alias}.security_name ~* '(Gold|Silver|Platinum|Palladium|Bullion) Trust'
        )
        AND ({symbols_alias}.security_name IS NULL OR (
            {symbols_alias}.security_name !~* '(Rights?|Warrants?)$'
            AND {symbols_alias}.security_name NOT ILIKE '%%Acquisition Corp%%'
            AND {symbols_alias}.security_name !~* '(Subordinated Debentures?|First Mortgage Bonds?|Collateral Trust Mortgage Bonds?)'
            AND {symbols_alias}.security_name !~* '(ETNs?|Exchange[- ]Traded Notes?)'
        ))
        """
