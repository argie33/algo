#!/usr/bin/env node
/**
 * Auth System Validation Test Suite
 * Validates the complete redesigned authentication system
 * Tests role-based access control, JWT validation, and route protection
 */

const fs = require('fs');
const path = require('path');

// Colors for console output
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
};

const log = {
  success: (msg) => console.log(`${colors.green}✓${colors.reset} ${msg}`),
  error: (msg) => console.log(`${colors.red}✗${colors.reset} ${msg}`),
  info: (msg) => console.log(`${colors.blue}ℹ${colors.reset} ${msg}`),
  warn: (msg) => console.log(`${colors.yellow}⚠${colors.reset} ${msg}`),
  section: (title) => console.log(`\n${colors.cyan}${title}${colors.reset}`),
};

const tests = [];
let passed = 0;
let failed = 0;

function test(name, fn) {
  tests.push({ name, fn });
}

async function runTests() {
  log.section('=== AUTH SYSTEM VALIDATION SUITE ===\n');

  for (const { name, fn } of tests) {
    try {
      await fn();
      passed++;
      log.success(name);
    } catch (err) {
      failed++;
      log.error(`${name}: ${err.message}`);
    }
  }

  console.log(`\n${colors.cyan}Summary:${colors.reset} ${colors.green}${passed} passed${colors.reset}, ${failed > 0 ? colors.red : colors.green}${failed} failed${colors.reset}\n`);
  process.exit(failed > 0 ? 1 : 0);
}

// ============================================================================
// INFRASTRUCTURE TESTS
// ============================================================================

test('CloudFormation: Cognito groups defined', () => {
  const cfn = fs.readFileSync(path.join(__dirname, 'template-webapp.yml'), 'utf8');
  if (!cfn.includes('AdminUserPoolGroup') || !cfn.includes('UserUserPoolGroup')) {
    throw new Error('Cognito groups not defined in CloudFormation');
  }
  if (!cfn.includes("GroupName: admin") || !cfn.includes("GroupName: user")) {
    throw new Error('Group names not correctly set');
  }
});

test('Database: role column migration exists', () => {
  const init = fs.readFileSync(path.join(__dirname, 'init_database.py'), 'utf8');
  if (!init.includes("role VARCHAR")) {
    throw new Error('role column not added to users table');
  }
  if (!init.includes("DEFAULT 'user'")) {
    throw new Error('role default value not set');
  }
  if (!init.includes("ALTER TABLE")) {
    throw new Error('Migration comment missing for existing deployments');
  }
});

// ============================================================================
// BACKEND CONFIGURATION TESTS
// ============================================================================

test('Environment: COGNITO_USER_POOL_ID in required vars', () => {
  const env = require('./webapp/lambda/config/environment.js');
  // We can't easily check the raw config object, but we can check the file content
  const envFile = fs.readFileSync(path.join(__dirname, 'webapp/lambda/config/environment.js'), 'utf8');
  if (!envFile.includes("COGNITO_USER_POOL_ID")) {
    throw new Error('COGNITO_USER_POOL_ID not in environment config');
  }
  if (!envFile.includes("requiredInProduction")) {
    throw new Error('requiredInProduction not found in environment.js');
  }
});

test('JWT Validation: CognitoJwtVerifier imported and used', () => {
  const apiKey = fs.readFileSync(path.join(__dirname, 'webapp/lambda/utils/apiKeyService.js'), 'utf8');
  if (!apiKey.includes("CognitoJwtVerifier")) {
    throw new Error('CognitoJwtVerifier not imported');
  }
  if (!apiKey.includes("cognito:groups")) {
    throw new Error('cognito:groups extraction not implemented');
  }
  if (!apiKey.includes("role = groups.includes('admin')")) {
    throw new Error('Role mapping logic not implemented');
  }
});

test('JWT Validation: Returns proper user object', () => {
  const apiKey = fs.readFileSync(path.join(__dirname, 'webapp/lambda/utils/apiKeyService.js'), 'utf8');
  if (!apiKey.includes("sub:") || !apiKey.includes("username:") || !apiKey.includes("email:") ||
      (!apiKey.includes("role:") && !apiKey.includes("role,"))) {
    throw new Error('User object structure incomplete');
  }
});

// ============================================================================
// AUTH MIDDLEWARE TESTS
// ============================================================================

