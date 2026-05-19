#!/usr/bin/env bash
# SentinAI launcher — activates the venv and starts the app
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
source .venv/bin/activate
exec python app.py "$@"
