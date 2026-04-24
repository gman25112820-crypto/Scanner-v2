@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

title RAGE Engine - Public Launcher

echo.
echo ==========================================
echo      RAGE ENGINE  ^|  PUBLIC LAUNCH
echo       Rob ^& Gareth  ^|  Cymru am byth
echo ==========================================
echo.

:: ── Pre-flight checks ──────────────────────────────────────

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo         Open a terminal and run:  python --version
    echo         If missing, install from https://python.org
    pause & exit /b 1
)

where streamlit >nul 2>nul
if errorlevel 1 (
    echo [WARN] Streamlit not found — installing now...
    python -m pip install streamlit --quiet
)

where ngrok >nul 2>nul
if errorlevel 1 (
    echo [ERROR] ngrok not found in PATH.
    echo.
    echo  Install ngrok:
    echo    1. Go to https://ngrok.com/download
    echo    2. Download the Windows zip
    echo    3. Extract ngrok.exe into this folder:
    echo       %cd%
    echo    4. Run this launcher again.
    echo.
    pause & exit /b 1
)

if not exist "app.py" (
    echo [ERROR] app.py not found in:
    echo         %cd%
    echo.
    echo  Make sure launch_rage_public.bat is in the same folder as app.py
    pause & exit /b 1
)

:: ── Check for missing output files ─────────────────────────

set WARNINGS=0

if not exist "output\allocator\strategy_allocation.csv" (
    echo [WARN] No allocator CSV found  ^(output\allocator\strategy_allocation.csv^)
    set WARNINGS=1
)
if not exist "output\trade_results.csv" (
    echo [WARN] No trade results found  ^(output\trade_results.csv^)
    set WARNINGS=1
)

if "%WARNINGS%"=="1" echo       These are optional — dashboard will still launch.
echo.

:: ── Step 1: Rebuild master performance tables ──────────────

if not exist "build_master_performance.py" (
    echo [SKIP] build_master_performance.py not found — skipping rebuild.
    goto :skip_build
)

echo [1/4] Rebuilding master performance tables...
python build_master_performance.py
if errorlevel 1 (
    echo.
    echo [WARN] Master build returned an error — check output above.
    echo        Continuing with dashboard launch...
    echo.
)
echo.

:skip_build

:: ── Step 2: Kill stale processes ───────────────────────────

echo [2/4] Clearing old sessions...
taskkill /F /IM ngrok.exe         >nul 2>nul
taskkill /F /FI "WINDOWTITLE eq RAGE_STREAMLIT*" >nul 2>nul
timeout /t 1 >nul

:: ── Step 3: Launch Streamlit ───────────────────────────────

echo [3/4] Starting Streamlit dashboard...
start "RAGE_STREAMLIT" cmd /k "cd /d %cd% && python -m streamlit run app.py --server.headless true"

echo       Waiting for Streamlit to come online...
set STREAMLIT_OK=0
for /L %%i in (1,1,25) do (
    powershell -NoProfile -Command ^
        "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8501' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
    if !errorlevel! == 0 (
        set STREAMLIT_OK=1
        goto :streamlit_ready
    )
    <nul set /p ".=."
    timeout /t 2 >nul
)

:streamlit_ready
echo.
if "%STREAMLIT_OK%"=="0" (
    echo [ERROR] Streamlit did not respond at http://127.0.0.1:8501
    echo         Check the RAGE_STREAMLIT window for Python errors.
    pause & exit /b 1
)
echo       Streamlit is live at http://127.0.0.1:8501
echo.

:: ── Step 4: Launch ngrok ───────────────────────────────────

echo [4/4] Starting ngrok tunnel...
start "RAGE_NGROK" cmd /k "ngrok http 8501"

echo       Waiting for ngrok public URL...
set PUBLIC_URL=
for /L %%i in (1,1,30) do (
    for /f "usebackq delims=" %%u in (
        `powershell -NoProfile -Command ^
            "try { $j = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 2; ($j.tunnels | Where-Object { $_.public_url -like 'https://*' } | Select-Object -First 1 -ExpandProperty public_url) } catch { '' }"`
    ) do set PUBLIC_URL=%%u
    if defined PUBLIC_URL goto :got_url
    <nul set /p ".=."
    timeout /t 2 >nul
)

:got_url
echo.
echo.
echo ==========================================
echo           RAGE ENGINE IS LIVE
echo ==========================================
echo.
echo   Local:
echo     http://127.0.0.1:8501
echo.

if defined PUBLIC_URL (
    echo   Public share link:
    echo     !PUBLIC_URL!
    echo.
    echo   Send that link to anyone — works anywhere.
    echo   They can view RAGE in their browser.
) else (
    echo   [WARN] ngrok URL not captured automatically.
    echo   Check the RAGE_NGROK window for the https://... link.
)

echo.
echo ==========================================
echo   Keep both windows open:
echo     - RAGE_STREAMLIT  ^(dashboard server^)
echo     - RAGE_NGROK      ^(public tunnel^)
echo   Closing either will take RAGE offline.
echo ==========================================
echo.
pause
endlocal
