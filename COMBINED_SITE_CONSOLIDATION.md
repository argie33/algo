# Combined Site Consolidation & Endpoint Redesign
**Status:** IN PROGRESS (frontend-admin removed, but server config not updated)  
**Goal:** One unified frontend + clean API endpoints serving both admin & user features

---

## CURRENT STATE

### What's Done ✅
- `webapp/frontend-admin/` directory DELETED (good!)
- All admin pages moved to `webapp/frontend/src/pages/`
- Single frontend codebase now

### What's BROKEN 🔴
- `webapp/lambda/index.js` still references deleted `frontend-admin/dist-admin` path
- Server will crash trying to serve admin pages from non-existent directory
- Need to update server to serve everything from `frontend/dist`

### What Needs Work
1. Fix server routing (currently broken)
2. Design clean API endpoint structure for admin vs user
3. Ensure both admin and user pages work with single API
4. Clean up endpoint duplication

---

## ARCHITECTURE: UNIFIED FRONTEND + CLEAN API

### Current Problem (Why it's an "arch nightmare")

**Frontend:** ✅ Already consolidated (frontend-admin merged into frontend)

**API:** ❌ Broken architecture
```javascript
// WRONG: endpoints return data for EITHER admin OR user
GET /api/portfolio/metrics
  ├─ Returns: portfolio data (user page)
  ├─ Returns: portfolio data (admin page)
  ├─ Unclear who should see what
  └─ Duplication across endpoints

GET /api/diagnostics
  ├─ Should be admin-only
  ├─ But no auth check
  └─ User can access it
```

**Solution:** Namespace endpoints by audience

---

## CLEAN API STRUCTURE (One Right Way)

### User-Facing API
```javascript
GET /api/user/portfolio/metrics
GET /api/user/stocks/list
GET /api/user/trades/history
```

### Admin-Only API
```javascript
GET /api/admin/diagnostics
GET /api/admin/system/health
GET /api/admin/data/status
GET /api/admin/logs
```

### Shared API (Both use)
```javascript
GET /api/stocks/:symbol
GET /api/sectors
GET /api/market/data
```

### Result
- Clear separation: `user/*` vs `admin/*` vs shared
- Easy to add auth checks at namespace level
- No duplication
- Both frontends call same API with their own namespace

---

## IMPLEMENTATION STEPS

### Step 1: Fix Server Config (15 min)
**File:** `webapp/lambda/index.js`

**Current (BROKEN):**
```javascript
const adminBuildPath = path.join(__dirname, '../frontend-admin/dist-admin');
const userBuildPath = path.join(__dirname, '../frontend/dist');

app.use('/admin', express.static(adminBuildPath));
app.use('/', express.static(userBuildPath));
```

**Fixed:**
```javascript
const frontendPath = path.join(__dirname, '../frontend/dist');

// Single static serve - all routes handled by React Router
app.use(express.static(frontendPath));

// SPA fallback - routes not matching API go to index.html
app.get('*', (req, res) => {
  res.sendFile(path.join(frontendPath, 'index.html'));
});
```

**Why this works:**
- React Router handles `/`, `/admin`, `/user` routes in frontend
- Server just serves files, doesn't know about routes
- No duplication, clean separation

### Step 2: Redesign API Endpoints (30 min)

**Current state** (broken duplication):
```
Get /api/portfolio/metrics         (user data, admin also uses)
GET /api/diagnostics               (admin data, no auth)
GET /api/stocks                    (everyone uses)
```

**New structure** (clean):
```
/api/user/
  /portfolio/metrics               (user portfolio)
  /trades/history                  (user trades)
  /alerts                          (user alerts)

/api/admin/
  /diagnostics                     (admin only - add auth)
  /system/health                   (admin only - add auth)
  /data/status                     (admin only - add auth)
  /logs                            (admin only - add auth)

/api/shared/
  /stocks/:symbol                  (everyone)
  /sectors                         (everyone)
  /market/data                     (everyone)
  /technicals/:symbol              (everyone)
```

**Implementation:**
1. Create new routes: `/api/user/`, `/api/admin/`, `/api/shared/`
2. Move existing endpoints to correct namespace
3. Add `requireAdmin()` middleware to `/api/admin/*`
4. Update frontend API calls to use new paths

