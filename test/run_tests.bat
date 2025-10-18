@echo off
echo Starting Docker-based test environment...
cd /d "%~dp0"

echo Cleaning up any existing containers...
docker-compose down -v

echo Building and running tests...
docker-compose up --build

echo Cleaning up...
docker-compose down

pause
