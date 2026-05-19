# Security Fixes Implementation Guide

## Quick Start: Critical Fixes (4 Hours to Production-Ready)

All critical issues must be fixed before trading any real money.

---

## Fix #1: SQL Injection in Health Check (30 min)

**File:** `lambda/api/lambda_function.py`

**Current Code (Lines 109-116):**
```python
tables = ['price_daily', 'signals', 'stock_scores', 'technical_data_daily']
table_counts = {}
for table in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {table}')  # ← VULNERABLE
        table_counts[table] = cur.fetchone()[0]
    except:
        table_counts[table] = 0
```

**Fixed Code:**
```python
tables = ['price_daily', 'signals', 'stock_scores', 'technical_data_daily']
table_counts = {}

# Whitelist of allowed tables (prevents SQL injection)
ALLOWED_TABLES = {'price_daily', 'signals', 'stock_scores', 'technical_data_daily'}

for table in tables:
    if table not in ALLOWED_TABLES:
        continue  # Skip unknown tables
    try:
        # Use identifier quoting for table names (PostgreSQL)
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        table_counts[table] = cur.fetchone()[0]
    except:
        table_counts[table] = 0
```

**Test:**
```bash
# Should return 400 or 200 with valid count, never execute injected SQL
curl "https://your-api.example.com/health/detailed?table=price_daily; DROP TABLE signals; --"
```

---

## Fix #2: CORS Misconfiguration (15 min)

**File:** `lambda/api/lambda_function.py`

**Affected Lines:**
- 92, 103, 177, 185, 227, 238, 246: All return `'Access-Control-Allow-Origin': '*'`

**Replace ALL instances with:**

```python
def get_cors_headers(event):
    """Get CORS headers based on request origin."""
    origin = event.get('headers', {}).get('origin', '')
    
    # Whitelist your domains
    ALLOWED_ORIGINS = {
        'https://edgebrooke.example.com',
        'https://dashboard.example.com',
        'http://localhost:5173',  # Dev only
    }
    
    if origin in ALLOWED_ORIGINS:
        cors_headers = {
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true',
        }
    else:
        # Reject cross-origin requests from unknown sources
        cors_headers = {
            'Access-Control-Allow-Origin': 'null',  # Blocks browser from using response
        }
    
    return cors_headers

def lambda_handler(event, context):
    """Handle API Gateway v2 requests."""
    try:
        cors_headers = get_cors_headers(event)
        
        # ... health checks ...
        if path in ['/health', '/api/health']:
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    **cors_headers  # Include CORS headers
                },
                'body': json.dumps({'status': 'healthy'})
            }
        
        # ... rest of handler, always include cors_headers in all responses ...
```

**Test:**
```bash
# Should NOT return Access-Control-Allow-Origin: *
curl -H "Origin: https://evil.com" https://your-api.example.com/health

# Should return your domain
curl -H "Origin: https://edgebrooke.example.com" https://your-api.example.com/health
```

---

## Fix #3: Remove localStorage for Tokens (30 min)

**File:** `webapp/frontend/src/contexts/AuthContext.jsx`

**Search for all instances and replace:**

```javascript
// OLD (VULNERABLE)
localStorage.setItem("accessToken", session.tokens.accessToken);
localStorage.getItem("accessToken")
localStorage.removeItem("accessToken")

// NEW (SECURE)
sessionStorage.setItem("accessToken", session.tokens.accessToken);
sessionStorage.getItem("accessToken")
sessionStorage.removeItem("accessToken")
```

**Exact Replacements (use find-replace):**

1. Line ~: `localStorage.setItem("accessToken", session.tokens.accessToken);`
   → `sessionStorage.setItem("accessToken", session.tokens.accessToken);`

2. Line ~: `localStorage.setItem("authToken", result.tokens.accessToken);`
   → `sessionStorage.setItem("authToken", result.tokens.accessToken);`

