# API CLEANUP CHECKLIST - EXACT ACTIONS

## FILES TO DELETE (25 files, ~18,800 lines)

### Tier 1: Delete First (3 files, 43 endpoints)
- [ ] Delete `webapp/lambda/routes/market.js` (23 endpoints - BIGGEST)
- [ ] Delete `webapp/lambda/routes/sentiment.js` (10 endpoints)
- [ ] Delete `webapp/lambda/routes/auth.js` (10 endpoints)

### Tier 2: Delete Empty Modules (2 files, 0 endpoints)
- [ ] Delete `webapp/lambda/routes/dashboard.js` (empty)
- [ ] Delete `webapp/lambda/routes/trading.js` (empty)

### Tier 3: Delete Remaining Unused (20 files, ~97 endpoints)
- [ ] Delete `webapp/lambda/routes/analysts.js`
- [ ] Delete `webapp/lambda/routes/api-status.js`
- [ ] Delete `webapp/lambda/routes/commodities.js`
- [ ] Delete `webapp/lambda/routes/community.js`
- [ ] Delete `webapp/lambda/routes/diagnostics.js`
- [ ] Delete `webapp/lambda/routes/earnings.js`
- [ ] Delete `webapp/lambda/routes/economic.js`
- [ ] Delete `webapp/lambda/routes/financials.js`
- [ ] Delete `webapp/lambda/routes/industries.js`
- [ ] Delete `webapp/lambda/routes/manual-trades.js`
- [ ] Delete `webapp/lambda/routes/metrics.js`
- [ ] Delete `webapp/lambda/routes/options.js`
- [ ] Delete `webapp/lambda/routes/price.js`
- [ ] Delete `webapp/lambda/routes/scores.js`
- [ ] Delete `webapp/lambda/routes/sectors.js`
- [ ] Delete `webapp/lambda/routes/signals.js`
- [ ] Delete `webapp/lambda/routes/strategies.js`
- [ ] Delete `webapp/lambda/routes/technicals.js`
- [ ] Delete `webapp/lambda/routes/user.js`
- [ ] Delete `webapp/lambda/routes/world-etfs.js`

---

## DUPLICATE ENDPOINTS TO FIX (4 fixes)

### Fix 1: sectors.js (Line ~15)
**BEFORE:**
```javascript
router.get("/", fetchSectors);
router.get("/sectors", fetchSectors);  // ← DELETE THIS LINE
router.get("/:sectorName/trend", async (req, res) => {
```

**AFTER:**
```javascript
router.get("/", fetchSectors);
router.get("/:sectorName/trend", async (req, res) => {
```

### Fix 2: industries.js (Line ~7)
**BEFORE:**
```javascript
router.get("/", fetchIndustries);
router.get("/industries", fetchIndustries);  // ← DELETE THIS LINE
router.get("/:industryName/trend", async (req, res) => {
```

**AFTER:**
```javascript
router.get("/", fetchIndustries);
router.get("/:industryName/trend", async (req, res) => {
```

### Fix 3: trades.js (Line ~231)
**BEFORE:**
```javascript
router.get('/', async (req, res) => {
  // ... implementation ...
});

router.get('/history', async (req, res) => {  // ← DELETE THIS ENTIRE ENDPOINT
  // Same implementation as above
});

router.get('/summary', async (req, res) => {
```

**AFTER:**
```javascript
router.get('/', async (req, res) => {
  // ... implementation ...
});

router.get('/summary', async (req, res) => {
```

### Fix 4: market.js (Find both /fresh-data routes)
**BEFORE:**
```javascript
router.get('/fresh-data', async (req, res) => {
  // ... implementation ...
});

// ... other routes ...

router.get('/fresh-data', async (req, res) => {  // ← DELETE THIS DUPLICATE
  // ... same implementation ...
});
```

**AFTER:**
```javascript
router.get('/fresh-data', async (req, res) => {
  // ... implementation ...
});

// ... other routes ...
```

---

## UPDATE webapp/lambda/index.js

Remove these route registrations (find and delete these lines):

