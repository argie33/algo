# Auth System — Comprehensive Scenario Testing

**Purpose:** Verify the auth system handles all edge cases, failure modes, and integration scenarios correctly.

**Status:** Testing in progress...

---

## Test Categories

### 1. Token & JWT Scenarios
### 2. Role Mapping & Group Scenarios  
### 3. Frontend-Backend Integration
### 4. State Management & Storage
### 5. Routing & Navigation
### 6. Error Recovery & Resilience
### 7. Dev/Test/Prod Mode Transitions
### 8. Admin Permission Boundaries
### 9. Security & Validation
### 10. Concurrent & Race Conditions

---

## Scenarios Being Tested

### Category 1: Token & JWT Scenarios

**1.1 - Missing cognito:groups in JWT**
- Scenario: JWT is valid but has no cognito:groups claim
- Expected: groups = [], role = 'user'
- Code check needed: apiKeyService.js line 38
- Status: ⏳ Testing

**1.2 - Malformed idToken in frontend**
- Scenario: idToken is not a valid JWT (wrong format, missing dots)
- Expected: extractGroupsFromIdToken catches error, returns {groups: [], role: 'user'}
- Code check needed: AuthContext.jsx lines 46-59
- Status: ⏳ Testing

**1.3 - Token expiration during request**
- Scenario: Token expires between frontend request and backend processing
- Expected: Backend returns 401, frontend should trigger refresh
- Code check needed: auth.js authenticateTokenAsync, AuthContext refresh logic
- Status: ⏳ Testing

**1.4 - Empty groups array in JWT**
- Scenario: cognito:groups: [] (present but empty)
- Expected: role = 'user' (no admin)
- Code check needed: apiKeyService.js line 39
- Status: ⏳ Testing

**1.5 - Multiple groups including admin**
- Scenario: cognito:groups: ['user', 'admin', 'developers']
- Expected: role = 'admin' (includes('admin') check)
- Code check needed: apiKeyService.js line 39
- Status: ⏳ Testing

**1.6 - Groups with different casing**
- Scenario: cognito:groups: ['Admin'] or ['ADMIN']
- Expected: role = 'user' (case-sensitive check)
- Code check needed: apiKeyService.js line 39
- Status: ⏳ Testing

**1.7 - CognitoJwtVerifier fails to initialize**
- Scenario: Missing COGNITO_USER_POOL_ID or COGNITO_CLIENT_ID
- Expected: getVerifier() throws error, caught by validateJwtToken
- Code check needed: apiKeyService.js lines 10-26
- Status: ⏳ Testing

**1.8 - JWT verification signature failure**
- Scenario: Token signed with different key or tampered
- Expected: getVerifier().verify() throws, caught, returns {valid: false}
- Code check needed: apiKeyService.js lines 54-59
- Status: ⏳ Testing

---

### Category 2: Role Mapping & Group Scenarios

**2.1 - User without admin group tries admin endpoint**
- Scenario: User has groups: ['user'], attempts GET /api/diagnostics/
- Expected: 403 Insufficient Permissions
- Code check needed: requireRole middleware, user.role check
- Status: ⏳ Testing

**2.2 - Admin user accesses regular endpoint**
- Scenario: Admin attempts GET /api/portfolio/manual-positions
- Expected: 200 OK (admin is authenticated)
- Code check needed: requireAuth only (no role check)
- Status: ⏳ Testing

**2.3 - User role changes in Cognito mid-session**
- Scenario: User logged in as regular user, then admin adds them to admin group
- Expected: Role stays 'user' until token refresh/relogin
- Code check needed: AuthContext extracts role at LOGIN_SUCCESS, not live
- Status: ⏳ Testing

**2.4 - Dev mode vs Cognito role conflict**
- Scenario: NODE_ENV=development (role='admin') vs real token (role='user')
- Expected: Dev mode takes precedence (authenticateToken middleware path 1 checked first)
- Code check needed: auth.js lines 12-24 before other paths
- Status: ⏳ Testing

**2.5 - Role claim missing entirely from JWT**
- Scenario: validateJwtToken extracts groups, groups empty, sets role='user'
- Expected: Works correctly, user treated as regular user
- Code check needed: apiKeyService.js line 39 (groups.includes defaults to false)
- Status: ⏳ Testing

