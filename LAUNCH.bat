@echo off
title RAGE Engine V4
color 0A

echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║          RAGE ENGINE V4 — Launching...              ║
echo  ║          🏴󠁧󠁢󠁷󠁬󠁳󠁥 Cymru am byth 🐉                   ║
echo  ╚══════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

start http://localhost:8501
streamlit run app.py --server.port 8501 --server.headless false

pause