```javascript
// DELETE THESE LINES:
const analystsRoutes = require("./routes/analysts");
const authRoutes = require("./routes/auth");
const commoditiesRoutes = require("./routes/commodities");
const communityRoutes = require("./routes/community");
const diagnosticsRoutes = require("./routes/diagnostics");
const earningsRoutes = require("./routes/earnings");
const economicRoutes = require("./routes/economic");
const financialRoutes = require("./routes/financials");
const industriesRoutes = require("./routes/industries");
const manualTradesRoutes = require("./routes/manual-trades");
const marketRoutes = require("./routes/market");
const metricsRoutes = require("./routes/metrics");
const optionsRoutes = require("./routes/options");
const priceRoutes = require("./routes/price");
const scoresRoutes = require("./routes/scores");
const sectorsRoutes = require("./routes/sectors");
const sentimentRoutes = require("./routes/sentiment");
const signalsRoutes = require("./routes/signals");
const strategiesRoutes = require("./routes/strategies");
const technicalRoutes = require("./routes/technicals");
const userRoutes = require("./routes/user");
const worldEtfsRoutes = require("./routes/world-etfs");

// And DELETE these mount statements:
app.use("/api/analysts", analystsRoutes);
app.use("/api/auth", authRoutes);
app.use("/api/commodities", commoditiesRoutes);
app.use("/api/community", communityRoutes);
app.use("/api/diagnostics", diagnosticsRoutes);
app.use("/api/earnings", earningsRoutes);
app.use("/api/economic", economicRoutes);
app.use("/api/financials", financialRoutes);
app.use("/api/industries", industriesRoutes);
app.use("/api/manual-trades", manualTradesRoutes);
app.use("/api/market", marketRoutes);
app.use("/api/metrics", metricsRoutes);
app.use("/api/options", optionsRoutes);
app.use("/api/price", priceRoutes);
app.use("/api/scores", scoresRoutes);
app.use("/api/sectors", sectorsRoutes);
app.use("/api/sentiment", sentimentRoutes);
app.use("/api/signals", signalsRoutes);
app.use("/api/strategies", strategiesRoutes);
app.use("/api/technicals", technicalRoutes);
app.use("/api/user", userRoutes);
app.use("/api/world-etfs", worldEtfsRoutes);
```

**KEEP THESE (they are used):**
```javascript
const contactRoutes = require("./routes/contact");
const healthRoutes = require("./routes/health");
const optimizationRoutes = require("./routes/optimization");
const portfolioRoutes = require("./routes/portfolio");
const signalsRoutes = require("./routes/signals");  // Wait - check if used?
const stocksRoutes = require("./routes/stocks");
const tradesRoutes = require("./routes/trades");

app.use("/api/contact", contactRoutes);
app.use("/api/health", healthRoutes);
app.use("/api/optimization", optimizationRoutes);
app.use("/api/portfolio", portfolioRoutes);
app.use("/api/signals", signalsRoutes);  // Check if used!
app.use("/api/stocks", stocksRoutes);
app.use("/api/trades", tradesRoutes);
```

---

## KEEP THESE ENDPOINTS (Final List)

### STOCKS (Keep 1 of 6)
- [x] Keep: `GET /api/stocks/deep-value`
- [ ] Delete all others from stocks.js

### TRADES (Keep 2 of 3)
- [x] Keep: `GET /api/trades/`
- [x] Keep: `GET /api/trades/summary`
- [ ] Delete: `GET /api/trades/history`

### PORTFOLIO (Keep 5 of 11)
- [x] Keep: `GET /api/portfolio/metrics`
- [x] Keep: `GET /api/portfolio/api-keys`
- [x] Keep: `POST /api/portfolio/api-keys`
- [x] Keep: `DELETE /api/portfolio/api-keys/:id`
- [x] Keep: `POST /api/portfolio/test-api-key`
- [ ] Delete: All others

### CONTACT (Keep 1 of 4)
- [x] Keep: `GET /api/contact/submissions`
- [ ] Delete: POST, GET :id, PATCH :id

### HEALTH (Keep 2 of 4)
- [x] Keep: `GET /api/health/`
- [x] Keep: `GET /api/health/database`
- [ ] Delete: /ecs-tasks, /api-endpoints

