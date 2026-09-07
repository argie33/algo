"""Entry-period resolution and replacement-ranking for the XBRL concept-aggregation engine,
extracted from sec_statements_aggregate.py (2026-09-05, further split: that file itself
exceeded the 800-line new-file cap once first extracted from sec_statements.py). Bodies are
verbatim, no logic changed - called by _aggregate_concepts in sec_statements_aggregate.py.
"""

import datetime
import logging
from typing import Any

from utils.external.sec_statements_shared import (
    _ANNUAL_REPORT_FORMS,
    _MIN_PLAUSIBLE_FISCAL_YEAR,
    _PRIMARY_STATEMENT_FORMS,
    _fx_rate_cache,
)

logger = logging.getLogger(__name__)


def _aggregate_concepts_resolve_entry_period(  # noqa: C901 -- inherits pre-existing complexity debt extracted from _aggregate_concepts, not new logic
    entry: Any,
    source: str,
    period: str,
    fp_filter: str | tuple[str, ...],
    has_annual_report_form: bool,
    _max_annual_report_end: str | None,
    has_december_fiscal_year_end: bool,
    _max_end_by_accn: dict[str, str],
    _short_span_val_by_accn: dict[str, set[Any]],
    _fy_by_start_end_val: dict[tuple[str, str, Any], tuple[int, str]],
    _max_plausible_fiscal_year: int,
    symbol: str,
    concept: str,
) -> tuple[Any, Any, Any, Any] | None:
    """Resolve a single fact entry's (fp, fiscal_year, start_date, end_date), or None to skip it.

    Extracted from _aggregate_concepts (mechanical extraction, no behavior change) - every
    ``continue`` in the original per-entry loop became a ``return None`` here.
    """
    # dei facts (e.g. EntityCommonStockSharesOutstanding) are reported in
    # whatever share unit the local filing uses - domestic 10-K/10-Q filers
    # report it in the actual registered security's units, but foreign 20-F/
    # 40-F/6-K filers often report it in home-market local shares with no
    # ADS-ratio conversion available in XBRL. A prior session in this file hit
    # exactly this trap with a different IFRS shares concept (see the removed-
    # concept comment above _INCOME_IFRS_ALIASES: SRAD's value was a stale
    # pre-restructuring Swiss AG share count, live-caught via a market-cap
    # sanity check) and reverted it. Restrict dei facts to domestic forms only
    # to avoid reintroducing the same class of silent unit-mismatch error.
    if source == "dei" and entry.get("form") in ("20-F", "40-F", "6-K"):
        return None
    fp = entry.get("fp")
    # BUG FOUND 2026-09-05 (goal session: quantifying the retry-gap fix's impact, live-
    # confirmed via KRC/Kilroy Realty): a fp=None (proxy-statement) entry for a whole-dollar
    # monetary concept (NetIncomeLoss) carried val=302.64 for FY2025 - a "Pay versus
    # Performance" DEF 14A compensation table reporting the figure in $ millions with a
    # decimal, under the SAME us-gaap:NetIncomeLoss tag a real 10-K uses for the whole-dollar
    # figure ($302,640,000). This DEF 14A entry was filed 2026-04-09, AFTER KRC's real 10-K,
    # and KRC's 10-K never itemizes plain NetIncomeLoss at all (only ProfitLoss) - so there
    # was no primary-form entry for THIS concept to rank-gate against, and the corrupted
    # value landed directly in annual_income_statement.net_income (confirmed live in the DB:
    # 302.64 instead of 302,640,000 for FY2025, 232.95 instead of ~232,950,000 for FY2024).
    # A genuine XBRL USD monetary fact for a real company's annual net income/revenue/etc. is
    # always a whole-dollar integer (verified against EE's real fp=None NetIncomeLoss facts -
    # the case this fp=None acceptance was originally added for - all whole integers, e.g.
    # 79996000) - a non-integer value under a whole-dollar concept is the specific, reliable
    # signature of this scale error. Scoped to fp is None only (real 10-K/10-Q facts are
    # never affected) and skips PerShare concepts (EPS is legitimately fractional).
    if fp is None and "PerShare" not in concept:
        val = entry.get("val")
        if isinstance(val, (int, float)) and val != 0 and abs(val - round(val)) > 0.005:
            return None
    # Fixed 2026-07-31: For annual extraction, accept quarterly (Q1-Q4), annual (FY),
    # and proxy-statement (fp=None) data. This handles:
    # - Standard annual 10-Ks: fp='FY'
    # - Quarterly-only reporters (ETFs like EE): fp in ('Q1'-'Q4')
    # - Proxy statements with annual data: fp=None (e.g., EE's net income from DEF 14A)
    # Use the end date to derive the fiscal year. This fixes 466 companies (8.4%)
    # with zero net_income coverage because extraction silently skipped them.
    #
    # FIXED 2026-08-09: annual extraction had no check on the entry's actual
    # reporting SPAN, so a genuine single-quarter duration fact (~90 days) was
    # accepted into the annual "FY" bucket with no annualization - silently
    # masquerading as a full year's figure. Live-confirmed via ORLY: its FY2026
    # 10-K hasn't been filed yet (mid-year), so revenue/gross_profit had no real
    # annual entry; but a real Q1-2026 "InterestAndDividendIncomeOperating" fact
    # (a minor interest-income line, $1.75M, unrelated to their real ~$4B/qtr
    # retail revenue) got bucketed into fiscal_year=2026 "FY" as if it were the
    # year's revenue, producing garbage 1000%+ margins downstream once divided
    # against a genuine (also wrongly quarter-only) gross_profit figure. Duration
    # (end - start) is only meaningful for flow/duration facts (revenue, income,
    # cash flow - always have "start"); instant/point-in-time balance-sheet facts
    # (Assets, Liabilities, ...) have no "start" and are correctly accepted for any
    # fp, since an "as of" balance is valid regardless of the tag's fp. Threshold
    # (330 days) intentionally excludes real single-quarter chunks (~90 days) while
    # still accepting genuine full-year cumulative facts that got mistagged with a
    # quarterly fp (e.g. some Q4 YTD figures span the whole year).
    #
    # WIDENED 2026-08-09 (same day, later session): the check above only fired for
    # fp in ('Q1'-'Q4'), on the assumption a short-duration entry would always carry
    # a quarterly fp tag. Live-confirmed false via AAT (American Assets Trust, a
    # REIT): its FY2025 10-K's XBRL "Revenues" facts include a genuinely 90-day
    # entry (2024-01-01 to 2024-03-31, real Q1 2024 data used as a comparative
    # figure elsewhere in the filing) tagged fp='FY' - the SEC fy/fp combination
    # apparently isn't a reliable proxy for actual span even when fp='FY'. That
    # entry was accepted into the FY2024 annual bucket, understating real revenue
    # ($110.7M quarter vs a real ~$440M+ full year, confirmed via the same filing's
    # own comparative FY2023 entry). Now applies the same span check to every fp
    # value during annual extraction, not just Q1-Q4 - only gated on period=="annual"
    # so quarterly extraction (which legitimately wants short-duration entries) is
    # unaffected.
    start_date = entry.get("start")
    if period == "annual" and start_date and entry.get("end"):
        try:
            span_days = (datetime.date.fromisoformat(entry["end"]) - datetime.date.fromisoformat(start_date)).days
        except ValueError:
            span_days = None
        if span_days is not None and span_days < 330:
            return None  # Real single-quarter/partial-year data - not annual
        # See the _short_span_val_by_accn comment above this loop (JAKK case):
        # an annual-shaped span whose value exactly matches a genuine quarter
        # from the same accn is that quarter's value under borrowed annual
        # dates, not a real annual total.
        if span_days is not None and span_days >= 330:
            _accn = entry.get("accn")
            if _accn and entry.get("val") in _short_span_val_by_accn.get(_accn, ()):
                return None

    # BUG FOUND 2026-08-31 (goal session: "get all the data we need" full-
    # coverage audit): a duration fact (has "start") sourced from an 8-K is
    # never a genuine periodic financial statement - Item 9.01 exhibits, investor-
    # presentation Regulation FD disclosures, and other 8-K content are not
    # subject to the same XBRL-tagging rigor as a 10-K/10-Q, and can carry
    # numbers that are wrong, a peer-comparison figure, or otherwise not the
    # filer's own audited result. Live-confirmed via real SEC companyfacts JSON:
    # Essential Utilities (WTRG, CIK 0000078128) tags
    # RevenueFromContractWithCustomerExcludingAssessedTax for FY2023/2024/2025
    # under a single 2026-03-25 "Regulation FD Disclosure" 8-K (accn
    # 0001193125-26-124163, fp=None, fy=None) with values ($4.217B/$4.653B/
    # $5.121B) that exactly match American Water Works' (AWK, an unrelated
    # company) real 10-K-sourced revenue for the same years to the dollar - not
    # WTRG's own real revenue (WTRG's genuine "Revenues" concept for the same
    # years, sourced from real 10-Ks, is ~$2.1-2.5B). Because this concept is
    # listed after "Revenues" in get_income_statement()'s concepts list (ASC-606
    # tags legitimately supersede the older concept for most post-2018 filers),
    # this bad 8-K value silently overwrote WTRG's real revenue in
    # annual_income_statement, corrupting every downstream ratio.
    # Deliberately does NOT extend to DEF 14A/proxy statements (fp=None is
    # accepted above specifically because 2026-07-31 relies on exactly that for
    # quarterly-only reporters like EE with no full annual filing) - 8-K
    # specifically, since it's a "current report" for events/exhibits, never a
    # periodic financial statement, and no fix in this file has ever relied on
    # trusting one for duration data (test_sec_custom_xbrl_concepts.py already
    # treats 8-K as something to skip when looking for a filer's authoritative
    # annual data, for the same reason).
    if start_date and entry.get("form") in ("8-K", "8-K/A"):
        return None

    # See the _max_end_by_accn comment above this loop: drop any instant fact
    # that isn't the latest-end-date one within its own filing - a comparative/
    # rollforward echo of a period whose real value comes from its own filing.
    if not start_date:
        _accn, _e_end = entry.get("accn"), entry.get("end")
        if _accn and _e_end and _max_end_by_accn.get(_accn) not in (None, _e_end):
            return None

    # FIXED 2026-08-18 (no-SEC-data audit continuation): see the
    # has_annual_report_form comment above this loop. An instant fact sourced
    # from a 10-Q/6-K must not seed the annual bucket when this concept has
    # real 10-K/20-F/40-F history and the fact is BEYOND that history's own
    # reach - it's a genuine mid-year snapshot, not a fiscal-year-end position,
    # and the fiscal year it falls in (derived from its own end date below)
    # usually has no 10-K filed yet at all.
    # NARROWED 2026-09-02 (see _max_annual_report_end comment above this loop,
    # WEC live-confirmed): only skip when this fact's end date is genuinely
    # AFTER the concept's own latest confirmed 10-K/20-F/40-F end date - a
    # fact at or before that boundary is a past fiscal year-end the annual
    # filing itself simply never re-tagged (recoverable from a later filing's
    # comparative column), not a premature current-year snapshot.
    if (
        period == "annual"
        and not start_date
        and has_annual_report_form
        and entry.get("form") not in _ANNUAL_REPORT_FORMS
        and (_max_annual_report_end is None or (entry.get("end") or "") > _max_annual_report_end)
    ):
        return None

    if period == "annual":
        if fp == "FY" or fp is None or fp in ("Q1", "Q2", "Q3", "Q4"):
            pass  # Accept annual, proxy, and quarterly(-but-full-span) data
        else:
            return None  # Skip other FP values
    elif period == "quarterly" and fp not in fp_filter:
        # See has_december_fiscal_year_end's comment above this loop for the
        # full AGNC-verified rationale. Only ever a fallback when the filer's
        # own fp tag doesn't already give a real Q1-Q4 answer; derived_fp stays
        # None (entry skipped, same as before this fix) for every case this
        # doesn't narrowly apply to - duration facts, non-December fiscal
        # years, or an end date that isn't a clean quarter-boundary month.
        derived_fp = None
        if not start_date and has_december_fiscal_year_end and entry.get("end") and len(entry["end"]) >= 7:
            derived_fp = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}.get(entry["end"][5:7])
        if derived_fp is None:
            return None
        fp = derived_fp
    elif period == "quarterly" and has_december_fiscal_year_end and entry.get("end") and len(entry["end"]) >= 7:
        # BUG FOUND 2026-08-24 (goal session: real-money-readiness audit,
        # quarterly_balance_sheet residual follow-up): an instant fact's own fp
        # tag reflects the FILING's reporting period, not the fact's own period -
        # the exact same filing-context-vs-fact-identity conflation this file
        # already documents for fy (see "Use period end year..." below) and for
        # fp when it's mistagged 'FY' (the AGNC case just above). This is a THIRD
        # variant: fp already looks like a normal Q1-Q4 tag (so the branch above
        # never fires), but the fact is actually a prior-period comparative echo
        # that its own filing never re-tagged with a genuine current-period value
        # for this concept - live-confirmed via CCLD: its Q1/Q2/Q3 2021 10-Qs each
        # have exactly ONE Assets fact, end=2020-12-31 (the FY2020 year-end
        # comparative), tagged fp='Q1'/'Q2'/'Q3' (borrowed from the FILING's own
        # quarter) - so it passes the accn-latest-end-date filter above (it's the
        # only Assets fact in that accn) and, untouched, would collide with the
        # real Q1/Q2/Q3 2020 facts' own (2020, 'Q1'/'Q2'/'Q3') keys, winning via
        # the "prefer latest end date" tiebreak below and silently overwriting
        # them with the FY-end value. A universe-wide scan for this exact
        # single-quarter-aliasing signature found 53 symbols, including
        # actively-traded large/mid-caps (BX, BN, AES), not just micro-caps.
        # Always deriving fp from the fact's own end date (already trusted
        # elsewhere in this file - see period_year below - as more reliable than
        # any SEC period label) instead of trusting a syntactically-valid-looking
        # fp tag closes this: when the filer's own fp already agrees with the
        # end-date-derived quarter, this is a no-op; when it doesn't, the derived
        # quarter is the fact's real period, and the key it produces will
        # correctly collide with (not overwrite) the genuine same-period fact.
        #
        # EXTENDED 2026-09-02 (goal session: "missing SEC/XBRL data" audit,
        # restoring the duration-fact half of `fd1c8a99f`, which - like the
        # self-consistency block above - only ever landed on the unmerged
        # `growth-factor-realignment` branch, not main). Live-confirmed via OFRM
        # why "not start_date" (instant-only) isn't enough on its own: even with
        # the self-consistency block above correctly setting
        # has_december_fiscal_year_end=True and the existing shorter-span-wins
        # tiebreak below (2026-08-29, META fix), OFRM's real Q2-2026 NetIncomeLoss
        # bucket has THREE competing duration facts - a genuine H1 cumulative
        # (~180 days), the real discrete Q2 (Apr-Jun, 90 days), and a Q1
        # comparative mistagged with the filing's own fp='Q2' (Jan-Mar, 89 days,
        # same accn as the H1 fact). The shorter-span heuristic correctly prefers
        # a genuine quarter over a cumulative echo, but is not a meaningful
        # tiebreak between TWO genuine single-quarter spans - Jan-Mar's 89 days
        # happens to be one day shorter than Apr-Jun's 90 (February is short), so
        # the mistagged comparative silently won over the real value purely by
        # calendar-month coincidence (live-confirmed: net_income_loss stored
        # -$15,811,000 for both Q1 and Q2 2026, when Q2's real value is
        # -$4,950,000). The fix is to remove the mistagged entry from the Q2
        # bucket entirely rather than out-tiebreak it: applying this same
        # end-date-derived fp correction to a duration fact - narrowly gated to a
        # genuine single-quarter span (80-100 days) so real cumulative (H1/9mo)
        # facts are untouched and still resolved by the shorter-span tiebreak once
        # co-located with their quarter's real discrete fact via this same
        # derivation - relocates Jan-Mar's comparative echo to Q1 (where it
        # harmlessly duplicates the real Q1 value already there), leaving Q2's
        # bucket with only the real discrete fact and the H1 cumulative, which the
        # existing tiebreak already resolves correctly.
        _duration_span_days: int | None = None
        if start_date:
            try:
                _duration_span_days = (
                    datetime.date.fromisoformat(entry["end"]) - datetime.date.fromisoformat(start_date)
                ).days
            except ValueError:
                _duration_span_days = None
        if not start_date or (_duration_span_days is not None and 80 <= _duration_span_days <= 100):
            derived_fp = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}.get(entry["end"][5:7])
            if derived_fp is not None:
                fp = derived_fp

    # Use period end year as the fiscal year key, not SEC's fy field.
    # SEC tags ALL periods in a 10-K with fy=FILING_YEAR - so prior-year
    # comparison data (end='2022-06-30') included in a FY2024 10-K would
    # have fy=2024 instead of fy=2022. Deriving year from end date correctly
    # separates current-year data from the multi-year comparison tables.
    end_date = entry.get("end", "")
    period_year = int(end_date[:4]) if end_date and len(end_date) >= 4 else entry.get("fy")

    # FIXED 2026-08-16: 52/53-week fiscal calendars (common among retail/
    # industrial filers, e.g. SWK) can end a few days into January instead
    # of Dec 31 - live-confirmed SWK's real FY2020 10-K reports fy=2020,
    # start=2019-12-29, end=2021-01-02 (370-day/53-week year, majority of
    # days in calendar 2020). Bucketing by end-date's bare calendar year put
    # this in "2021", silently colliding with (and getting overwritten by)
    # FY2021's own later-filed entry - leaving FY2020 revenue/net_income
    # NULL (data_unavailable='incomplete_sec_filing_income') despite SEC
    # having the data all along; live-confirmed via direct DB query this
    # single mislabeling pattern accounts for a meaningful share of the
    # ~1,077 historical-year "incomplete_sec_filing" rows. Narrowly scoped
    # to end dates in the first 10 days of January, so ordinary non-calendar
    # fiscal years that end well into January/February (e.g. Walmart's Jan
    # 31) or other months (e.g. Apple's Sep 30) are untouched - only the
    # narrow year-end-crosses-Jan-1 case is affected. entry['fy'] is trusted
    # here specifically because in this window it's the filing's own current-
    # period label, not a comparative-year figure (see comment above) - only
    # applied when it actually points one year earlier than the naive
    # end-date bucket, so a filer that genuinely intends the end-year label
    # is left alone.
    if period == "annual" and end_date and len(end_date) >= 10 and end_date[5:10] <= "01-10":
        fy = entry.get("fy")
        if start_date:
            _corroborated = _fy_by_start_end_val.get((start_date, end_date, entry.get("val")))
            if _corroborated is not None:
                fy = _corroborated[0]
        if isinstance(fy, int) and fy == period_year - 1:
            period_year = fy

    # FIXED 2026-08-18 (goal: "no SEC data"/missing factor inputs audit): DEI
    # cover-page facts (e.g. EntityCommonStockSharesOutstanding) are "as of the
    # latest practicable date before filing" snapshots, not economic-activity
    # facts - their own end date can be weeks to months AFTER the real fiscal
    # year end. Live-confirmed via AAP: the FY2024 10-K's real revenue duration
    # fact ends 2024-12-28 (bucketed fiscal_year=2024, correct), but its
    # accompanying dei:EntityCommonStockSharesOutstanding cover-page fact is
    # dated 2025-02-19 - 6 weeks later, crossing into the next calendar year.
    # Bucketing by end-date year (the general rule above, justified for us-gaap/
    # ifrs facts since SEC's fy tag conflates current-year and comparative-year
    # data within one filing - see the "Use period end year..." comment above)
    # created a phantom fiscal_year=2025 bucket containing ONLY this one DEI
    # fact, sandwiched between the real FY2024 and FY2026 buckets - and every
    # prior-year lookback in load_value_quality_growth_metrics.py keys strictly
    # off fiscal_year-1, so this phantom bucket silently blocked EVERY
    # *_growth_yoy/*_trend metric for the symbol (live DB scan: 120 active
    # symbols have this exact sandwiched-incomplete-year signature). Unlike
    # us-gaap/ifrs facts, DEI cover-page facts don't carry historical
    # comparative-year entries (one "as of" value per filing, not a multi-year
    # table), so entry['fy'] IS reliably the filing's real fiscal year for this
    # source - trust it directly instead of the end-date derivation.
    if source == "dei" and period == "annual" and isinstance(entry.get("fy"), int):
        period_year = entry["fy"]

    # BUG FOUND 2026-08-19 (goal: fix today's halting/data-quality issues):
    # SEC's own XBRL data is occasionally corrupted in ways that produce an
    # implausible fiscal year from either derivation path above - live-confirmed
    # two distinct patterns: (1) NAII NetIncomeLoss fact tagged end="2031-09-25"
    # (evidently meant 2023 - fy=2022 on the same fact is correct) fed
    # fiscal_year=2031 via the end-date derivation, writing REAL revenue/
    # net_income into the DB under a 5-years-in-the-future fiscal year
    # (data_unavailable=False, so it would be picked up as "latest data" by any
    # naive ORDER BY fiscal_year DESC caller); (2) PRTH dei:
    # EntityCommonStockSharesOutstanding facts carry fy=43465/43830 directly in
    # SEC's JSON (an Excel-serial-like value, not a real year) - trusted verbatim
    # by the dei-source branch above, this also broke
    # data_loader_status's MAX(fiscal_year) -> date(fiscal_year, 12, 31) watermark
    # write every run ("year 43830 is out of range", live-confirmed in
    # logs/load_financial_statements_1787150329.log). Neither end_date nor fy is
    # trustworthy in isolation, so fall back to whichever of the two is itself
    # plausible, and skip the entry entirely (like other malformed-data skip
    # paths in this file) only if neither is.
    if isinstance(period_year, int) and not (_MIN_PLAUSIBLE_FISCAL_YEAR <= period_year <= _max_plausible_fiscal_year):
        fallback_year = entry.get("fy")
        end_year = int(end_date[:4]) if end_date and len(end_date) >= 4 else None
        candidate = fallback_year if isinstance(fallback_year, int) else None
        if candidate is None or not (_MIN_PLAUSIBLE_FISCAL_YEAR <= candidate <= _max_plausible_fiscal_year):
            candidate = end_year
        if candidate is not None and (_MIN_PLAUSIBLE_FISCAL_YEAR <= candidate <= _max_plausible_fiscal_year):
            logger.warning(
                f"[SEC_STATEMENTS] {symbol}: implausible fiscal_year={period_year} "
                f"from concept={concept} end={end_date!r} fy={entry.get('fy')!r} - "
                f"using {candidate} instead"
            )
            period_year = candidate
        else:
            logger.warning(
                f"[SEC_STATEMENTS] {symbol}: skipping entry with implausible "
                f"fiscal_year={period_year} and no plausible fallback "
                f"(end={end_date!r} fy={entry.get('fy')!r})"
            )
            return None

    # FIX 2026-09-03 (goal: SEC/XBRL missing-data audit, BTCS live-verified via
    # real SEC companyfacts JSON): the annual branch above already rejects a too-
    # SHORT duration from its own bucket (span_days < 330 -> skip, "Real single-
    # quarter/partial-year data - not annual"), but quarterly had no mirror-image
    # guard against a too-LONG one. A fact whose OWN fp tag already equals Q1-Q4
    # skips the derived_fp relocation logic above entirely (that only fires when fp
    # does NOT already match a real quarter) and was accepted at face value with no
    # span check at all. Live-confirmed via BTCS: its 2012 Q1/Q2/Q3 10-Qs (and 2014
    # 10-Q/A amendments) each independently mistagged the SAME full FY2010 annual
    # total (start=2010-01-01, end=2010-12-31, 365 days) as that quarter's own
    # "prior year" comparative figure - fp="Q1" in the Q1 10-Q, fp="Q2" in the Q2
    # 10-Q, fp="Q3" in the Q3 10-Q, four separate genuine filer-side tagging errors
    # across four filings, not one mis-relocated comparative like the OFRM/DXC case
    # `b8c37c0bc` fixed. With no genuine discrete quarterly fact ever filed for
    # FY2010 to tiebreak against, each mistagged annual total became the sole
    # occupant of its (2010, Q1/Q2/Q3) bucket - reproduced exactly via
    # get_income_statement(client, 'BTCS', period='quarterly'): FY2010 Q1/Q2/Q3
    # revenue/net_income all equalled the FY2010 annual total. Same 330-day
    # threshold as the annual branch's own span_days<330 guard, applied
    # symmetrically: no genuine quarterly-bucket fact (even a 9-month YTD
    # cumulative, the longest legitimate one) should ever approach a full year.
    if period == "quarterly" and start_date and fp in ("Q1", "Q2", "Q3", "Q4") and end_date:
        try:
            _q_span_days = (datetime.date.fromisoformat(end_date) - datetime.date.fromisoformat(start_date)).days
        except ValueError:
            _q_span_days = None
        if _q_span_days is not None and _q_span_days >= 330:
            return None

    return fp, period_year, start_date, end_date