### Step 3: Update Frontend API Calls (20 min)

**Current (scattered):**
```javascript
// User pages use:
api.get('/api/portfolio/metrics')
api.get('/api/trades')

// Admin pages use:
api.get('/api/diagnostics')
api.get('/api/health')
```

**New (consistent):**
```javascript
// User pages use:
api.get('/api/user/portfolio/metrics')
api.get('/api/user/trades/history')

// Admin pages use:
api.get('/api/admin/diagnostics')
api.get('/api/admin/system/health')

// Both use:
api.get('/api/shared/stocks/:symbol')
api.get('/api/shared/sectors')
```

**Change in:** `webapp/frontend/src/services/api.js`
```javascript
export const api = {
  user: {
    portfolio: () => get('/api/user/portfolio/metrics'),
    trades: () => get('/api/user/trades/history'),
    // ... user endpoints
  },
  
  admin: {
    diagnostics: () => get('/api/admin/diagnostics'),
    health: () => get('/api/admin/system/health'),
    // ... admin endpoints
  },
  
  shared: {
    stocks: (symbol) => get(`/api/shared/stocks/${symbol}`),
    sectors: () => get('/api/shared/sectors'),
    // ... shared endpoints
  }
}
```

### Step 4: Add Admin Auth Middleware (10 min)

**File:** `webapp/lambda/utils/auth.js`
```javascript
function requireAdmin(req, res, next) {
  const userRole = req.user?.role; // from JWT token
  if (userRole !== 'admin') {
    return res.status(403).json({
      success: false,
      error: 'Admin access required'
    });
  }
  next();
}
```

**Usage in routes:**
```javascript
// Admin endpoints
router.get('/diagnostics', requireAdmin, (req, res) => {
  // Admin-only logic
});
```

### Step 5: Create API Namespace Structure (20 min)

**Create new route files:**
```
webapp/lambda/routes/
  user/
    portfolio.js      (user portfolio endpoints)
    trades.js         (user trade history)
    alerts.js         (user alerts)
    dashboard.js      (user dashboard data)
  
  admin/
    diagnostics.js    (system diagnostics)
    health.js         (system health)
    logs.js           (system logs)
    data.js           (data loading status)
  
  shared/
    stocks.js         (stock data for everyone)
    sectors.js        (sector data for everyone)
    technicals.js     (technical indicators for everyone)
    market.js         (market data for everyone)
```

**Mount in index.js:**
```javascript
// User API
app.use('/api/user', require('./routes/user/portfolio'));
app.use('/api/user', require('./routes/user/trades'));
// ... other user routes

// Admin API (all protected)
app.use('/api/admin', requireAdmin);
app.use('/api/admin', require('./routes/admin/diagnostics'));
app.use('/api/admin', require('./routes/admin/health'));
// ... other admin routes

// Shared API (no auth needed)
app.use('/api/shared', require('./routes/shared/stocks'));
app.use('/api/shared', require('./routes/shared/sectors'));
// ... other shared routes
```

### Step 6: Update Frontend Routing (10 min)

**File:** `webapp/frontend/src/App.jsx`

**Current structure:**
```javascript
<Routes>
  <Route path="/" element={<Dashboard />} />
  <Route path="/portfolio" element={<Portfolio />} />
  // No clear /admin path
</Routes>
```

**New structure:**
```javascript
<Routes>
  <Route path="/" element={<UserLayout />}>
    <Route path="" element={<Dashboard />} />
    <Route path="portfolio" element={<Portfolio />} />
    <Route path="trades" element={<TradeHistory />} />
  </Route>

  <Route path="/admin" element={<AdminLayout />}>
    <Route path="" element={<AdminDashboard />} />
    <Route path="diagnostics" element={<Diagnostics />} />
    <Route path="health" element={<Health />} />
    <Route path="logs" element={<Logs />} />
  </Route>
</Routes>
```

**Result:**
- `/` - User pages (calls `/api/user/*`)
- `/admin` - Admin pages (calls `/api/admin/*`)
- Both share common data (calls `/api/shared/*`)

