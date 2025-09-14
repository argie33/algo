# Unit Test Coverage Gap Analysis

## 🎯 Goal: 100% Unit Test Coverage Before E2E Tests

## 📊 Current Status Analysis

### Backend Unit Tests (Lambda)
**Location**: `/home/stocks/algo/webapp/lambda/tests/unit/`
**Current Count**: 85 test files ✅

#### Coverage by Category:
| Category | Files | Test Status |
|----------|-------|-------------|
| **Utils** (17 files) | 17/17 | ✅ COMPLETE |
| **Routes** (43 files) | ~35/43 | 🟡 MOSTLY COVERED |
| **Services** (2 files) | 2/2 | ✅ COMPLETE |
| **Middleware** (5 files) | 5/5 | ✅ COMPLETE |

### Frontend Unit Tests (React/Vitest)
**Location**: `/home/stocks/algo/webapp/frontend/src/tests/unit/`
**Current Count**: 154 test files ✅

## 🔍 Systematic Coverage Analysis

### Backend Files vs Unit Tests Matrix

#### Utils Coverage (COMPLETE ✅)
```bash
utils/                          tests/unit/
├── alertSystem.js       ✅ →   alertSystem.test.js
├── alpacaService.js     ✅ →   alpacaService.test.js
├── apiKeyService.js     ✅ →   apiKeyService.test.js
├── backtestStore.js     ✅ →   backtestStore.test.js
├── database.js          ✅ →   database.test.js
├── errorTracker.js      ✅ →   errorTracker.test.js
├── factorScoring.js     ✅ →   factorScoring.test.js
├── liveDataManager.js   ✅ →   liveDataManager.test.js
├── logger.js            ✅ →   logger.test.js
├── newsAnalyzer.js      ✅ →   newsAnalyzer.test.js
├── performanceMonitor.js ✅ →  performanceMonitor.test.js
├── realTimeDataService.js ✅ → realTimeDataService.test.js
├── responseFormatter.js ✅ →   responseFormatter.test.js
├── riskEngine.js        ✅ →   riskEngine.test.js
├── schemaValidator.js   ✅ →   schemaValidator.test.js
├── sentimentEngine.js   ✅ →   sentimentEngine.test.js
└── tradingModeHelper.js ✅ →   tradingModeHelper.test.js
```

#### Routes Coverage (GAPS IDENTIFIED 🔴)
Let me check what route unit tests exist vs what routes we have...