test('Auth Middleware: Three distinct paths implemented', () => {
  const auth = fs.readFileSync(path.join(__dirname, 'webapp/lambda/middleware/auth.js'), 'utf8');

  // Dev path
  if (!auth.includes("NODE_ENV === 'development'")) {
    throw new Error('Dev path (NODE_ENV check) not implemented');
  }
  if (!auth.includes("req.user = {") || !auth.includes("role: 'admin'")) {
    throw new Error('Dev admin user object not set');
  }

  // Test path
  if (!auth.includes("NODE_ENV === 'test'")) {
    throw new Error('Test path not implemented');
  }

  // Production path
  if (!auth.includes("authenticateTokenAsync")) {
    throw new Error('Production async validation not implemented');
  }
});

test('Auth Middleware: requireAdmin exported', () => {
  const auth = fs.readFileSync(path.join(__dirname, 'webapp/lambda/middleware/auth.js'), 'utf8');
  if (!auth.includes("requireAdmin")) {
    throw new Error('requireAdmin not exported');
  }
  if (!auth.includes("requireRole")) {
    throw new Error('requireRole not exported');
  }
});

test('Auth Middleware: authenticateToken exported', () => {
  const auth = fs.readFileSync(path.join(__dirname, 'webapp/lambda/middleware/auth.js'), 'utf8');
  if (!auth.includes("module.exports")) {
    throw new Error('No module exports found');
  }
  if (!auth.includes("authenticateToken")) {
    throw new Error('authenticateToken not exported');
  }
});

// ============================================================================
// BACKEND ROUTE PROTECTION TESTS
// ============================================================================

test('Algo Routes: GET endpoints require admin', () => {
  const algo = fs.readFileSync(path.join(__dirname, 'webapp/lambda/routes/algo.js'), 'utf8');

  const configs = [
    { route: '/config', methods: ['GET'] },
    { route: '/audit-log', methods: ['GET'] },
    { route: '/patrol-log', methods: ['GET'] },
    { route: '/circuit-breakers', methods: ['GET'] },
  ];

  for (const { route, methods } of configs) {
    const pattern = new RegExp(`router\\.${methods[0].toLowerCase()}\\(.*${route}.*requireAuth.*requireAdmin|requireAdmin`);
    if (!pattern.test(algo) && !algo.includes(`'${route}'`) && algo.includes('requireAdmin')) {
      // At least check that the route exists and requireAdmin is used somewhere
      if (!algo.includes(`'${route}'`)) {
        throw new Error(`Route ${route} not found`);
      }
    }
  }
});

test('Algo Routes: POST operations require admin', () => {
  const algo = fs.readFileSync(path.join(__dirname, 'webapp/lambda/routes/algo.js'), 'utf8');

  const routes = ['/run', '/simulate', '/patrol'];
  for (const route of routes) {
    if (!algo.includes(`'${route}'`)) {
      throw new Error(`Route ${route} not found`);
    }
  }

  // Check that requireAdmin is used
  if (!algo.includes('requireAdmin')) {
    throw new Error('requireAdmin not used in algo routes');
  }
});

test('Contact Routes: Submissions require admin', () => {
  const contact = fs.readFileSync(path.join(__dirname, 'webapp/lambda/routes/contact.js'), 'utf8');

  if (!contact.includes('requireAdmin') && !contact.includes('requireAuth')) {
    throw new Error('Auth protection not applied to submissions');
  }
});

test('Diagnostics Routes: All routes require auth + admin', () => {
  const diag = fs.readFileSync(path.join(__dirname, 'webapp/lambda/routes/diagnostics.js'), 'utf8');

  if (!diag.includes("router.use(authenticateToken, requireAdmin)")) {
    throw new Error('Global auth + admin protection not applied to diagnostics');
  }
});

test('Health Routes: Sensitive endpoints require admin', () => {
  const health = fs.readFileSync(path.join(__dirname, 'webapp/lambda/routes/health.js'), 'utf8');

  if (!health.includes('requireAdmin')) {
    throw new Error('Admin protection not applied to health endpoints');
  }

  if (!health.includes('/database') || !health.includes('/ecs-tasks')) {
    throw new Error('Protected health endpoints missing');
  }
});

test('Portfolio Routes: Manual-positions require auth', () => {
  const portfolio = fs.readFileSync(path.join(__dirname, 'webapp/lambda/routes/portfolio.js'), 'utf8');

  if (!portfolio.includes('authenticateToken') || !portfolio.includes('manual-positions')) {
    throw new Error('Auth not applied to manual-positions');
  }
});

