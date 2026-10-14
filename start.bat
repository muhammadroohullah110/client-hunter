@echo off
REM ============================================================
REM  TDSOCH — double-click this file to open the web app.
REM  It starts the local server and opens your browser.
REM  Close this black window (or press Ctrl+C) to stop it.
REM ============================================================
title TDSOCH
cd /d "%~dp0"

if not defined PY set PY=python
echo Starting TDSOCH... your browser will open in a moment.
echo (Keep this window open while you use it. Close it to stop.)
echo.
"%PY%" tdsoch.py serve
pause
