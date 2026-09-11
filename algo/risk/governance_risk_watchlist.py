"""Known governance/audit-access risk flags that no fundamentals-or-price factor can see.

Added 2026-09-11 (/goal session, "make the scores make sense" review). Live investigation of
the top-of-leaderboard names surfaced XYF (X Financial) and JFIN (Jiayin Group) - both
China-domiciled consumer-lending ADRs - scoring well on Quality/Value despite a real,
well-documented risk category no financial-statement ratio captures: PCAOB audit-access
restrictions under the Holding Foreign Companies Accountable Act (HFCAA) and VIE
(variable-interest-entity) corporate structures common to China-domiciled ADRs, both of
which carry real delisting/opacity risk independent of reported fundamentals.

Same shape and same honesty bar as utils/external/sec_ticker_cache.py's
KNOWN_NON_SEC_FILER_BANK_TICKERS: a small, explicitly-scoped, hand-verified list - NOT a
comprehensive sweep of every China-domiciled or VIE-structured issuer in the universe. Only
the two symbols actually live-observed in this session's leaderboard review are listed here.
Extend deliberately (verify each addition, don't bulk-import a screener list) rather than
treating this as exhaustive.

This is informational only - a flag surfaced to a viewer via the API (see
lambda/api/routes/financials.py / stock_details.py), same non-invasive precedent as the
ROE distress-artifact flag added the same session. It does NOT alter composite_score,
quality_score, or any other scored value, and does NOT exclude these symbols from trading -
whether governance risk of this kind should be a hard trading exclusion (vs. an informational
flag) is a real investment-policy decision, not one this fix makes unilaterally.
"""

KNOWN_HFCAA_RISK_ADR_TICKERS: frozenset[str] = frozenset({"XYF", "JFIN"})


def is_known_hfcaa_risk_adr(symbol: str) -> bool:
    """True if `symbol` is a confirmed China-domiciled ADR with HFCAA audit-access/VIE-
    structure risk not captured by any fundamentals-or-price factor. See this module's
    docstring for the live-verification trail and scope caveat (not exhaustive)."""
    return symbol.upper() in KNOWN_HFCAA_RISK_ADR_TICKERS