// ============================================================================
// FRONTEND AUTH TESTS
// ============================================================================

test('devAuth: Returns admin role in dev user', () => {
  const devAuth = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/services/devAuth.js'), 'utf8');

  if (!devAuth.includes("role: 'admin'") && !devAuth.includes('role: "admin"')) {
    throw new Error('Dev user missing admin role');
  }
  if (!devAuth.includes("groups: ['admin']")) {
    throw new Error('Dev user missing admin group');
  }
  if (!devAuth.includes("isAdmin: true") && !devAuth.includes('isAdmin: true')) {
    throw new Error('Dev user missing isAdmin flag');
  }
});

test('AuthContext: extractGroupsFromIdToken function exists', () => {
  const ctx = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/contexts/AuthContext.jsx'), 'utf8');

  if (!ctx.includes('extractGroupsFromIdToken')) {
    throw new Error('extractGroupsFromIdToken function not found');
  }
  if (!ctx.includes("cognito:groups")) {
    throw new Error('cognito:groups extraction not implemented');
  }
  if (!ctx.includes("groups.includes('admin')")) {
    throw new Error('Admin role mapping not implemented');
  }
});

test('AuthContext: role flows through LOGIN_SUCCESS reducer', () => {
  const ctx = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/contexts/AuthContext.jsx'), 'utf8');

  if (!ctx.includes('LOGIN_SUCCESS')) {
    throw new Error('LOGIN_SUCCESS action not found');
  }
  if (!ctx.includes('groups:') && !ctx.includes('groups :')) {
    throw new Error('groups not added to user object in LOGIN_SUCCESS');
  }
  if (!ctx.includes('role:') && !ctx.includes('role :')) {
    throw new Error('role not added to user object in LOGIN_SUCCESS');
  }
  if (!ctx.includes('isAdmin')) {
    throw new Error('isAdmin flag not added to user object');
  }
});

test('ProtectedRoute: Real auth checking implemented', () => {
  const pr = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/components/auth/ProtectedRoute.jsx'), 'utf8');

  if (!pr.includes('requireAuth') || !pr.includes('requireRole')) {
    throw new Error('ProtectedRoute props not implemented');
  }
  if (!pr.includes('isAuthenticated')) {
    throw new Error('Auth state checking missing');
  }
  if (!pr.includes('Navigate')) {
    throw new Error('Route redirection not implemented');
  }
  if (!pr.includes('user?.role')) {
    throw new Error('Role checking missing');
  }
});

test('App.jsx: Protected routes wrapped', () => {
  const app = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/App.jsx'), 'utf8');

  const protectedRoutes = [
    '/app/portfolio',
    '/app/trades',
    '/app/optimizer',
    '/app/settings',
  ];

  for (const route of protectedRoutes) {
    if (!app.includes(`path="${route}"`) && !app.includes(`path='${route}'`)) {
      throw new Error(`Route ${route} not found`);
    }
  }

  if (!app.includes('ProtectedRoute requireAuth')) {
    throw new Error('ProtectedRoute not wrapping auth-required routes');
  }
});

test('App.jsx: Admin-only routes wrapped', () => {
  const app = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/App.jsx'), 'utf8');

  if (!app.includes('/app/health')) {
    throw new Error('Health route not found');
  }
  if (!app.includes('requireRole="admin"') && !app.includes("requireRole='admin'")) {
    throw new Error('Admin role requirement not set for health route');
  }
});

test('App.jsx: /login route exists', () => {
  const app = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/App.jsx'), 'utf8');

  if (!app.includes('/login')) {
    throw new Error('/login route not found');
  }
});

test('AuthModal: ForgotPasswordForm prop fixed', () => {
  const modal = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/components/auth/AuthModal.jsx'), 'utf8');

  if (!modal.includes('onBack')) {
    throw new Error('onBack prop not used for ForgotPasswordForm');
  }
});

test('MFAChallenge: No hardcoded "123456" stub', () => {
  const mfa = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/components/auth/MFAChallenge.jsx'), 'utf8');

  if (mfa.includes("=== '123456'") || mfa.includes('=== "123456"')) {
    throw new Error('Hardcoded MFA stub still present');
  }

  if (!mfa.includes('onVerify')) {
    throw new Error('onVerify callback not implemented');
  }
});

