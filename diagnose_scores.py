#!/usr/bin/env python3
"""Comprehensive scores data pipeline diagnostic.

Tests the entire flow:
1. Database has scores → API sees them
2. API endpoint returns correct structure
3. Fetcher extracts data correctly
4. Panel renders it correctly
5. Individual factor completeness
"""

import os
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform.startswith("win"):
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except:
        pass

sys.path.insert(0, str(Path.cwd()))
os.environ["DASHBOARD_API_URL"] = "http://localhost:3001"

def test_database():
    """Test 1: Check database for scores."""
    from utils.db.context import DatabaseContext

    print("\n" + "=" * 70)
    print("TEST 1: DATABASE SCORES")
    print("=" * 70)

    with DatabaseContext("read") as cur:
        cur.execute("""
            SELECT COUNT(*) as total,
                   COUNT(CASE WHEN composite_score > 0 THEN 1 END) as valid,
                   COUNT(CASE WHEN composite_score > 0 AND data_completeness >= 70
                                AND (data_unavailable = false OR data_unavailable IS NULL) THEN 1 END) as api_eligible
            FROM stock_scores
        """)
        result = cur.fetchone()
        if result:
            total, valid, api_eligible = result
            print(f"[OK] Total scores: {total}")
            print(f"[OK] Valid (composite > 0): {valid}")
            print(f"[OK] API eligible (completeness >= 70): {api_eligible}")

            if valid > 0:
                # Check individual factors
                cur.execute("""
                    SELECT
                        COUNT(CASE WHEN composite_score IS NULL THEN 1 END),
                        COUNT(CASE WHEN momentum_score IS NULL THEN 1 END),
                        COUNT(CASE WHEN quality_score IS NULL THEN 1 END),
                        COUNT(CASE WHEN value_score IS NULL THEN 1 END),
                        COUNT(CASE WHEN growth_score IS NULL THEN 1 END),
                        COUNT(CASE WHEN stability_score IS NULL THEN 1 END),
                        COUNT(CASE WHEN positioning_score IS NULL THEN 1 END)
                    FROM stock_scores
                    WHERE composite_score > 0
                """)
                result2 = cur.fetchone()
                if result2:
                    c, m, q, v, g, s, p = result2
                    print(f"\nFactor NULL counts in valid scores:")
                    print(f"  Composite: {c} (critical)")
                    print(f"  Momentum: {m}")
                    print(f"  Quality: {q}")
                    print(f"  Value: {v} [WARN]")
                    print(f"  Growth: {g} [WARN]")
                    print(f"  Stability: {s}")
                    print(f"  Positioning: {p} [WARN]")

def test_api_raw():
    """Test 2: Check raw API response."""
    import requests

    print("\n" + "=" * 70)
    print("TEST 2: RAW API RESPONSE")
    print("=" * 70)

    try:
        resp = requests.get("http://localhost:3001/api/algo/scores?limit=10", timeout=5)
        print(f"[OK] Status: {resp.status_code}")
        data = resp.json()
        print(f"[OK] Response format: {type(data)}")
        print(f"[OK] Top-level keys: {list(data.keys())}")

        if "data" in data and "top" in data["data"]:
            top = data["data"]["top"]
            print(f"[OK] Items in response: {len(top)}")

            # Check first item completeness
            if top:
                first = top[0]
                print(f"\nFirst item ({first.get('symbol')}):")
                print(f"  composite: {first.get('composite_score')}")
                print(f"  momentum: {first.get('momentum_score')}")
                print(f"  quality: {first.get('quality_score')}")
                print(f"  value: {first.get('value_score')}")
                print(f"  growth: {first.get('growth_score')}")
                print(f"  stability: {first.get('stability_score')}")
                print(f"  positioning: {first.get('positioning_score')}")

                # Check if ANY items have NULL factors
                null_factors = {f: 0 for f in ['momentum_score', 'quality_score', 'value_score', 'growth_score', 'stability_score', 'positioning_score']}
                for item in top:
                    for factor in null_factors:
                        if item.get(factor) is None:
                            null_factors[factor] += 1

                if any(null_factors.values()):
                    print(f"\n[WARN] NULL factors in response:")
                    for factor, count in null_factors.items():
                        if count > 0:
                            print(f"  {factor}: {count}/{len(top)}")
    except Exception as e:
        print(f"[ERROR] Error: {e}")

