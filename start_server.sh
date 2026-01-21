#!/bin/bash
# Start the FastAPI server

cd "$(dirname "$0")"
echo "Starting server on http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""

python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
