# 🚀 Algo Trading System - Complete Installation Guide

## Quick Overview

Your system is **90% ready**. You just need PostgreSQL installed, then everything will work.

### Current Status
- ✅ **Code Repository** - Loaded from GitHub
- ✅ **Node.js** - v25.9.0 installed
- ✅ **npm** - 11.12.1 installed  
- ✅ **Dependencies** - 83 packages installed
- ✅ **Configuration** - .env.local configured
- ⏳ **PostgreSQL** - Waiting for installation

---

## Installation Steps

### Step 1: Run Verification (Optional but Recommended)

Double-click this file to check current setup:
```
verify-setup.bat
```

This will show you what's installed and what needs to be done.

---

### Step 2: Install PostgreSQL

#### Option A: Automatic Installation (Easiest)
If you have Administrator privileges, double-click:
```
install-postgres-auto.bat
```

This will:
1. Download PostgreSQL 16
2. Install it silently
3. Create the database automatically
4. Test the connection

**Estimated time: 3-5 minutes**

---

#### Option B: Manual Installation (More Control)

1. **Download PostgreSQL 16**
   - Visit: https://www.postgresql.org/download/windows/
   - Download: PostgreSQL 16 (latest stable)

2. **Run the Installer**
   - Double-click the `.exe` file
   - Follow the wizard:
     - **Installation Directory**: Leave as default
     - **Port**: `5432` (important - don't change)
     - **Superuser Password**: Set any password (e.g., `postgres`)
     - **Install as service**: Check this box
   - Let it complete (2-3 minutes)

3. **Create the Database**
   - Double-click: `setup-database.bat`
   - This will create the `stocks` database and user automatically

---

### Step 3: Verify Installation

Double-click to verify everything is working:
```
verify-setup.bat
```

You should see:
- ✅ Node.js installed
- ✅ npm installed
- ✅ Dependencies installed
- ✅ PostgreSQL installed
- ✅ PostgreSQL service running

---

### Step 4: Start the Application

**Option A: Click the Batch File**
```
start-app.bat
```

**Option B: Command Line**
```cmd
npm start
```

You should see:
```
Server running at http://localhost:3001
Connected to database: stocks
```

---

### Step 5: Access the Application

Open your browser and go to:
```
http://localhost:3001
```

---

## What Each Batch File Does

| File | Purpose |
|------|---------|
| `verify-setup.bat` | Check if everything is installed correctly |
| `install-postgres-auto.bat` | Download and install PostgreSQL automatically |
| `setup-database.bat` | Create the stocks database and user |
| `start-app.bat` | Start the Node.js application |

---

## Database Details

Once installed, your database will be configured as:

```
Host:         localhost
Port:         5432
Database:     stocks
User:         stocks
Password:     bed0elAn
Connection:   postgresql://stocks:bed0elAn@localhost:5432/stocks
```

This is already configured in `.env.local` - no manual changes needed!

---

## Troubleshooting

### PostgreSQL Installation Failed
1. Try manual installation from: https://www.postgresql.org/download/windows/
2. When running installer, make sure:
   - Port is set to 5432
   - Service is enabled
3. After manual installation, run: `setup-database.bat`

### "PostgreSQL not found" after installation
1. Close and reopen Command Prompt
2. If still not found, verify:
   - PostgreSQL installed at: `C:\Program Files\PostgreSQL\16`
   - Service running: Open `services.msc` and search for "postgresql"

### Application won't start
1. Run: `verify-setup.bat`
2. Check that PostgreSQL service is running
3. Try: `npm install` then `npm start`

### Port 3001 already in use
Edit `.env.local`:
```
Change: PORT=3001
To:     PORT=3002
```

Then access at: http://localhost:3002

### Database connection errors
1. Verify PostgreSQL service is running:
   ```cmd
   sc query postgresql-x64-16
   ```

2. Test connection manually:
   ```cmd
   "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U stocks -d stocks -h localhost
   ```

3. If fails, run: `setup-database.bat` again

---

## Full Documentation

For detailed information about each component:

- **POSTGRES_SETUP.md** - Complete PostgreSQL guide with all options
- **SETUP_SUMMARY.md** - Project overview and architecture
- **README_QUICK_START.txt** - Quick reference guide
- **config.js** - Application configuration and scoring algorithm

---

## Common Questions

**Q: Do I need Administrator privileges?**  
A: Only if using `install-postgres-auto.bat`. Manual installation doesn't require it until creating the database.

**Q: What if I already have PostgreSQL installed?**  
A: Just run `setup-database.bat` to create the stocks database.

**Q: Can I change the database password?**  
A: Yes, but you must update `.env.local` to match.

**Q: What Python version is needed?**  
A: For data loaders (optional): Python 3.8+. Check individual loader scripts for dependencies.

**Q: How do I backup the database?**  
A: Use:
```cmd
"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -U stocks -d stocks > backup.sql
```

**Q: How do I restore from backup?**  
A: Use:
```cmd
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U stocks -d stocks < backup.sql
```

---

## Next Steps After Setup

1. **Verify Setup Works**
   - Open: http://localhost:3001
   - You should see the web application

2. **Load Initial Data** (Optional)
   - The Python loaders can populate the database with stock data
   - For example: `python loadstocksymbols.py`

3. **Configure APIs** (Optional)
   - Edit `.env.local` to add API keys:
     - Alpaca trading API
     - Financial data APIs
     - See `.env.example` for all options

4. **Explore the Code**
   - Main app: `./webapp`
   - Data loaders: `./load*.py`
   - Configuration: `config.js`

---

## Support & Resources

- PostgreSQL Help: https://www.postgresql.org/docs/
- Node.js Help: https://nodejs.org/docs/
- Express.js: https://expressjs.com/
- See inline comments in: `POSTGRES_SETUP.md`

---

## Time Estimate

| Task | Time |
|------|------|
| Download PostgreSQL | 5-10 min |
| Install PostgreSQL (auto) | 3-5 min |
| Create database | 1 min |
| Start application | 1 min |
| **Total** | **10-17 min** |

---

**Status**: Ready for PostgreSQL installation  
**Last Updated**: 2026-04-22

Let's get this running! 🚀
