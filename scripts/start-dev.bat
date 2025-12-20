@echo off
REM Development Environment Startup Script for Windows
REM Starts both frontend (Vite) and backend (Express) servers

setlocal enabledelayedexpansion

REM Configuration
set BACKEND_PORT=3001
set FRONTEND_PORT=5173
set BACKEND_DIR=webapp\lambda
set FRONTEND_DIR=webapp\frontend
set BACKEND_URL=http://localhost:%BACKEND_PORT%
set FRONTEND_URL=http://localhost:%FRONTEND_PORT%

REM Change to project root
cd /d "%~dp0\.."
set PROJECT_ROOT=%cd%

echo.
echo ===============================================================
echo   Financial Dashboard - Development Startup Script
echo ===============================================================
echo.

REM Check Node.js
echo Checking Node.js...
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Please install Node.js 20.19+
    exit /b 1
)
echo [OK] Node.js installed

REM Check npm
echo Checking npm...
npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found
    exit /b 1
)
echo [OK] npm installed

echo.
echo Starting Backend...
cd /d "%PROJECT_ROOT%\%BACKEND_DIR%"

if not exist "node_modules" (
    echo Installing backend dependencies...
    call npm install
)

start "Financial Dashboard Backend" cmd /k "npm start"
echo [OK] Backend started on %BACKEND_URL%

timeout /t 3 /nobreak

echo.
echo Starting Frontend...
cd /d "%PROJECT_ROOT%\%FRONTEND_DIR%"

if not exist "node_modules" (
    echo Installing frontend dependencies...
    call npm install
)

start "Financial Dashboard Frontend" cmd /k "npm run dev"
echo [OK] Frontend started on %FRONTEND_URL%

echo.
echo ===============================================================
echo   Development environment is running!
echo ===============================================================
echo.
echo Frontend:  %FRONTEND_URL%
echo Backend:   %BACKEND_URL%
echo.
echo Close the command windows to stop the services.
echo.

pause
