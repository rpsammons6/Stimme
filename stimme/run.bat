@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

:: ─────────────────────────────────────────────────────────────────────
::  Stimme Bootstrapper
::  Double-click to launch. Creates a local .venv on first run.
:: ─────────────────────────────────────────────────────────────────────

:: 1. Check Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Python is not installed or not on PATH.
    echo          Please install Python 3.11+ from https://python.org
    echo.
    pause
    exit /b 1
)

:: 2. Check Python version >= 3.11
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
    if %%a LSS 3 goto :badver
    if %%a==3 if %%b LSS 11 goto :badver
)
goto :goodver

:badver
echo.
echo  [ERROR] Python 3.11+ required (found %PYVER%).
echo          Please upgrade from https://python.org
echo.
pause
exit /b 1

:goodver

:: 3. Create .venv if it doesn't exist or is broken
if not exist ".venv\Scripts\python.exe" (
    :: Remove partial .venv if it exists
    if exist ".venv" (
        echo  [SETUP] Removing broken .venv...
        rmdir /s /q .venv
    )

    echo.
    echo  [SETUP] Creating local environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )

    echo  [SETUP] Upgrading pip...
    .venv\Scripts\python.exe -m pip install --upgrade pip --quiet

    echo  [SETUP] Installing dependencies (this may take a minute)...
    .venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
    if %errorlevel% neq 0 (
        echo  [ERROR] Dependency installation failed. Check your network connection.
        pause
        exit /b 1
    )
    echo  [SETUP] Done.
    echo.
)

:: 4. Launch Stimme
::    Use python.exe (not pythonw) so errors are visible in the console.
::    The console stays open until the app exits — if it closes instantly,
::    check the error message above.
echo  [SYSTEM] Launching Stimme...
.venv\Scripts\python.exe main.py
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Stimme exited with an error (code %errorlevel%).
    echo          Check the output above for details.
    echo.
    pause
)
