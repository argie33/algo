/**
 * API-Frontend Compatibility Validation
 *
 * Verifies that the backend API response matches what the frontend component expects
 * This ensures the frontend can consume the API response without errors
 */

// Expected field structure from frontend component
const EXPECTED_STRUCTURE = {
  // Top level
  success: 'boolean',
  data: 'object',

  // Data object
  'data.optimization_id': 'string',
  'data.timestamp': 'string',
  'data.user_id': 'string',
  'data.portfolio_state': 'object',
  'data.sector_allocation': 'array',
  'data.recommended_trades': 'array',
  'data.portfolio_metrics': 'object',
  'data.formulas_used': 'array',
  'data.data_quality': 'object',

  // Portfolio state
  'portfolio_state.total_value': 'number',
  'portfolio_state.total_cost': 'number',
  'portfolio_state.unrealized_pnl': 'number',
  'portfolio_state.unrealized_pnl_pct': 'number',
  'portfolio_state.num_holdings': 'number',
  'portfolio_state.composite_score': 'number',
  'portfolio_state.concentration_ratio': 'number',
  'portfolio_state.top_holdings': 'array',

  // Top holdings item
  'top_holdings_item.symbol': 'string',
  'top_holdings_item.shares': 'number',
  'top_holdings_item.cost': 'number',
  'top_holdings_item.market_value': 'number',
  'top_holdings_item.weight_pct': 'number',
  'top_holdings_item.score': 'number|null',
  'top_holdings_item.pnl_pct': 'number|null',

  // Sector allocation item
  'sector_item.sector': 'string',
  'sector_item.holdings': 'array',
  'sector_item.num_holdings': 'number',
  'sector_item.current_pct': 'number',
  'sector_item.target_pct': 'number',
  'sector_item.drift': 'number',
  'sector_item.value': 'number',
  'sector_item.status': 'string',

  // Recommendation item
  'trade_item.rank': 'number',
  'trade_item.action': 'string',
  'trade_item.symbol': 'string',
  'trade_item.composite_score': 'number',
  'trade_item.portfolio_fit_score': 'number',
  'trade_item.sector': 'string',
  'trade_item.rationale': 'string',
  'trade_item.suggested_amount': 'number|undefined',

  // Portfolio metrics
  'portfolio_metrics.before': 'object',
  'portfolio_metrics.after_recommendations': 'object',
  'portfolio_metrics.expected_improvements': 'object',
};

/**
 * Validation Result
 */
class ValidationResult {
  constructor() {
    this.passed = 0;
    this.failed = 0;
    this.warnings = [];
    this.errors = [];
  }

  pass(message) {
    this.passed++;
    console.log(`✅ ${message}`);
  }

  fail(message) {
    this.failed++;
    this.errors.push(message);
    console.log(`❌ ${message}`);
  }

  warn(message) {
    this.warnings.push(message);
    console.log(`⚠️  ${message}`);
  }

  summary() {
    console.log('\n' + '='.repeat(70));
    console.log(`VALIDATION SUMMARY`);
    console.log('='.repeat(70));
    console.log(`✅ Passed: ${this.passed}`);
    console.log(`❌ Failed: ${this.failed}`);
    console.log(`⚠️  Warnings: ${this.warnings.length}`);

    if (this.errors.length > 0) {
      console.log('\nErrors:');
      this.errors.forEach(e => console.log(`  - ${e}`));
    }

    if (this.warnings.length > 0) {
      console.log('\nWarnings:');
      this.warnings.forEach(w => console.log(`  - ${w}`));
    }

    console.log('='.repeat(70));
    return this.failed === 0;
  }
}

/**
 * Validate API Response Structure
 */
