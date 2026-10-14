@echo off
REM ───────────────────────────────────────────────────────────────────────────
REM  CHunter nightly brain — find -> audit -> score.  Zero cost, no LLM.
REM  Point Windows Task Scheduler at this file to run it ~2 AM while you sleep.
REM  (Task Scheduler setup is in README.md.)
REM ───────────────────────────────────────────────────────────────────────────
setlocal
cd /d "%~dp0"

REM Use the Python that has the deps. If you made a venv, point to it here:
REM set PY=.venv\Scripts\python.exe
if not defined PY set PY=python

echo [%date% %time%] CHunter nightly run starting >> logs\nightly.log
"%PY%" run_step1.py >> logs\nightly.log 2>&1
echo [%date% %time%] CHunter nightly run finished (exit %errorlevel%) >> logs\nightly.log

endlocal
