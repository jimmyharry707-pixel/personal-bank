#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
    echo "Virtual environment not found. Create it and install requirements first."
    echo "python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi
exec .venv/bin/python -m personalbank
