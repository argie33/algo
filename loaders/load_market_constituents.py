#!/usr/bin/env python3
"""Market Constituents Loader - S&P 500 + Russell 2000 symbol membership (Market-wide).

Consolidates:
- load_stock_symbols.py (NASDAQ/NYSE tradable symbols)
- load_sp500_constituents.py (S&P 500 membership flag)
- load_russell2000_constituents.py (Russell 2000 membership flag)

Into a single atomic transaction to eliminate fragile cron-based ordering.

Run:
    python3 load_market_constituents.py
"""

import csv
import json
import logging
import os
import re
import socket
import sys
from datetime import date
from io import StringIO
from typing import Any, cast

import pandas as pd
import requests

from loaders.runner import run_loader
from utils.db import DatabaseContext
from utils.infrastructure.url_validator import validate_url
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

NASDAQ_URL = os.getenv("NASDAQ_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
OTHER_URL = os.getenv("OTHER_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt")
# NO FREE OFFICIAL SOURCE EXISTS for S&P 500 *index membership* - it's S&P Dow Jones
# Indices' proprietary data, not published by SEC/NASDAQ. Live-verified 2026-08-10: the
# usual "official-ish" fallback (ETF-sponsor holdings feeds, which track the index almost
# exactly) doesn't help either - iShares IVV's holdings endpoint returns an HTML
# compliance/geo-gate interstitial instead of the CSV, and SSGA's SPY holdings file 301s
# to a similar gate; both would need the same browser-spoofing this is trying to avoid,
# plus session/cookie handling on top. Wikipedia's table (community-maintained, sourced
# from S&P's own press releases) is the least-bad option - same class of accepted
# tradeoff as the NAAIM/AAII survey scrapes and yfinance analyst ratings (see
# loaders/DEPRECATED_LOADERS.md). This only sets the is_sp500 enrichment flag, not the
# base tradable universe (that's NASDAQ/OTHER above, both real official feeds).
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# GOVERNANCE 2026-08-04: symbols the upstream NASDAQ/NYSE symbol directory's "ETF" column
# misclassifies as non-ETF (root cause of migration 069's JHDV/JVAL data patch). Without
# this override, _upsert_etf_symbols()'s TRUNCATE+rebuild silently drops them from
# etf_symbols again (and stock_symbols.etf reverts to 'N') on the very next loader run,
# undoing that migration - the loader itself must correct this every run, not a one-off
# manual DB patch. Add future confirmed upstream misclassifications here.
KNOWN_ETF_MISCLASSIFICATIONS = {"JHDV", "JVAL"}

# GOVERNANCE 2026-08-18 (goal: "missing SEC data"/loader-failure audit): same class of
# problem as KNOWN_ETF_MISCLASSIFICATIONS above - the upstream NASDAQ/NYSE symbol
# directory's security_name text hasn't been cleaned up since these symbols' respective
# corporate-action settlement, so `\bwhen-issued\b` (a real, correct pattern for
# genuinely-still-when-issued shares) keeps excluding them long after the fact.
# Live-confirmed against TODAY's actual feed (not a cached copy): both still say
# "...Common Stock When-Issued" despite being large, long-established, actively-traded
# common stocks - SNDK (Sandisk Corp, spun off from Western Digital Feb 2025) and CEG
# (Constellation Energy Corp, spun off from Exelon Feb 2022) are both far past any
# realistic when-issued settlement window; SEC's own live submissions data
# (data.sec.gov/submissions) registers both under their plain names with no
# when-issued qualifier at all. Add future confirmed upstream misclassifications here.
KNOWN_WHEN_ISSUED_MISCLASSIFICATIONS = {"SNDK", "CEG"}

EXCLUSION_PATTERNS = [
    r"\bpreferred\b",
    r"\bwarrant(s)?\b",
    r"\bunit(s)?\b",
    r"\bconvertible\b",
    r"\bpreferred share(s)?\b",
    r"\btest stock\b",
    r"\bfund\b",
    r"\bblank check\b",
    r"\bspac\b",
    r"\bspecial purpose\b",
    r"\betn\b",
    r"\bexchange[- ]traded note\b",
    # NOTE: Removed bare \betf\b pattern that was excluding ALL ETFs (SPY, IWM, GLD, etc.)
    # These broad-market index ETFs are tradeable instruments.  Only exclude leveraged/inverse:
    r"\b[2-9]x\b",  # Leveraged ETFs (2x, 3x, etc.) - covered separately below
    r"\binverse\b",  # Inverse ETFs - covered separately below
    r"\bnotes?\b.*\bdue\b",  # bonds/notes with maturity date
    r"\bclosed[- ]end\b",
    r"\b2x\b",
    r"\b3x\b",
    r"\binverse\b",
    # GOVERNANCE 2026-07-28: preferred/subordinated-debt securities that don't say the
    # literal word "preferred" - live-confirmed 58 already-active symbols in the local
    # DB (dual-class-looking "$"-suffix tickers like BAC$E, ALL$B, plus plain tickers
    # like AFGC/DTB/RZC) flowing through technical indicators/scoring/signals as if they
    # were common equity, none matched by the patterns above. "Preference Shares"
    # (British/insurance-industry spelling), "Subordinated Debentures"/"Subordinated
    # Notes" (junior debt, not equity), and "Pfd Ser"/"Pfd Stock" (abbreviated
    # depositary-share preferred notation) are all real, common NASDAQ/NYSE listing-file
    # phrasings this loader had never covered. Deliberately NOT a bare `\bpfd\b` - that
    # false-positived on BNS ("Bank Nova Scotia Halifax Pfd 3 Ordinary Shares"), a real,
    # actively-traded common ADR with a garbled security_name in the raw feed.
    r"\bpreference\b",
    r"\bdebenture",
    r"\bsubordinated\b",
    r"\bpfd (ser|stock)",
    # GOVERNANCE 2026-08-03: rights offerings, when-issued shares, and depositary-share
    # preferred notation that don't match any pattern above - live-confirmed 28
    # already-active symbols in the local DB (SPAC rights like AIIA.R/JENA.R, when-issued
    # like REZI.V/ADIG.V, bare "X% Series Y" preferred like DBRG$H/NLY$F, and "Depositary
    # Shares"/"Dep Shs" preferred like EQH$A/MS$F) flowing through price_daily and every
    # downstream loader as if they were common equity - this is the root cause of
    # price_daily's chronic ~4% "missing symbol" gap (yfinance has no ticker for most of
    # these instrument types at all). Verified against Bank Nova Scotia's known-tricky
    # "...Pfd 3 Ordinary Shares" and Apple/McCormick "...Common Stock" security_names to
    # confirm none of these new patterns false-positive on real common equity.
    # GOVERNANCE 2026-08-18 (goal: "missing SEC data"/loader-failure audit): the bare
    # \brights?\b above matched real SPAC-rights instruments ("... - Rights", "... -
    # Right", "... Series B Right") correctly, but ALSO matched ordinary ADR-ratio prose
    # describing the underlying-share conversion ("American Depositary Shares... each
    # representing the RIGHT TO RECEIVE 20 Series B Shares") - live-confirmed 3 real
    # common stocks (AMX/America Movil, RLX/RLX Technology, WDH/Waterdrop) wrongly
    # excluded this way. A real rights-offering ticker's name never says "right(s) to
    # receive" - negative lookahead excludes just that phrasing, not the instrument type.
    r"\brights?\b(?!\s+to\s+receive\b)",
    r"\bwhen-issued\b",
    r"\bpfd\b.{0,20}\bser\b",
    r"\d+(\.\d+)?%\s+series\s+[a-z]\b",
    # GOVERNANCE 2026-08-18 (goal: "no SEC data"/loader-failure audit): utility first-
    # mortgage bonds and synthetic trust-certificate/repackaged-note instruments that
    # aren't caught by any pattern above (no "preferred"/"debenture"/"subordinated"/
    # "notes...due" in the name) - live-confirmed 14 already-active symbols in the local
    # DB (ELC/EMP/ENJ/ENO/EAI Entergy "First Mortgage Bonds...Series due <date>"; GJH/
    # GJO/GJP/GJR/GJS/GJT "Synthetic Fixed-Income Securities...STRATS...Certificates";
    # KTN "...CorTS...Corporate Backed Trust Securities"; JBK "Lehman ABS...Adjustable
    # Corp Backed Tr Certs"; PYT "PPlus Tr...Tr Ctf") flowing through
    # value/quality/growth_metrics as if they were common equity - none of these are
    # operating companies, so every SEC-derived factor for them was permanently
    # "missing_sec_data" (misleadingly implying a loader bug) rather than correctly
    # excluded. Checked against the full live active-universe security_name feed
    # (4,932 symbols): these 6 patterns match exactly those 14 and zero others.
    r"\bmortgage bonds?\b",
    r"\bstrats\b",
    r"\bcorts\b",
    r"\bpplus\b",
    r"\bbacked tr\.? certs?\b",
    r"\bsynthetic fixed-income securities\b",
    # GOVERNANCE 2026-08-21 (goal session - "is analyst coverage really missing, or are
    # we scoring the wrong thing" audit, same bug class as the TVA Power Bonds fix in
    # utils/loaders/helpers.py::get_active_symbols): CCZ ("Comcast Holdings ZONES" - Zero-
    # premium Exchangeable Notes, a structured debt security exchangeable into Comcast
    # stock, not common equity) was flowing through this loader as if it were real common
    # stock. Live-confirmed: near-zero price_daily volume (0-400 shares/day, not real
    # trading activity), and its "income statement" rows are literally Comcast's own
    # whole-company financials ($121-124B revenue, matching Comcast's real consolidated
    # figures - same CIK/filer as the parent) misattributed to a thinly-traded note,
    # producing a $237.9B "market_cap" for CCZ specifically. Unlike TVA's bonds, "ZONES"
    # is a distinctive enough product name to safely regex-match: checked against the full
    # live security_name feed (active and inactive), this pattern matches CCZ and zero
    # other symbols - one real false-positive risk (BNT, "...Exchangeable Limited Voting
    # Shares", real common equity) doesn't contain the word "zones" at all, so it's
    # unaffected.
    r"\bzones\b",
    # GOVERNANCE 2026-09-01 (goal: "top 10 per factor" review - Momentum's top ranks look
    # wrong investigation): PSNYW ("Polestar Automotive Holding UK Limited - Class C-1 ADS
    # (ADW)") is Polestar's publicly traded ADS WARRANT, not common equity - "(ADW)" is an
    # abbreviated "ADS Warrant" notation the bare `\bwarrant(s)?\b` pattern above doesn't
    # catch since the word "warrant" never appears spelled out. Live-confirmed via price
    # action, not name alone: PSNYW went from $0.2645 (2025-09-30) to $5.75 (2026-08-31), a
    # ~21.7x move, while the underlying PSNY common ADS only traded $12.59 that same day -
    # the classic leveraged-warrant amplification signature (a warrant moves far more than
    # its underlying for the same event), not a plausible common-equity return. This
    # inflated a single-instrument leverage artifact into Momentum's top-10, ahead of real
    # operating companies. Checked against the full live active-universe security_name feed:
    # "(ADW)" matches PSNYW and zero other symbols today, so a narrow literal pattern is
    # safe rather than a broader "ADW"/warrant-abbreviation guess that could false-positive
    # on an unrelated ticker or name fragment.
    r"\(adw\)",
    # GOVERNANCE 2026-08-31 (goal: factor-score review - "why does Risk's safest list look
    # wrong" investigation): trust-preferred securities named "<Company> Capital Trust N"
    # (e.g. Dillard's Capital Trust I / DDT) aren't common equity and don't say
    # "preferred"/"debenture"/"subordinated" anywhere in the name, so none of the existing
    # patterns catch them. Live-confirmed the specific bug this caused: DDT's
    # company_profile row had DILLARD'S, INC.'s whole-company financials (a different,
    # much larger real entity sharing the same underlying CIK/filer) misattributed to the
    # trust security's own tiny market cap, producing nonsense value_metrics (PE 0.72, PB
    # 0.23, FCF yield 153%, 97% margin of safety) that then ranked DDT in stock_scores'
    # Value top-15 - same "whole-company financials misattributed to a thinly-traded related
    # security" bug class as the CCZ/ZONES fix above, different instrument type. Checked
    # against the full live active-universe security_name feed: this pattern matches only
    # DDT and no other active symbol.
    r"\bcapital trust\b",
]

# GOVERNANCE 2026-08-03: a bare `\binvestment corp\b` pattern used to sit in
# EXCLUSION_PATTERNS above. Live-confirmed it silently excluded AGNC ("AGNC Investment
# Corp. - Common Stock", a large actively-traded mortgage REIT) and SAR ("Saratoga
# Investment Corp New", a real BDC common stock) from the entire trading universe -
# neither is a SPAC. The pattern exists to catch serial-SPAC-sponsor shell companies
# (Hennessy Capital Investment Corp. VIII, NewHold Investment Corp III/IV, Origin
# Investment Corp I, Vine Hill Capital Investment Corp. II, Bain Capital GSS Investment
# Corp.) whose base equity lines ("... Class A Ordinary Shares") aren't caught by any
# other pattern (their units/warrants/rights lines already are, via the patterns above).
# Real US operating companies list "Common Stock"; these SPACs (offshore blank-check
# vehicles) list "Ordinary Shares" instead - only exclude "investment corp" names that
# also carry that SPAC share-class language, not the bare phrase on its own. Verified
# against the full live nasdaqlisted.txt/otherlisted.txt feeds: this change flips exactly
# AGNC and SAR to included and leaves every SPAC-family row (units/warrants/rights/base
# shares) excluded, same as before.
#
# GOVERNANCE 2026-08-04: `\binvestment corp\b` alone missed the more common SPAC-sponsor
# naming convention, "... Acquisition Corp[oration]" (Abony Acquisition Corp. I, Alpex
# Acquisition Corporation, Iron Dome Acquisition I Corp., etc.) - live-confirmed 75
# already-active symbols in the local DB whose base "Class A Ordinary Share(s)" equity
# line was never excluded by any pattern (their units/rights lines already were), showing
# up as chronic "missing" gaps against price_daily since yfinance has no ticker for them.
# Same false-positive guard as above applies here: only excludes when the SPAC
# "Ordinary Shares"/"Rights" share-class language is also present, so a real operating
# company that happens to have "Acquisition Corp" in its legal name but lists "Common
# Stock" is untouched.
#
# GOVERNANCE 2026-08-04 (same day, follow-up): the pattern above required "acquisition"/
# "investment" immediately adjacent to "corp", but the most common real-world SPAC-sponsor
# convention numbers the entity BETWEEN those two words ("Acquisition I Corp", "Acquisition
# II Corp.", "M3-Brigade Acquisition V Corp.", "StoneBridge Acquisition II Corporation") -
# including the exact "Iron Dome Acquisition I Corp." example cited above, which the
# adjacency-only regex never actually matched. Live-confirmed 2026-08-04: 16 already-active
# symbols in the local DB (APAC, DBCA, DMII, IDAC, LCCC, MBVI, NCO, PACH, MBAV, AESP, TVA,
# TVIV, VLOS, ARCL, MCAH, BCAR among them) still slipping through - all real, currently
# yfinance-quotable pre-merger SPAC units trading near their ~$10 trust value, not
# no-data symbols, so they were silently inflating the tradable universe with shells that
# provide no real operating signal rather than showing up as a data gap. Allow an optional
# short numbering token (roman numeral, plain digit, or ordinal like "1st") between the
# sponsor word and "corp" - bounded to avoid matching arbitrary intervening company-name
# words. No "Corp <numeral>" (numeral-after-corp) ordering found in current live data;
# add that ordering here too if a future audit finds one.
#
# GOVERNANCE 2026-09-01 (goal: "top 10 per factor" review - Risk's safest list still wrong):
# live-reverified against the CURRENT active universe and found this pattern, unchanged since
# 2026-08-04, has been outrun by newer SPAC-sponsor naming conventions - 21 pre-merger shells
# fingerprint-confirmed (same two-signal standard as KNOWN_SPAC_MISCLASSIFICATIONS below: beta
# -0.04 to 0.03, volatility_60d 1.3%-5.8%, max_drawdown_1y under 13.5%, AND zero computable
# growth history) sitting in stock_scores' Risk top-10, above Royal Bank of Canada and other
# real names - the same pollution class as the 2026-08-31 fix, just newer sponsor cohorts. 9 of
# the 21 (Artius II Acquisition Inc., American Drive Acquisition Company, Chenghe Acquisition
# III Co., Republic Digital Acquisition Company, TRG Latin America Acquisitions Corp., Black
# Spade Acquisition III Co, APEX Tech Acquisition Inc., Jackson Acquisition Company II, Shreya
# Acquisition Group, Twelve Seas Investment Company III) were missed by two narrow gaps in the
# regex, not a naming style outside its scope entirely: (1) "acquisition" required an exact
# singular match, so the "Acquisitions" (plural) naming variant slipped through with no \b match
# at all, and (2) the sponsor-keyword's only accepted suffixes were corp/corporation/limited/ltd
# - "Acquisition Company"/"Acquisition Group"/"Acquisition Inc"/"Acquisition Co." (all real,
# common SPAC-sponsor suffix conventions, not exotic ones) matched neither. Added optional
# plural "s?" and inc(orporated)?/co\.?/company/group as accepted suffixes - verified against
# the FULL active universe first (not just the 21 already found): matches exactly those 9 new
# symbols and zero previously-included real operating companies (the false-positive risk this
# pattern already guards against via requiring BOTH an explicit sponsor keyword AND the SPAC
# share-class signal - see should_exclude below - the same reason a bare "Corp + Ordinary
# Shares" pattern was rejected in the 2026-08-31 GOVERNANCE note above; broadening the accepted
# suffix list under an unchanged, already-narrow sponsor-keyword requirement does not reopen
# that risk). The remaining 12 (Karbon Capital Partners Corp., KRAKacquisition Corp, Dynamix
# Corporation III, Gores Holdings X Inc., Cantor Equity Partners IV Inc., Social Commerce
# Partners Corporation, Stellar V Capital Corp., Talon Capital Corp., KPET Ultra Paceline
# Corporation, SilverBox Corp V, Insight Digital Partners II, Aldel Financial II Inc.) carry no
# investment/acquisition/merger keyword at all (pure sponsor-brand names, plus one - KRAKacquisition
# - that concatenates "acquisition" with no word boundary) - added individually to
# KNOWN_SPAC_MISCLASSIFICATIONS below, same convention as the existing 7.
CORP_SPONSOR_PATTERN = re.compile(
    r"\b(investment|acquisitions?|merger)\s+(?:[ivxlcdm]+|\d+(?:st|nd|rd|th)?)?\s*"
    r"(corp(oration)?|limited|ltd|inc(orporated)?|co\.?|company|group)\b",
    re.IGNORECASE,
)
SPAC_SHARE_CLASS_PATTERN = re.compile(r"\bordinary share(s)?\b|\brights?\b", re.IGNORECASE)

# GOVERNANCE 2026-08-31 (same goal session as the Capital Trust pattern above): CORP_SPONSOR_PATTERN
# requires an explicit "investment"/"acquisition"/"merger" sponsor keyword immediately before
# "corp"/"limited" - live-confirmed 6 already-active pre-merger SPAC shells in the local DB whose
# sponsor-brand name carries none of those three words (GigCapital8 Corp., Aperture AC, New
# America Acquisition I Corp. [share class says "Common Stock" not "Ordinary Shares", failing
# SPAC_SHARE_CLASS_PATTERN], XFLH Capital Corporation, SilverBox Corp IV, Dynamix Corporation) -
# every one confirmed a genuine trust-shell via BOTH signals independently: stability_metrics
# shows the SPAC trust-mechanic fingerprint (beta -0.046 to 0.037, essentially flat; volatility_60d
# 1.6%-10%; max_drawdown_1y under 6.5%) AND growth_metrics has zero computable operating history
# ("insufficient_history"/no revenue or EPS growth at all). This inflated Risk's "safest" ranking
# above Royal Bank of Canada and Manulife (12/50 of stock_scores' top-50 risk_score names were
# SPAC-shaped, live-verified 2026-08-31). Deliberately a symbol-level override, NOT a broader
# regex ("Corp/Corporation" + "Ordinary Shares" alone) - that combination was tested against the
# full active universe first and matches 47 symbols, most of them real large operating companies
# (First Majestic Silver Corp/AG, Telus Corp/TU, Pembina Pipeline Corp/PBA, Eldorado Gold Corp/EGO,
# Denison Mines Corp/DNN, Webull Corp/BULL, ProKidney Corp/PROK among them) - the same
# false-positive shape CORP_SPONSOR_PATTERN's own two-signal design already exists to avoid (see
# the GOVERNANCE 2026-08-03 AGNC/SAR note above). Same convention as
# KNOWN_WHEN_ISSUED_MISCLASSIFICATIONS/KNOWN_ETF_MISCLASSIFICATIONS: individually-verified
# tickers, not a pattern change, when the general rule can't be safely widened further.
# CUB (Lionheart Holdings - Class A Ordinary Shares) added same pass, same evidence shape
# (beta 0.016, volatility_60d 2.7%, max_drawdown_1y -1.28%, zero computable growth history) -
# "Holdings" carries no sponsor keyword either.
#
# GOVERNANCE 2026-09-01 (same regex-broadening pass documented on CORP_SPONSOR_PATTERN above):
# 12 more, same evidentiary bar (fingerprint-verified via stability_metrics beta/volatility_60d/
# max_drawdown_1y AND growth_metrics zero computable history before adding, not a text-pattern
# guess) - KBON (Karbon Capital Partners Corp., beta 0.027, vol60d 2.6%, dd -1.1%), KRAQ
# (KRAKacquisition Corp - "acquisition" concatenated onto the brand name with no word boundary,
# beta 0.009, vol60d 1.9%, dd -0.7%), DNMX (Dynamix Corporation III - a numbered sequel to the
# already-known DYNC/"Dynamix Corporation" sponsor, beta 0.010, vol60d 1.3%, dd -0.9%), GTEN
# (Gores Holdings X, Inc., beta 0.023, vol60d 5.8%, dd -2.2%), CEPF (Cantor Equity Partners IV,
# Inc., beta 0.029, vol60d 3.7%, dd -4.5%), SCPQ (Social Commerce Partners Corporation, beta
# 0.016, vol60d 1.7%, dd -0.5%), SVCC (Stellar V Capital Corp., beta 0.0001, vol60d 2.1%, dd
# -1.0%), TLNC (Talon Capital Corp., beta -0.016, vol60d 3.6%, dd -1.6%), KPET (KPET Ultra
# Paceline Corporation, beta 0.011, vol60d 3.9%, dd -1.7%), SBXE (SilverBox Corp V - a numbered
# sequel to the already-known XFLH/"SilverBox Corp IV" sponsor, beta -0.042, vol60d 3.2%, dd
# -1.9%), DYOR (Insight Digital Partners II, beta -0.006, vol60d 2.4%, dd -0.6%), ALDF (Aldel
# Financial II Inc., beta 0.007, vol60d 2.5%, dd -1.4%) - all found sitting in stock_scores'
# Risk top-10/50 the same way the original 7 were.
#
# GOVERNANCE 2026-09-01 (same pass, follow-up sweep after the regex/list changes above): re-ran
# the fingerprint scan (beta -0.15..0.20, volatility_60d <=13%, max_drawdown_1y >= -8%, zero
# computable growth history) across the ENTIRE active universe by data shape rather than by name
# pattern, to catch anything CORP_SPONSOR_PATTERN can never reach - specifically SPACs that list
# "Common Stock" instead of "Ordinary Shares" (failing SPAC_SHARE_CLASS_PATTERN entirely, the
# same evasion already noted for "New America Acquisition I Corp." above). 7 fingerprint matches
# total; 4 confirmed genuine shells by name (IRHO "Iron Horse Acquisitions II Corp. - Common
# Stock", beta 0.002, vol60d 1.4%, dd -0.6%; SDHI "Siddhi Acquisition Corp - Class A Common
# stock", beta -0.007, vol60d 2.0%, dd -0.6%; GRAF/TONT both literally "Graf Global Corp. Class A
# ordinary shares" - two different symbols sharing one security_name string verbatim in
# stock_symbols, a data-quality oddity worth a future loader-side look but not chased further
# here since both independently fingerprint- and name-confirm as the same shell either way, beta
# 0.007-0.021, vol60d 12.7%, dd -4.6%). The other 3 fingerprint matches (HYNE "Hoyne Bancorp,
# Inc.", NUTR "Nusatrip Incorporated", WSBK "Winchester Bancorp, Inc.") are real, if obscure and
# thinly-traded, operating companies - NOT added; genuinely thin trading history producing a
# SPAC-shaped fingerprint is not the same bug as an actual trust shell, and misclassifying a real
# company here would be the exact wrong-direction error this whole exclusion mechanism exists to
# avoid (see the AGNC/SAR false-positive note above).
KNOWN_SPAC_MISCLASSIFICATIONS = {
    "GIW",
    "APUR",
    "NWAX",
    "XFLH",
    "SBXD",
    "DYNC",
    "CUB",
    "KBON",
    "KRAQ",
    "DNMX",
    "GTEN",
    "CEPF",
    "SCPQ",
    "SVCC",
    "TLNC",
    "KPET",
    "SBXE",
    "DYOR",
    "ALDF",
    "IRHO",
    "SDHI",
    "GRAF",
    "TONT",
}

# GOVERNANCE 2026-08-18 (goal: "missing SEC data"/loader-failure audit): a bare
# \bdepositary shares?\b/\bdep shs?\b pattern used to sit in EXCLUSION_PATTERNS above,
# added 2026-08-03 to catch preferred-stock "X% Series Y Depositary Shares" notation
# (e.g. ATH$D, BAC$E, EQH$A, FITB$I, MET$E, MS$F, RNR$F). It was never scoped to exclude
# "American Depositary Shares"/"American Depositary Receipts" - the standard listing
# terminology for ANY foreign company's US-exchange common stock (ADRs) - so it also
# silently excluded 272 real, liquid, large-cap common stocks (BABA, JD, ERIC, GRFS, IQ,
# FUTU, HIMX, BHP, SHEL, VOD, GSK, UL, ARM, NTES, PDD, SONY, and more), starving them
# from the entire metrics/loader pipeline (data_unavailable_reason='excluded_by_naming_
# pattern', active=false). Checked every confirmed real preferred depositary-share name
# in the local DB (ATH$*, BAC$E, EQH$A, FITB$I, MET$E, MS$F, RNR$F): none say "American"
# immediately before "Depositary Shares" - that word marks the ADR mechanism
# specifically (a foreign company's shares held by a US depositary bank), distinct from
# a US company issuing depositary shares representing its own preferred/preference
# stock. Two-signal check (same shape as CORP_SPONSOR_PATTERN/SPAC_SHARE_CLASS_PATTERN
# above): exclude on "depositary shares" only when NOT immediately preceded by
# "American".
DEPOSITARY_SHARES_PATTERN = re.compile(r"\bdepositary shares?\b|\bdep shs?\b", re.IGNORECASE)
# Covers "Global Depositary Shares/Receipts" (GDR/GDS) too - the same foreign-listing
# mechanism under a different regional name, live-confirmed on IRS (IRSA Inversiones Y
# Representaciones, a real $11.4B Argentine real-estate company). Same reasoning as
# "American" above: no real preferred depositary-share name in the local DB says
# "Global" either.
AMERICAN_DEPOSITARY_PATTERN = re.compile(r"\b(american|global)\s+depositary\s+(shares?|receipts?)\b", re.IGNORECASE)


def should_exclude(name: str) -> bool:
    if any(re.search(p, name, flags=re.IGNORECASE) for p in EXCLUSION_PATTERNS):
        return True
    if CORP_SPONSOR_PATTERN.search(name) and SPAC_SHARE_CLASS_PATTERN.search(name):
        return True
    if DEPOSITARY_SHARES_PATTERN.search(name) and not AMERICAN_DEPOSITARY_PATTERN.search(name):
        return True
    return False


def _is_excluded(symbol: str, name: str) -> bool:
    """should_exclude() plus the KNOWN_WHEN_ISSUED_MISCLASSIFICATIONS override - the
    single source of truth for exclusion decisions used by fetch_global's initial
    write path AND both deactivate/reactivate reconciliation methods, so a symbol-level
    override applies consistently everywhere `should_exclude` would otherwise be called
    directly on stored/fetched text alone."""
    if symbol in KNOWN_SPAC_MISCLASSIFICATIONS:
        return True
    return should_exclude(name) and symbol not in KNOWN_WHEN_ISSUED_MISCLASSIFICATIONS


class MarketConstituentsLoader(OptimalLoader):
    """Load all tradable symbols and mark S&P 500 / Russell 2000 membership."""

    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "created_at"
    # BUG FOUND 2026-08-17: loader_registry.py already listed etf_symbols as this loader's
    # second output table (used to pre-mark it RUNNING before the subprocess starts), but
    # this class never declared it here - the only place runner.py's mark_completed()/
    # mark_failed() secondary-table sweep looks. Every run correctly TRUNCATE+rebuilt
    # etf_symbols (see _upsert_etf_symbols) yet left its data_loader_status row stuck RUNNING
    # forever, later reaped as FAILED - live-reproduced 2026-08-17 19:37 UTC: loader logged
    # "SUCCESS" in 2.6s, but etf_symbols was reaped FAILED 15 min later anyway (3rd
    # consecutive occurrence, not intermittent - every single run hit this).
    output_tables = ["etf_symbols"]

    def _deactivate_stale_excluded_symbols(self) -> None:
        """Re-apply should_exclude() to already-`active=true` rows and flip any new matches.

        GOVERNANCE 2026-08-04: excluded symbols are simply omitted from the `rows` list
        fetch_global() returns, so the bulk-insert write path below never touches them -
        a symbol that was `active=true` under an OLDER, looser EXCLUSION_PATTERNS/
        CORP_SPONSOR_PATTERN stays `active=true` forever, even after a pattern tightens to
        newly cover it. Live-confirmed: the 2026-08-03 `\\brights?\\b` pattern addition left
        59 already-active SPAC-rights symbols (AACPR, AESPR, ...) untouched, silently
        inflating price_daily's "active universe" denominator and pinning its completion %
        below the 98% mark_completed() safety threshold every single day since - the
        dashboard's Data Freshness table showed price_daily as chronically FAILED for a
        reason with nothing to do with the price loader itself. This reconciles existing
        rows against the CURRENT patterns on every run, using each row's own stored
        security_name (no need to re-fetch anything).
        """
        with DatabaseContext("read") as cur:
            cur.execute("SELECT symbol, security_name FROM stock_symbols WHERE active = true")
            active_rows = cur.fetchall()

        stale = [symbol for symbol, name in active_rows if name and _is_excluded(symbol, name)]
        if not stale:
            return

        logger.warning(
            f"[MARKET_CONSTITUENTS] Deactivating {len(stale)} already-active symbol(s) that now "
            f"match should_exclude() under current patterns: {stale[:10]}"
            + (f" ...and {len(stale) - 10} more" if len(stale) > 10 else "")
        )
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                UPDATE stock_symbols
                SET active = false, data_unavailable = true,
                    data_unavailable_reason = 'excluded_by_naming_pattern'
                WHERE symbol = ANY(%s)
                """,
                (stale,),
            )

        # BUG FOUND 2026-09-01 (/goal session, same class as the sibling
        # _deactivate_symbols_delisted_from_exchange_feed fix below): only ever a WARNING
        # log line, no notify() anywhere. A tightened/broadened EXCLUSION_PATTERNS/
        # CORP_SPONSOR_PATTERN regex (this session alone broadened CORP_SPONSOR_PATTERN to
        # add "merger"/"limited"/"ltd" - see spac_trust_preferred_universe_leaks_fixed_20260831
        # in memory) can reach into the already-active universe and flip real symbols
        # inactive on the very next run this reconciliation executes - the false-positive
        # risk this docstring's own test suite spends most of its lines guarding against
        # (AGNC/Saratoga/First Majestic Silver near-misses). An operator watching only
        # alerts deserves the same visibility here as the feed-absence sibling gets.
        try:
            from algo.reporting import notify

            notify(
                severity="warning",
                title="Symbols Deactivated by Exclusion Pattern",
                message=(
                    f"{len(stale)} already-active symbol(s) deactivated (active=false) after "
                    f"newly matching should_exclude() under current naming patterns: "
                    f"{', '.join(stale[:10])}"
                    + (f" ...and {len(stale) - 10} more" if len(stale) > 10 else "")
                    + ". Verify each is a genuine non-equity instrument (SPAC/preferred/trust/"
                    "etc.) - a recently-broadened exclusion pattern could catch a real "
                    "operating company."
                ),
                details={"symbols": stale},
            )
        except (ValueError, TypeError, RuntimeError) as notify_err:
            logger.error(f"[MARKET_CONSTITUENTS] Failed to send excluded-by-pattern alert: {notify_err}")

    def _reactivate_no_longer_excluded_symbols(self) -> None:
        """Reverse of `_deactivate_stale_excluded_symbols` - re-apply should_exclude() to
        already-`active=false, data_unavailable_reason='excluded_by_naming_pattern'` rows
        and flip any that a LOOSENED pattern no longer matches.

        GOVERNANCE 2026-08-18 (goal: "missing SEC data"/loader-failure audit): the
        deactivation direction above was already handled, but nothing handled the
        opposite direction - once a symbol is excluded, its row is permanently omitted
        from fetch_global()'s `rows` list (same mechanism the docstring above describes),
        so the bulk-insert write path never touches it again even after a pattern is
        corrected to no longer match it. Live-confirmed: the `\\bdepositary shares?\\b`
        over-broad-pattern fix (see DEPOSITARY_SHARES_PATTERN/AMERICAN_DEPOSITARY_PATTERN
        above) alone would NOT reactivate the 272 real ADR common stocks (BABA, JD, ERIC,
        GRFS, IQ, FUTU, HIMX, BHP, SHEL, VOD, GSK, UL, ARM, NTES, PDD, ...) it wrongly
        excluded - `active` is never a key in any row dict this loader produces, so
        BulkInsertManager's dynamically-built ON CONFLICT SET clause never includes it,
        meaning a normal re-run's UPDATE path silently can't touch the column at all.
        Scoped to `data_unavailable_reason = 'excluded_by_naming_pattern'` specifically
        (not blanket `active = false`) so this never touches symbols inactive for an
        unrelated, still-valid reason (e.g. genuinely delisted).
        """
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT symbol, security_name FROM stock_symbols
                WHERE active = false AND data_unavailable_reason = 'excluded_by_naming_pattern'
                """
            )
            excluded_rows = cur.fetchall()

        recovered = [symbol for symbol, name in excluded_rows if name and not _is_excluded(symbol, name)]
        if not recovered:
            return

        logger.warning(
            f"[MARKET_CONSTITUENTS] Reactivating {len(recovered)} symbol(s) that no longer "
            f"match should_exclude() under current patterns: {recovered[:10]}"
            + (f" ...and {len(recovered) - 10} more" if len(recovered) > 10 else "")
        )
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                UPDATE stock_symbols
                SET active = true, data_unavailable = false, data_unavailable_reason = NULL
                WHERE symbol = ANY(%s)
                """,
                (recovered,),
            )

    def _deactivate_symbols_delisted_from_exchange_feed(self, current_feed_symbols: set[str]) -> None:
        """Deactivate already-active symbols that have vanished entirely from today's
        NASDAQ/otherlisted feed - i.e. no longer trade under this symbol on any listed exchange.

        GOVERNANCE 2026-08-21 (goal session - "why does price_daily keep retry-failing on
        the same handful of symbols every day"): `active` is never a key in the row dicts
        fetch_global() returns, so BulkInsertManager's UPSERT only ever adds/updates symbols
        present in THIS run's fetch - a symbol that drops out of nasdaqlisted.txt/
        otherlisted.txt entirely (real delisting/acquisition) stays `active=true` forever.
        That's exactly the gap _reactivate_no_longer_excluded_symbols()'s docstring assumed
        was already handled elsewhere ("an unrelated, still-valid reason (e.g. genuinely
        delisted)") - nothing actually covered it. Live-confirmed: NSA/ELSE/LPRO/PSTV/SKYT/
        VSTD are absent from both live feeds today, and Alpaca has zero bars for each past
        its own last real trading day (NSA: stopped 2026-07-21 despite >100k-share days
        before that) - not a data source problem, they're genuinely gone. Left
        `active=true`, price_daily retried and logged them FAILED every single day with
        nothing an operator could act on.

        BUG FOUND 2026-08-21 (same session, live-caught before this reached any real
        pipeline run): "absent from this fetch of the feed" ALONE is not trustworthy
        signal - the very first live run of this method deactivated 110 symbols, and 94 of
        them (AVB, EQR, WBS, BBBY, ...) had price_daily rows within the last 2 weeks,
        obviously still trading. The feed fetch this environment reaches is not guaranteed
        to be a complete, ground-truth snapshot of the real listing universe every time
        (rate limiting, partial mirrors, whatever - the exact cause doesn't matter). Per
        the "verify via a second, orthogonal signal before acting" pattern used everywhere
        else in this codebase for exactly this class of risk (see MEMORY.md - CNY
        conversion, sec_valuations sanity checks), a symbol is only deactivated here if it
        is BOTH absent from the feed AND has had no real price_daily data for
        STALE_PRICE_DAYS - a feed hiccup alone can never flip an actively-traded symbol to
        inactive; only a feed hiccup THAT ALSO coincides with a genuine multi-week pricing
        gap can.

        Guarded like _deactivate_stale_excluded_symbols() (scoped UPDATE, not blanket),
        plus a floor on the fetched feed size and a per-run cap on rows flipped - a
        truncated or malformed feed fetch must never be able to mass-deactivate the universe.
        """
        min_trusted_feed_size = 5000
        if len(current_feed_symbols) < min_trusted_feed_size:
            logger.error(
                f"[MARKET_CONSTITUENTS] Fetched feed only has {len(current_feed_symbols)} symbols "
                f"(expected >= {min_trusted_feed_size}) - too small to trust for delisting "
                "detection, likely a truncated/failed fetch. Skipping delisted-symbol "
                "deactivation this run."
            )
            return

        with DatabaseContext("read") as cur:
            cur.execute("SELECT symbol FROM stock_symbols WHERE active = true")
            active_symbols = {row[0] for row in cur.fetchall()}

        missing_from_feed = sorted(active_symbols - current_feed_symbols)
        if not missing_from_feed:
            return

        stale_price_days = 14
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT symbol FROM (
                    SELECT symbol, MAX(date) AS last_price_date
                    FROM price_daily WHERE symbol = ANY(%s) GROUP BY symbol
                ) latest
                WHERE last_price_date >= CURRENT_DATE - INTERVAL '%s days'
                """,
                (missing_from_feed, stale_price_days),
            )
            recently_priced = {row[0] for row in cur.fetchall()}

        gone = [s for s in missing_from_feed if s not in recently_priced]
        still_priced = [s for s in missing_from_feed if s in recently_priced]
        if still_priced:
            logger.warning(
                f"[MARKET_CONSTITUENTS] {len(still_priced)} symbol(s) absent from today's feed "
                f"still have price_daily data within {stale_price_days}d - treating as a feed "
                f"gap, not a real delisting, and leaving active: {still_priced[:10]}"
                + (f" ...and {len(still_priced) - 10} more" if len(still_priced) > 10 else "")
            )
        if not gone:
            return

        max_auto_deactivate = 50
        if len(gone) > max_auto_deactivate:
            logger.critical(
                f"[MARKET_CONSTITUENTS] {len(gone)} symbols are both missing from today's feed "
                f"AND have no recent price_daily data - exceeds the {max_auto_deactivate} safety "
                "cap, which more likely means an upstream data problem than a real mass-"
                f"delisting event. Skipping automatic deactivation this run. Sample: {gone[:10]}"
            )
            return

        logger.warning(
            f"[MARKET_CONSTITUENTS] Deactivating {len(gone)} symbol(s) absent from today's "
            f"NASDAQ/otherlisted feed with no price_daily data in {stale_price_days}d "
            f"(delisted/acquired): {gone[:10]}" + (f" ...and {len(gone) - 10} more" if len(gone) > 10 else "")
        )
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                UPDATE stock_symbols
                SET active = false, data_unavailable = true,
                    data_unavailable_reason = 'delisted_or_removed_from_exchange_feed'
                WHERE symbol = ANY(%s)
                """,
                (gone,),
            )

        # BUG FOUND 2026-09-01 (/goal session, "check the logs" pass, same class as
        # loaders/load_prices.py's _mark_symbol_permanently_unavailable fix): this
        # deactivation was only ever a WARNING/CRITICAL log line, no notify() anywhere in
        # this function. Live-caught firing a genuine false positive for EQR (Equity
        # Residential, a real S&P 500 REIT still recognized as an active NYSE equity by
        # yfinance's own company-info API) - the "second orthogonal signal" guard this
        # function's own docstring describes (absent from feed AND stale price) isn't
        # actually fully independent when the SAME upstream yfinance gap that stales the
        # price can coincide with an unrelated transient NASDAQ feed-fetch gap, tripping
        # both conditions together for a symbol that's still genuinely listed and trading.
        # Full deactivation (not just data_unavailable while still active, unlike the
        # load_prices.py sibling case) drops the symbol from ALL downstream processing -
        # an operator watching only alerts would never learn this happened, and nothing
        # anywhere automatically reactivates a symbol marked this way.
        try:
            from algo.reporting import notify

            notify(
                severity="warning",
                title="Symbols Deactivated as Delisted/Removed From Exchange Feed",
                message=(
                    f"{len(gone)} symbol(s) deactivated (active=false) after being absent from "
                    f"today's NASDAQ/otherlisted feed AND having no price_daily data in "
                    f"{stale_price_days}d: {', '.join(gone[:10])}"
                    + (f" ...and {len(gone) - 10} more" if len(gone) > 10 else "")
                    + ". Verify each is genuinely delisted before trusting this - the two "
                    "signals aren't fully independent when a shared upstream data-provider gap "
                    "can affect both at once."
                ),
                details={"symbols": gone, "stale_price_days": stale_price_days},
            )
        except (ValueError, TypeError, RuntimeError) as notify_err:
            logger.error(f"[MARKET_CONSTITUENTS] Failed to send delisted-deactivation alert: {notify_err}")

    def fetch_global(self, since: date | None) -> list[dict[str, Any]]:
        """Fetch all symbols and mark index membership.

        ATOMIC OPERATION:
        1. Fetch NASDAQ/NYSE symbols (primary dataset)
        2. Fetch S&P 500 constituents (enrichment)
        3. Fetch Russell 2000 constituents (enrichment)
        4. Return combined dataset with flags

        This eliminates the fragile cron-based ordering where sp500 and russell
        loaders depend on stock_symbols running first.
        """
        socket.setdefaulttimeout(15.0)

        try:
            self._deactivate_stale_excluded_symbols()
            self._reactivate_no_longer_excluded_symbols()

            # STEP 1: Fetch NASDAQ/NYSE symbols
            logger.info("STEP 1/3: Fetching NASDAQ/NYSE tradable symbols")
            base_symbols = self._fetch_nasdaq_symbols()

            if not base_symbols:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] No tradable symbols fetched from NASDAQ/NYSE. "
                    "Cannot load market constituents without base symbol list."
                )

            logger.info(f"Fetched {len(base_symbols)} base symbols from NASDAQ/NYSE")

            self._deactivate_symbols_delisted_from_exchange_feed(
                {row["symbol"] for row in base_symbols if row.get("symbol")}
            )

            # STEP 2: Fetch and index S&P 500 constituents (critical enrichment for signal generation)
            logger.info("STEP 2/3: Fetching S&P 500 constituents")
            sp500_set = set()
            sp500_fetch_failed = False
            try:
                sp500_symbols = self._fetch_sp500_symbols()
                if sp500_symbols:
                    sp500_set = set(sp500_symbols)
                    logger.info(f"Fetched {len(sp500_set)} S&P 500 constituents")
                else:
                    logger.critical(
                        "[MARKET_CONSTITUENTS] S&P 500 fetch returned 0 symbols. "
                        "This indicates a data source issue (Wikipedia unavailable or format changed). "
                        "Marking S&P 500 enrichment as failed to alert operator."
                    )
                    sp500_fetch_failed = True
            except Exception as e:
                logger.critical(
                    f"[MARKET_CONSTITUENTS] Failed to fetch S&P 500: {type(e).__name__}: {e}. "
                    f"Cannot enrich market constituents with S&P 500 membership. "
                    f"Data source issue or network timeout - check Wikipedia/data source availability."
                )
                sp500_fetch_failed = True

            # STEP 3: Fetch and index Russell 2000 constituents (optional enrichment)
            logger.info("STEP 3/3: Fetching Russell 2000 constituents")
            russell_set = set()
            try:
                russell_symbols = self._fetch_russell2000_symbols()
                if russell_symbols:
                    russell_set = set(russell_symbols)
                    logger.info(f"Fetched {len(russell_set)} Russell 2000 constituents")
                else:
                    logger.warning(
                        "[MARKET_CONSTITUENTS] Russell 2000 fetch returned 0 symbols. "
                        "This is optional enrichment data - continuing without it."
                    )
            except Exception as e:
                logger.warning(
                    f"[MARKET_CONSTITUENTS] Failed to fetch Russell 2000 ({type(e).__name__}: {e}). "
                    f"This is optional enrichment - continuing without it."
                )

            # CRITICAL: Fail if S&P 500 fetch failed - this is essential enrichment
            if sp500_fetch_failed:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] S&P 500 constituent fetch failed and returned 0 symbols. "
                    "Cannot proceed with incomplete enrichment. This indicates a data source issue. "
                    "OPERATOR ACTION: Check if Wikipedia is accessible and not blocked. "
                    "The loader requires S&P 500 data to properly enrich market constituents."
                )

            # Enrich base symbols with index membership flags
            enriched_count = 0
            for i, row in enumerate(base_symbols):
                if "symbol" not in row or not row.get("symbol"):
                    raise ValueError(
                        f"CRITICAL: Market constituent row {i} missing required 'symbol' field. "
                        f"Cannot determine index membership without symbol. Row: {row}"
                    )
                sym = row["symbol"]
                row["is_sp500"] = sym in sp500_set
                row["is_russell2000"] = sym in russell_set
                enriched_count += 1

            # Validate enrichment completed for all rows
            if enriched_count < len(base_symbols):
                raise RuntimeError(
                    f"CRITICAL: Enrichment incomplete. "
                    f"Processed {enriched_count}/{len(base_symbols)} symbols. "
                    "Cannot proceed with partial index membership data."
                )

            # Verify all rows were enriched with flags
            missing_flags = [i for i, r in enumerate(base_symbols) if "is_sp500" not in r or "is_russell2000" not in r]
            if missing_flags:
                raise RuntimeError(
                    f"CRITICAL: Enrichment validation failed. "
                    f"Rows {missing_flags} missing index membership flags. "
                    "Cannot proceed with incomplete enrichment."
                )

            sp500_count = sum(1 for r in base_symbols if r.get("is_sp500"))
            russell_count = sum(1 for r in base_symbols if r.get("is_russell2000"))

            logger.info(
                f"Enriched {len(base_symbols)} symbols with index membership. "
                f"S&P 500: {sp500_count} "
                f"Russell 2000: {russell_count}"
            )

            # Add data availability markers (successful load)
            for row in base_symbols:
                row["data_unavailable"] = False
                row["data_unavailable_reason"] = None

            return base_symbols

        except (requests.RequestException, requests.Timeout, json.JSONDecodeError) as e:
            raise RuntimeError(f"[MARKET_CONSTITUENTS] Failed to fetch constituent data: {e}") from e

    def _fetch_nasdaq_symbols(self) -> list[dict[str, Any]]:  # noqa: C901
        # Validate URLs
        for url, url_name in [
            (NASDAQ_URL, "NASDAQ_SYMBOLS_URL"),
            (OTHER_URL, "OTHER_SYMBOLS_URL"),
        ]:
            is_valid, error_msg = validate_url(url, allowed_domains=["nasdaqtrader.com"])
            if not is_valid:
                raise RuntimeError(
                    f"[MARKET_CONSTITUENTS] SSRF validation failed for {url_name}: {error_msg}. "
                    "Cannot fetch tradable symbols without valid data source."
                )

        try:
            logger.debug("Downloading NASDAQ list")
            try:
                nas_text = requests.get(NASDAQ_URL, timeout=15).text
            except requests.exceptions.Timeout as e:
                raise RuntimeError(
                    f"[MARKET_CONSTITUENTS] NASDAQ symbols fetch timeout ({NASDAQ_URL}). "
                    "nasdaqtrader.com is unreachable or slow."
                ) from e

            logger.debug("Downloading OTHER list")
            try:
                oth_text = requests.get(OTHER_URL, timeout=15).text
            except requests.exceptions.Timeout as e:
                raise RuntimeError(
                    f"[MARKET_CONSTITUENTS] Other symbols fetch timeout ({OTHER_URL}). "
                    "nasdaqtrader.com is unreachable or slow."
                ) from e

            rows = []
            etf_rows = []
            seen_symbols: set[str] = set()

            # BUGFIX 2026-07-20: nasdaqlisted.txt and otherlisted.txt use DIFFERENT column
            # schemas (confirmed live against both feeds). nasdaqlisted.txt: "Symbol",
            # "Market Category" (Q/G/S), has "Financial Status". otherlisted.txt (the feed
            # for NYSE/NYSE American/NYSE Arca/BATS/IEXG-listed stocks - i.e. most non-NASDAQ
            # names): "ACT Symbol", "Exchange" (N/A/P/Z/V), NO "Financial Status" column at
            # all. The old single shared parse loop looked up "Symbol"/"Market Category"
            # unconditionally, so EVERY row of otherlisted.txt failed the "Symbol" presence
            # check and was silently skipped - meaning stock_symbols has never contained a
            # single true NYSE-listed company (AbbVie, Abbott, Alcoa, ADM, ...) via this
            # loader; only NASDAQ + the NASDAQ feed's own "NYSE MKT" rows ever landed there.
            schemas = [
                {
                    "text": nas_text,
                    "symbol_field": "Symbol",
                    "exchange_field": "Market Category",
                    "exchange_map": {"Q": "NASDAQ", "G": "NASDAQ", "S": "NYSE MKT"},
                    "has_financial_status": True,
                },
                {
                    "text": oth_text,
                    "symbol_field": "ACT Symbol",
                    "exchange_field": "Exchange",
                    "exchange_map": {"N": "NYSE", "A": "NYSE MKT", "P": "NYSE ARCA", "Z": "BATS", "V": "IEXG"},
                    "has_financial_status": False,
                },
            ]

            for schema in schemas:
                symbol_field = cast(str, schema["symbol_field"])
                exchange_field = cast(str, schema["exchange_field"])
                exchange_map = cast(dict[str, str], schema["exchange_map"])
                reader = csv.DictReader(cast(str, schema["text"]).splitlines(), delimiter="|")
                for r in reader:
                    # CRITICAL: Symbol is required - explicit validation, no defaults
                    if symbol_field not in r or not r[symbol_field]:
                        logger.warning(
                            f"[MARKET_CONSTITUENTS] Skipping row with missing or empty '{symbol_field}' field."
                        )
                        continue
                    sym = r[symbol_field].strip()
                    if sym.startswith("File Creation Time"):
                        continue
                    if sym in seen_symbols:
                        # Cross-listed on both feeds (rare) - keep the first classification.
                        continue

                    # CRITICAL: Security Name is required
                    if "Security Name" not in r:
                        raise ValueError(
                            f"[MARKET_CONSTITUENTS] Symbol {sym} missing required 'Security Name' field. "
                            "Cannot process market constituent without name."
                        )
                    name = r["Security Name"].strip()
                    if not name:
                        raise ValueError(
                            f"[MARKET_CONSTITUENTS] Symbol {sym} has empty 'Security Name' field. "
                            "Cannot process market constituent with empty name."
                        )

                    # ETFs go to separate table (not stock_symbols)
                    required_classifier_fields = ["ETF", "Test Issue"] + (
                        ["Financial Status"] if schema["has_financial_status"] else []
                    )
                    for field in required_classifier_fields:
                        if field not in r:
                            raise ValueError(
                                f"[MARKET_CONSTITUENTS] Symbol {sym} missing required field '{field}'. "
                                f"Cannot safely classify security. Available fields: {list(r.keys())}"
                            )

                    if r["ETF"].upper() == "Y" or sym in KNOWN_ETF_MISCLASSIFICATIONS:
                        etf_rows.append(
                            {
                                "symbol": sym,
                                "security_name": name,
                                "data_unavailable": False,
                                "data_unavailable_reason": None,
                            }
                        )
                        seen_symbols.add(sym)
                        continue

                    if _is_excluded(sym, name):
                        continue
                    if r["Test Issue"].upper() == "Y":
                        continue
                    # otherlisted.txt has no "Financial Status" (deficient-issuer) column -
                    # that NASDAQ-specific flag simply doesn't exist for NYSE/other listings.
                    if schema["has_financial_status"] and r["Financial Status"].strip() == "D":
                        continue
                    if "etf" in name.lower() or "fund" in name.lower():
                        logger.debug(f"Excluding {sym} ({name}) by security name pattern")
                        continue

                    if exchange_field not in r or not r[exchange_field]:
                        logger.warning(f"[MARKET_CONSTITUENTS] Symbol {sym} missing exchange field. Skipping.")
                        continue
                    exchange_code = r[exchange_field].upper().strip()
                    # FAIL-FAST: Skip symbols with unmapped exchange codes instead of using "UNKNOWN"
                    if exchange_code not in exchange_map:
                        logger.warning(
                            f"[MARKET_CONSTITUENTS] Symbol {sym} has unmapped exchange code '{exchange_code}'. "
                            f"Skipping. This indicates: (1) New exchange code from API, or (2) Data quality issue. "
                            f"Known codes: {list(exchange_map.keys())}"
                        )
                        continue
                    exchange = exchange_map[exchange_code]
                    rows.append(
                        {
                            "symbol": sym,
                            "security_name": name,
                            "exchange": exchange,
                            "etf": "N",
                        }
                    )
                    seen_symbols.add(sym)

            # Upsert ETFs to separate table
            if etf_rows:
                self._upsert_etf_symbols(etf_rows)

            if not rows:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] No tradable symbols parsed from NASDAQ/NYSE data. "
                    "Cannot proceed with market constituent list."
                )
            return rows

        except (requests.RequestException, json.JSONDecodeError) as e:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] Failed to fetch NASDAQ symbols: {e}. "
                "Cannot load market constituents without base symbol data."
            ) from e

    def _fetch_sp500_symbols(self) -> list[str]:
        is_valid, error_msg = validate_url(SP500_URL, allowed_domains=["wikipedia.org"])
        if not is_valid:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] SSRF validation failed for S&P 500 URL: {error_msg}. "
                "Cannot fetch S&P 500 constituent data."
            )

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(SP500_URL, headers=headers, timeout=15)
            response.raise_for_status()

            tables = pd.read_html(StringIO(response.text))
            if not tables:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] Could not parse S&P 500 table from Wikipedia. "
                    "Cannot load S&P 500 constituent membership data."
                )

            df = tables[0]
            col = "Symbol" if "Symbol" in df.columns else "Ticker"

            if col not in df.columns:
                raise RuntimeError(
                    f"[MARKET_CONSTITUENTS] S&P 500 table missing {col} column. "
                    "Cannot extract S&P 500 constituents without symbol data."
                )

            symbols: list[str] = df[col].str.strip().tolist()
            return symbols

        except requests.exceptions.Timeout as e:
            raise RuntimeError(
                "[MARKET_CONSTITUENTS] S&P 500 fetch timeout. Wikipedia API is unreachable or slow."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] Failed to fetch S&P 500: {e}. Cannot load S&P 500 constituent data."
            ) from e

    def _fetch_russell2000_symbols(self) -> list[str]:
        """Fetch Russell 2000 constituents from reliable source (optional enrichment).

        Returns empty list if unavailable - Russell 2000 is optional enrichment data.
        The loader continues without it rather than failing.

        KNOWN BROKEN 2026-08-25 (goal: "before real money" data-source audit): both URLs below
        are structurally incapable of ever returning a constituent list, not just flaky -
        `is_russell2000` has been false for all 5,635 symbols since this loader's inception
        (confirmed via `SELECT COUNT(*) FILTER (WHERE is_russell2000), COUNT(*) FROM
        stock_symbols` -> 0/5635). multpl.com's page is Russell 2000 INDEX PRICE history (a
        single time series, no per-symbol table), not a membership list. Wikipedia's Russell
        2000 article has no constituent table at all - unlike the S&P 500 article Wikipedia
        maintains, Russell doesn't license Wikipedia to republish its (paid, FTSE Russell-owned)
        membership list. Investigated free replacements and none worked within this session's
        budget: iShares IWM holdings CSV (`ishares.com/.../1467271812596.ajax?fileType=csv...`)
        returns HTTP 200 but serves an HTML disclaimer/bot-check page instead of the CSV even
        with a browser User-Agent and Referer; Vanguard VTWO's holdings page is a JS-rendered
        SPA with no static table; SEC EDGAR's `browse-edgar` company search returned zero hits
        for "ishares russell 2000" / "ishares trust" NPORT-P filings (a free-text company-name
        match, not the right lookup). A REAL working path exists but was deliberately not built
        out this pass (scope - needs a new NPORT-EX holdings parser with its own tests, not a
        quick fix): `https://www.sec.gov/files/company_tickers_mf.json` maps ticker "IWM" ->
        CIK 1100663 ("iShares Trust"), seriesId "S000004344"; that CIK's NPORT-P filings (via
        `data.sec.gov/submissions/CIK0001100663.json`) are filed in per-series batches across
        many dates - full-text search (`efts.sec.gov/LATEST/search-index?q=%22iShares+Russell
        +2000+ETF%22&forms=NPORT-P&ciks=0001100663`) is how to actually find the right
        accession/series among the ~90 series this trust files under one CIK (e.g. accession
        0001752724-25-210405, period 2025-06-30, found this way). Russell reconstitutes
        annually each June, so even a several-months-stale NPORT-EX snapshot is normal-fidelity
        membership data - this is a legitimate real source, just needs real engineering (XML
        holdings parsing + tests) to land, not a copy-paste URL swap. Not wired into any
        scoring/universe-filtering/risk logic (`grep -rn is_russell2000` outside this file and
        two unrelated allowlists in `utils/db/sql_safety.py` /`utils/loaders/sla_monitor.py`
        returns nothing) - dead enrichment column, not a trading-correctness risk. Left as a
        documented gap rather than a silent one; fix properly if this ever becomes load-bearing
        (a paid index-data provider, or an N-PORT filing located by exact CIK, are the real
        paths - not another free scrape).
        """
        urls = [
            "https://www.multpl.com/russell-2000/table/by-date",
            "https://en.wikipedia.org/wiki/Russell_2000",
        ]

        for url_index, url in enumerate(urls, 1):
            is_valid, error_msg = validate_url(url, allowed_domains=["multpl.com", "wikipedia.org"])
            if not is_valid:
                logger.debug(
                    f"[MARKET_CONSTITUENTS] Russell 2000 URL validation failed ({url_index}/{len(urls)}): {error_msg}. "
                    "Attempting next source."
                )
                continue

            try:
                logger.debug(f"Attempting Russell 2000 fetch from source {url_index}/{len(urls)}: {url}")
                headers = {"User-Agent": "Mozilla/5.0"}
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()

                tables = pd.read_html(StringIO(response.text))
                if not tables:
                    logger.debug(
                        f"[MARKET_CONSTITUENTS] No tables found at Russell 2000 source ({url_index}/{len(urls)}). Attempting next source."
                    )
                    continue

                for table in tables:
                    for col in ["Ticker", "Symbol", "symbol"]:
                        if col in table.columns:
                            symbols: list[str] = table[col].str.strip().tolist()
                            if symbols:
                                logger.info(
                                    f"Successfully fetched Russell 2000 data from source {url_index}/{len(urls)} using column '{col}': {len(symbols)} constituents"
                                )
                                return symbols

                logger.debug(
                    f"[MARKET_CONSTITUENTS] No valid symbol column found at source {url_index}/{len(urls)}. Attempting next source."
                )

            except requests.exceptions.Timeout as e:
                logger.debug(
                    f"[MARKET_CONSTITUENTS] Timeout fetching Russell 2000 from source {url_index}/{len(urls)}: {e}. "
                    "Attempting next source."
                )
                continue
            except Exception as e:
                logger.debug(
                    f"[MARKET_CONSTITUENTS] Failed to fetch Russell 2000 from source {url_index}/{len(urls)}: {e}. "
                    "Attempting next source."
                )
                continue

        error_msg = (
            f"[MARKET_CONSTITUENTS] Russell 2000 data unavailable from all sources ({len(urls)} attempted). "
            "Cannot load Russell 2000 constituent data without valid source."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    def _upsert_etf_symbols(self, etf_rows: list[dict[str, Any]]) -> None:
        """Refresh ETF symbols table with explicit validation (keep separate from tradable symbols)."""
        if not etf_rows:
            logger.info("No ETF symbols to upsert (empty list)")
            return

        # Validate ETF data structure before database operation
        for i, row in enumerate(etf_rows):
            if "symbol" not in row or not row["symbol"]:
                raise ValueError(
                    f"[MARKET_CONSTITUENTS] ETF row {i} missing or empty 'symbol' field. "
                    f"Cannot upsert ETF symbol without symbol. Row: {row}"
                )
            if "security_name" not in row or not row["security_name"]:
                raise ValueError(
                    f"[MARKET_CONSTITUENTS] ETF row {i} (symbol={row['symbol']}) missing or empty 'security_name' field. "
                    f"Cannot upsert ETF symbol without name."
                )

        try:
            import psycopg2

            from utils.db.context import DatabaseContext

            with DatabaseContext("write") as cur:
                cur.execute("TRUNCATE TABLE etf_symbols")
                cur.executemany(
                    "INSERT INTO etf_symbols (symbol, security_name, data_unavailable, data_unavailable_reason) VALUES (%s, %s, %s, %s)",
                    [
                        (row["symbol"], row["security_name"], row["data_unavailable"], row["data_unavailable_reason"])
                        for row in etf_rows
                    ],
                )
            logger.info(f"Successfully refreshed etf_symbols table with {len(etf_rows)} ETF symbols")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] Failed to refresh etf_symbols table with {len(etf_rows)} symbols: {e}. "
                "Cannot proceed with incomplete ETF symbol update."
            ) from e


if __name__ == "__main__":
    sys.exit(run_loader(MarketConstituentsLoader, global_mode=True))