function validateApiResponse(response) {
  const result = new ValidationResult();

  console.log('\n📋 VALIDATING API RESPONSE STRUCTURE\n');

  // Check top-level fields
  if (typeof response.success === 'boolean') {
    result.pass('Top-level "success" field is boolean');
  } else {
    result.fail('Top-level "success" field must be boolean');
  }

  if (response.data && typeof response.data === 'object') {
    result.pass('Top-level "data" field exists and is object');
  } else {
    result.fail('Top-level "data" field must exist and be object');
    return result;
  }

  const data = response.data;

  // Validate data fields
  if (typeof data.optimization_id === 'string') {
    result.pass('data.optimization_id is string');
  } else {
    result.fail('data.optimization_id must be string');
  }

  if (typeof data.timestamp === 'string') {
    result.pass('data.timestamp is string');
  } else {
    result.fail('data.timestamp must be string');
  }

  if (data.user_id) {
    result.pass('data.user_id field exists');
  }

  // Validate portfolio_state
  if (data.portfolio_state && typeof data.portfolio_state === 'object') {
    result.pass('data.portfolio_state exists and is object');

    const ps = data.portfolio_state;

    // Check numeric fields
    const numericFields = ['total_value', 'total_cost', 'unrealized_pnl', 'unrealized_pnl_pct', 'num_holdings', 'composite_score', 'concentration_ratio'];
    numericFields.forEach(field => {
      if (typeof ps[field] === 'number') {
        result.pass(`portfolio_state.${field} is number`);
      } else {
        result.fail(`portfolio_state.${field} must be number, got ${typeof ps[field]}`);
      }
    });

    // Check top_holdings array
    if (Array.isArray(ps.top_holdings)) {
      result.pass(`portfolio_state.top_holdings is array with ${ps.top_holdings.length} items`);

      if (ps.top_holdings.length > 0) {
        const holding = ps.top_holdings[0];

        // Validate first holding structure
        const holdingFields = {
          symbol: 'string',
          shares: 'number',
          cost: 'number',
          market_value: 'number',
          weight_pct: 'number',
          score: 'number|null',
          pnl_pct: 'number|null',
        };

        Object.entries(holdingFields).forEach(([field, expectedType]) => {
          const actualType = holding[field] === null ? 'null' : typeof holding[field];
          if (expectedType.includes(actualType)) {
            result.pass(`top_holdings[0].${field} is ${actualType}`);
          } else {
            result.fail(`top_holdings[0].${field} must be ${expectedType}, got ${actualType}`);
          }
        });
      }
    } else {
      result.fail('portfolio_state.top_holdings must be array');
    }
  } else {
    result.fail('data.portfolio_state must exist and be object');
  }

  // Validate sector_allocation
  if (Array.isArray(data.sector_allocation)) {
    result.pass(`data.sector_allocation is array with ${data.sector_allocation.length} sectors`);

    if (data.sector_allocation.length > 0) {
      const sector = data.sector_allocation[0];

      // Verify sector fields
      const sectorFields = {
        sector: 'string',
        holdings: 'array',
        num_holdings: 'number',
        current_pct: 'number',
        target_pct: 'number',
        drift: 'number',
        value: 'number',
        status: 'string',
      };

      Object.entries(sectorFields).forEach(([field, expectedType]) => {
        const actualType = typeof sector[field];
        if (expectedType === 'array' ? Array.isArray(sector[field]) : actualType === expectedType) {
          result.pass(`sector_allocation[0].${field} is ${expectedType}`);
        } else {
          result.fail(`sector_allocation[0].${field} must be ${expectedType}, got ${actualType}`);
        }
      });

      // Verify drift calculation
      const calculatedDrift = sector.current_pct - sector.target_pct;
      if (Math.abs(sector.drift - calculatedDrift) < 0.01) {
        result.pass(`sector.drift calculation is correct: ${sector.drift} ≈ ${calculatedDrift}`);
      } else {
        result.warn(`sector.drift may be incorrect: ${sector.drift} should be ≈ ${calculatedDrift}`);
      }
    }
  } else {
    result.fail('data.sector_allocation must be array');
  }

  // Validate recommended_trades
  if (Array.isArray(data.recommended_trades)) {
    result.pass(`data.recommended_trades is array with ${data.recommended_trades.length} trades`);

    if (data.recommended_trades.length > 0) {
      const trade = data.recommended_trades[0];

      // Required trade fields for frontend display
      const requiredFields = {
        rank: 'number',
        action: 'string',
        symbol: 'string',
        composite_score: 'number',
        portfolio_fit_score: 'number',
        sector: 'string',
        rationale: 'string',
      };

      Object.entries(requiredFields).forEach(([field, expectedType]) => {
        const actualType = typeof trade[field];
        if (actualType === expectedType) {
          result.pass(`recommended_trades[0].${field} is ${expectedType}`);
        } else {
          result.fail(`recommended_trades[0].${field} must be ${expectedType}, got ${actualType}`);
        }
      });

      // Optional fields
      if (trade.market_fit_component !== undefined) {
        result.pass('recommended_trades[0].market_fit_component exists (optional)');
      }
      if (trade.correlation_component !== undefined) {
        result.pass('recommended_trades[0].correlation_component exists (optional)');
      }
      if (trade.sector_component !== undefined) {
        result.pass('recommended_trades[0].sector_component exists (optional)');
      }
      if (trade.formula_explanation !== undefined) {
        result.pass('recommended_trades[0].formula_explanation exists (optional)');
      }

      // Validate action values
      const validActions = ['BUY', 'SELL', 'REDUCE', 'HOLD'];
      if (validActions.includes(trade.action)) {
        result.pass(`recommended_trades[0].action is valid: "${trade.action}"`);
      } else {
        result.fail(`recommended_trades[0].action must be one of ${validActions}, got "${trade.action}"`);
      }

      // Validate fit score range
      if (trade.portfolio_fit_score >= 0 && trade.portfolio_fit_score <= 100) {
        result.pass(`recommended_trades[0].portfolio_fit_score in valid range: ${trade.portfolio_fit_score}`);
      } else {
        result.warn(`recommended_trades[0].portfolio_fit_score outside typical range: ${trade.portfolio_fit_score}`);
      }
    }
  } else {
    result.fail('data.recommended_trades must be array');
  }

  // Validate portfolio_metrics
  if (data.portfolio_metrics && typeof data.portfolio_metrics === 'object') {
    result.pass('data.portfolio_metrics exists and is object');

    const metrics = data.portfolio_metrics;
    if (metrics.before && metrics.after_recommendations && metrics.expected_improvements) {
      result.pass('portfolio_metrics has before, after_recommendations, and expected_improvements');
    } else {
      result.fail('portfolio_metrics missing required subfields');
    }
  } else {
    result.fail('data.portfolio_metrics must exist and be object');
  }

  // Validate formulas_used
  if (Array.isArray(data.formulas_used)) {
    result.pass(`data.formulas_used is array with ${data.formulas_used.length} formulas`);
  } else {
    result.warn('data.formulas_used should be array for transparency');
  }

  // Validate data_quality
  if (data.data_quality && typeof data.data_quality === 'object') {
    result.pass('data.data_quality exists and is object');

    const dq = data.data_quality;
    if (typeof dq.holdings_with_scores === 'number' && typeof dq.total_holdings === 'number') {
      result.pass(`data_quality: ${dq.holdings_with_scores}/${dq.total_holdings} holdings have scores`);
    }
  } else {
    result.warn('data.data_quality should exist for transparency');
  }

  return result;
}