def _aggregate_concepts_should_replace_entry(
    entry: Any,
    entry_filed: str,
    entry_form: str | None,
    key: tuple[Any, Any],
    row: dict[str, Any],
    col: str,
    start_date: Any,
    end_date: Any,
    period: str,
    concept: str | None = None,
) -> tuple[bool, int, bool]:
    """Decide whether ``entry`` should replace the currently-stored value for ``col``.

    Extracted from _aggregate_concepts (mechanical extraction, no behavior change).
    Returns (should_replace, entry_rank, is_instant).

    FIXED 2026-09-07 (CVE FY2022 current_assets=0.0 live-confirmed): a secondary/fallback
    IFRS alias concept for the same target column (e.g. sec_balance_sheet.py's
    _BALANCE_IFRS_ALIASES CurrentAssetsOtherThan...HeldForSale fallback) could overwrite an
    already-populated PRIMARY concept's value via the frame-preference tiebreak (added for
    PMT/IPAR, designed for same-concept multi-fact collisions, not cross-concept ones).
    CVE's primary CurrentAssets concept correctly reports $12.43B CAD with no frame key;
    the fallback concept's same-accn/same-filed/same-end_date fact reports 0 but DOES carry
    SEC's frame tag, so it wrongly won. Fix: track which concept last populated each column
    and require a concept match before falling through to the frame/end-date tiebreak -
    first-populated-wins for cross-concept collisions, same-concept PMT/IPAR/RIGL/LADR
    tiebreaks unaffected.
    """
    # FIXED 2026-09-02 (goal session: "missing SEC/XBRL data" audit, live SEC
    # EDGAR verification): _PRIMARY_STATEMENT_FORMS ranks 10-K and 10-Q equally
    # (both "primary", tier 1) - correct for a QUARTERLY bucket, but wrong for
    # an annual ("FY") bucket: a 10-Q can carry a genuine "trailing twelve
    # months" duration fact (start/end exactly ~365 days apart, passing this
    # loop's own span_days>=330 "annual-shaped" filter above) that is NOT the
    # filer's real Jan-Dec fiscal year - it's a rolling window ending mid-year.
    # Live-confirmed via real SEC EDGAR companyconcept JSON: AMZN's Q2 2026
    # 10-Q (filed 2026-07-31) tags NetIncomeLoss with start=2025-07-01,
    # end=2026-06-30, val=$135,281,000,000 (a real TTM figure) - this lands in
    # the SAME (period_year=2026, "FY") bucket as AMZN's real FY2026 10-K would,
    # and via the old equal-rank-then-latest-filed tiebreak, ALSO clobbered the
    # already-correct FY2025 entry: AMZN's real FY2025 10-K (filed 2026-02-06)
    # reports NetIncomeLoss=$77,670,000,000, but a LATER-filed Q2 2026 10-Q TTM
    # fact (start=2024-07-01, end=2025-06-30, val=$70,623,000,000, also >=330
    # days) won the (2025, "FY") bucket instead purely by filing date - live-
    # confirmed exactly these two wrong values on file in annual_income_statement
    # before this fix. A genuine annual-report-form entry (10-K/20-F/40-F) must
    # always outrank a same-tier 10-Q/6-K entry for the "FY" key specifically,
    # regardless of filed date - same "structural form authority beats filing
    # recency" principle _ANNUAL_REPORT_FORMS already applies to the instant-fact
    # premature-bucket guard elsewhere in this function. Only applies to the "FY"
    # key; quarterly buckets (fp in Q1-Q4) are unaffected, so a pure quarterly-
    # only reporter's own latest-filed 10-Q still wins its bucket unchanged - and
    # a 10-Q still wins the "FY" bucket by the ordinary rank-vs-non-primary-form
    # rule above when no annual-report-form entry exists for that period at all.
    is_fy_bucket = key[1] == "FY"
    entry_rank = (
        2 if is_fy_bucket and entry_form in _ANNUAL_REPORT_FORMS else 1 if entry_form in _PRIMARY_STATEMENT_FORMS else 0
    )
    row_filed = row.get(f"_filed_{col}")
    row_end = row.get(f"_end_{col}")
    rank_key = f"_rank_{col}"
    row_rank = int(row[rank_key]) if rank_key in row else 0
    # Form-rank gates first: a primary form (10-K/10-Q) always outranks a
    # non-primary one (DEF 14A, 8-K, S-1, etc.) regardless of end/filed date -
    # see the 2026-08-17 DEF 14A comment above. Only when ranks tie do we fall
    # through to the existing instant-vs-duration end-date/filed-date tiebreak.
    is_instant = not start_date
    if col not in row:
        should_replace = True
    elif entry_rank != row_rank:
        should_replace = entry_rank > row_rank
    elif is_instant != bool(row.get(f"_is_instant_{col}")):
        # FIX 2026-08-31 (/goal pre-real-money audit, live-verified LADR): a
        # genuine annual duration fact (has "start", already passed the
        # span_days>=330 annual-shape filter above) must always outrank an
        # instant (point-in-time, no "start") fact colliding into the same
        # (fiscal_year, "FY") bucket for the same concept - an instant fact
        # appearing at all under a duration-shaped concept's name is itself
        # anomalous (a real annual total is never point-in-time). Live-confirmed
        # via LADR (Ladder Capital, mortgage REIT) FY2019: OperatingLeaseLeaseIncome
        # has both the real annual total (start=2019-01-01/end=2019-12-31,
        # val=$106,366,000) AND a bare instant fact (no start, end=2019-05-01,
        # val=$3,900,000 - almost certainly a future-minimum-lease-payments
        # schedule row, not a period total) from the SAME accn/filed date, so
        # neither the rank gate above nor the old filed-date tiebreak below could
        # tell them apart - whichever was iterated first in SEC's JSON silently
        # won, and that was the wrong one. Safe for balance-sheet concepts too:
        # they structurally never emit a genuine annual-duration-shaped fact
        # under their own concept name (Assets/Liabilities/etc. are inherently
        # point-in-time - no legitimate "start" date ever exists for them), so
        # this branch is a no-op there and only fires on a real conflict like
        # LADR's.
        should_replace = bool(row.get(f"_is_instant_{col}"))
    elif concept is not None and row.get(f"_concept_{col}") not in (None, concept):
        # FIXED 2026-09-07: same rank AND same instant-ness, but a DIFFERENT concept than
        # the one that already populated this column - never let the tiebreak refinements
        # below hand a fallback/secondary alias concept priority over an already-populated
        # primary concept's fact. First-populated-wins for cross-concept collisions.
        should_replace = False
    else:
        # FIXED 2026-08-18 (live-verified RIGL): instant/point-in-time balance-
        # sheet facts (no "start" - see this loop's is_instant-equivalent comment
        # above) for DIFFERENT periods within the same calendar year (e.g. a Q1
        # comparative StockholdersEquity figure re-cited in a later 10-Q's
        # context, alongside the real FY-end figure) collide into the SAME
        # (fiscal_year, "FY") bucket and frequently share the identical "filed"
        # date (both facts come from the same filing). "latest filed wins" alone
        # then picks whichever entry happened to be iterated last - arbitrary,
        # not correctness-driven. Live-confirmed: RIGL's real FY2025 10-K/10-Q
        # filings tag StockholdersEquity end=2025-03-31 ($18.567M, a Q1 snapshot)
        # AND end=2025-12-31 ($391.48M, the real year-end) with the SAME filed
        # date - the Q1 value won on iteration order, producing net_income
        # ($367.0M) / equity($18.567M) = 1976.75% ROE instead of the real ~94%.
        # For instant facts, prefer the entry whose end date is latest (closest
        # to the true fiscal year end) before falling back to filed-date as a
        # tiebreak; annual duration facts are unaffected - their span-day filter
        # above already narrows the field to genuine annual totals, where "most
        # recently filed" legitimately means "most likely restated/corrected".
        # Quarterly duration facts get their own span tiebreak below - see the
        # 2026-08-29 comment at that branch.
        if is_instant:
            should_replace = row_end is None or end_date > row_end
            if not should_replace and end_date == row_end:
                # FIXED 2026-08-22 (goal session: PMT debt-maturity-schedule
                # contamination): multiple facts can legitimately share the exact
                # same (concept, end_date) - a real balance-sheet snapshot AND
                # unrelated debt-maturity-schedule footnote entries that happen to
                # use the same future end date as a schedule bucket boundary.
                # "latest filed wins" alone is NOT reliable here: schedule entries
                # get re-disclosed (same date, same value) in every subsequent
                # year's 10-K/10-Q, so a schedule entry can have a LATER filed
                # date than the one real snapshot fact for that period. SEC's own
                # "frame" key is the reliable signal - it's only assigned to the
                # single canonical, non-dimensional instant/duration fact for a
                # standardized calendar period, never to a dimensional/footnote
                # schedule entry. Live-confirmed via PMT's real companyfacts JSON:
                # LongTermDebt end=2026-03-31 has 4 candidate entries (fy=2021/22/23
                # all val=$695M, no frame; fy=2024 val=$1.497B, frame="CY2026Q1I")
                # - the frame'd entry is the real snapshot, the other 3 are the
                # same static debt-maturity-schedule bucket re-cited across 3 years
                # of filings. DB-wide cross-check against every frame-confirmed
                # LongTermDebt value found 11 real mismatches (FY2022-2024 Q1-Q3,
                # off by billions - e.g. FY2022 stored $1.70B vs real $5.07B).
                entry_has_frame = bool(entry.get("frame"))
                row_has_frame = bool(row.get(f"_frame_{col}"))
                if entry_has_frame != row_has_frame:
                    should_replace = entry_has_frame
                    # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, tie-out
                    # audit follow-up): SEC's own "frame" assignment is normally trusted
                    # unconditionally as the canonical-value signal (see the PMT case above),
                    # but it is itself just an index over whatever facts filers submitted -
                    # live-confirmed via Inter Parfums (IPAR) FY2021 CashAndCashEquivalentsAt
                    # CarryingValue: the ORIGINAL FY2021 10-K (filed 2022-03-01) and three later
                    # 10-Qs/one 10-K comparative period all agree on ~$159-168M with NO frame
                    # key at all, but IPAR's FY2023 10-K (filed 2024-02-27) re-cites the same
                    # 2021-12-31 period as $159,613,000,000 - a filer-side 1000x decimals-tag
                    # error on their part - and THAT corrupted entry is the one SEC's frames API
                    # happened to tag "CY2021Q4I", so the existing frame-preference rule
                    # confidently replaced the correct ~$159.6M figure with a bogus $159.6B one.
                    # A frame-tagged replacement whose value differs from unanimous prior
                    # agreement by a ratio suspiciously close to a clean power of 10 (100x/
                    # 1000x/10000x, within 1%) is far more likely a decimals-tag error than a
                    # real business change - real restatements essentially never move a balance
                    # by an exact round factor of 10. Only overrides the frame-preference in
                    # this narrow, high-confidence shape; every other frame-vs-no-frame case
                    # (the overwhelming majority) is unaffected.
                    if entry_has_frame and col in row:
                        _existing_val = row.get(col)
                        _entry_val = entry.get("val")
                        if (
                            isinstance(_existing_val, int | float)
                            and isinstance(_entry_val, int | float)
                            and _existing_val != 0
                            and _entry_val != 0
                        ):
                            _ratio = abs(_entry_val) / abs(_existing_val)
                            if _ratio < 1:
                                _ratio = 1 / _ratio
                            if any(abs(_ratio - _power) / _power < 0.01 for _power in (100, 1000, 10000)):
                                logger.warning(
                                    f"[frame_magnitude_scale_guard] Rejecting frame-tagged "
                                    f"replacement for {col} (accn {entry.get('accn')}): "
                                    f"{_entry_val} is a {_ratio:.0f}x-scaled outlier vs the "
                                    f"already-agreed {_existing_val} - likely a filer decimals-"
                                    f"tag error, not a real restatement."
                                )
                                should_replace = False
                else:
                    should_replace = row_filed is None or entry_filed > row_filed
        elif period == "quarterly":
            # FIXED 2026-08-29 (goal: composite-score validation against real
            # data): a Q2/Q3 10-Q's XBRL discloses BOTH the discrete "three
            # months ended" fact AND the cumulative "six/nine months ended"
            # fact for the same line item, and SEC tags fp='Q2'/'Q3' on the
            # FILING's own period for both - identical (fiscal_year, fp) key,
            # same filed date (same filing) - so the old filed-date-only
            # tiebreak picked whichever happened to iterate first, which
            # empirically was the CUMULATIVE fact. Live-confirmed via META's
            # real companyfacts JSON: fy=2026/fp=Q2 has both a 2026-04-01to
            # 2026-06-30 discrete fact (val=$60.801B, frame="CY2026Q2") and a
            # 2026-01-01to2026-06-30 cumulative fact (val=$117.111B,
            # frame=None) - quarterly_income_statement stored the $117.111B
            # H1-cumulative figure as META's "Q2 2026 revenue", corrupting
            # every downstream growth_metrics YoY/TTM calc (revenue_growth_1y
            # came out -71.98% against margins that were actually improving).
            # Same pattern independently confirmed for AAPL and MSFT - this is
            # a systemic bug affecting essentially every calendar-Q2/Q3 filer,
            # not a META-specific data issue. A genuine single quarter always
            # spans ~89-92 days; a same-fiscal-year cumulative echo spans
            # ~180-190 (H1) or ~270-280 (9mo) days - always clearly
            # distinguishable via duration alone, so prefer the entry with the
            # SHORTER start-to-end span over the filed-date tiebreak.
            entry_span = (
                (datetime.date.fromisoformat(entry["end"]) - datetime.date.fromisoformat(start_date)).days
                if entry.get("end")
                else None
            )
            row_span = row.get(f"_span_{col}")
            if entry_span is not None and row_span is not None and entry_span != row_span:
                should_replace = entry_span < row_span
            else:
                should_replace = row_filed is None or entry_filed > row_filed
        else:
            # FIX 2026-08-31 (/goal pre-real-money audit, live-verified TKR):
            # two genuine annual-length (>=330-day) duration facts for the SAME
            # concept can both exist in the SAME filing (same accn/filed date) -
            # a real calendar-year total and an off-calendar spurious value
            # (e.g. a stray sub-line or filing-agent error) - and then both get
            # re-cited verbatim in later years' 10-Ks with matching filed dates
            # each time, so the old plain filed-date tiebreak (strict >) never
            # distinguishes them; whichever was iterated first in SEC's JSON
            # silently won. Live-confirmed via TKR (Timken) FY2015
            # SalesRevenueGoodsNet: the real total (start=2015-01-01/
            # end=2015-12-31, val=$2,872,300,000) and a spurious value
            # (start=2014-10-01/end=2015-09-30, val=$20,600,000, ~0.7% of real
            # revenue) both first appear in accn 0000098362-16-000097 (filed
            # 2016-02-24) and both get re-cited identically in 2 later 10-Ks
            # (accn ...17-000031 filed 2017-02-21, accn ...18-000033 filed
            # 2018-02-15) - same filed dates every time. The one reliable
            # difference: the real value eventually gets frame="CY2015" in its
            # later re-citations (SEC's own signal for "the single canonical
            # value for this standardized period" - already trusted the same
            # way for the instant-fact PMT case above), the spurious value
            # never does, in any of its 3 occurrences. Applying the identical
            # frame-preference principle here (not a new heuristic - the same
            # one already proven safe for instant facts) before falling back to
            # filed-date resolves this the same way it does for PMT.
            entry_has_frame = bool(entry.get("frame"))
            row_has_frame = bool(row.get(f"_frame_{col}"))
            if entry_has_frame != row_has_frame:
                should_replace = entry_has_frame
            else:
                should_replace = row_filed is None or entry_filed > row_filed

    return should_replace, entry_rank, is_instant