def test_api_unwrapped():
    """Test 3: Check unwrapped API response."""
    from dashboard.api_data_layer import api_call

    print("\n" + "=" * 70)
    print("TEST 3: UNWRAPPED API RESPONSE")
    print("=" * 70)

    try:
        result = api_call("/api/algo/scores", params={"limit": 10, "sortOrder": "desc", "offset": 0})
        print(f"[OK] Result type: {type(result)}")
        print(f"[OK] Keys: {list(result.keys())}")
        print(f"[OK] Has statusCode: {result.get('statusCode')}")
        print(f"[OK] Has _error: {'_error' in result}")

        if "top" in result:
            print(f"[OK] Items in 'top': {len(result['top'])}")

        if "avg_composite" in result:
            print(f"[OK] avg_composite: {result.get('avg_composite')}")

        if "universe_total" in result:
            print(f"[OK] universe_total: {result.get('universe_total')}")

    except Exception as e:
        print(f"[ERROR] Error: {e}")

def test_fetcher():
    """Test 4: Check fetcher output."""
    from dashboard.fetchers_signals import fetch_scores

    print("\n" + "=" * 70)
    print("TEST 4: FETCHER OUTPUT")
    print("=" * 70)

    try:
        result = fetch_scores(None)
        print(f"[OK] Result type: {type(result)}")
        print(f"[OK] Keys: {list(result.keys())}")
        print(f"[OK] Has _error: {'_error' in result}")

        if "_error" in result:
            print(f"[ERROR] Error: {result['_error']}")
        else:
            print(f"[OK] Items in 'top': {len(result.get('top', []))}")
            print(f"[OK] avg_composite: {result.get('avg_composite')}")
            print(f"[OK] universe_total: {result.get('universe_total')}")
            print(f"[OK] grades: {result.get('grades')}")

    except Exception as e:
        print(f"[ERROR] Error: {e}")

def test_panel():
    """Test 5: Check panel rendering."""
    from dashboard.fetchers_signals import fetch_scores
    from dashboard.panels.scores import panel_scores_compact, panel_scores_expanded

    print("\n" + "=" * 70)
    print("TEST 5: PANEL RENDERING")
    print("=" * 70)

    try:
        scores_data = fetch_scores(None)

        # Compact panel
        try:
            compact = panel_scores_compact(scores_data)
            print(f"[OK] Compact panel rendered: {type(compact)}")
        except Exception as e:
            print(f"[ERROR] Compact panel error: {e}")

        # Expanded panel
        try:
            expanded = panel_scores_expanded(scores_data)
            print(f"[OK] Expanded panel rendered: {type(expanded)}")
        except Exception as e:
            print(f"[ERROR] Expanded panel error: {e}")

    except Exception as e:
        print(f"[ERROR] Error: {e}")

def test_full_load():
    """Test 6: Check full dashboard load."""
    from dashboard.fetchers import load_all

    print("\n" + "=" * 70)
    print("TEST 6: FULL DASHBOARD LOAD")
    print("=" * 70)

    try:
        data = load_all()
        print(f"[OK] Loaded {len(data)} data sources")

        if "scores" in data:
            scores = data["scores"]
            print(f"[OK] Scores loaded: {type(scores)}")
            if isinstance(scores, dict):
                if "_error" in scores:
                    print(f"[ERROR] Scores error: {scores['_error']}")
                else:
                    print(f"[OK] Top items: {len(scores.get('top', []))}")
                    print(f"[OK] avg_composite: {scores.get('avg_composite')}")
        else:
            print(f"[ERROR] Scores not in loaded data")

    except Exception as e:
        print(f"[ERROR] Error: {e}")

if __name__ == "__main__":
    test_database()
    test_api_raw()
    test_api_unwrapped()
    test_fetcher()
    test_panel()
    test_full_load()

    print("\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)