---

### Category 3: Frontend-Backend Integration

**3.1 - Frontend says admin, backend says user (role mismatch)**
- Scenario: Frontend has stale role from older JWT
- Expected: Backend returns 403, frontend should refresh token
- Code check needed: Backend requireAdmin enforces role check
- Status: ⏳ Testing

**3.2 - Frontend redirects to /login, modal doesn't open**
- Scenario: ProtectedRoute redirects to /login but LoginPage doesn't open modal
- Expected: LoginPage useEffect opens modal on mount
- Code check needed: LoginPage.jsx line with setAuthModalOpen(true)
- Status: ⏳ Testing

**3.3 - User closes auth modal on /login**
- Scenario: User navigates to /login, opens modal, then closes it
- Expected: Redirects back to home
- Code check needed: LoginPage.jsx handleAuthModalClose
- Status: ⏳ Testing

**3.4 - User logs in successfully**
- Scenario: Full login flow: modal → authenticate → role extracted → redirect
- Expected: User redirected to /app/portfolio (or ?from= param)
- Code check needed: LoginPage.jsx useEffect line 25
- Status: ⏳ Testing

**3.5 - Authorization header missing on API call**
- Scenario: Frontend makes API request without Authorization header
- Expected: Backend returns 401 MISSING_AUTHORIZATION
- Code check needed: auth.js lines 138-143
- Status: ⏳ Testing

**3.6 - Authorization header malformed**
- Scenario: Authorization: "InvalidFormat token" (missing Bearer)
- Expected: Backend returns 401 INVALID_TOKEN_FORMAT (test mode)
- Code check needed: auth.js line 47 Bearer check
- Status: ⏳ Testing

---

### Category 4: State Management & Storage

**4.1 - localStorage cleared while user logged in**
- Scenario: User clears localStorage manually or browser privacy mode
- Expected: Next page reload detects no session, AuthContext initializes to logged out
- Code check needed: AuthContext checkAuthState, localStorage.getItem
- Status: ⏳ Testing

**4.2 - Token stored in localStorage correctly**
- Scenario: After login, token should be persisted
- Expected: localStorage.setItem("accessToken") called
- Code check needed: AuthContext.jsx line 248
- Status: ⏳ Testing

**4.3 - Token cleared on logout**
- Scenario: User logs out
- Expected: localStorage removed, sessionStorage cleared, state reset
- Code check needed: auth.js LOGOUT action lines 95-100
- Status: ⏳ Testing

**4.4 - Session persists across page reload**
- Scenario: User logs in, refresh page
- Expected: Token in storage, AuthContext restores session
- Code check needed: AuthContext.jsx checkAuthState useEffect
- Status: ⏳ Testing

**4.5 - User object accessible throughout component tree**
- Scenario: Any component calls useAuth() to get user data
- Expected: user.role, user.groups, user.isAdmin available
- Code check needed: AuthContext.jsx useAuth hook and value spread
- Status: ⏳ Testing

---

### Category 5: Routing & Navigation

**5.1 - User navigates to /app/portfolio without auth**
- Scenario: Direct URL access to protected route
- Expected: ProtectedRoute checks isAuthenticated=false, redirects to /login
- Code check needed: ProtectedRoute.jsx line 17
- Status: ⏳ Testing

**5.2 - User navigates to /app/health without admin role**
- Scenario: Authenticated user (role='user') goes to /app/health
- Expected: ProtectedRoute checks requireRole="admin", redirects to /app/markets
- Code check needed: ProtectedRoute.jsx lines 22-26
- Status: ⏳ Testing

**5.3 - User navigates to /login while already authenticated**
- Scenario: Already logged in, manually goes to /login
- Expected: LoginPage useEffect detects isAuthenticated, redirects to /app/portfolio
- Code check needed: LoginPage.jsx lines 23-26
- Status: ⏳ Testing

**5.4 - ?from= parameter in /login URL**
- Scenario: ProtectedRoute redirects to /login?from=/app/trades
- Expected: LoginPage reads from param, redirects there after login
- Code check needed: LoginPage.jsx line 18 URLSearchParams
- Status: ⏳ Testing