/**
 * Validate Frontend Integration Points
 */
function validateFrontendIntegration(response) {
  const result = new ValidationResult();

  console.log('\n📱 VALIDATING FRONTEND INTEGRATION POINTS\n');

  if (!response.data) {
    result.fail('Cannot validate frontend integration without data');
    return result;
  }

  const data = response.data;

  // Portfolio Summary Cards (lines 228-300 in PortfolioOptimization.jsx)
  console.log('Portfolio Summary Cards:');
  if (data.portfolio_state) {
    result.pass('portfolio_state available for summary cards');

    // Card 1: Total Value
    if (typeof data.portfolio_state.total_value === 'number') {
      result.pass('Can display total_value in card');
    }

    // Card 2: Holdings Count
    if (typeof data.portfolio_state.num_holdings === 'number') {
      result.pass('Can display num_holdings in card');
    }

    // Card 3: Portfolio Score
    if (typeof data.portfolio_state.composite_score === 'number') {
      result.pass('Can display composite_score in card');
    }

    // Card 4: Concentration
    if (typeof data.portfolio_state.concentration_ratio === 'number') {
      result.pass('Can display concentration_ratio in card');
    }
  }

  // Top Holdings Section (lines 304-356)
  console.log('\nTop Holdings Display:');
  if (Array.isArray(data.portfolio_state?.top_holdings)) {
    const topHoldings = data.portfolio_state.top_holdings;
    result.pass(`Can render top ${topHoldings.length} holdings`);

    if (topHoldings.length > 0) {
      const h = topHoldings[0];
      if (h.symbol && h.weight_pct && h.market_value && h.shares) {
        result.pass('Top holding has all required display fields');
      }
    }
  }

  // Sector Allocation Table (lines 359-437)
  console.log('\nSector Allocation Table:');
  if (Array.isArray(data.sector_allocation)) {
    const sectors = data.sector_allocation;
    result.pass(`Can render ${sectors.length} sector rows`);

    if (sectors.length > 0) {
      const s = sectors[0];
      const requiredFields = ['sector', 'num_holdings', 'current_pct', 'target_pct', 'drift', 'status'];
      const hasAll = requiredFields.every(f => s[f] !== undefined);
      if (hasAll) {
        result.pass('Sector has all required table columns');
      }
    }
  }

  // Recommendations Table (lines 440-530)
  console.log('\nRecommendations Table:');
  if (Array.isArray(data.recommended_trades)) {
    const trades = data.recommended_trades;
    result.pass(`Can render ${trades.length} recommendation rows`);

    if (trades.length > 0) {
      const t = trades[0];
      const requiredFields = ['action', 'symbol', 'sector', 'portfolio_fit_score', 'composite_score', 'rationale'];
      const hasAll = requiredFields.every(f => t[f] !== undefined);
      if (hasAll) {
        result.pass('Trade has all required table columns');
      } else {
        const missing = requiredFields.filter(f => t[f] === undefined);
        result.fail(`Trade missing fields: ${missing.join(', ')}`);
      }
    }
  }

  // Data Quality Footer
  console.log('\nData Quality Display:');
  if (data.data_quality && data.optimization_id) {
    result.pass('Can display optimization_id and data_quality in footer');
  }

  return result;
}

