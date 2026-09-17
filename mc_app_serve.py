"""Run the app without auto-opening a browser tab (used by the preview/launch config)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mc_app
mc_app.app.run(host="127.0.0.1", port=8765, debug=False)
