#!/bin/bash
# Meeting Intelligence Platform - One-Click Startup Script
# Usage: ./scripts/start.sh  (run from project root)

cd "$(dirname "$0")/.."

echo "🚀 Meeting Intelligence Platform"
echo "=================================="
echo ""

# ── Python venv ───────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

if ! python -c "import fastapi" 2>/dev/null; then
    echo "📦 Installing Python dependencies..."
    pip install -e . > /dev/null 2>&1
fi

# ── FFmpeg check ──────────────────────────────────────────────────
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg not found."
    echo "   macOS:  brew install ffmpeg"
    echo "   Ubuntu: sudo apt install ffmpeg"
    echo ""
fi

# ── React build (only if src/ is newer than build/) ───────────────
NEEDS_BUILD=false
if [ ! -d "frontend/build" ] || [ ! -f "frontend/build/index.html" ]; then
    NEEDS_BUILD=true
elif [ -n "$(find frontend/src -newer frontend/build/index.html -name '*.js' -o -newer frontend/build/index.html -name '*.css' 2>/dev/null | head -1)" ]; then
    echo "🔄 Source files changed since last build — rebuilding..."
    NEEDS_BUILD=true
fi

if [ "$NEEDS_BUILD" = true ]; then
    echo "🔨 Building React frontend..."
    cd frontend
    if ! command -v npm &> /dev/null; then
        echo "❌ npm not found. Install Node.js from https://nodejs.org"
        exit 1
    fi
    npm install --silent
    npm run build
    cd ..
    echo "✅ React build complete"
fi

# ── Port check ────────────────────────────────────────────────────
if lsof -i :8000 > /dev/null 2>&1; then
    echo "⚠️  Port 8000 in use, freeing it..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# ── Start server ──────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🌐  http://localhost:8000"
echo "📚  http://localhost:8000/docs"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python scripts/run_server.py
