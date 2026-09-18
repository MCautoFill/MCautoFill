#!/bin/bash
# macOS launcher: double-click to start the app (opens http://127.0.0.1:8765 in your browser).
# The bundled mpc-autofill tool needs Python 3.11 or newer.
cd "$(dirname "$0")"

# Prefer the project virtual environment if it exists.
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  # Otherwise find the newest Python 3.11+ on this machine.
  PY=""
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      PY="$candidate"
      break
    fi
  done
  if [ -z "$PY" ]; then
    echo "MC Autofill needs Python 3.11 or newer, but none was found."
    echo "Install it from https://www.python.org/downloads/ and run this launcher again."
    read -n 1 -s -r -p "Press any key to close"
    exit 1
  fi
  echo "Creating the .venv virtual environment with $PY and installing requirements..."
  "$PY" -m venv .venv && .venv/bin/python -m pip install -q -r requirements.txt
  PY=".venv/bin/python"
fi

"$PY" mc_app.py
read -n 1 -s -r -p "Press any key to close"