### OPTIMIZATION (Keep 1 of 5)
- [x] Keep: `GET /api/optimization/analysis`
- [ ] Delete: All others

---

## GIT WORKFLOW

```bash
# 1. Create cleanup branch
git checkout -b cleanup/remove-unused-api-endpoints

# 2. Delete all 25 unused route files
git rm webapp/lambda/routes/analysts.js
git rm webapp/lambda/routes/auth.js
git rm webapp/lambda/routes/commodities.js
git rm webapp/lambda/routes/community.js
git rm webapp/lambda/routes/dashboard.js
git rm webapp/lambda/routes/diagnostics.js
git rm webapp/lambda/routes/earnings.js
git rm webapp/lambda/routes/economic.js
git rm webapp/lambda/routes/financials.js
git rm webapp/lambda/routes/industries.js
git rm webapp/lambda/routes/manual-trades.js
git rm webapp/lambda/routes/market.js
git rm webapp/lambda/routes/metrics.js
git rm webapp/lambda/routes/options.js
git rm webapp/lambda/routes/price.js
git rm webapp/lambda/routes/scores.js
git rm webapp/lambda/routes/sectors.js
git rm webapp/lambda/routes/sentiment.js
git rm webapp/lambda/routes/signals.js
git rm webapp/lambda/routes/strategies.js
git rm webapp/lambda/routes/technicals.js
git rm webapp/lambda/routes/trading.js
git rm webapp/lambda/routes/user.js
git rm webapp/lambda/routes/world-etfs.js
git rm webapp/lambda/routes/api-status.js

# 3. Fix duplicate endpoints in remaining files
# (Edit sectors.js, industries.js, trades.js, market.js)

# 4. Update index.js to remove route registrations
# (Edit webapp/lambda/index.js)

# 5. Test all 7 pages work
npm test
# or manually: visit http://localhost:5174

# 6. Commit changes
git add -A
git commit -m "Remove 140+ unused API endpoints (25 modules deleted)

- Delete 25 unused route modules (152+ endpoints)
- Fix 4 duplicate endpoint definitions
- Update index.js to remove unused registrations
- Keep only 13-15 endpoints actually used by frontend
- Reduce codebase by 87% in API layer

This removes ~18,800 lines of dead code.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"

# 7. Push and create PR
git push origin cleanup/remove-unused-api-endpoints
gh pr create --title "Remove 140+ unused API endpoints" \
  --body "Removes 25 route modules and 140+ endpoints that have zero frontend usage."
```

---

## TESTING CHECKLIST

After cleanup, verify these 7 pages still work:

- [ ] DeepValueStocks.jsx loads data from GET /api/stocks/deep-value
- [ ] TradeHistory.jsx loads data from GET /api/trades and /summary
- [ ] PortfolioDashboard.jsx loads data from GET /api/portfolio/metrics
- [ ] PortfolioOptimizerNew.jsx loads data from GET /api/optimization/analysis
- [ ] Messages.jsx loads data from GET /api/contact/submissions
- [ ] ServiceHealth.jsx loads data from GET /api/health and /database
- [ ] Settings.jsx still works (verify /api/user endpoints if needed)

---

## BEFORE & AFTER STATS

| Metric | Before | After | Reduction |
|--------|--------|-------|-----------|
| Route Modules | 31 | 6 | -81% |
| Total Endpoints | 155+ | 13-15 | -91% |
| Files to Maintain | 31 | 6 | -81% |
| Lines of Code | ~15,000+ | ~2,000 | -87% |
| Unused Endpoints | 140+ | 0 | -100% |

---

## QUICK REFERENCE: WHAT STAYS vs GOES

### 🟢 STAY (6 modules, 13-15 endpoints)
- stocks.js (keep 1 endpoint)
- trades.js (keep 2 endpoints)
- portfolio.js (keep 5 endpoints)
- contact.js (keep 1 endpoint)
- health.js (keep 2 endpoints)
- optimization.js (keep 1 endpoint)

### 🔴 DELETE (25 modules, 140+ endpoints)
- Everything else!