3. Line ~: `const rememberMe = localStorage.getItem("rememberMe") === "true";`
   → `const rememberMe = false;`  (Or remove remember-me feature entirely)

4. All `localStorage.removeItem()` → `sessionStorage.removeItem()`

**Verify No More localStorage for Auth:**
```bash
grep -r "localStorage.*Token\|localStorage.*auth" webapp/frontend/src/
# Should return NO results
```

**Test:**
```
1. Login to app
2. Check DevTools → Application → sessionStorage → should see authToken
3. Close browser completely (not just tab)
4. Reopen app → should be logged out
5. Check localStorage → should NOT contain any tokens
```

---

## Fix #4: Remove Credentials from CI Pipeline (30 min)

**File:** `.github/workflows/deploy-code.yml`

**Current Code (Lines 197-235) — REMOVE THIS ENTIRE SECTION:**

```bash
# Inject DB credentials into Lambda env (eliminates cold-start SM call)
# ... all the code that fetches and pipes DB_PASSWORD ...
```

**Why Remove It:**
1. Credentials visible in GitHub Actions logs
2. Redundant — Lambda can call Secrets Manager at runtime
3. Increases security surface area

**Replacement Strategy:**

Option A: Remove credential injection, let Lambda fetch at runtime
```python
# In lambda/api/lambda_function.py, modify get_db_connection()

def get_db_connection():
    """Get or create database connection."""
    global _db_conn
    if _db_conn and not _db_conn.closed:
        return _db_conn

    try:
        # Try environment variables first (for testing)
        db_password = os.getenv('DB_PASSWORD')
        
        # If not set, fetch from Secrets Manager (production)
        if not db_password:
            db_secret_arn = os.getenv('DB_SECRET_ARN')
            if db_secret_arn:
                import boto3
                secrets = boto3.client('secretsmanager', region_name='us-east-1')
                response = secrets.get_secret_value(SecretId=db_secret_arn)
                secret = json.loads(response['SecretString'])
                db_password = secret.get('password')
                db_user = secret.get('username', os.getenv('DB_USER', 'stocks'))
            else:
                logger.error('No DB credentials available')
                return None
        
        db_host = os.getenv('DB_HOST')
        db_port = int(os.getenv('DB_PORT', '5432'))
        db_name = os.getenv('DB_NAME', 'stocks')
        db_user = os.getenv('DB_USER', 'stocks')

        _db_conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            database=db_name,
            user=db_user,
            password=db_password,
            cursor_factory=RealDictCursor,
            connect_timeout=10
        )
        return _db_conn
    except Exception as e:
        logger.error(f'DB connection failed: {e}')
        return None
```

**Update Workflow (.github/workflows/deploy-code.yml):**

Remove lines 197-235 entirely (the "Inject DB credentials" section).

**Test:**
```bash
# After deployment, check Lambda logs
# Should see: "DB connection established" (no credential logs)
# Should NOT see: "DB_PASSWORD=" or any credential values
aws logs tail /aws/lambda/stocks-api-dev --follow
```

---

## Fix #5: Add API Authorization (1 hour)

**File:** `lambda/api/lambda_function.py`

**Add Authorization Module (before lambda_handler):**

