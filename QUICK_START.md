# Quick Start Guide
**Last Updated**: 2025-10-20

---

## 🚀 Start Everything

```bash
bash /home/stocks/algo/start-all-services.sh
```

That's it! This starts:
- ✅ Backend API on :3001
- ✅ Frontend on :5173 (or next available port)
- ✅ Proper API configuration (frontend → backend)

---

## 🌐 Access the Application

| Service | URL | Purpose |
|---------|-----|---------|
| **Frontend** | http://localhost:5173 | Web UI (or :5174, :5175 if port taken) |
| **Backend API** | http://localhost:3001 | API endpoints |
| **API Health** | http://localhost:3001/api/health | System status |

---

## 🧪 Test API

```bash
# Test all endpoints
python3 /home/stocks/algo/test_all_apis.py
```

---

## 📊 View Logs

```bash
# Backend logs
tail -f /tmp/backend.log

# Frontend logs
tail -f /tmp/frontend.log
```

---

## 🛑 Stop Services

```bash
# Kill backend and frontend
killall node
```

Or from the startup script output:
```bash
kill 943022 943096
```

---

## ⚙️ Configuration

### Frontend API URL
Currently set to: `http://localhost:3001`

If you need to change it:
```bash
export API_URL="http://your-api-url"
npm start
```

---

## 📁 Key Files

| File | Purpose |
|------|---------|
| `/home/stocks/algo/start-all-services.sh` | Master startup script |
| `/home/stocks/algo/test_all_apis.py` | API testing suite |
| `/home/stocks/algo/webapp/frontend/public/config.js` | Frontend API config |
| `/home/stocks/algo/webapp/lambda/index.js` | Backend entry point |
| `/home/stocks/algo/API_FIXES_IMPLEMENTED.md` | Detailed fix documentation |

---

## ✅ What's Working

- Stock scores loading (2,133 stocks)
- Sector data aggregation
- Dashboard basic functionality
- All critical APIs responding
- Frontend ↔ Backend communication

---

## 📋 Common Issues & Fixes

### Issue: "Cannot connect to API"
**Fix**: Run the startup script
```bash
bash /home/stocks/algo/start-all-services.sh
```

### Issue: "Port already in use"
**Fix**: Kill existing processes first
```bash
killall node
bash /home/stocks/algo/start-all-services.sh
```

### Issue: Frontend still trying port 5001
**Fix**: Already fixed! Just run startup script

---

## 📊 Data Status

- **Total Stocks**: 2,133 with complete scores
- **Coverage**: 40.1% of available stocks
- **ETFs**: ✅ Properly removed
- **Duplicates**: ✅ None found

---

## 🔗 API Endpoints

```
GET  /api/scores              - All stocks with scores
GET  /api/scores/:symbol      - Single stock score
GET  /api/sectors             - Sector list
GET  /api/sectors/:sector/stocks       - Stocks in sector
GET  /api/dashboard           - Dashboard summary
GET  /api/health              - System health
```

See `API_TESTING_REPORT.md` for complete list.

---

## 💾 Database

- **Type**: PostgreSQL
- **Host**: localhost
- **Port**: 5432
- **Database**: stocks
- **Status**: ✅ Running

---

**Need more help?** See `API_FIXES_IMPLEMENTED.md` for detailed documentation.
