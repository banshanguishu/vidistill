@echo off
setlocal enabledelayedexpansion

REM Run from the directory this script lives in.
cd /d "%~dp0"

set REGISTRY=192.168.1.252:15000
set TAG=latest
set IMAGE_NAME=vidistill
set IMAGE=%REGISTRY%/%IMAGE_NAME%:%TAG%

echo.
docker build -t %IMAGE% .
if !ERRORLEVEL! NEQ 0 (
    echo ============================================================
    echo   Image: %IMAGE%
    echo   Build: FAIL
    echo   Push:  -
    echo ============================================================
    exit /b 1
)

docker push %IMAGE%
if !ERRORLEVEL! NEQ 0 (
    echo ============================================================
    echo   Image: %IMAGE%
    echo   Build: SUCCESS
    echo   Push:  FAIL
    echo ============================================================
    exit /b 1
)

echo ============================================================
echo   Image: %IMAGE%
echo   Build: SUCCESS
echo   Push:  SUCCESS
echo ============================================================

endlocal
exit /b 0