**5.5 - Public routes accessible without auth**
- Scenario: User accesses /app/markets without logging in
- Expected: Route renders (no ProtectedRoute wrapper)
- Code check needed: App.jsx routes not wrapped for markets
- Status: ⏳ Testing

**5.6 - Deep link to protected route**
- Scenario: User receives link to /app/optimizer, clicks while logged out
- Expected: Redirects to /login?from=/app/optimizer, then back to optimizer after login
- Code check needed: ProtectedRoute redirect logic
- Status: ⏳ Testing

---

### Category 6: Error Recovery & Resilience

**6.1 - Cognito service unavailable**
- Scenario: CognitoJwtVerifier.verify() times out or AWS is down
- Expected: Error caught, returns {valid: false, error: message}, backend returns 401
- Code check needed: apiKeyService.js try-catch block
- Status: ⏳ Testing

**6.2 - COGNITO_USER_POOL_ID not set in production**
- Scenario: Lambda deployed without COGNITO_USER_POOL_ID env var
- Expected: environment.js validation throws error on startup
- Code check needed: environment.js validateEnvironment() function
- Status: ⏳ Testing

**6.3 - JWT_SECRET not set in test environment**
- Scenario: NODE_ENV=test but JWT_SECRET missing
- Expected: handleTestAuth returns 500 MISSING_JWT_SECRET
- Code check needed: auth.js lines 95-100
- Status: ⏳ Testing

**6.4 - Invalid JWT causes middleware error**
- Scenario: malformed token causes exception in getVerifier().verify()
- Expected: Error caught, returns 401 INVALID_CREDENTIALS
- Code check needed: apiKeyService.js catch block line 54
- Status: ⏳ Testing

**6.5 - Database down during role check**
- Scenario: Hypothetically, if role was checked against DB (it's not, it's in JWT)
- Expected: N/A - role is from JWT, not DB, so DB state doesn't matter
- Code check needed: Confirm role comes from JWT, not database
- Status: ⏳ Testing

---

### Category 7: Dev/Test/Prod Mode Transitions

**7.1 - NODE_ENV=development behavior**
- Scenario: Server started with NODE_ENV=development
- Expected: authenticateToken returns admin user immediately, no token validation
- Code check needed: auth.js line 12 check comes first
- Status: ⏳ Testing

**7.2 - NODE_ENV=test behavior**
- Scenario: Tests run with NODE_ENV=test
- Expected: Uses handleTestAuth, accepts test-token/admin-token
- Code check needed: auth.js line 27 check
- Status: ⏳ Testing

**7.3 - NODE_ENV=production behavior**
- Scenario: Production deployment with NODE_ENV=production
- Expected: Uses authenticateTokenAsync, real Cognito JWT validation
- Code check needed: auth.js line 32 fallthrough to authenticateTokenAsync
- Status: ⏳ Testing

