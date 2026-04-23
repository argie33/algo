================================================================================
ALGO TRADING SYSTEM - QUICK START GUIDE
================================================================================

STATUS: ✅ READY FOR SETUP

What's been done:
  ✅ Code repository loaded from GitHub
  ✅ Node.js dependencies installed (express, pg, cors)
  ✅ Security vulnerabilities fixed
  ✅ Environment configuration created (.env.local)
  ✅ Setup scripts created
  ⏳ PostgreSQL - WAITING FOR INSTALLATION

================================================================================
STEP 1: INSTALL POSTGRESQL (One-time setup)
================================================================================

Download: https://www.postgresql.org/download/windows/
  - PostgreSQL 16 (recommended) or 15+
  - Run installer with port 5432
  - Set superuser password during install

Then create the database:
  - Open Command Prompt
  - Run: "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres
  - Enter superuser password
  - Copy & paste these commands:

    CREATE USER stocks WITH PASSWORD 'bed0elAn';
    CREATE DATABASE stocks OWNER stocks;
    GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;
    ALTER ROLE stocks WITH CREATEDB;
    \q

Details: See POSTGRES_SETUP.md

================================================================================
STEP 2: START THE APPLICATION
================================================================================

Option A - Click the batch file:
  Double-click: start-app.bat

Option B - Command line:
  npm start

Server will start at: http://localhost:3001

================================================================================
DATABASE CONFIGURATION
================================================================================

Host:     localhost
Port:     5432
Database: stocks
User:     stocks
Password: bed0elAn

Status:   ✅ Configured in .env.local (ready to use)

================================================================================
FILES CREATED FOR YOU
================================================================================

Setup & Configuration:
  ✅ POSTGRES_SETUP.md      - Detailed PostgreSQL installation guide
  ✅ SETUP_SUMMARY.md       - Complete project overview
  ✅ setup-postgres.ps1     - Automated setup (requires admin)
  ✅ start-app.bat          - Quick launch script
  ✅ init-db.sql            - Database initialization
  ✅ .env.local             - Database credentials (ready)

Dependencies:
  ✅ package.json           - Node.js packages
  ✅ package-lock.json      - Locked versions
  ✅ node_modules/          - Installed packages

================================================================================
QUICK HELP
================================================================================

PostgreSQL not starting?
  → See POSTGRES_SETUP.md → Troubleshooting section

Node.js errors?
  → npm audit fix
  → npm install
  → npm start

Port 3001 already in use?
  → Edit .env.local and change PORT=3001 to PORT=3002

Database connection errors?
  → Verify PostgreSQL service is running
  → Check .env.local credentials
  → See POSTGRES_SETUP.md → Troubleshooting

================================================================================
NEXT: Install PostgreSQL, then run "npm start"
================================================================================
