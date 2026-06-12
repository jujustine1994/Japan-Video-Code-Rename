@echo off
cd /d "%~dp0"
call venv\Scripts\activate
python scripts\bulk_enrich_by_actress.py %*
pause
