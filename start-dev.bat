@echo off
REM Start Financial Dashboard (API + Frontend) with PM2

echo.
echo Checking PM2...
where pm2 >/dev/null 2>/dev/null
if errorlevel 1 (
  echo Installing PM2 globally...
  npm install -g pm2
)

echo.
echo Stopping any existing PM2 processes...
pm2 delete-all >/dev/null 2>/dev/null

echo.
echo Starting API server (port 3001)...
cd /d C:\Users\arger\code\algo
pm2 start webapp/lambda/index.js --name "api"

echo.
echo Starting Frontend (port 5173)...
cd /d C:\Users\arger\code\algo\webapp\frontend
pm2 start "npm run dev" --name "frontend"

echo.
echo Saving PM2 process list...
pm2 save

echo.
timeout /t 5 /nobreak

echo.
echo ===== Dashboard Status =====
pm2 list

echo.
echo API:      http://localhost:3001/api/status
echo Frontend: http://localhost:5173
echo.
echo Commands:
echo   pm2 logs api        - View API logs
echo   pm2 logs frontend   - View Frontend logs
echo   pm2 logs            - View all logs
echo   pm2 stop all        - Stop all services
echo   pm2 restart all     - Restart all services
echo.
pause
