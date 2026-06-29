# Fallback-to-Fail-Fast Audit Report
**Date**: 2026-06-28  
**Scope**: Complete finance application codebase (algo/, dashboard/, loaders/, lambda/)  
**Goal**: Identify cases where code silently falls back when it should fail fast  
**Status**: 47+ issues identified across 4 severity tiers

---

## Executive Summary

This audit uncovered **47+ locations** where the finance application silently falls back to empty/None/default values instead of raising errors. In a trading system, silent data loss = incorrect risk calculations, wrong position sizing, and inaccurate market regime detection.

**Key Finding**: Fall-back behavior exists across three patterns:
1. **Credential/Config Fallbacks** — Passwords and API keys default to empty strings
2. **Optional Data Lacking Explicit Flags** — Missing data returns `None`/`{}` without marking why
3. **Log Levels Too Low** — Missing financial data logged at DEBUG instead of WARNING

---

## Critical Issues (Fix This Week)

### 🔴 CRITICAL-1: Password Defaults to Empty String
**File**: `lambda/data-freshness-monitor/lambda_function.py:37`  
**Current**: `return json.loads(response["SecretString"]).get("password", "")`  
**Problem**: Missing password defaults to empty string, authentication fails silently

### 🔴 CRITICAL-2: Run Identifier Defaults to Empty String
**File**: `lambda/algo_orchestrator/lambda_function.py:137`  
**Current**: `run_identifier = event.get("run_identifier", "")`  
**Problem**: Missing orchestration ID loses traceability

### 🔴 CRITICAL-3: Yield Curve Silent Skip with DEBUG Log
**File**: `loaders/load_market_health_daily.py:304-306`  
**Current**: `logger.debug("...skipping...") return`  
**Problem**: Market regime detection failure, rows created with missing yield_curve_slope

### 🔴 CRITICAL-4: Secret String Missing → Empty Dict
**File**: `lambda/api/dev_server.py:57`  
**Current**: `creds = json.loads(secret.get("SecretString", "{}"))`  
**Problem**: All credentials become None silently

---

## High Severity Issues

### 🟠 HIGH-1: Yield Curve Returns Empty Dict Without Flag
**File**: `loaders/market_health_fetchers.py:215-225`  
**Problem**: No `data_unavailable` flag on optional data failures

### 🟠 HIGH-2: Stock Scores Return Empty List on Missing Metrics
**File**: `loaders/load_stock_scores.py:50-55`  
**Problem**: Returns `[]` when metrics unavailable, caller can't distinguish failure modes

### 🟠 HIGH-3: Stability Metrics Return None Without Flag
**File**: `loaders/load_stability_metrics.py:90-94`  
**Problem**: Returns `None` without `data_available` marker

### 🟠 HIGH-4: Alignment Data Missing Logged at DEBUG
**File**: `algo/signals/advanced_filters.py:459`  
**Problem**: Missing technical data invisible to operations (DEBUG level)

### 🟠 HIGH-5: Pocket Pivot Missing Data at DEBUG
**File**: `algo/signals/signal_momentum.py:305,310`  
**Problem**: Missing OHLC data preventing patterns, hidden at DEBUG level

---

## Medium Severity

### 🟡 MEDIUM-1: Dashboard API Cascading .get()
**File**: `dashboard/diagnose_metrics.py:26,53,90,128`  
**Problem**: API validation delayed, `None` cascades through operations

---

## Good Patterns (Keep)

✅ **VIX Fetcher** — Raises on critical data failures  
✅ **Circuit Breaker Validation** — Validates completeness before writes  
✅ **Performance Metrics** — Warning log + error raise  
✅ **Dashboard Error Boundary** — Detects errors at boundary  

---

## Summary Table

| Issue | File | Severity |
|-------|------|----------|
| Password → "" | lambda/data-freshness-monitor:37 | CRITICAL |
| Run ID → "" | lambda/algo_orchestrator:137 | CRITICAL |
| Yield curve silent skip | loaders/load_market_health_daily:304 | CRITICAL |
| Secret → {} | lambda/api/dev_server:57 | CRITICAL |
| Yield curve no flag | loaders/market_health_fetchers:215-225 | HIGH |
| Stock scores [] | loaders/load_stock_scores:50-55 | HIGH |
| Stability metrics None | loaders/load_stability_metrics:90-94 | HIGH |
| Alignment DEBUG | algo/signals/advanced_filters:459 | HIGH |
| Pocket pivot DEBUG | algo/signals/signal_momentum:305,310 | HIGH |
| Dashboard cascade | dashboard/diagnose_metrics:26,53,90,128 | MEDIUM |

---

## Fix Priority

**Week 1**: CRITICAL-1 to CRITICAL-4, plus elevate yield curve log level to WARNING  
**Week 2**: HIGH-1 to HIGH-5 — add data_unavailable flags and elevate log levels  
**Week 3+**: MEDIUM-1 and systematic review of all `return None` patterns (~48+)

---

## Full Details

Comprehensive analysis with specific code fixes available in:
- **Memory**: `memory/fallback_audit_findings.md` (full context, all 47 locations, testing strategy)
- **This File**: Quick reference summary above

**Total locations found**: 47+ organized by severity, file, and type  
**Files requiring audit**: loaders/, lambda/api/, algo/signals/, dashboard/

Status: **Audit Complete** — Ready to begin prioritized fixes.
