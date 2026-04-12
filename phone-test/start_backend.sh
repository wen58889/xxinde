#!/usr/bin/env bash
# 从任意目录启动 backend
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

export PYTHONPATH="$BACKEND_DIR"
cd "$BACKEND_DIR"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
