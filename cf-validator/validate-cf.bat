@echo off
REM CloudFormation Fast Validation - Quick Access
REM Usage: validate-cf.bat template.yml [stack-name]

setlocal enabledelayedexpansion

if "%1"=="" (
    echo Usage: validate-cf.bat template.yml [stack-name]
    echo.
    echo Examples:
    echo   validate-cf.bat template-webapp-lambda.yml
    echo   validate-cf.bat template-webapp-lambda.yml stocks-webapp-stack
    echo   validate-cf.bat template-webapp-lambda.yml stocks-webapp-stack --quick
    exit /b 1
)

set TEMPLATE=%1
set STACK_NAME=%2
set EXTRA_ARGS=%3 %4 %5

echo 🚀 CloudFormation Fast Validation
echo Template: %TEMPLATE%
if not "%STACK_NAME%"=="" echo Stack: %STACK_NAME%
echo.

REM Check if template file exists
if not exist "%TEMPLATE%" (
    echo ❌ Template file not found: %TEMPLATE%
    exit /b 1
)

REM Build PowerShell command
set PS_CMD=powershell -ExecutionPolicy Bypass -File "validate-cf.ps1" -TemplatePath "%TEMPLATE%"

if not "%STACK_NAME%"=="" (
    set PS_CMD=!PS_CMD! -StackName "%STACK_NAME%"
)

if not "%EXTRA_ARGS%"=="" (
    set PS_CMD=!PS_CMD! %EXTRA_ARGS%
)

REM Execute validation
echo Running: !PS_CMD!
echo.
!PS_CMD!

exit /b %ERRORLEVEL%