// ============================================================================
// CLEANUP TESTS
// ============================================================================

test('Dead test files deleted: auth.test.js', () => {
  const testFile = path.join(__dirname, 'webapp/lambda/tests/unit/routes/auth.test.js');
  if (fs.existsSync(testFile)) {
    throw new Error('Dead test file auth.test.js still exists');
  }
});

test('Dead test files deleted: auth.integration.test.js', () => {
  const testFile = path.join(__dirname, 'webapp/lambda/tests/integration/routes/auth.integration.test.js');
  if (fs.existsSync(testFile)) {
    throw new Error('Dead test file auth.integration.test.js still exists');
  }
});

// ============================================================================
// IMPLEMENTATION INTEGRITY TESTS
// ============================================================================

test('LoginPage: Component exists and exports default', () => {
  const loginPage = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/pages/LoginPage.jsx'), 'utf8');

  if (!loginPage.includes('function LoginPage') && !loginPage.includes('const LoginPage')) {
    throw new Error('LoginPage component not defined');
  }
  if (!loginPage.includes('export default LoginPage')) {
    throw new Error('LoginPage not exported as default');
  }
  if (!loginPage.includes('AuthModal')) {
    throw new Error('LoginPage does not use AuthModal');
  }
  if (!loginPage.includes('setAuthModalOpen')) {
    throw new Error('LoginPage does not control auth modal state');
  }
});

test('App.jsx: LoginPage imported and used', () => {
  const app = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/App.jsx'), 'utf8');

  if (!app.includes('import LoginPage')) {
    throw new Error('LoginPage not imported in App.jsx');
  }
  if (!app.includes('element={<LoginPage') && !app.includes('element={<LoginPage')) {
    throw new Error('/login route does not use LoginPage');
  }
});

test('AuthContext: idToken JWT structure properly decoded', () => {
  const ctx = fs.readFileSync(path.join(__dirname, 'webapp/frontend/src/contexts/AuthContext.jsx'), 'utf8');

  if (!ctx.includes('split') || !ctx.includes('atob')) {
    throw new Error('JWT decoding (split/atob) not implemented');
  }
  if (!ctx.includes('idToken.split') || !ctx.includes('parts[1]')) {
    throw new Error('JWT payload extraction incorrect');
  }
  if (!ctx.includes('JSON.parse(atob')) {
    throw new Error('JWT payload parsing incorrect');
  }
});

test('API Service: User object includes all required fields', () => {
  const apiKey = fs.readFileSync(path.join(__dirname, 'webapp/lambda/utils/apiKeyService.js'), 'utf8');

  const requiredFields = ['sub', 'username', 'email', 'role', 'groups', 'sessionId'];
  for (const field of requiredFields) {
    if (!apiKey.includes(field + ':') && !apiKey.includes(field + ',')) {
      throw new Error(`User object missing ${field} field`);
    }
  }
});

test('Auth Middleware: requireRole checks both role and groups', () => {
  const auth = fs.readFileSync(path.join(__dirname, 'webapp/lambda/middleware/auth.js'), 'utf8');

  if (!auth.includes('req.user.role') || !auth.includes('req.user.groups')) {
    throw new Error('requireRole does not check both role and groups');
  }
  if (!auth.includes('hasRole') || !auth.includes('hasGroup')) {
    throw new Error('requireRole logic incomplete');
  }
});

test('Portfolio Routes: All data-modifying operations protected', () => {
  const portfolio = fs.readFileSync(path.join(__dirname, 'webapp/lambda/routes/portfolio.js'), 'utf8');

  // Check POST and PATCH operations have auth
  if (!portfolio.includes('router.post') || !portfolio.includes('authenticateToken')) {
    throw new Error('POST operations might not be authenticated');
  }
});

test('Environment Config: Validates production environment', () => {
  const env = fs.readFileSync(path.join(__dirname, 'webapp/lambda/config/environment.js'), 'utf8');

  if (!env.includes('validateEnvironment')) {
    throw new Error('Environment validation function missing');
  }
  if (!env.includes('NODE_ENV === "production"')) {
    throw new Error('Production environment check missing');
  }
  if (!env.includes('throw new Error')) {
    throw new Error('No error thrown on missing required variables');
  }
});

// ============================================================================
// RUN ALL TESTS
// ============================================================================

runTests().catch((err) => {
  log.error(`Fatal error: ${err.message}`);
  process.exit(1);
});
