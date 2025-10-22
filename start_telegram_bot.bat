@echo off
REM Change directory to the project root
cd /d "C:\Users\phill\ttuex-bot"

REM Activate the virtual environment
call .\.venv\Scripts\activate.bat

REM Start the Telegram bot in the background
start "TTUEX Bot" pythonw -m ttuex_bot.cli run-telegram