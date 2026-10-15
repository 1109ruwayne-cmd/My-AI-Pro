#!/usr/bin/env bash
# Start your AI on Mac / Linux:  ./start.sh   (then open http://localhost:8000)
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First start: setting things up (takes a minute)..."
  python3 -m venv .venv || { echo "Please install Python 3.10+ from https://www.python.org/downloads/"; exit 1; }
fi
. .venv/bin/activate
pip install -q --disable-pip-version-check -r requirements.txt
python app.py --open
