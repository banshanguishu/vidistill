@echo off
setlocal enabledelayedexpansion

REM Run from the directory this script lives in.
cd /d "%~dp0"

set REGISTRY=192.168.1.252:15000
set IMAGE=%REGISTRY%/vidistill:latest

echo.
echo ============================================================
echo  Building image: %IMAGE%
echo ============================================================
docker build -t %IMAGE% .
set BUILD_CODE=%errorlevel%
if not %BUILD_CODE%==0 (
  echo.
  echo ============================================================
  echo  [FAIL] Image build failed (exit code %BUILD_CODE%)
  echo ============================================================
  exit /b %BUILD_CODE%
)
echo.
echo [OK] Image build succeeded.

echo.
echo ============================================================
echo  Pushing %IMAGE% to registry
echo ============================================================
docker push %IMAGE%
set PUSH_CODE=%errorlevel%
if not %PUSH_CODE%==0 (
  echo.
  echo ============================================================
  echo  [FAIL] Push failed (exit code %PUSH_CODE%)
  echo  Hint: if this is a TLS/insecure registry error, in
  echo        Docker Desktop -^> Settings -^> Docker Engine,
  echo        add to the JSON:
  echo            "insecure-registries": ["%REGISTRY%"]
  echo        then Apply ^& Restart, and re-run this script.
  echo ============================================================
  exit /b %PUSH_CODE%
)
echo.
echo [OK] Push succeeded.

echo.
echo ============================================================
echo  Summary
echo ============================================================
echo   Image: %IMAGE%
echo   Build: OK
echo   Push:  OK
echo.
echo  Next step: on the server, run:
echo      bash deploy.sh
echo ============================================================

endlocal
exit /b 0