def _aggregate_concepts_apply_entry_value(
    row: dict[str, Any],
    col: str,
    entry: Any,
    entry_rank: int,
    is_instant: bool,
    start_date: Any,
    end_date: Any,
    period: str,
    is_major_currency: bool,
    _currency_code: str,
    concept: str | None = None,
) -> None:
    """Write ``entry``'s value (with FX conversion if needed) into ``row[col]``.

    Extracted from _aggregate_concepts (mechanical extraction, no behavior change). A failed
    FX lookup returns early (leaving the column unset for this entry), matching the original
    ``continue``.
    """
    val = entry.get("val")
    if is_major_currency and isinstance(val, (int, float)) and end_date:
        fx_rate = _fx_rate_cache.get_usd_rate(_currency_code, end_date)
        if fx_rate is None or fx_rate == 0:
            # No real rate available for this exact date - fail closed,
            # never guess. Leaves this entry unset for this column, same
            # as if the whole currency had been rejected outright.
            return
        val = val / fx_rate
    row[col] = val
    row[f"_filed_{col}"] = entry.get("filed")
    row[f"_end_{col}"] = end_date
    row[f"_rank_{col}"] = entry_rank
    row[f"_frame_{col}"] = bool(entry.get("frame"))
    row[f"_is_instant_{col}"] = is_instant
    row[f"_concept_{col}"] = concept
    if period == "quarterly" and start_date and end_date:
        try:
            row[f"_span_{col}"] = (datetime.date.fromisoformat(end_date) - datetime.date.fromisoformat(start_date)).days
        except ValueError:
            row[f"_span_{col}"] = None
