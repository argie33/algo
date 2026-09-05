"""Currency/unit-context resolution for the XBRL concept-aggregation engine, extracted from
sec_statements_aggregate.py (2026-09-05, further split: that file itself exceeded the 800-line
new-file cap once first extracted from sec_statements.py). Body is verbatim, no logic changed -
called by _aggregate_concepts in sec_statements_aggregate.py.
"""

import datetime
from typing import Any

from utils.external.sec_statements_shared import _ANNUAL_REPORT_FORMS


def _aggregate_concepts_build_unit_context(  # noqa: C901 -- inherits pre-existing complexity debt extracted from _aggregate_concepts, not new logic
    entries: list[dict[str, Any]],
) -> tuple[
    bool,
    str | None,
    bool,
    dict[str, str],
    dict[str, set[Any]],
    dict[tuple[str, str, Any], tuple[int, str]],
]:
    """Precompute per-(concept, unit) context used to resolve each entry's real period.

    Extracted from _aggregate_concepts (mechanical extraction, no behavior change).
    Returns (has_annual_report_form, max_annual_report_end, has_december_fiscal_year_end,
    max_end_by_accn, short_span_val_by_accn, fy_by_start_end_val).
    """
    # FIXED 2026-08-18 (no-SEC-data audit continuation): live-confirmed via GM and
    # DIS - both file normal 10-Ks every year, yet annual_balance_sheet had a
    # fiscal_year=2026 row (the current, not-yet-concluded fiscal year) with
    # total_assets/stockholders_equity populated from a 10-Q's mid-year instant
    # snapshot (e.g. GM: Assets end=2026-06-30, form=10-Q, val=$282.742B) while
    # long_term_debt stayed NULL because no 10-Q that quarter re-tagged that
    # concept. Real, complete FY2025 data (long_term_debt=$131.574B) already
    # existed one row back, but every "ORDER BY fiscal_year DESC LIMIT 1" caller
    # picked the incomplete FY2026 stub instead - this single pattern explains a
    # large share of "missing_sec_data" across quality_metrics/value_metrics
    # (debt_to_equity, interest_coverage, total_debt, roic_pct, ...), not a
    # per-concept fallback gap. The instant-fact "prefer latest end date" logic
    # below (test_sec_statements_instant_fact_prefers_latest_end_date.py) already
    # established that only a true fiscal-year-end snapshot should win within a
    # single bucket; this closes the related gap where a mid-year 10-Q snapshot
    # creates an entirely NEW, premature bucket for a fiscal year whose 10-K
    # hasn't been filed yet. Only suppresses 10-Q/6-K instant facts when this
    # concept has a real annual-report history at all - quarterly-only reporters
    # (no 10-K/20-F/40-F ever, e.g. EE) keep using their 10-Q instant facts as the
    # only available annual data, same fallback-of-last-resort precedent as
    # _PRIMARY_STATEMENT_FORMS above.
    has_annual_report_form = any(e.get("form") in _ANNUAL_REPORT_FORMS for e in entries)
    # ADDED 2026-09-02 (goal session: "missing SEC/XBRL data" audit, WEC live-
    # confirmed): the has_annual_report_form gate below (2026-08-18 GM/DIS fix)
    # blanket-skips every non-10-K-form instant fact once a concept has ANY real
    # 10-K history, on the assumption a 10-Q-sourced instant fact is always a
    # premature mid-year snapshot for a not-yet-filed fiscal year. That's true for
    # the CURRENT in-progress year (the case it was built for) but wrongly also
    # drops a PAST fiscal year-end that a filer's own 10-K genuinely never tagged
    # this exact concept for - live-confirmed via WEC's real companyfacts JSON:
    # StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest has
    # 10-K-form entries for FY2019-2025 but NONE for FY2018 (WEC's real FY2018
    # 10-K apparently didn't tag this concept at all that year), while three
    # FY2019 10-Qs each cite the real FY2018-end comparative value ($9.8427B,
    # end=2018-12-31) - the ONLY source for that fiscal year, silently dropped by
    # the blanket rule, leaving annual_balance_sheet.stockholders_equity NULL for
    # FY2018 despite total_assets/current_liabilities/etc. all being populated
    # (211 symbols / 1,144 rows share this "data_unavailable=FALSE but core field
    # NULL" shape live). Track the latest end date this concept's own confirmed
    # 10-K/20-F/40-F history actually reaches - only a fact BEYOND that boundary
    # is a genuine premature snapshot; one at or before it is a legitimate past
    # fiscal year-end the annual filing itself just never re-tagged.
    _max_annual_report_end = max(
        (e["end"] for e in entries if e.get("form") in _ANNUAL_REPORT_FORMS and not e.get("start") and e.get("end")),
        default=None,
    )
    # FIXED 2026-08-22 (goal session: real-money-readiness audit, quarterly_balance_
    # sheet residual-contamination follow-up): some filers mistag EVERY 10-Q's fp as
    # "FY" instead of "Q1"/"Q2"/"Q3" for a specific fiscal year (a filer-side XBRL
    # tagging quirk, not per-fact noise - live-confirmed via AGNC/AGNC Investment
    # Corp: every one of its FY2020 10-Qs tags fp="FY", while its FY2021 10-Qs
    # correctly tag fp="Q1"/"Q2"/"Q3"). The strict `fp not in fp_filter` quarterly
    # gate below then drops the ENTIRE fiscal year from quarterly extraction, even
    # though real, distinct, correctly-deduped quarter-end instant values exist
    # (AGNC FY2020: Q1=$85.137B, Q2=$89.853B, Q3=$79.968B, live-confirmed via real
    # companyfacts JSON) - quarterly_balance_sheet was left showing 3 straight
    # quarters frozen at the FY-end value ($81.817B) from a stale pre-fix write,
    # untouched by the 2026-08-22 watermark-bypass backfill because the current
    # (correct) extraction logic produces zero rows for that year at all, not a
    # wrong value to overwrite it with. Derive a fallback quarter from the entry's
    # own end-date month instead of trusting the filer's fp tag, but ONLY when: (a)
    # it's an instant fact (no start - the accn+max-end-date dedup above already
    # guarantees this is the filing's own genuine current-period value, never a
    # comparative echo, so fp's unreliability here doesn't risk the contamination
    # this file's other fp-trust fixes are guarding against), and (b) this filer's
    # own fiscal year genuinely ends in December (checked below from its real
    # 10-K/equivalent instant facts) - deliberately NOT extended to non-calendar
    # fiscal years, where a bare calendar-month-to-quarter mapping would be wrong.
    _fye_month: int | None = None
    for _e in entries:
        if _e.get("form") in _ANNUAL_REPORT_FORMS and not _e.get("start") and _e.get("end"):
            _fye_month = int(_e["end"][5:7])
            break
    has_december_fiscal_year_end = _fye_month == 12
    # RESTORED 2026-09-02 (goal session: "missing SEC/XBRL data" audit) - this block
    # was part of `fd1c8a99f` (OFRM comparative-fp-aliasing fix) but that commit only
    # ever landed on the unmerged `growth-factor-realignment` branch; main picked up
    # the OTHER half of that same commit (the span-gated derived_fp override a few
    # dozen lines below, "not start_date" removed + 80-100 day duration-span gate
    # added) via a later commit, but not this block - a partial-hunk loss, not a
    # deliberate removal (confirmed via `git log -S` finding only fd1c8a99f ever
    # touched this exact line, and `git merge-base --is-ancestor fd1c8a99f HEAD`
    # returning false). Live re-verified the regression directly: calling
    # get_income_statement(client, 'OFRM', period='quarterly') against real SEC data
    # right now reproduces the original bug exactly - fiscal_year=2026 net_income_loss
    # is -$15,811,000 for BOTH Q1 and Q2 (Q1's real value silently overwriting Q2's),
    # instead of Q2's real -$4,950,000 per the original commit message.
    #
    # The instant-fact check above can never fire for an income-statement/cash-flow
    # concept (NetIncomeLoss, Revenues, ...) - those are always duration facts, so
    # "not _e.get('start')" never matches, and a company with < 1 year of public
    # history (e.g. OFRM, IPO'd Feb 2026) has no 10-K at all yet for ANY concept to
    # borrow a fiscal-year-end signal from. Fall back to a self-consistency check on
    # this concept's own duration facts: a genuine (non-comparative-echo) quarterly
    # fact's own fp tag agrees with the calendar quarter its own end-date month
    # implies under a December fiscal year end (Q1->03, Q2->06, Q3->09, Q4->12) - a
    # coincidence only possible for a company whose fiscal quarters actually do end
    # in Mar/Jun/Sep/Dec in that exact Q1-Q4 order, i.e. a genuine December fiscal
    # year end. Live-confirmed via OFRM's real NetIncomeLoss facts: its own Q1-2026
    # 10-Q reports start=2026-01-01/end=2026-03-31 under fp="Q1" - self-consistent -
    # even though OFRM has filed zero 10-Ks to date.
    #
    # NARROWED vs. the original fd1c8a99f version: only accept a match whose span is
    # a genuine single quarter (80-100 days), same gate already used a few dozen
    # lines below for the override itself. Found and live-confirmed why this matters
    # via DXC (a March-fiscal-year-end filer, one quarter offset from calendar): its
    # cash-flow concepts have exactly 2 "matches" under the original unqualified
    # check, both ~183/364-day CUMULATIVE comparative facts that happen to land on a
    # calendar-quarter-end month purely by coincidence (e.g. a 6-month-cumulative
    # fact spanning 2017-04-01 to 2017-09-30, re-tagged with the filing's own fp='Q3'
    # - an aliased comparative echo, not genuine self-consistency evidence). Without
    # this gate, restoring the block would wrongly mark DXC has_december_fiscal_year_
    # end=True and corrupt its real Q1 (a genuine 90-91 day fact) into the Q2 bucket
    # via the override below - live-confirmed via
    # utils.external.sec_statements.get_cash_flow(client, 'DXC', period='quarterly')
    # matching real SEC values ($-66M/$1.585B/$2.062B for Q1/Q2/Q3 FY2019) only
    # WITHOUT this block; a plain restoration of the original unqualified check
    # reproduces the exact Q1==Q2 collision found live in quarterly_cash_flow for 250
    # symbols (768 collision rows) that motivated this investigation. A genuine
    # single-quarter self-consistency match (like OFRM's, span=89) is unaffected by
    # this narrowing.
    if not has_december_fiscal_year_end:
        _q_from_month = {"03": "Q1", "06": "Q2", "09": "Q3", "12": "Q4"}
        for _e in entries:
            _e_fp = _e.get("fp")
            _e_start = _e.get("start")
            _e_end = _e.get("end")
            if _e_fp not in ("Q1", "Q2", "Q3", "Q4") or not _e_end or len(_e_end) < 7:
                continue
            if _q_from_month.get(_e_end[5:7]) != _e_fp:
                continue
            if _e_start:
                try:
                    _e_span = (datetime.date.fromisoformat(_e_end) - datetime.date.fromisoformat(_e_start)).days
                except ValueError:
                    continue
                if not (80 <= _e_span <= 100):
                    continue
            has_december_fiscal_year_end = True
            break
    # BUG FOUND 2026-08-22 (goal session: quarterly balance-sheet comparative-period
    # contamination): a single filing (one accession number, "accn") typically tags
    # an instant concept's value TWICE - once for its own current reporting period,
    # once as a "prior period" comparative shown for context (occasionally a THIRD
    # time for an even older rollforward comparative, e.g. in a statement-of-equity
    # table). All copies inherit that SAME filing's fp/fy, which reflects the FILING's
    # own period, not each individual fact's real period (same filing-context-vs-
    # fact-identity conflation the "Use period end year..." comment below already
    # documents for "fy" specifically). Within any one filing, the fact with the
    # LATEST end date for a concept is always the filing's own current-period value;
    # every other same-accn fact for that concept is a comparative echo of a period
    # whose real value is already captured by ITS OWN filing (where it WAS the latest
    # end date). Tried a fiscal-year-end-month/day heuristic first instead of this -
    # live-confirmed too unreliable via PMT: its own 10-Ks separately tag "selected
    # quarterly financial data" footnote disclosures under fp='FY' with genuine
    # quarter-end dates, so a fact's own end date being a quarter-end date does NOT
    # reliably distinguish it from a true fiscal-year-end fact either way. Excluding
    # every non-latest-in-its-accn instant fact sidesteps the fp/fy unreliability
    # entirely - it only ever looks at each filing's own internal facts, never trusts
    # SEC's period labels. Duration facts (has "start") are unaffected - each real
    # duration fact within a filing already has its own distinct (start, end) span,
    # so they don't collide across periods the way instant facts do.
    _max_end_by_accn: dict[str, str] = {}
    for _e in entries:
        if _e.get("start"):
            continue
        _accn, _e_end = _e.get("accn"), _e.get("end")
        if _accn and _e_end and (_accn not in _max_end_by_accn or _e_end > _max_end_by_accn[_accn]):
            _max_end_by_accn[_accn] = _e_end
    # BUG FOUND 2026-08-31 (goal session: real-money-readiness audit, resolving
    # jakk_duration_fact_comparative_aliasing_found_not_fixed_20260831): the comment
    # just above ("duration facts... don't collide across periods the way instant
    # facts do") assumes a comparative echo always carries dates matching its real
    # period. Live-confirmed false via JAKK (JAKKS Pacific, CIK 1009829): its Q1
    # 2026 10-Q (accn 0001185185-26-001667) correctly tags its own Q1-2025
    # comparative (start=2025-01-01/end=2025-03-31, val=$113,253,000,
    # frame="CY2025Q1") but ALSO carries a second fact for the SAME concept with
    # FULL-YEAR dates (start=2025-01-01/end=2025-12-31) and the IDENTICAL
    # $113,253,000 value - not FY2025's real revenue ($570,671,000, confirmed via
    # JAKK's own real FY2025 10-K, accn 0001185185-26-000723, filed 2026-03-02).
    # This full-year-shaped fact even carries frame="CY2025" - the canonical-period
    # marker the PMT fix above trusts for instant facts - while the REAL 10-K fact
    # for that year carries no frame at all here, so extending that precedent to
    # duration facts would pick the WRONG value; deliberately not done. The
    # reliable signal instead: a real annual total practically never exactly equals
    # a single quarter's total for an operating company (verified zero false
    # positives against AAPL/MSFT/CHTR/ANDE's combined 685 real annual-span
    # duration facts) - only a copy-pasted/aliased comparative would. Detect this
    # per-accn: if an annual-span (>=330 day) duration fact's value exactly matches
    # a genuine short-span (<330 day) duration fact for the SAME concept from the
    # SAME accn (i.e. the filing's own real quarter figure), the long-span fact is
    # that quarter's value wearing borrowed annual dates, not a real annual total.
    # Skipped entirely below rather than let it win a "latest filed" tiebreak
    # against the genuine 10-K figure - exactly what happened for JAKK: the
    # mistagged fact's 2026-05-01 filed date beat the real 10-K's 2026-03-02 filed
    # date under the plain latest-filed rule the annual duration-fact tiebreak
    # otherwise uses.
    _short_span_val_by_accn: dict[str, set[Any]] = {}
    for _e in entries:
        _e_start = _e.get("start")
        if not _e_start or not _e.get("end"):
            continue
        try:
            _span = (datetime.date.fromisoformat(_e["end"]) - datetime.date.fromisoformat(_e_start)).days
        except ValueError:
            continue
        if _span < 330:
            _accn = _e.get("accn")
            if _accn:
                _short_span_val_by_accn.setdefault(_accn, set()).add(_e.get("val"))
    # BUG FOUND 2026-09-01 (goal session: "understand our data gaps" audit,
    # 52/53-week-fiscal-year phantom-year follow-up): the Jan-1-10-crossing
    # correction just below trusts entry['fy'] to detect and correct a 52/53-week
    # fiscal year whose end date lands in early January. That works for a fact's
    # own home filing (a 10-K correctly tags fy=<the fiscal year it's labeled>),
    # but breaks for TWO kinds of same-concept echo of that same fact appearing in
    # a later filing:
    #   (a) a DEF 14A proxy restating prior years for its compensation-discussion
    #       table - live-confirmed via FLO's and EXPO's proxies - carries
    #       fy=None/fp=None (no SEC period label at all).
    #   (b) a LATER 10-K's own prior-year comparative column for the same fact -
    #       live-confirmed via EXPO's FY2025 10-K (accn 0001193125-26-082508):
    #       its FY2024 comparative entry (start=2023-12-30, end=2025-01-03,
    #       val=$109,002,000 - identical to FY2024's own 10-K figure) carries
    #       fy=2025, NOT 2024 - SEC's "fy tags the FILING's own year, not each
    #       fact's true period" behavior (already documented above for the
    #       plain non-crossing case) applies just as much inside the Jan-crossing
    #       window. Unlike case (a), this entry's fy IS a plausible-looking int,
    #       so it doesn't even reach a "fy is missing" check - it just silently
    #       fails the `fy == period_year - 1` test (2025 != 2024) and keeps its
    #       naive, one-year-too-late period_year.
    # Case (a) leaves an fy-less entry with no correction at all - a phantom
    # bucket one year ahead of the real one, seeded with only whatever concept(s)
    # the proxy restates (usually just NetIncomeLoss, not EPS/shares) while the
    # real fiscal year's own complete row sits one bucket back - live-confirmed
    # FLO (phantom fiscal_year=2026 has only net_income_loss) and EXPO (same
    # shape). Case (b) is worse: it collides INTO the real next fiscal year's own
    # bucket (same period_year, same "FY" key, same form/filed date as the real
    # current-year fact, since both come from the same 10-K) and can silently win
    # or lose the existing tiebreak by iteration order alone - live-confirmed via
    # EXPO: with only fix (a) applied, this comparative echo (FY2024's real
    # $109,002,000) overwrote FY2025's own real value ($106,009,000) in the
    # fiscal_year=2025 bucket.
    #
    # Fix: for any entry landing in this Jan-crossing window, resolve fy from
    # whichever entry for this SAME concept+(start, end, val) - i.e. a genuine
    # duplicate/echo of the identical real-world fact - was FILED EARLIEST, not
    # from the entry's own bare fy field. A fact's earliest-filed appearance is
    # always its own home filing (10-K/20-F/etc., correctly fy-tagged for its own
    # period); every later echo (a subsequent 10-K's comparative column, a DEF
    # 14A's restated table) inherits that echoing filing's own fy/no-fy instead,
    # which this proves is not trustworthy. Applied unconditionally (not just
    # when the entry's own fy is missing) so case (b)'s misleading-but-present fy
    # is overridden too, not just case (a)'s absent one. Falls back to the
    # pre-fix behavior (no correction) when no earlier-filed corroborating entry
    # exists at all.
    _fy_by_start_end_val: dict[tuple[str, str, Any], tuple[int, str]] = {}
    for _e in entries:
        _e_fy = _e.get("fy")
        _e_filed = _e.get("filed")
        if isinstance(_e_fy, int) and _e.get("start") and _e.get("end") and _e_filed:
            _key = (_e["start"], _e["end"], _e.get("val"))
            _existing = _fy_by_start_end_val.get(_key)
            if _existing is None or _e_filed < _existing[1]:
                _fy_by_start_end_val[_key] = (_e_fy, _e_filed)
    return (
        has_annual_report_form,
        _max_annual_report_end,
        has_december_fiscal_year_end,
        _max_end_by_accn,
        _short_span_val_by_accn,
        _fy_by_start_end_val,
    )
