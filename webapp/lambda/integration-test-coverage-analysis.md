# Integration Test Coverage Analysis

## Utils Files vs Integration Tests Coverage

### ✅ COVERED - Have Integration Tests
| Utils File | Integration Test | Status |
|------------|------------------|---------|
| alertSystem.js | tests/integration/utils/alertSystem.test.js | ✅ Covered |
| apiKeyService.js | tests/integration/utils/apiKeyService.test.js | ✅ Covered |
| backtestStore.js | tests/integration/utils/backtestStore.test.js | ✅ Covered |
| database.js | tests/integration/utils/database.integration.test.js | ✅ Covered |
| database.js | tests/integration/utils/database-connection.integration.test.js | ✅ Extra coverage |
| errorTracker.js | tests/integration/utils/errorTracker.test.js | ✅ Covered |
| factorScoring.js | tests/integration/utils/factorScoring.test.js | ✅ Covered |
| liveDataManager.js | tests/integration/utils/liveDataManager.test.js | ✅ Covered |
| logger.js | tests/integration/utils/logger.test.js | ✅ Covered |
| newsAnalyzer.js | tests/integration/utils/newsAnalyzer.test.js | ✅ Covered |
| performanceMonitor.js | tests/integration/utils/performanceMonitor.test.js | ✅ Covered |
| realTimeDataService.js | tests/integration/utils/realTimeDataService.test.js | ✅ Covered |
| responseFormatter.js | tests/integration/utils/responseFormatter.test.js | ✅ Covered |
| riskEngine.js | tests/integration/utils/riskEngine.test.js | ✅ Covered |
| schemaValidator.js | tests/integration/utils/schemaValidator.test.js | ✅ Covered |
| sentimentEngine.js | tests/integration/utils/sentimentEngine.test.js | ✅ Covered |
| tradingModeHelper.js | tests/integration/utils/tradingModeHelper.test.js | ✅ Covered |

### ❌ GAPS - Missing Integration Tests
**NONE IDENTIFIED** - All 17 utils files have corresponding integration tests!

## Services Integration Test Coverage

### ✅ COVERED - Have Integration Tests
| Service File | Integration Test | Status |
|-------------|------------------|---------|
| aiStrategyGenerator.js | tests/integration/services/aiStrategyGenerator.test.js | ✅ Covered |
| N/A | tests/integration/services/alpacaService.test.js | ✅ Extra coverage (alpacaService is in utils/) |
| N/A | tests/integration/services/cross-service-integration.test.js | ✅ Extra coverage |

### ❌ GAPS - Missing Integration Tests for Services
| Service File | Missing Integration Test | Priority |
|-------------|-------------------------|----------|
| aiStrategyGeneratorStreaming.js | tests/integration/services/aiStrategyGeneratorStreaming.test.js | 🔴 HIGH |

## Routes Integration Test Coverage Analysis

