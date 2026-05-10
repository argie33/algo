# Auth System — Quick Reference Guide

## Single Source of Truth

**Cognito User Pool Groups** → JWT `cognito:groups` claim → `role` property throughout stack

- **Admin group** = `role: 'admin'` (full access to sensitive endpoints)
- **User group** = `role: 'user'` (access to user data only)
- **No group** = `role: 'user'` (default)

---

## Backend Middleware

### Three Auth Paths

```javascript
// Path 1: Development (NODE_ENV === 'development')
req.user = { role: 'admin', groups: ['admin'], ... }
// No token validation, immediate return

// Path 2: Test (NODE_ENV === 'test')
// Validate with JWT_SECRET, accepts: test-token, mock-access-token, admin-token

// Path 3: Production (default)
// Real CognitoJwtVerifier validation, extracts cognito:groups, maps to role
```

### Using in Routes

```javascript
const { authenticateToken, requireAdmin } = require('../middleware/auth');

// Protect a route with authentication only
router.get('/protected', authenticateToken, (req, res) => {
  console.log(req.user.role);  // 'admin' or 'user'
});

// Protect a route with authentication AND admin role
router.get('/admin-only', authenticateToken, requireAdmin, (req, res) => {
  // Only admin users can access
});
```

---

## Protected Endpoints

