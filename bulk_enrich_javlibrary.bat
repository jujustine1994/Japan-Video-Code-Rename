@echo off
cd /d "%~dp0"
call venv\Scripts\activate
python scripts\bulk_enrich_javlibrary.py %*
pause