---

## CLEANUP: Remove Duplication

### Duplicate API Routes to Consolidate
```
GET /api/portfolio/metrics         → Move to /api/user/portfolio/metrics
GET /api/stocks/:symbol            → Move to /api/shared/stocks/:symbol
GET /api/diagnostics               → Move to /api/admin/diagnostics
```

### Duplicate Code in Routes
- Multiple files calling same database queries
- Multiple files formatting same data
- Multiple files handling same errors

**Solution:** Move to shared utilities
```
webapp/lambda/utils/
  formatters.js      (format all responses)
  queries.js         (reusable database queries)
  validators.js      (input validation)
  middleware.js      (auth, error handling)
```

---

## EXECUTION PLAN

### Phase A: Server Fix (TODAY - 15 min)
```bash
# Step 1: Fix index.js server config
# Remove reference to frontend-admin
# Update to serve single frontend

# Verify: npm start → frontend loads on http://localhost:5174
```

### Phase B: API Redesign (TODAY - 1 hour)
```bash
# Step 1: Create /api/user, /api/admin, /api/shared structure
# Step 2: Move endpoints to correct namespaces
# Step 3: Add requireAdmin middleware
# Step 4: Update frontend api.js to use new paths
# Step 5: Test all endpoints

# Verify: Both user and admin pages load data correctly
```

### Phase C: Frontend Routing (TODAY - 30 min)
```bash
# Step 1: Update App.jsx with /admin route
# Step 2: Create UserLayout and AdminLayout wrappers
# Step 3: Move admin pages to /admin/* paths
# Step 4: Test navigation between user and admin areas

# Verify: Can navigate to / (user) and /admin (admin) pages
```

### Phase D: Consolidation & Cleanup (NEXT - 1 hour)
```bash
# Step 1: Delete old duplicate routes
# Step 2: Create shared utilities for common logic
# Step 3: Remove hardcoded paths and duplicated queries
# Step 4: Verify no broken endpoints

# Verify: All endpoints work, no 404s, no duplicates
```

---

## WHAT WILL WORK AFTER THIS

### User Can:
- ✅ See user dashboard (`/`)
- ✅ See portfolio (`/portfolio`)
- ✅ See trades (`/trades`)
- ✅ See stock details (`/stocks/AAPL`)
- ✅ Cannot access `/admin`

### Admin Can:
- ✅ See user pages if logged in as admin
- ✅ See admin dashboard (`/admin`)
- ✅ See diagnostics (`/admin/diagnostics`)
- ✅ See system health (`/admin/health`)
- ✅ See logs (`/admin/logs`)
- ✅ Cannot access user-only features

### Architecture:
- ✅ One unified frontend
- ✅ One clear API structure
- ✅ No duplicate endpoints
- ✅ No duplicate code
- ✅ Easy to add new features
- ✅ Easy to understand

---

## BLOCKERS BEFORE STARTING

**These need to be done FIRST:**

1. **Commit uncommitted changes:**
   ```bash
   git add webapp/frontend/src/App.jsx
   git add webapp/frontend/src/services/api.js
   git commit -m "WIP: Prepare for site consolidation"
   ```

2. **Check if anyone is working on:**
   - loadfundamentals branch? (No - last updated June 2025)
   - refactor branch? (No - last updated May 2025)
   - Any other branches? (Just check)

3. **Verify frontend builds:**
   ```bash
   cd webapp/frontend
   npm install
   npm run build
   # Should create dist/ directory
   ```

4. **Backup current state:**
   ```bash
   git branch backup-before-consolidation main
   ```

---

## READY TO START?

Answer these and we'll begin:

1. ✅ Uncommitted changes committed? → Y/N
2. ✅ No one actively working on other branches? → Y/N  
3. ✅ Frontend builds successfully? → Y/N
4. ✅ Backup branch created? → Y/N

**Once all YES, I'll execute:**
- Phase A: Server fix (15 min)
- Phase B: API redesign (1 hour)
- Phase C: Frontend routing (30 min)
- Phase D: Cleanup (1 hour)

**Total: ~2.5 hours to complete unified, clean site architecture.**
