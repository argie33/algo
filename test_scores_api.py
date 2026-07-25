#!/usr/bin/env python3
"""Test the API scores endpoint to verify data is being returned correctly."""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_api():
    """Test /api/scores/stockscores endpoint."""
    print("\n" + "="*70)
    print("API TEST: /api/scores/stockscores")
    print("="*70)

    try:
        # Start a local connection to the dev server query
        from utils.db import DatabaseContext
        import psycopg2.extras

        with DatabaseContext("read") as cur:
            cur = cur.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # Run the same query the API runs (simplified for testing)
            # This mimics what lambda/api/routes/scores.py does

            # Get one stock with full data
            query = """
                SELECT
                    ss.symbol,
                    sc.composite_score,
                    sc.quality_score,
                    sc.value_score,
                    sc.growth_score,
                    sc.momentum_score,
                    sc.positioning_score,
                    sc.stability_score,
                    sc.data_completeness,

                    -- Value metrics
                    vm.pe_ratio AS trailing_pe,
                    vm.pe_ratio_unavailable_reason,
                    vm.forward_pe,
                    vm.forward_pe_unavailable_reason,
                    vm.pb_ratio AS price_to_book,
                    vm.pb_ratio_unavailable_reason,
                    vm.ps_ratio AS ps_ratio_val,
                    vm.ps_ratio_unavailable_reason,
                    vm.peg_ratio AS peg_ratio_val,
                    vm.peg_ratio_unavailable_reason,
                    vm.ev_ebitda,
                    vm.ev_ebitda_unavailable_reason,
                    vm.dividend_yield,
                    vm.dividend_yield_unavailable_reason,
                    vm.fcf_yield AS fcf_yield_val,
                    vm.fcf_yield_unavailable_reason,

                    -- Quality metrics
                    qm.roe AS roe_pct,
                    qm.roe_unavailable_reason,
                    qm.roa AS roa_val,
                    qm.roa_unavailable_reason,
                    qm.operating_margin AS operating_margin_val,
                    qm.operating_margin_unavailable_reason,
                    qm.net_margin AS net_margin_val,
                    qm.net_margin_unavailable_reason,
                    qm.debt_to_equity,
                    qm.debt_to_equity_unavailable_reason
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                WHERE sc.symbol = 'AAPL'
                  AND sc.data_completeness >= 70
                LIMIT 1
            """

            cur.execute(query)
            row = cur.fetchone()

            if row:
                print(f"\nData returned for AAPL:")
                print(f"  Symbol: {row['symbol']}")
                print(f"  Composite Score: {row['composite_score']}")
                print(f"  Quality Score: {row['quality_score']}")
                print(f"  Value Score: {row['value_score']}")
                print(f"  Data Completeness: {row['data_completeness']}%")

                print(f"\n  Value metrics (raw response):")
                print(f"    trailing_pe: {row['trailing_pe']}")
                print(f"    pe_ratio_unavailable_reason: {row['pe_ratio_unavailable_reason']}")
                print(f"    pb_ratio: {row['price_to_book']}")
                print(f"    ps_ratio_val: {row['ps_ratio_val']}")
                print(f"    peg_ratio_val: {row['peg_ratio_val']}")
                print(f"    ev_ebitda: {row['ev_ebitda']}")
                print(f"    ev_ebitda_unavailable_reason: {row['ev_ebitda_unavailable_reason']}")
                print(f"    dividend_yield: {row['dividend_yield']}")
                print(f"    fcf_yield_val: {row['fcf_yield_val']}")

                print(f"\n  Quality metrics (raw response):")
                print(f"    roe_pct: {row['roe_pct']}")
                print(f"    roe_unavailable_reason: {row['roe_unavailable_reason']}")
                print(f"    roa_val: {row['roa_val']}")
                print(f"    operating_margin_val: {row['operating_margin_val']}")
                print(f"    net_margin_val: {row['net_margin_val']}")
                print(f"    debt_to_equity: {row['debt_to_equity']}")
                print(f"    debt_to_equity_unavailable_reason: {row['debt_to_equity_unavailable_reason']}")

                # Now test _build_factor_inputs like the API does
                print(f"\n" + "-"*70)
                print("API's _build_factor_inputs() transformation:")
                print("-"*70)

                d = dict(row)

                # Mimic the API's _build_factor_inputs
                quality_inputs = {
                    "return_on_equity_pct": d.get("roe_pct"),
                    "return_on_equity_unavailable_reason": d.get("roe_unavailable_reason"),
                    "return_on_assets_pct": d.get("roa_val"),
                    "return_on_assets_unavailable_reason": d.get("roa_unavailable_reason"),
                    "operating_margin_pct": d.get("operating_margin_val"),
                    "operating_margin_unavailable_reason": d.get("operating_margin_unavailable_reason"),
                    "profit_margin_pct": d.get("net_margin_val"),
                    "profit_margin_unavailable_reason": d.get("net_margin_unavailable_reason"),
                    "debt_to_equity": d.get("debt_to_equity"),
                    "debt_to_equity_unavailable_reason": d.get("debt_to_equity_unavailable_reason"),
                }

                value_inputs = {
                    "stock_pe": d.get("trailing_pe"),
                    "stock_pe_unavailable_reason": d.get("pe_ratio_unavailable_reason"),
                    "stock_pb": d.get("price_to_book"),
                    "stock_pb_unavailable_reason": d.get("pb_ratio_unavailable_reason"),
                    "stock_ps": d.get("ps_ratio_val"),
                    "stock_ps_unavailable_reason": d.get("ps_ratio_unavailable_reason"),
                    "peg_ratio": d.get("peg_ratio_val"),
                    "peg_ratio_unavailable_reason": d.get("peg_ratio_unavailable_reason"),
                    "stock_ev_ebitda": d.get("ev_ebitda"),
                    "stock_ev_ebitda_unavailable_reason": d.get("ev_ebitda_unavailable_reason"),
                    "stock_dividend_yield": d.get("dividend_yield"),
                    "stock_dividend_yield_unavailable_reason": d.get("dividend_yield_unavailable_reason"),
                    "fcf_yield": d.get("fcf_yield_val"),
                    "fcf_yield_unavailable_reason": d.get("fcf_yield_unavailable_reason"),
                }

                print(f"\nquality_inputs:")
                print(json.dumps(quality_inputs, indent=2, default=str))

                print(f"\nvalue_inputs:")
                print(json.dumps(value_inputs, indent=2, default=str))

                # Test frontend schema extraction
                print(f"\n" + "-"*70)
                print("Frontend InputsCard schema extraction test:")
                print("-"*70)

                # Test the VALUE_SCHEMA key mappings
                VALUE_SCHEMA = [
                    { 'key': 'stock_pe', 'label': 'P/E' },
                    { 'key': 'stock_pb', 'label': 'P/B' },
                    { 'key': 'stock_ps', 'label': 'P/S' },
                    { 'key': 'peg_ratio', 'label': 'PEG' },
                ]

                print("\nExtracting values from value_inputs:")
                for schema_item in VALUE_SCHEMA:
                    key = schema_item['key']
                    value = value_inputs.get(key)
                    # Try to extract reason with the frontend logic
                    reason = value_inputs.get(key + "_unavailable_reason")
                    print(f"  {key}: value={value}, reason={reason}")
            else:
                print("No AAPL data returned from query")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_api()