**7.4 - Switching NODE_ENV requires restart**
- Scenario: Change NODE_ENV at runtime without restart
- Expected: New requests still use old path (because it's set at startup)
- Code check needed: NODE_ENV is read at request time, so changes apply immediately
- Status: ⏳ Testing (note: this might be a design decision to document)

**7.5 - NODE_ENV case sensitivity**
- Scenario: NODE_ENV=Development vs NODE_ENV=development
- Expected: Case-sensitive check, only 'development' matches
- Code check needed: auth.js line 12 === 'development'
- Status: ⏳ Testing

**7.6 - Unknown NODE_ENV value**
- Scenario: NODE_ENV=staging (not development, test, or production)
- Expected: Falls through to authenticateTokenAsync (production path)
- Code check needed: No explicit production check, just fallthrough
- Status: ⏳ Testing

---

### Category 8: Admin Permission Boundaries

**8.1 - All sensitive endpoints protected**
- Scenario: Enumerate all endpoints that should be admin-only
- Expected: Each has requireAuth, requireAdmin
- Code check needed: Verify all 14 endpoints in validation report
- Status: ⏳ Testing

**8.2 - No accidentally public admin endpoints**
- Scenario: Search for all routes that aren't protected but should be
- Expected: None found
- Code check needed: grep for router.get/post without authenticateToken
- Status: ⏳ Testing

**8.3 - Cannot elevate user to admin from frontend**
- Scenario: User tries to set user.role='admin' in browser console
- Expected: Frontend sends token to backend, backend extracts role from JWT (can't be spoofed)
- Code check needed: Backend requires valid Cognito JWT, not frontend user object
- Status: ⏳ Testing

**8.4 - Cannot create fake Cognito JWT**
- Scenario: User tries to create JWT with admin groups
- Expected: CognitoJwtVerifier validates signature against AWS JWKS, forged token fails
- Code check needed: CognitoJwtVerifier signature validation
- Status: ⏳ Testing

**8.5 - Test tokens can't be used in production**
- Scenario: test-token used with NODE_ENV=production
- Expected: CognitoJwtVerifier verification fails (not a real Cognito token)
- Code check needed: Only dev/test modes accept test tokens, production uses real verification
- Status: ⏳ Testing

---

### Category 9: Security & Validation

**9.1 - SQL injection via user claims**
- Scenario: JWT contains malicious SQL in username claim
- Expected: Not a risk - user data only used in auth checks (role/groups), not SQL queries
- Code check needed: Confirm username only used for req.user object, not queries
- Status: ⏳ Testing

**9.2 - XSS via user claims in frontend**
- Scenario: JWT contains <script> tag in email claim
- Expected: React escapes HTML, rendered safely
- Code check needed: user.email displayed in UI gets escaped by React
- Status: ⏳ Testing

**9.3 - Token replay attack**
- Scenario: Attacker captures token and replays old request
- Expected: If token is valid, request succeeds (correct behavior - token is proof of auth)
- Code check needed: Token validity checked, revocation not needed (short-lived tokens)
- Status: ⏳ Testing

**9.4 - CSRF protection**
- Scenario: Cross-site form submission
- Expected: Not a concern for API endpoints (token in header, not cookie)
- Code check needed: Authorization header required, not cookie-based
- Status: ⏳ Testing

**9.5 - Rate limiting by user**
- Scenario: rateLimitByUser middleware applied to endpoints
- Expected: Limits requests per user per minute
- Code check needed: middleware/auth.js rateLimitByUser function exists
- Status: ⏳ Testing

---

### Category 10: Concurrent & Race Conditions

**10.1 - Multiple simultaneous requests with different auth states**
- Scenario: Request 1 (user), Request 2 (admin) in parallel
- Expected: Each request's req.user set independently, no cross-contamination
- Code check needed: req.user is request-scoped, not global
- Status: ⏳ Testing

**10.2 - Token refresh during in-flight request**
- Scenario: Token refreshes while previous request still processing
- Expected: Request completes with old token (valid at time of auth)
- Code check needed: Per-request validation, not global state
- Status: ⏳ Testing

**10.3 - Login completes while logout in progress**
- Scenario: User logs out, but before localStorage clears, new login happens
- Expected: Final state should be either logged in (new) or logged out (old), not mixed
- Code check needed: AuthContext reducer handles atomicity of state updates
- Status: ⏳ Testing

**10.4 - Page navigation while token validation in progress**
- Scenario: User navigates to /app/health while authenticateTokenAsync still checking auth
- Expected: ProtectedRoute shows loading state, waits for auth check to complete
- Code check needed: ProtectedRoute.jsx isLoading check lines 8-14
- Status: ⏳ Testing

---

## Summary Table

| Category | Scenarios | Status |
|----------|-----------|--------|
| 1. Token & JWT | 8 | ⏳ Testing |
| 2. Role Mapping | 5 | ⏳ Testing |
| 3. Frontend-Backend | 6 | ⏳ Testing |
| 4. State Management | 5 | ⏳ Testing |
| 5. Routing & Nav | 6 | ⏳ Testing |
| 6. Error Recovery | 5 | ⏳ Testing |
| 7. Dev/Test/Prod | 6 | ⏳ Testing |
| 8. Admin Boundaries | 5 | ⏳ Testing |
| 9. Security | 5 | ⏳ Testing |
| 10. Concurrency | 4 | ⏳ Testing |
| **TOTAL** | **60** | **⏳ IN PROGRESS** |

---

## Test Results & Issues Found

(To be filled in as each scenario is tested)

