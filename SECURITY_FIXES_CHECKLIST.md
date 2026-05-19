# Security Fixes Checklist

## Phase 1: Critical Fixes (4 Hours to Production-Ready)

**Deadline:** Before any production trading  
**Target Completion:** Today

### Issue #1: SQL Injection in Health Check (30 min)
- [ ] Read: `lambda/api/lambda_function.py` lines 109-116
- [ ] Whitelist allowed tables: `price_daily`, `signals`, `stock_scores`, `technical_data_daily`
- [ ] Quote table names with `f'SELECT COUNT(*) FROM "{table}"'`
- [ ] Test: `curl "https://your-api.example.com/health/detailed?table=price_daily; DROP TABLE signals; --"` should not execute SQL
- [ ] Commit with message: `security(fix): prevent SQL injection in health check endpoint`

### Issue #2: CORS Misconfiguration (15 min)
- [ ] Read: `lambda/api/lambda_function.py` lines 92, 103, 177, 185, 227, 238, 246
- [ ] Create `get_cors_headers(event)` function that checks request origin
- [ ] Whitelist domains:
  - [ ] `https://edgebrooke.example.com`
  - [ ] `https://dashboard.example.com`
  - [ ] `http://localhost:5173` (dev only)
- [ ] Replace ALL `'Access-Control-Allow-Origin': '*'` with dynamic CORS header
- [ ] Test:
  - [ ] `curl -H "Origin: https://evil.com" ...` → should NOT return `Access-Control-Allow-Origin: *`
  - [ ] `curl -H "Origin: https://edgebrooke.example.com" ...` → should return allowed origin
- [ ] Commit with message: `security(fix): restrict CORS to whitelisted origins`

### Issue #3: Token Stored in localStorage (30 min)
- [ ] Read: `webapp/frontend/src/contexts/AuthContext.jsx`
- [ ] Find/Replace: `localStorage` → `sessionStorage`
  - [ ] Line ~: `localStorage.setItem("accessToken", ...)` → `sessionStorage.setItem`
  - [ ] Line ~: `localStorage.getItem("accessToken")` → `sessionStorage.getItem`
  - [ ] Line ~: `localStorage.removeItem(...)` → `sessionStorage.removeItem`
- [ ] Remove "Remember Me" functionality (or change to not persist tokens)
- [ ] Verify: `grep -r "localStorage.*Token\|localStorage.*auth" webapp/frontend/src/` returns NO results
- [ ] Test:
  - [ ] Login to app
  - [ ] Check DevTools → Application → sessionStorage → should see authToken
  - [ ] Close browser completely (all tabs)
  - [ ] Reopen app → should be logged out (no token in session)
  - [ ] Check localStorage → should NOT contain any tokens
- [ ] Commit with message: `security(fix): use sessionStorage instead of localStorage for auth tokens`

### Issue #4: Database Credentials in CI Logs (30 min)
- [ ] Read: `.github/workflows/deploy-code.yml` lines 197-235
- [ ] Delete the entire section: "Inject DB credentials into Lambda env (eliminates cold-start SM call)"
  - [ ] Lines 197-235 should be deleted
- [ ] Update `lambda/api/lambda_function.py` `get_db_connection()` to fetch from Secrets Manager if env var not set:
  ```python
  # If db_password not in env, fetch from Secrets Manager
  if not db_password and db_secret_arn:
      secret = boto3.client('secretsmanager').get_secret_value(SecretId=db_secret_arn)
      secret_dict = json.loads(secret['SecretString'])
      db_password = secret_dict.get('password')
  ```
- [ ] Test: After deployment, check Lambda logs for NO credential values
  - [ ] `aws logs tail /aws/lambda/stocks-api-dev --follow` should NOT show `DB_PASSWORD=`
- [ ] Commit with message: `security(fix): remove credential injection from CI/CD pipeline`

### Issue #5: Missing API Authorization (1 hour)
- [ ] Read: `lambda/api/lambda_function.py`
- [ ] Add functions before `lambda_handler`:
  - [ ] `get_bearer_token(event)` — extracts token from Authorization header
  - [ ] `validate_bearer_token(token)` — validates JWT format/length
  - [ ] `require_auth(event, path)` — determines if path needs auth
- [ ] Public endpoints (no auth required):
  - [ ] `/health`, `/api/health`
  - [ ] `/health/detailed`, `/api/health/detailed`
  - [ ] `/health/pipeline`, `/api/health/pipeline`
- [ ] Protected endpoints (all others under `/api/`):
  - [ ] `/api/algo/trades` — requires Bearer token
  - [ ] `/api/algo/positions` — requires Bearer token
  - [ ] `/api/algo/performance` — requires Bearer token
  - [ ] etc. (all other /api/ endpoints)
- [ ] Add auth check in `lambda_handler` before routing
- [ ] Return 401 Unauthorized if token missing or invalid
- [ ] Test:
  - [ ] `curl https://your-api.example.com/api/health` → 200 (public)
  - [ ] `curl https://your-api.example.com/api/algo/trades` → 401 (no token)
  - [ ] `curl -H "Authorization: Bearer token123" https://your-api.example.com/api/algo/trades` → 200 (with token)
- [ ] Commit with message: `security(fix): add API authorization middleware to protected endpoints`

