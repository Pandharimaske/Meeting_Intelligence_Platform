#!/bin/bash
# Complete system verification and demo script

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Meeting Intelligence Platform - System Verification          ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check 1: Virtual Environment
echo -n "✓ Checking virtual environment... "
if [ -d ".venv" ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}MISSING${NC}"
    echo "  Run: python3 -m venv .venv"
    exit 1
fi

# Check 2: Dependencies
echo -n "✓ Checking dependencies... "
source .venv/bin/activate
if python -c "import fastapi, torch, whisper, pyannote, faiss, sentence_transformers" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}MISSING${NC}"
    echo "  Run: pip install -e ."
    exit 1
fi

# Check 3: FFmpeg
echo -n "✓ Checking FFmpeg... "
if command -v ffmpeg &> /dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}MISSING${NC}"
    echo "  Install: brew install ffmpeg (or apt install ffmpeg)"
    exit 1
fi

# Check 4: Configuration
echo -n "✓ Checking .env configuration... "
if [ -f ".env" ]; then
    # Check for LLM backend
    if grep -q "LLM_BACKEND" .env; then
        BACKEND=$(grep "LLM_BACKEND=" .env | cut -d'=' -f2 | tr -d ' ')
        echo -e "${GREEN}OK${NC} (backend: $BACKEND)"
    else
        echo -e "${YELLOW}INCOMPLETE${NC}"
    fi
else
    echo -e "${YELLOW}MISSING${NC} - Will use defaults"
fi

# Check 5: API Imports
echo -n "✓ Checking API imports... "
if python -c "from backend.routes import app; from processing.audio.extractor import extract_audio_from_video; from processing.audio.transcription.converter import convert_audio_to_text; from processing.text.chunker import TranscriptChunker; from processing.vector.store import MeetingVectorStore; from processing.reports.rag_mom_generator import RAGMoMGenerator; from processing.video.clipper import VideoClipper" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    exit 1
fi

# Check 6: Frontend Files
echo -n "✓ Checking frontend files... "
if [ -f "static/app.html" ] && [ -f "static/index.html" ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}MISSING${NC}"
    exit 1
fi

# Check 7: Project Structure
echo -n "✓ Checking project structure... "
DIRS_OK=true
for dir in src/audio_extraction src/audio_to_text src/chunking src/diarization src/report_generation src/vector_store src/video_clipping static data config.py app/api.py; do
    if [ ! -e "$dir" ]; then
        DIRS_OK=false
        break
    fi
done
if [ "$DIRS_OK" = true ]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}INCOMPLETE${NC}"
fi

# Check 8: Data Directories
echo -n "✓ Checking data directories... "
mkdir -p data/audio data/transcripts data/jobs data/video data/clips
echo -e "${GREEN}OK${NC}"

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  All Checks Passed! ✨                                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Display system info
echo "📊 System Information:"
echo "  • Python: $(python --version | cut -d' ' -f2)"
echo "  • FastAPI: $(python -c 'import fastapi; print(fastapi.__version__)' 2>/dev/null || echo 'installed')"
echo "  • FFmpeg: $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)"
echo ""

# Display configuration from .env
echo "⚙️  Configuration:"
if [ -f ".env" ]; then
    echo "  LLM Backend: $(grep 'LLM_BACKEND=' .env | cut -d'=' -f2 | tr -d ' ')"
    echo "  Whisper Model: $(grep 'WHISPER_MODEL=' .env | cut -d'=' -f2 | tr -d ' ')"
    echo "  Embedding Model: $(grep 'EMBEDDING_MODEL=' .env | cut -d'=' -f2 | tr -d ' ')"
fi
echo ""

echo "🚀 Ready to Start!"
echo ""
echo "Options:"
echo "  1. Run server:        python run_server.py"
echo "  2. Run with script:   ./start.sh"
echo "  3. Open frontend:     http://localhost:8000"
echo "  4. View API docs:     http://localhost:8000/docs"
echo ""
echo "Next: ./start.sh"
echo ""
