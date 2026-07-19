# Frontend Quick Start Card

## One-Command Start

```bash
cd webapp/frontend
npm run start
```

This runs:
- ✅ `npm run setup-dev` (configures for localhost)
- ✅ `npm run dev` (starts Vite on localhost:5173+)
- ✅ Opens browser automatically

**First run:** ~30s  
**Subsequent runs:** Instant

---

## Manual Start (3 Terminals)

### Terminal 1: Backend API
```bash
python lambda/api/dev_server.py
# Watch for: "Starting API dev server on http://localhost:3001"
```

### Terminal 2: Frontend Build
```bash
cd webapp/frontend
npm run setup-dev  # One time setup
npm run dev        # Start Vite
# Watch for: "Local: http://localhost:5173" (or 5174+)
```

### Terminal 3: Open in Browser
```
http://localhost:5173 (or whatever port shows in Terminal 2)
Press F12 to check console for errors
```

---

## What to Expect in Console (F12)

### ✅ GOOD Signs
- Info/Debug messages (gray/blue text)
- Vite connection messages
- React DevTools suggestions
- "React application rendered successfully"

### ⚠️ OK Signs (Don't worry about these)
- 503/500 API errors - dev server is incomplete
- "Failed to load resource" - expected for stub endpoints

### ❌ BAD Signs (Fix these!)
- CORS errors ("blocked by CORS policy")
- JavaScript errors in red
- "Cannot read properties of undefined"
- Component PropTypes errors

---

## Switching Environments

### To Local Development
```bash
cd webapp/frontend
npm run setup-dev  # Generates config.js with empty API_URL
npm run dev
```

### To AWS Production
```bash
cd webapp/frontend  
npm run setup-prod  # Generates config.js with AWS URL
npm run build       # Build for production
```

**Note:** `setup-dev` and `setup-prod` ONLY change `config.js`. No code changes needed!

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port 5173 already in use | Vite auto-increments (use shown port) |
| CORS errors in console | Run `npm run setup-dev` |
| "Cannot GET /api/..." | Make sure `python lambda/api/dev_server.py` running |
| 503/500 API errors | Normal - dev server is incomplete |
| PropTypes warnings | All fixed - should not see these anymore |

---

## What Got Fixed

1. **CORS Errors** → Config.js now uses empty API_URL for local dev
2. **PropTypes** → Added `decimal1` formatter to SafeMetric components  
3. **Environment** → `VITE_PROXY_TARGET` variable cleared

---

## Files to Know

```
webapp/frontend/
├── public/config.js           ← Auto-generated, DO NOT EDIT
├── scripts/setup-dev.js       ← Generates development config
├── scripts/setup-prod.js      ← Generates production config
├── vite.config.js             ← Proxy configuration
├── package.json               ← npm scripts
└── src/                        ← Your code
    ├── main.jsx               ← Entry point
    ├── App.jsx                ← Routes
    └── services/api.js        ← API client (uses config)
```

---

## Status

✅ **Local Development:** Working perfectly  
✅ **CORS:** Fixed  
✅ **PropTypes:** Fixed  
✅ **Ready to Deploy:** Yes  

Go to http://localhost:5173 (or shown port) and start developing!