### Issue #6: Secrets in .env Files (15 min)
- [ ] **WARNING:** If repo is public, these credentials are compromised. Rotate them after removal.
- [ ] Remove from git tracking:
  ```bash
  git rm --cached .env.local
  git rm --cached webapp/frontend/.env
  ```
- [ ] Update `.gitignore`:
  ```bash
  cat >> .gitignore << 'EOF'
  .env
  .env.local
  .env.*.local
  .env.production.local
  EOF
  ```
- [ ] Create templates (no real credentials):
  ```bash
  # .env.local.example
  cp .env.local .env.local.example
  # Edit to replace: DB_PASSWORD=stocks → DB_PASSWORD=<SET_YOUR_LOCAL_DB_PASSWORD>
  
  # webapp/frontend/.env.example
  cp webapp/frontend/.env webapp/frontend/.env.example
  ```
- [ ] Commit:
  ```bash
  git add .gitignore .env.local.example webapp/frontend/.env.example
  git commit -m "security(fix): remove .env files from repo and add gitignore"
  ```
- [ ] **Rotate Credentials:**
  - [ ] Database password (update in AWS Secrets Manager)
  - [ ] Alpaca API keys (if exposed in git history)
  - [ ] FRED API key (if exposed in git history)
  - [ ] AWS IAM keys for GitHub Actions (if exposed in git history)
- [ ] Test: `git log -p --all | grep -i "password\|api_key" | head -5` → should find no recent commits with credentials

---

## Phase 1 Summary

- [ ] All 6 critical issues fixed
- [ ] Tests passing: `npm test` and `python -m pytest tests/ -v`
- [ ] No hardcoded secrets in recent commits
- [ ] No SQL injection vulnerabilities
- [ ] All API endpoints require auth (except /health)
- [ ] CORS restricted to specific origins
- [ ] Tokens in sessionStorage only
- [ ] Credentials NOT in CI/CD logs

**Phase 1 Status:** _____ (Not Started / In Progress / Complete)

**Date Started:** _______  
**Date Completed:** _______  
**Time Spent:** _______ hours

---

## Phase 2: High-Priority (This Week)

### Issue #7: Generic Error Responses (1 hour)
- [ ] Update `lambda/api/routes/utils.py` `error_response()` to not leak internal details
- [ ] Log full errors internally, return generic message to client
- [ ] Test: Error responses should NOT contain table names, SQL syntax, etc.

### Issue #8: Security Headers (1 hour)
- [ ] Add headers to all API responses:
  - [ ] `Strict-Transport-Security: max-age=31536000`
  - [ ] `X-Content-Type-Options: nosniff`
  - [ ] `X-Frame-Options: DENY`
  - [ ] `X-XSS-Protection: 1; mode=block`
  - [ ] `Referrer-Policy: strict-origin-when-cross-origin`

### Issue #9: Rate Limiting (1.5 hours)
- [ ] Option A (Recommended): Configure in API Gateway Terraform
- [ ] Option B: Implement in Lambda with in-memory limiter
- [ ] Test: Send 2000+ req/sec, should get 429 errors

### Issue #10: Input Validation (1.5 hours)
- [ ] Apply `safe_limit()`, `safe_offset()`, `safe_days()` consistently
- [ ] Add symbol validation (alphanumeric + dash only)
- [ ] Test: Invalid params should return 400, not crash

### Issue #11: Hardcoded DB Host (30 min)
- [ ] Remove default: `db_host = os.getenv('DB_HOST', 'algo-db...')`
- [ ] Make required: `db_host = os.getenv('DB_HOST')` or raise error

### Issue #12: TLS Enforcement (2 hours)
- [ ] Terraform: CloudFront + API Gateway enforce HTTPS only
- [ ] Terraform: RDS enable encryption at rest
- [ ] Test: HTTP requests should redirect to HTTPS

### Issue #13: Rotate Compromised Credentials (1 hour)
- [ ] Alpaca: Create new API keys, update Secrets Manager
- [ ] FRED: Create new API key, update Secrets Manager
- [ ] AWS: Create new IAM keys for GitHub Actions, update Secrets
- [ ] Test: Verify new keys work in Lambda/CLI

### Issue #14: Strengthen CSP (1 hour)
- [ ] Remove `'unsafe-inline'` from `scriptSrc`
- [ ] Remove inline styles, use external stylesheets
- [ ] Test: No inline script/style execution allowed

### Issue #15: Add SRI to External Resources (1 hour)
- [ ] Calculate SRI hashes for all CDN resources
- [ ] Add `integrity="sha384-..."` to script/link tags

---

## Phase 3: Medium-Priority (Next 2 Weeks)

### Issue #16: Security Event Logging
### Issue #17: Input Sanitization (DOMPurify)
### Issue #18: Password Strength Enforcement
### Issue #19: Account Lockout
### Issue #20: POST for Sensitive Queries
### Issue #21: Cache Control Headers
### Issue #23: AWS WAF

---

## Sign-Off

**Prepared By:** Claude Code  
**Date:** 2026-05-19  
**Reviewed By:** _________________  
**Review Date:** _________________  
**Approved By:** _________________  
**Approval Date:** _________________  

**Phase 1 Completion Target:** Today  
**Phase 2 Completion Target:** End of week  
**Phase 3 Completion Target:** Next sprint  

---

## Notes

- Keep GitHub Secrets up-to-date for new credentials
- Test each fix in dev environment before merging
- Run full test suite after each phase
- Consider security testing tools: OWASP ZAP, Burp Suite
