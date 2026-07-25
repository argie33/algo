/**
 * Frontend Scores Diagnostics Tool
 * Paste this into your browser console to diagnose "No data" display issues
 *
 * Usage:
 * 1. Open browser DevTools (F12)
 * 2. Go to Console tab
 * 3. Paste this entire script
 * 4. Run: scoresDiagnostics()
 *
 * This will test:
 * - API response structure
 * - Factor inputs presence
 * - Reason field extraction
 * - React component data flow
 */

async function scoresDiagnostics() {
  console.group("🔍 SCORES PIPELINE DIAGNOSTICS");

  // ===== TEST 1: API Response =====
  console.group("1. API Response Structure");
  try {
    const apiResp = await fetch("/api/scores?limit=1").then(r => r.json());

    console.log("✓ API responded");
    console.log(`  statusCode: ${apiResp.statusCode}`);
    console.log(`  has data: ${"data" in apiResp}`);
    console.log(`  has data.items: ${"items" in (apiResp.data || {})}`);

    if (apiResp.data?.items?.length > 0) {
      const firstItem = apiResp.data.items[0];
      console.log(`\n✓ Sample stock: ${firstItem.symbol}`);
      console.log(`  has quality_inputs: ${"quality_inputs" in firstItem}`);
      console.log(`  has momentum_inputs: ${"momentum_inputs" in firstItem}`);
      console.log(`  has value_inputs: ${"value_inputs" in firstItem}`);

      // Check quality_inputs structure
      if (firstItem.quality_inputs) {
        const qi = firstItem.quality_inputs;
        const valueFields = Object.entries(qi).filter(([k]) => !k.endsWith("_unavailable_reason"));
        const reasonFields = Object.entries(qi).filter(([k]) => k.endsWith("_unavailable_reason"));

        console.log(`\n  quality_inputs fields:`);
        console.log(`    - Value fields: ${valueFields.length}`);
        console.log(`    - Reason fields: ${reasonFields.length}`);

        // Show sample reason extractions
        console.log(`\n  Sample reason fields:`);
        reasonFields.slice(0, 3).forEach(([k, v]) => {
          console.log(`    ${k}: "${v}"`);
        });
      }
    }
    console.groupEnd();
  } catch (e) {
    console.error("✗ API test failed:", e);
    console.groupEnd();
    return;
  }

  // ===== TEST 2: Reason Extraction Logic =====
  console.group("2. Reason Extraction Logic");
  if (apiResp.data?.items?.length > 0) {
    const qi = apiResp.data.items[0].quality_inputs;
    if (qi) {
      // Test the reason extraction logic from InputsCard
      const testKeys = ["return_on_equity_pct", "operating_margin_pct", "debt_to_assets"];

      testKeys.forEach(key => {
        let reason = qi[key + "_unavailable_reason"];
        if (!reason && key.endsWith("_pct")) {
          reason = qi[key.slice(0, -4) + "_unavailable_reason"];
        }
        if (!reason && key.endsWith("_val")) {
          reason = qi[key.slice(0, -4) + "_unavailable_reason"];
        }

        const value = qi[key];
        console.log(`✓ ${key}:`);
        console.log(`    value: ${value}`);
        console.log(`    reason: ${reason}`);
        console.log(`    display: ${reason ? `"${reason}"` : (value ? `${value}` : `"No data"`)}`);
      });
    }
  }
  console.groupEnd();

  // ===== TEST 3: React State (if available) =====
  console.group("3. React Component Data");
  try {
    // Find React Fiber node in DevTools (Hermes doesn't expose it easily)
    const rootElement = document.querySelector('[data-testid="stock-score-accordion"], .stock-detail');
    if (rootElement) {
      console.log("✓ Found component element");
      const fiberKey = Object.keys(rootElement).find(key => key.startsWith("__react"));
      if (fiberKey) {
        const fiber = rootElement[fiberKey];
        console.log("  React component detected");
        console.log("  (Use React DevTools to inspect component state)");
      } else {
        console.log("  ⚠ Could not locate React Fiber (React DevTools extension recommended)");
      }
    } else {
      console.log("⚠ Component not currently mounted (navigate to scores page and try again)");
    }
  } catch (e) {
    console.warn("Could not inspect React state:", e.message);
  }
  console.groupEnd();

  // ===== TEST 4: Frontend Schema Validation =====
  console.group("4. Frontend Schema Validation");
  try {
    // Basic schema check - these are imported in StockScoreAccordion.jsx
    const qualitySchema = [
      "return_on_equity_pct", "return_on_assets_pct", "return_on_invested_capital_pct",
      "profit_margin_pct", "operating_margin_pct", "debt_to_equity"
    ];

    const apiItem = apiResp.data?.items?.[0];
    if (apiItem?.quality_inputs) {
      const missing = qualitySchema.filter(k => !(k in apiItem.quality_inputs));
      if (missing.length === 0) {
        console.log("✓ All quality schema keys present in API response");
      } else {
        console.error(`✗ Missing schema keys: ${missing.join(", ")}`);
      }
    }
  } catch (e) {
    console.warn("Schema validation skipped:", e.message);
  }
  console.groupEnd();

  // ===== SUMMARY =====
  console.group("📊 SUMMARY");
  console.log("If you still see 'No data' on the dashboard:");
  console.log("1. Hard refresh browser: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)");
  console.log("2. Check browser console (F12) for warnings about missing factor_inputs");
  console.log("3. Open React DevTools and inspect StockScoreAccordion component props");
  console.log("4. Verify API response has quality_inputs/momentum_inputs/etc");
  console.groupEnd();

  console.groupEnd();
}

// Run diagnostics
scoresDiagnostics().catch(console.error);
