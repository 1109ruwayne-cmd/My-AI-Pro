@echo off
rem Start your AI on Windows: double-click this file. Your browser opens automatically.
cd /d "%~dp0"
if not exist .venv (
  echo First start: setting things up, this takes a minute...
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist .venv\Scripts\activate.bat (
  echo Please install Python 3.10 or newer from https://www.python.org/downloads/ and tick "Add Python to PATH".
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
pip install -q --disable-pip-version-check -r requirements.txt
python app.py --open
pause
