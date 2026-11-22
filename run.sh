#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run: creating virtualenv and installing dependencies..."
  if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
  "$PY" -m venv .venv || { echo "ERROR: venv failed (Debian/Ubuntu: sudo apt install python3-venv python3-pip)"; exit 1; }
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -r requirements.txt
fi
exec ./.venv/bin/python chess_shorts_studio.py