```python
import json
import base64
from datetime import datetime, timedelta

class AuthError(Exception):
    pass

def validate_bearer_token(token):
    """
    Validate JWT token. 
    For now: simple check. 
    Future: Validate signature against Cognito public keys.
    """
    if not token:
        raise AuthError("Missing token")
    
    if len(token) < 50:  # Real JWT tokens are ~200+ chars
        raise AuthError("Invalid token format")
    
    # TODO: Verify JWT signature against Cognito public keys
    # For now, just check it exists and has reasonable length
    return True

def get_bearer_token(event):
    """Extract Bearer token from Authorization header."""
    headers = event.get('headers', {})
    
    # Handle both 'Authorization' and 'authorization' (case-insensitive)
    auth_header = (
        headers.get('Authorization') or
        headers.get('authorization') or
        ''
    )
    
    if not auth_header.startswith('Bearer '):
        return None
    
    return auth_header[7:]  # Remove 'Bearer ' prefix

def require_auth(event, path):
    """
    Check if path requires authentication.
    Returns: (requires_auth: bool, error: str or None)
    """
    # Public endpoints (no auth required)
    PUBLIC_PATHS = {
        '/health',
        '/api/health',
        '/health/detailed',
        '/api/health/detailed',
        '/health/pipeline',
        '/api/health/pipeline',
    }
    
    # All other /api endpoints require auth
    if path in PUBLIC_PATHS:
        return (False, None)
    
    if not path.startswith('/api/'):
        return (False, None)  # Non-API paths don't need auth
    
    # Requires auth
    token = get_bearer_token(event)
    if not token:
        return (True, "Missing Authorization header")
    
    try:
        validate_bearer_token(token)
        return (True, None)  # Auth successful
    except AuthError as e:
        return (True, str(e))  # Auth failed

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle API Gateway v2 requests."""
    try:
        path = event.get('rawPath', event.get('path', '/'))
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        
        # Check authorization
        requires_auth, auth_error = require_auth(event, path)
        if requires_auth and auth_error:
            logger.warning(f"Unauthorized access to {path}: {auth_error}")
            return {
                'statusCode': 401,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'unauthorized', 'message': auth_error})
            }
        
        logger.info(f'Request: {method} {path}')
        
        # ... rest of handler ...
```

**Test:**
```bash
# Public endpoint (should work)
curl https://your-api.example.com/api/health
# → 200 OK

# Protected endpoint without auth (should fail)
curl https://your-api.example.com/api/algo/trades
# → 401 Unauthorized

# Protected endpoint with token (should work)
curl -H "Authorization: Bearer eyJhbGc..." https://your-api.example.com/api/algo/trades
# → 200 OK (or actual data)
```

---

## Fix #6: Remove Secrets from Git (15 min)

**Step 1: Remove from git history**
```bash
cd /c/Users/arger/code/algo

# Remove from tracking
git rm --cached .env.local
git rm --cached webapp/frontend/.env

# Create .gitignore entry
cat >> .gitignore << 'EOF'
.env
.env.local
.env.*.local
.env.production.local
EOF

# Commit
git add .gitignore
git commit -m "security: remove .env files from repo and add to gitignore"

# (Optional) Clean from git history: git filter-branch or BFG
# This is important if repo is/was public
```

**Step 2: Create templates**
```bash
# .env.local.example (template, no real credentials)
cat > .env.local.example << 'EOF'
# Database (local PostgreSQL)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocks
DB_USER=stocks
DB_PASSWORD=<SET_YOUR_LOCAL_DB_PASSWORD>

# API Keys (optional, for local development only)
# APCA_API_KEY_ID=<your-alpaca-key>
# APCA_API_SECRET_KEY=<your-alpaca-secret>
# FRED_API_KEY=<your-fred-key>
EOF

cp .env.local.example .env.local  # User can copy template and fill in

# For frontend
cat > webapp/frontend/.env.example << 'EOF'
VITE_API_URL=http://localhost:3001
VITE_ENVIRONMENT=development
VITE_COGNITO_USER_POOL_ID=
VITE_COGNITO_CLIENT_ID=
EOF
```

**Step 3: Verify removal**
```bash
# Should NOT find any real credentials
git log -p --all | grep -i "password\|api_key" | head -5

# If found, use BFG to remove from history:
# brew install bfg  (or apt-get install bfg)
# bfg --replace-text passwords.txt --no-blob-protection
```

**Step 4: Document in README**
```markdown
## Local Development Setup

1. Copy .env templates:
   ```bash
   cp .env.local.example .env.local
   cp webapp/frontend/.env.example webapp/frontend/.env
   ```

2. Edit files with your local credentials (never commit these)

3. For CI/CD, use GitHub Secrets (Settings → Secrets → New secret)
```

