#!/bin/bash
# macOS launcher: double-click to start the app (opens http://127.0.0.1:8765 in your browser).
cd "$(dirname "$0")"
python3 mc_app.py
read -n 1 -s -r -p "Press any key to close"
