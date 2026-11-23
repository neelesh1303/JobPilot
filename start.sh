#!/usr/bin/env bash
# Start the JobPilot desktop UI (macOS / Linux) and open it in the browser.
cd "$(dirname "$0")"
( sleep 1.5; (command -v xdg-open >/dev/null && xdg-open http://127.0.0.1:5050) || (command -v open >/dev/null && open http://127.0.0.1:5050) ) >/dev/null 2>&1 &
exec python3 app.py
