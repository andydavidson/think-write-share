#!/usr/bin/env bash
# run.sh — start the Think-Write-Share app using a Python virtual environment.
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate

echo "Installing/checking dependencies..."
pip install -q -r requirements.txt

echo "Starting server at http://localhost:8000"
exec uvicorn app:app --host 0.0.0.0 --port 8000 --reload
