
/**
 * Portfolio Optimization System - Validation & Diagnostic Tool
 *
 * Checks all components and verifies the system is ready for testing
 */

const fs = require("fs");
const path = require("path");

// Color codes for output
const colors = {
  reset: "\x1b[0m",
  green: "\x1b[32m",
  red: "\x1b[31m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  cyan: "\x1b[36m",
};

function log(message, color = "reset") {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

function checkFile(filePath, description) {
  if (fs.existsSync(filePath)) {
    const size = fs.statSync(filePath).size;
    log(`  ✅ ${description} (${size} bytes)`, "green");
    return true;
  } else {
    log(`  ❌ ${description} - NOT FOUND`, "red");
    return false;
  }
}

async function validateSystem() {
  log("\n╔════════════════════════════════════════════════════════════╗", "cyan");
  log("║  Portfolio Optimization System - Validation Tool           ║", "cyan");
  log("╚════════════════════════════════════════════════════════════╝\n", "cyan");

  let allPassed = true;

  // 1. Check utility files
  log("📦 Checking Utility Files...", "blue");
  allPassed &= checkFile(
    path.join(__dirname, "../utils/correlationAnalysis.js"),
    "Correlation Analysis Utility"
  );
  allPassed &= checkFile(
    path.join(__dirname, "../utils/alpacaTrading.js"),
    "Alpaca Trading Utility"
  );

  // 2. Check handler files
  log("\n🔧 Checking Handler Files...", "blue");
  allPassed &= checkFile(
    path.join(__dirname, "../handlers/alpacaExecutionHandler.js"),
    "Alpaca Execution Handler"
  );
  allPassed &= checkFile(
    path.join(__dirname, "../handlers/errorRecoveryHandler.js"),
    "Error Recovery Handler"
  );

  // 3. Check route files
  log("\n🛣️ Checking Route Files...", "blue");
  allPassed &= checkFile(
    path.join(__dirname, "../routes/portfolio-optimization.js"),
    "Portfolio Optimization Route"
  );

  // 4. Check test files
  log("\n🧪 Checking Test Files...", "blue");
  allPassed &= checkFile(
    path.join(__dirname, "unit/portfolio-optimization.test.js"),
    "Unit Tests"
  );
  allPassed &= checkFile(
    path.join(__dirname, "integration/portfolio-optimization-integration.test.js"),
    "Integration Tests"
  );
  allPassed &= checkFile(
    path.join(__dirname, "e2e/portfolio-optimization-e2e.test.js"),
    "End-to-End Tests"
  );

  // 5. Check frontend files
  log("\n🎨 Checking Frontend Files...", "blue");
  allPassed &= checkFile(
    path.join(__dirname, "../../frontend/src/pages/PortfolioOptimization.jsx"),
    "Portfolio Optimization Page"
  );

  // 6. Check documentation
  log("\n📚 Checking Documentation...", "blue");
  allPassed &= checkFile(
    path.join(__dirname, "../../PORTFOLIO_OPTIMIZATION_GUIDE.md"),
    "Portfolio Optimization Guide"
  );

  // 7. Check database connectivity
  log("\n🗄️ Checking Database Connectivity...", "blue");
  try {
    const { query } = require("../utils/database");
    await query("SELECT 1");
    log("  ✅ Database connection successful", "green");
  } catch (error) {
    // Database may not be configured - that's OK for validation, just warn
    log(`  ⚠️ Database not configured: ${error.message}`, "yellow");
    log("     (This is OK - configure DB when running tests)", "yellow");
  }

  // 8. Check required imports
  log("\n📥 Checking Module Imports...", "blue");

  try {
    require("../utils/correlationAnalysis");
    log("  ✅ Correlation Analysis imports successfully", "green");
  } catch (error) {
    log(`  ❌ Correlation Analysis import failed: ${error.message}`, "red");
    allPassed = false;
  }

  try {
    require("../utils/alpacaTrading");
    log("  ✅ Alpaca Trading imports successfully", "green");
  } catch (error) {
    log(`  ❌ Alpaca Trading import failed: ${error.message}`, "red");
    allPassed = false;
  }

  try {
    require("../handlers/alpacaExecutionHandler");
    log("  ✅ Alpaca Execution Handler imports successfully", "green");
  } catch (error) {
    log(`  ❌ Alpaca Execution Handler import failed: ${error.message}`, "red");
    allPassed = false;
  }

  try {
    require("../handlers/errorRecoveryHandler");
    log("  ✅ Error Recovery Handler imports successfully", "green");
  } catch (error) {
    log(`  ❌ Error Recovery Handler import failed: ${error.message}`, "red");
    allPassed = false;
  }

  try {
    require("../routes/portfolio-optimization");
    log("  ✅ Portfolio Optimization Route imports successfully", "green");
  } catch (error) {
    log(`  ❌ Portfolio Optimization Route import failed: ${error.message}`, "red");
    allPassed = false;
  }

  // 9. Check function exports
  log("\n🔗 Checking Function Exports...", "blue");

  try {
    const { calculateCorrelationMatrix, calculateDiversificationScore, recommendLowCorrelationAsset } = require("../utils/correlationAnalysis");
    if (calculateCorrelationMatrix && calculateDiversificationScore && recommendLowCorrelationAsset) {
      log("  ✅ Correlation functions exported correctly", "green");
    } else {
      log("  ❌ Missing correlation function exports", "red");
      allPassed = false;
    }
  } catch (error) {
    log(`  ❌ Correlation export check failed: ${error.message}`, "red");
    allPassed = false;
  }

  try {
    const { AlpacaTrader, initializeAlpacaTrader } = require("../utils/alpacaTrading");
    if (AlpacaTrader && initializeAlpacaTrader) {
      log("  ✅ Alpaca functions exported correctly", "green");
    } else {
      log("  ❌ Missing Alpaca function exports", "red");
      allPassed = false;
    }
  } catch (error) {
    log(`  ❌ Alpaca export check failed: ${error.message}`, "red");
    allPassed = false;
  }

  try {
    const { executeOptimizationTrades, getExecutionStatus, checkPendingOrders } = require("../handlers/alpacaExecutionHandler");
    if (executeOptimizationTrades && getExecutionStatus && checkPendingOrders) {
      log("  ✅ Execution handler functions exported correctly", "green");
    } else {
      log("  ❌ Missing execution handler function exports", "red");
      allPassed = false;
    }
  } catch (error) {
    log(`  ❌ Execution handler export check failed: ${error.message}`, "red");
    allPassed = false;
  }

  try {
    const { retryWithBackoff, CircuitBreaker, validateOperationData } = require("../handlers/errorRecoveryHandler");
    if (retryWithBackoff && CircuitBreaker && validateOperationData) {
      log("  ✅ Error recovery functions exported correctly", "green");
    } else {
      log("  ❌ Missing error recovery function exports", "red");
      allPassed = false;
    }
  } catch (error) {
    log(`  ❌ Error recovery export check failed: ${error.message}`, "red");
    allPassed = false;
  }

  // 10. Summary
  log("\n╔════════════════════════════════════════════════════════════╗", "cyan");
  if (allPassed) {
    log("║  ✅ SYSTEM VALIDATION PASSED                              ║", "cyan");
    log("╚════════════════════════════════════════════════════════════╝\n", "cyan");

    log("🚀 System is ready for testing!\n", "green");
    log("Next steps:", "blue");
    log("  1. Run unit tests:        npm test -- tests/unit/", "cyan");
    log("  2. Run integration tests: npm test -- tests/integration/", "cyan");
    log("  3. Run E2E tests:         npm test -- tests/e2e/", "cyan");
    log("  4. Or run all tests:      bash tests/run-e2e-tests.sh\n", "cyan");

    return 0;
  } else {
    log("║  ❌ SYSTEM VALIDATION FAILED                              ║", "cyan");
    log("╚════════════════════════════════════════════════════════════╝\n", "cyan");

    log("⚠️  Some components are missing or not working correctly.\n", "yellow");
    log("Please review the errors above and fix any issues.\n", "yellow");

    return 1;
  }
}

// Run validation
validateSystem()
  .then((exitCode) => process.exit(exitCode))
  .catch((error) => {
    log(`\n❌ Validation error: ${error.message}`, "red");
    process.exit(1);
  });
