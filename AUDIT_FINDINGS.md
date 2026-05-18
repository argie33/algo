# Production Readiness Audit - 2026-05-18

## CRITICAL ISSUES (Must Fix Before Production)

### 1. ⚠️ SECURITY: .env.local Files Should Not Exist in Repo
**Status**: CRITICAL
**Files**: 
- `.env.local` (project root)
- `webapp/lambda/.env.local`

**Issue**: Per CLAUDE.md rules, no .env files should be committed. Credentials must come from AWS Secrets Manager.

**Current State**: 
- Files contain hardcoded DB credentials and API keys
- `config/credential_helper.py` auto-loads these for convenience
- `webapp/lambda/index.js` uses dotenv to load .env.local

**Fix Required**:
1. Delete both .env.local files
2. Update credential_helper.py to NOT auto-load .env.local in production
3. Ensure all env var loading comes from AWS Secrets Manager or proper CI environment
4. Add .env.local to .gitignore (if not already)

---

### 2. ⚠️ API: Frontend Hardcoded localhost:3001 Fallback in Production
**Status**: CRITICAL
**Files**:
- `webapp/frontend/src/config/index.js` (line 4)
- `webapp/frontend/public/config.js` (line 4)
- `webapp/frontend/vite.config.js` (line 19 proxy target mismatch)

**Issue**: API_BASE_URL falls back to `http://localhost:3001` for production, not using VITE_API_URL properly.

**Current Code**:
```javascript
// Line 4 of src/config/index.js - WRONG
export const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? '' : 'http://localhost:3001');
```

**Fix Required**: 
1. Require VITE_API_URL in production (throw error if missing)
2. Only use localhost as fallback in dev mode
3. Fix vite.config.js proxy target (line 19 should be 3001, not 4000)

---

### 3. 📝 DEBUG LOGGING: console.log() Calls Throughout Codebase
**Status**: HIGH
**Location**: 15+ console.log calls in webapp/lambda/

**Issue**: Debug logging statements should use proper logging module, not console.log.

**Files with console.log**:
- `webapp/lambda/middleware/auth.js` (2 calls)
- `webapp/lambda/routes/economic.js` (1 call)
- `webapp/lambda/routes/market.js` (2 calls)
- `webapp/lambda/routes/trades.js` (2 calls)
- `webapp/lambda/handlers/alpacaExecutionHandler.js`
- `webapp/lambda/index.js` (multiple error logging)
- `webapp/lambda/middleware/auth.js` (request logging)

**Fix Required**: Replace with proper logger utility

---

## ARCHITECTURAL ISSUES

### 4. 🔧 Configuration Management: Multiple Config Sources
**Status**: MEDIUM
**Files**:
- `.env.local` (local dev)
- `webapp/frontend/public/config.js` (build-time)
- `webapp/frontend/src/config/index.js` (runtime)
- `webapp/lambda/vite.config.js` (Vite build config)

**Issue**: Configuration comes from multiple sources with no clear precedence.

**Fix Required**: 
1. Centralize configuration management
2. Document clear precedence: ENV_VARS > Secrets Manager > Defaults
3. Remove hardcoded localhost values

---

### 5. 🗄️ Database Connection: Inconsistent Error Handling
**Status**: MEDIUM
**Files**:
- `webapp/lambda/utils/database.js`
- `config/credential_helper.py`

**Issue**: Database connection failures have different handling patterns:
- Python: Silent fallback
- Node: Secrets Manager with retry logic

**Fix Required**: Standardize error handling and ensure consistent behavior

---

## CODE QUALITY ISSUES

### 6. 📋 Missing Error Handling in Some Routes
**Status**: MEDIUM
**Files**:
- Various routes missing consistent error logging format
- Some routes missing input validation
- Inconsistent response formats (some use sendSuccess, some return raw objects)

**Fix Required**:
1. Audit all routes for consistent error handling
2. Ensure all routes return via sendSuccess/sendError
3. Add input validation middleware

---

### 7. 🧪 Test Coverage Assessment Needed
**Status**: MEDIUM
**Found Test Files**:
- `tests/backtest/test_backtest_regression.py`
- `tests/edge_cases/test_order_failures.py`
- `tests/integration/test_orchestrator_flow.py`
- `tests/test_api_contract_compliance.py`
- And 10+ more test files

**Issue**: Need to verify coverage of:
1. All API endpoints (contract validation)
2. Authentication flows
3. Error scenarios
4. Database connection failures

**Fix Required**: Run full test suite and identify gaps

---

### 8. 🔐 Credential Management: Multiple Fallback Paths
**Status**: MEDIUM
**Files**:
- `config/credential_helper.py` (3 fallback paths)
- `config/credential_manager.py`
- `config/credential_validator.py`

**Issue**: Complex credential loading with multiple sources:
1. Environment variable (DB_PASSWORD)
2. credential_manager (AWS Secrets Manager)
3. .env.local (local dev convenience)
4. Hardcoded defaults (testing)

**Fix Required**:
1. Simplify credential loading path
2. Ensure .env.local is ONLY loaded for local dev, never in CI/prod
3. Remove silent defaults

---

## MISSING PRODUCTION CONFIGURATIONS

### 9. 🚀 Missing Environment-Specific Build Config
**Status**: HIGH
**Files**:
- `webapp/frontend/` (no .env.production file)
- `webapp/lambda/` (no environment-specific config)

**Issue**: No production-specific configuration template.

**Fix Required**:
1. Create `.env.production.example` with required vars
2. Document all environment variables needed for prod
3. Create deployment checklist

---

### 10. 📊 Missing API Contract Validation
**Status**: MEDIUM
**Files**:
- `tests/test_api_contract_compliance.py`
- `tests/test_api_contract_validation.py`

**Issue**: API_CONTRACT.md exists but unclear if all endpoints are validated.

**Fix Required**: Run contract tests against all endpoints

---

## DEPLOYMENT READINESS

### 11. 🚢 Missing Deploy Pipeline Configuration
**Status**: HIGH
**Files**:
- No GitHub Actions workflow for API deployment
- Frontend build artifacts in dist/ but not deployed

**Issue**: Manual deployment required, no CI/CD pipeline.

**Fix Required**:
1. Set up GitHub Actions workflow
2. Auto-build frontend on push
3. Deploy to S3/CloudFront on tag

---

### 12. 🔍 Missing Monitoring & Logging Setup
**Status**: MEDIUM
**Files**:
- CloudWatch integration missing in Node code
- Error logging not structured
- No metrics collection

**Fix Required**:
1. Implement structured logging (JSON format)
2. Add CloudWatch integration
3. Set up error tracking

---

## SUMMARY BY PRIORITY

### MUST FIX (Production Blocking):
1. ✅ Delete .env.local files (security)
2. ✅ Fix frontend API URL configuration 
3. ✅ Remove debug console.log calls (clean logs)
4. ✅ Ensure proper error handling in all routes
5. ✅ Validate all endpoints work end-to-end

### SHOULD FIX (Production Ready):
1. Document all required environment variables
2. Ensure consistent credential management
3. Validate database connection patterns
4. Run full test suite
5. Set up monitoring/logging

### NICE TO FIX (Technical Debt):
1. Centralize configuration management
2. Improve error handling consistency
3. Add more comprehensive tests
4. Set up CI/CD pipeline

---

## NEXT STEPS

1. Review this audit with team
2. Fix critical security issues first
3. Run full end-to-end test
4. Set up production deployment
5. Enable monitoring

**Generated**: 2026-05-18
**Auditor**: Claude Code
