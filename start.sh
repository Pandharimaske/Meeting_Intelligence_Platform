#!/bin/bash
# Meeting Intelligence Platform - One-Click Startup Script
# Usage: ./start.sh

cd "$(dirname "$0")"

echo "🚀 Meeting Intelligence Platform"
echo "=================================="
echo ""

# Check if virtual env exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found"
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Check if dependencies are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip install -e . > /dev/null 2>&1
fi

# Check if FFmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg not found. Install with:"
    echo "   macOS: brew install ffmpeg"
    echo "   Ubuntu: sudo apt install ffmpeg"
    echo ""
fi

# Clear any lingering processes on port 8000
echo "🔌 Checking port 8000..."
if lsof -i :8000 > /dev/null 2>&1; then
    echo "⚠️  Port 8000 in use, attempting to free it..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Start the server
echo ""
echo "✅ Starting server..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 Frontend:  http://localhost:8000"
echo "📚 API Docs:  http://localhost:8000/docs"
echo "🔌 API Base:  http://localhost:8000/api/v1"
echo ""
echo "Press Ctrl+C to stop the server"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python run_server.py