/**
 * Main Validation
 */
function validateAllChecks(apiResponse) {
  console.log('\n' + '='.repeat(70));
  console.log('API-FRONTEND COMPATIBILITY VALIDATION');
  console.log('='.repeat(70));

  const structureResult = validateApiResponse(apiResponse);
  const integrationResult = validateFrontendIntegration(apiResponse);

  // Combine results
  const totalPassed = structureResult.passed + integrationResult.passed;
  const totalFailed = structureResult.failed + integrationResult.failed;
  const totalWarnings = structureResult.warnings.length + integrationResult.warnings.length;

  console.log('\n' + '='.repeat(70));
  console.log('FINAL VALIDATION RESULT');
  console.log('='.repeat(70));
  console.log(`✅ Total Passed: ${totalPassed}`);
  console.log(`❌ Total Failed: ${totalFailed}`);
  console.log(`⚠️  Total Warnings: ${totalWarnings}`);

  if (totalFailed === 0) {
    console.log('\n🎉 VALIDATION PASSED - Frontend and backend are compatible!');
  } else {
    console.log('\n❌ VALIDATION FAILED - Issues must be fixed before production use');
  }
  console.log('='.repeat(70) + '\n');

  return totalFailed === 0;
}

// Export for testing
module.exports = {
  validateApiResponse,
  validateFrontendIntegration,
  validateAllChecks,
  ValidationResult,
};
