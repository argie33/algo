# Frontend Setup & Troubleshooting

## ✅ Current Status
Frontend dev server on `http://localhost:5173` is stable. API proxy works correctly even when environment variables are misconfigured.

## 🚀 Start Frontend

### Prerequisites
- Backend dev server on `http://localhost:3001`
- Port 5173 available
- Node 20.19+

### Quick Start
```bash
cd webapp/frontend
npm run dev
```

**Expected output:**
```
✓ VITE v7.x.x ready in XXX ms
➜ Local: http://localhost:5173/
```

### Backend Must Be Running First
```bash
# Terminal 1: Backend
cd webapp/lambda
python api/dev_server.py
# Wait for: [INFO] Starting API dev server on http://localhost:3001

# Terminal 2: Frontend (only after backend is ready)
cd webapp/frontend
npm run dev
```

## 🛡️ What's Fixed

### The Problem (Solved)
- **Symptom:** 404 errors on `/api/health`, `/api/markets/*` endpoints
- **Root Cause:** `VITE_PROXY_TARGET` environment variable was set to AWS instead of localhost
- **Impact:** Frontend loads but all API calls fail, showing "Data not available"

### The Solution
1. **vite.config.js** - Detects AWS URLs and auto-redirects to `localhost:3001`
2. **setup-dev.js** - Clears AWS URLs when setting up local dev
3. **Safeguard:** Works even if someone accidentally sets `VITE_PROXY_TARGET` to AWS

### Verification
```bash
# This should work regardless of environment variables
curl http://localhost:5173/api/health
# Expected: 200 OK with JSON response
```

## 🔧 Proxy Flow

```
Browser (localhost:5173)
    ↓
Vite Proxy (/api/*)
    ↓
[SAFEGUARD: Detects AWS URL → redirects to localhost:3001]
    ↓
Backend Dev Server (localhost:3001)
    ↓
Response back to browser
```

## 📋 Key Files Modified

1. **vite.config.js** (lines 30-42)
   - Added safeguard: if `VITE_PROXY_TARGET` contains "amazonaws", redirect to localhost:3001
   - Ensures local dev always works

2. **scripts/setup-dev.js** (lines 12-18)
   - Clear AWS URLs when running local setup
   - Logs warning if AWS URL is detected

## 🐛 Troubleshooting

### API returns 404
```bash
# 1. Check backend is running
curl http://localhost:3001/api/health
# Should return: {"statusCode": 200, ...}

# 2. Check frontend can reach it through proxy
curl http://localhost:5173/api/health
# Should return same response as above

# 3. If port 3001 is not listening, start backend:
cd webapp/lambda
python api/dev_server.py
```

### Frontend shows "Data not available"
1. Refresh page in browser
2. Check DevTools → Network tab for failed requests
3. Run: `python check_system_health.py` from project root

### Port 5173 already in use
```bash
# Find process on port 5173
netstat -ano | findstr "5173"
# Kill it
taskkill /PID <PID> /F
# Restart frontend
npm run dev
```

### Vite crashes with "cannot find module"
```bash
# Clean install
rm -rf node_modules package-lock.json
npm install
npm run dev
```

## 🎯 Local Development Workflow

### Full Stack Start (Recommended)
```bash
# From project root
python start_dashboard_dev.py
# This:
# - Starts backend dev server (port 3001)
# - Starts frontend dev server (port 5173)
# - Opens dashboard
# - Auto-refreshes every 30s (optional flag: -w 30)
```

### Manual Setup
```bash
# Terminal 1: Backend
cd webapp/lambda
python api/dev_server.py

# Terminal 2: Frontend
cd webapp/frontend
npm run dev

# Terminal 3: Dashboard (optional)
python dashboard.py --local
```

## 📝 Important Notes

- **No .env files** - Configuration comes from `public/config.js` (auto-generated)
- **No secrets in config** - All credentials from environment or AWS Secrets Manager
- **Works offline** - Local dev doesn't need AWS credentials
- **Automatic detection** - Frontend detects correct API endpoint automatically

## ✅ Verification Checklist

- [ ] Backend listening on port 3001: `curl http://localhost:3001/api/health`
- [ ] Frontend serving on port 5173: `curl http://localhost:5173/`
- [ ] API proxy works: `curl http://localhost:5173/api/health`
- [ ] Browser opens http://localhost:5173 successfully
- [ ] Dashboard shows data (not "Data not available")

---

**Fixed:** 2026-07-19  
**Status:** Stable for local development