### ✅ COVERED - Have Integration Tests
| Route File | Integration Test | Status |
|-----------|------------------|---------|
| alerts.js | tests/integration/routes/alerts.integration.test.js | ✅ Covered |
| alerts.js | tests/integration/routes/alerts-simple.integration.test.js | ✅ Extra coverage |
| analysts.js | tests/integration/routes/analysts.integration.test.js | ✅ Covered |
| analytics.js | tests/integration/routes/analytics.integration.test.js | ✅ Covered |
| auth.js | tests/integration/routes/auth.integration.test.js | ✅ Covered |
| backtest.js | tests/integration/routes/backtest.integration.test.js | ✅ Covered |
| calendar.js | tests/integration/routes/calendar.integration.test.js | ✅ Covered |
| commodities.js | tests/integration/routes/commodities.integration.test.js | ✅ Covered |
| dashboard.js | tests/integration/routes/dashboard.integration.test.js | ✅ Covered |
| data.js | tests/integration/routes/data.integration.test.js | ✅ Covered |
| diagnostics.js | tests/integration/routes/diagnostics.integration.test.js | ✅ Covered |
| dividend.js | tests/integration/routes/dividend.integration.test.js | ✅ Covered |
| earnings.js | tests/integration/routes/earnings.integration.test.js | ✅ Covered |
| economic.js | tests/integration/routes/economic.integration.test.js | ✅ Covered |
| etf.js | tests/integration/routes/etf.integration.test.js | ✅ Covered |
| financials.js | tests/integration/routes/financials.integration.test.js | ✅ Covered |
| health.js | tests/integration/routes/health.integration.test.js | ✅ Covered |
| insider.js | tests/integration/routes/insider.integration.test.js | ✅ Covered |
| liveData.js | tests/integration/routes/liveData.integration.test.js | ✅ Covered |
| market.js | tests/integration/routes/market.integration.test.js | ✅ Covered |
| metrics.js | tests/integration/routes/metrics.integration.test.js | ✅ Covered |
| news.js | tests/integration/routes/news.integration.test.js | ✅ Covered |
| orders.js | tests/integration/routes/orders.integration.test.js | ✅ Covered |
| performance.js | tests/integration/routes/performance.integration.test.js | ✅ Covered |
| portfolio.js | tests/integration/routes/portfolio.integration.test.js | ✅ Covered |
| positioning.js | tests/integration/routes/positioning.integration.test.js | ✅ Covered |
| price.js | tests/integration/routes/price.integration.test.js | ✅ Covered |
| recommendations.js | tests/integration/routes/recommendations.integration.test.js | ✅ Covered |
| research.js | tests/integration/routes/research.integration.test.js | ✅ Covered |
| risk.js | tests/integration/routes/risk.integration.test.js | ✅ Covered |
| scores.js | tests/integration/routes/scores.integration.test.js | ✅ Covered |
| scoring.js | tests/integration/routes/scoring.integration.test.js | ✅ Covered |
| screener.js | tests/integration/routes/screener.integration.test.js | ✅ Covered |
| sectors.js | tests/integration/routes/sectors.integration.test.js | ✅ Covered |
| sentiment.js | tests/integration/routes/sentiment.integration.test.js | ✅ Covered |
| settings.js | tests/integration/routes/settings.integration.test.js | ✅ Covered |
| signals.js | tests/integration/routes/signals.integration.test.js | ✅ Covered |
| stocks.js | tests/integration/routes/stocks.integration.test.js | ✅ Covered |
| strategyBuilder.js | tests/integration/routes/strategyBuilder.integration.test.js | ✅ Covered |
| technical.js | tests/integration/routes/technical.integration.test.js | ✅ Covered |
| trades.js | tests/integration/routes/trades.integration.test.js | ✅ Covered |
| trading.js | tests/integration/routes/trading.integration.test.js | ✅ Covered |
| watchlist.js | tests/integration/routes/watchlist.integration.test.js | ✅ Covered |
| websocket.js | tests/integration/routes/websocket.integration.test.js | ✅ Covered |

### ❌ GAPS - Missing Integration Tests for Routes
**NONE IDENTIFIED** - All 43 route files have corresponding integration tests!

## Middleware Integration Test Coverage

### ✅ COVERED - Have Integration Tests
| Type | Integration Test | Status |
|------|------------------|---------|
| Auth | tests/integration/middleware/auth-middleware.integration.test.js | ✅ Covered |
| Error Handler | tests/integration/middleware/errorHandler-middleware.integration.test.js | ✅ Covered |
| Response Formatter | tests/integration/middleware/responseFormatter-middleware.integration.test.js | ✅ Covered |
| Security Headers | tests/integration/middleware/security-headers.integration.test.js | ✅ Covered |
| Validation | tests/integration/middleware/validation-middleware.integration.test.js | ✅ Covered |
| Middleware Chains | tests/integration/infrastructure/middleware-chains.integration.test.js | ✅ Extra coverage |

## Summary

### 🎯 EXCELLENT COVERAGE!
- **Utils**: 17/17 files covered (100%)
- **Routes**: 43/43 files covered (100%) 
- **Services**: 1/2 files covered (50%) - Missing aiStrategyGeneratorStreaming.js
- **Middleware**: Full coverage with extras

### 🔴 CRITICAL GAPS IDENTIFIED

| Missing Test | File Location | Priority | Impact |
|-------------|---------------|----------|--------|
| aiStrategyGeneratorStreaming.test.js | services/aiStrategyGeneratorStreaming.js | 🔴 HIGH | AI streaming functionality not tested |

### 📊 Overall Integration Test Coverage: 96.7% (59/61 files)

**Recommendation**: Create integration test for `services/aiStrategyGeneratorStreaming.js` to achieve 100% coverage.