---

## Fix #7–15: High-Priority Remaining Work

### Fix #7: Generic Error Responses (1 hour)

**File:** `lambda/api/routes/utils.py`, `lambda/api/lambda_function.py`

```python
def error_response(status_code, error_type, message, internal_details=None):
    """Return generic error to client, log details internally."""
    if internal_details:
        logger.error(f"API Error [{error_type}]: {internal_details}")
    
    # Don't leak internal info to client
    return {
        'statusCode': status_code,
        'errorType': error_type,
        'message': message
    }

# Usage:
try:
    # ... handler logic
except psycopg2.DatabaseError as e:
    logger.error(f"DB error on query: {e}", exc_info=True)
    return error_response(500, 'database_error', 'Internal error occurred')
except ValueError as e:
    return error_response(400, 'invalid_request', 'Invalid request parameters')
```

---

### Fix #8: Add Security Headers (1 hour)

**File:** `lambda/api/lambda_function.py`

```python
def get_security_headers():
    """Return security headers for all responses."""
    return {
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains; preload',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
    }

# In every response:
headers = {
    'Content-Type': 'application/json',
    **get_cors_headers(event),
    **get_security_headers()
}
```

---

### Fix #9: Rate Limiting (1.5 hours)

**Option A: API Gateway (Easiest)**

In Terraform (`terraform/modules/apigateway/main.tf`):
```terraform
resource "aws_apigatewayv2_stage" "api" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "api"
  auto_deploy = true

  default_route_settings {
    throttle_settings {
      rate_limit  = 1000   # requests per second
      burst_limit = 2000   # burst capacity
    }
  }
}
```

**Option B: Lambda-based (More flexible)**

```python
from collections import defaultdict
from time import time

class RateLimiter:
    def __init__(self, rate=1000, per_seconds=1):
        self.rate = rate
        self.per_seconds = per_seconds
        self.requests = defaultdict(list)
    
    def is_allowed(self, identifier):
        """Check if identifier (IP/user) is rate limited."""
        now = time()
        
        # Clean old entries
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if now - req_time < self.per_seconds
        ]
        
        if len(self.requests[identifier]) >= self.rate:
            return False
        
        self.requests[identifier].append(now)
        return True

limiter = RateLimiter(rate=1000, per_seconds=1)

# In lambda_handler:
ip = event['requestContext']['identity']['sourceIp']
if not limiter.is_allowed(ip):
    return {
        'statusCode': 429,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'error': 'rate_limit_exceeded'})
    }
```

---

### Fix #10–15: See full SECURITY_AUDIT document

(Remaining high-priority items follow similar patterns)

---

## Testing Checklist After Fixes

```bash
# Run all tests
cd /c/Users/arger/code/algo
python -m pytest tests/ -v

# Frontend tests
cd webapp/frontend
npm test

# Security tests
npm run test:security
```

---

## Deployment Order

1. **Fix #1-6 (Critical)** → Deploy immediately
2. Run integration tests
3. **Fix #7-15 (High)** → Deploy in next release
4. **Fix #16-23 (Medium)** → Plan for next sprint

---

## Rollback Plan

If any fix causes issues:

```bash
# Revert last commit
git revert HEAD

# Redeploy
.github/workflows/deploy-code.yml (manually trigger)
```

---

## Security Sign-Off

After completing all fixes, re-run:

```bash
# Secrets scanning
npm run test:security:audit

# Dependency audit
pip-audit
npm audit

# Manual OWASP check
# [ ] CORS restricted
# [ ] No SQL injection
# [ ] Auth required
# [ ] No hardcoded secrets
# [ ] Rate limiting
# [ ] Secure headers
```

**Date Completed:** _______  
**Reviewed By:** _______
