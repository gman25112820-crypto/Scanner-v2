@echo off
title RAGE Engine V4 — Setup
color 0A

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║          RAGE ENGINE V4 — One-Click Setup           ║
echo  ║          Rob And Gareth Engine  🏴󠁧󠁢󠁷󠁬󠁳󠁥              ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

:: ── Set working directory to scanner_v2 ──────────────────────────────────────
cd /d "%~dp0"
echo [1/7] Working directory: %CD%
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
echo [2/7] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ❌ Python not found.
    echo     Download from https://python.org and re-run this script.
    echo.
    pause
    exit /b 1
)
python --version
echo  ✅ Python found.
echo.

:: ── Create strategies folder if missing ──────────────────────────────────────
echo [3/7] Checking folder structure...
if not exist "strategies" mkdir strategies
if not exist "output" mkdir output
if not exist "output\trades" mkdir output\trades
if not exist "output\journal" mkdir output\journal
if not exist "output\backtest" mkdir output\backtest
if not exist "output\allocator" mkdir output\allocator
echo  ✅ Folders ready.
echo.

:: ── Move mtf_strategies.py into strategies/ ───────────────────────────────────
echo [4/7] Placing files...

if exist "mtf_strategies.py" (
    move /Y "mtf_strategies.py" "strategies\mtf_strategies.py" >nul
    echo  ✅ mtf_strategies.py → strategies\
) else if exist "strategies\mtf_strategies.py" (
    echo  ✅ mtf_strategies.py already in strategies\
) else (
    echo  ⚠️  mtf_strategies.py not found — drop it in scanner_v2\ and re-run
)

:: All other .py files stay in root — confirm they're present
set FILES_OK=1
for %%F in (
    broker_alpaca.py
    broker_manager.py
    rage_signal_bridge.py
    risk_manager.py
    signal_filter.py
    smart_order_router.py
    trade_logger.py
    trade_journal.py
    performance_dashboard.py
    ai_signal_reasoner.py
    news_sentiment.py
    earnings_aware.py
    options_flow.py
    darkpool_feed.py
    macro_calendar.py
    insider_activity.py
    portfolio_heat.py
    monte_carlo.py
    telegram_bot.py
    discord_bot.py
    daily_report.py
    ngrok_launcher.py
    app.py
) do (
    if not exist "%%F" (
        echo  ⚠️  Missing: %%F
        set FILES_OK=0
    )
)

if "%FILES_OK%"=="1" (
    echo  ✅ All module files present.
) else (
    echo.
    echo  Some files are missing. Download them from Claude and drop into:
    echo  %CD%
    echo.
)
echo.

:: ── Create .env if it doesn't exist ──────────────────────────────────────────
echo [5/7] Setting up .env...
if not exist ".env" (
    if exist ".env.template" (
        copy ".env.template" ".env" >nul
        echo  ✅ .env created from template.
        echo.
        echo  ╔══════════════════════════════════════════════════════╗
        echo  ║  IMPORTANT — Edit .env before launching!            ║
        echo  ║                                                      ║
        echo  ║  Required:                                           ║
        echo  ║    ALPACA_API_KEY    — from alpaca.markets (free)   ║
        echo  ║    ALPACA_SECRET_KEY — same                         ║
        echo  ║    RAGE_PASSWORD     — change from RAGE2024         ║
        echo  ║                                                      ║
        echo  ║  Optional but recommended:                           ║
        echo  ║    ANTHROPIC_API_KEY — for AI signal analysis       ║
        echo  ║    FINNHUB_API_KEY   — for news/earnings/insider    ║
        echo  ║    TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID            ║
        echo  ╚══════════════════════════════════════════════════════╝
        echo.
        echo  Opening .env for you to fill in now...
        timeout /t 2 >nul
        notepad .env
    ) else (
        echo  Creating .env from scratch...
        (
            echo # RAGE ENGINE V4 — Environment Config
            echo # Fill these in before launching
            echo.
            echo ALPACA_API_KEY=your_alpaca_api_key_here
            echo ALPACA_SECRET_KEY=your_alpaca_secret_key_here
            echo ALPACA_PAPER=true
            echo.
            echo RAGE_PASSWORD=change_me_before_sharing
            echo.
            echo ANTHROPIC_API_KEY=your_anthropic_key_here
            echo FINNHUB_API_KEY=your_finnhub_key_here
            echo.
            echo TELEGRAM_BOT_TOKEN=
            echo TELEGRAM_CHAT_ID=
            echo.
            echo DISCORD_WEBHOOK_URL=
            echo.
            echo REPORT_EMAIL_FROM=
            echo REPORT_EMAIL_TO=
            echo REPORT_EMAIL_PASSWORD=
            echo.
            echo NGROK_AUTH_TOKEN=
        ) > .env
        echo  ✅ .env created.
        notepad .env
    )
) else (
    echo  ✅ .env already exists — skipping.
)
echo.

:: ── Install dependencies ──────────────────────────────────────────────────────
echo [6/7] Installing Python packages...
echo  This may take 2-3 minutes on first run...
echo.

if exist "requirements.txt" (
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo.
        echo  ⚠️  Some packages failed. Trying individually...
        pip install streamlit pandas numpy plotly python-dotenv --quiet
        pip install alpaca-py --quiet
        pip install anthropic --quiet
        pip install yfinance finnhub-python requests --quiet
        pip install pyngrok --quiet
    )
    echo  ✅ Packages installed.
) else (
    echo  ⚠️  requirements.txt not found — installing core packages only...
    pip install streamlit pandas numpy plotly python-dotenv alpaca-py anthropic yfinance requests --quiet
    echo  ✅ Core packages installed.
)
echo.

:: ── Launch dashboard ──────────────────────────────────────────────────────────
echo [7/7] Launching RAGE Engine V4...
echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║  Dashboard starting at http://localhost:8501        ║
echo  ║                                                      ║
echo  ║  Press Ctrl+C in this window to stop.               ║
echo  ║  🏴󠁧󠁢󠁷󠁬󠁳󠁥 Cymru am byth 🐉                           ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

timeout /t 2 >nul
start http://localhost:8501
streamlit run app.py --server.port 8501 --server.headless false

echo.
echo  RAGE Engine stopped.
pause
