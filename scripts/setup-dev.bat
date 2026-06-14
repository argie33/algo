@echo off
REM Quick setup for local development environment
REM This is a convenience wrapper for the PowerShell setup script

REM Check if PowerShell is available
where pwsh >nul 2>&1
if %ERRORLEVEL% equ 0 (
    pwsh -NoProfile -ExecutionPolicy Bypass -Command "& { . .\scripts\setup-local-dev.ps1 @args }" %*
) else (
    REM Fallback to Windows PowerShell
    powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . .\scripts\setup-local-dev.ps1 @args }" %*
)
