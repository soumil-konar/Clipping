#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if [ ! -d ".venv" ]; then
    echo "Virtual environment .venv not found. Creating..."
    python3 -m venv .venv
    ./.venv/bin/pip install --upgrade pip
fi

# Activate venv
source .venv/bin/activate

# Check if port 8000 is occupied
PORT=${PORT:-8000}
echo "Starting ClipForge Studio on http://localhost:$PORT ..."

python3 -m uvicorn backend.server:app --host 0.0.0.0 --port $PORT --reload