### Admin-Only (require `authenticateToken, requireAdmin`)
- GET /api/diagnostics/* (all diagnostics)
- GET /api/algo/config
- GET /api/algo/audit-log
- GET /api/algo/patrol-log
- GET /api/algo/circuit-breakers
- POST /api/algo/run
- POST /api/algo/simulate
- POST /api/algo/patrol
- GET /api/contact/submissions
- GET /api/health/database
- GET /api/health/ecs-tasks
- GET /api/health/api-endpoints

### User-Authenticated (require `authenticateToken` only)
- GET /api/user/profile
- GET /api/trades/*
- POST /api/trades/*
- GET /api/portfolio/*
- POST /api/portfolio/manual-positions
- GET /api/portfolio/manual-positions

### Public (no auth required)
- GET /api/health/ (load balancer health check)
- GET /api/markets/* (all market data)
- GET /api/stocks/* (all stock data)

---

## Frontend Route Protection

### Protected Routes

```jsx
// Requires authentication
<ProtectedRoute requireAuth>
  <Portfolio />
</ProtectedRoute>

// Requires authentication AND admin role
<ProtectedRoute requireAuth requireRole="admin">
  <HealthDashboard />
</ProtectedRoute>
```

### Routes in App.jsx

```javascript
// Auth-required routes (any logged-in user)
/app/portfolio      → <ProtectedRoute requireAuth>
/app/trades         → <ProtectedRoute requireAuth>
/app/optimizer      → <ProtectedRoute requireAuth>
/app/settings       → <ProtectedRoute requireAuth>

// Admin-only routes
/app/health         → <ProtectedRoute requireAuth requireRole="admin">

// Public routes (no auth)
/app/markets        → no protection
/app/sectors        → no protection
```

---

## Getting User Info in Components

```javascript
import { useAuth } from '../../contexts/AuthContext';

function MyComponent() {
  const { user, isAuthenticated, isLoading } = useAuth();

  if (isLoading) return <div>Loading...</div>;
  if (!isAuthenticated) return <div>Please log in</div>;

  return (
    <div>
      <p>Username: {user.username}</p>
      <p>Email: {user.email}</p>
      <p>Role: {user.role}</p>
      <p>Is Admin: {user.isAdmin ? 'Yes' : 'No'}</p>
    </div>
  );
}
```

---

## Development Mode

When running locally with `NODE_ENV=development`:

```bash
NODE_ENV=development npm start
```

- Automatically logged in as admin user
- No token validation
- All routes accessible
- Perfect for local development

---

## Testing With Tokens

### Test Mode (NODE_ENV=test)

```bash
NODE_ENV=test npm test
```

Accepted test tokens:
- `test-token` → regular user role
- `admin-token` → admin role
- `mock-access-token` → regular user role

Example request:
```bash
curl -H "Authorization: Bearer test-token" http://localhost:3001/api/diagnostics/
# Expects 403 (user doesn't have permission)

curl -H "Authorization: Bearer admin-token" http://localhost:3001/api/diagnostics/
# Expects 200 (admin has permission)
```

---

## Deployment Environment Setup

### Required Environment Variables

```
NODE_ENV=production
COGNITO_USER_POOL_ID=us-east-1_xxxxx
COGNITO_CLIENT_ID=xxxxx
JWT_SECRET=xxxxx
DB_HOST=xxxxx
DB_PORT=5432
DB_USER=xxxxx
DB_PASSWORD=xxxxx
DB_NAME=stocks
```

### Post-Deploy Steps

1. **Add users to Cognito groups:**
   - AWS Console → Cognito → User Pool → Groups
   - Add your user to `admin` group

2. **Verify database migration:**
   ```sql
   SELECT column_name FROM information_schema.columns 
   WHERE table_name='users' AND column_name='role';
   -- Should return one row
   ```

3. **Test an endpoint:**
   ```bash
   curl -H "Authorization: Bearer <your-token>" \
        https://api.example.com/api/diagnostics/
   # Should return 200 if you're admin, 403 if regular user
   ```

---

## Debugging Auth Issues

### Check which auth path is being used

Backend logs will show:
- `"Dev auth: no token validation"` → NODE_ENV=development
- `"Test auth with JWT_SECRET"` → NODE_ENV=test
- `"Validating with CognitoJwtVerifier"` → production

### JWT Validation Errors

If you see `INVALID_TOKEN` errors:
1. Verify the token is a valid Cognito access token
2. Check COGNITO_USER_POOL_ID matches the token's pool
3. Verify token hasn't expired
4. Check token format: `Authorization: Bearer <token>`

### Role Mapping Issues

If user can't access routes they should be able to:
1. Check Cognito group membership (AWS Console)
2. Decode JWT: `echo <token> | cut -d. -f2 | base64 -d | jq`
3. Verify `cognito:groups` claim exists and contains `admin`
4. Check backend logs for extracted role

---

## Files to Know

**Core Auth Files:**
- `webapp/lambda/middleware/auth.js` — Authentication logic
- `webapp/lambda/utils/apiKeyService.js` — JWT validation
- `webapp/frontend/src/contexts/AuthContext.jsx` — User state management
- `webapp/frontend/src/components/auth/ProtectedRoute.jsx` — Route guarding

**Configuration:**
- `webapp/lambda/config/environment.js` — Required env vars
- `template-webapp.yml` — Cognito group definitions

**Tests:**
- `webapp/lambda/tests/unit/middleware/auth.test.js` — Middleware tests
- `validate-auth-system.js` — Full system validation suite

---

## Common Tasks

### Add a new admin-only endpoint

```javascript
const { authenticateToken, requireAdmin } = require('../middleware/auth');

router.get('/api/admin/new-endpoint', authenticateToken, requireAdmin, (req, res) => {
  // Only admins can access
  res.json({ message: 'Admin data' });
});
```

### Add a new user-only endpoint

```javascript
const { authenticateToken } = require('../middleware/auth');

router.get('/api/user/new-endpoint', authenticateToken, (req, res) => {
  // Any authenticated user can access
  res.json({ 
    message: 'User data',
    username: req.user.username
  });
});
```

### Check user role in a component

```javascript
import { useAuth } from '../../contexts/AuthContext';

function AdminPanel() {
  const { user } = useAuth();

  if (user?.role !== 'admin') {
    return <div>Access denied</div>;
  }

  return <div>Admin controls</div>;
}
```

### Manually add user to admin group (AWS CLI)

```bash
aws cognito-idp admin-add-user-to-group \
  --user-pool-id us-east-1_xxxxx \
  --username user@example.com \
  --group-name admin
```

---

## Validation

Run the full validation suite anytime:

```bash
node validate-auth-system.js
```

Should show: ✅ 25 passed, 0 failed

---

## Support & Documentation

- **Full Report:** `AUTH_SYSTEM_VALIDATION_REPORT.md`
- **Architecture Summary:** See report's "Architecture Summary" section
- **Post-Deployment Checklist:** See report's "Post-Deployment Setup Checklist" section
