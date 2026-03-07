# 🚀 Meeting Intelligence Platform - Quick Start

## **One Command to Start Everything**

```bash
cd /Users/pandhari/Desktop/Meeting_Intelligence_Platform

# Activate virtual environment
source .venv/bin/activate

# Start the server
python run_server.py
```

Then open your browser to:
### **👉 http://localhost:8000**

---

## **What You'll See**

The modern web interface will load with:

### ✨ **Features**

1. **Upload Section** (Left Sidebar)
   - Drag & drop or click to select a meeting video
   - One-click upload and processing

2. **Processing Progress** (Main Panel)
   - Real-time step tracking (Audio Extraction → Transcription → Diarization → Embedding → MoM Generation)
   - Visual progress indicators with animated spinners

3. **Four Information Tabs**
   - 📝 **Transcript** - Full meeting transcript with speaker names and timestamps
   - 📋 **Minutes of Meeting** - Agenda, key points, decisions, and action items
   - 💬 **AI Chat** - Ask questions about the meeting using intelligent RAG search
   - 🎬 **Video Clips** - Generate and play exact segments from the meeting

4. **Video Player**
   - Stream the original meeting video
   - Play generated clips with timestamps

5. **Job History** (Left Sidebar)
   - View all previous meetings
   - Click to re-view results
   - Status indicator (Processing/Completed/Failed)

---

## **Quick Demo Flow**

1. **Start Server** → `python run_server.py`
2. **Open Browser** → `http://localhost:8000`
3. **Upload Video** → Click upload zone, select a `.mp4` file
4. **Watch Progress** → See real-time processing steps
5. **View Results** → Tabs show transcript, MoM, and chat interface
6. **Ask Questions** → Type in chat to get intelligent answers
7. **Generate Clips** → Click timestamps in transcript or MoM

---

## **Tech Stack Used**

- **Frontend**: Modern HTML5 + Tailwind CSS + Vanilla JS (No build required!)
- **Backend**: FastAPI (Python)
- **AI/ML**: Whisper (Transcription) + pyannote (Diarization) + FAISS (Search) + Claude/GPT (MoM)
- **Video**: FFmpeg (Processing and Clipping)

---

## **API Endpoints** (For Advanced Users)

All endpoints available at `/docs` for interactive testing:

### Upload & Process
- `POST /api/v1/upload` - Upload video/audio file
- `GET /api/v1/jobs` - List all jobs
- `GET /api/v1/jobs/{job_id}` - Get single job details

### Data Retrieval
- `GET /api/v1/jobs/{job_id}/transcript` - Get transcript
- `GET /api/v1/jobs/{job_id}/mom` - Get Minutes of Meeting
- `GET /api/v1/jobs/{job_id}/video` - Stream video

### Interaction
- `POST /api/v1/jobs/{job_id}/chat` - Ask questions (RAG-powered)
- `GET /api/v1/jobs/{job_id}/clips/{start}/{end}` - Generate video clip

---

## **Troubleshooting**

### **Port 8000 Already in Use**
```bash
# Kill existing process
lsof -ti:8000 | xargs kill -9

# Try again
python run_server.py
```

### **FFmpeg Not Found**
```bash
# macOS
brew install ffmpeg

# Ubuntu
sudo apt-get install ffmpeg

# Windows (WSL)
sudo apt-get install ffmpeg
```

### **Module Import Errors**
```bash
# Reinstall dependencies
pip install -e .

# Or
uv sync
```

---

## **File Locations**

- 🖥️ **Frontend**: `/static/app.html`
- 🔌 **Backend**: `/app/api.py`
- ⚙️ **Config**: `/config.py`
- 📦 **Pipelines**: `/src/`

---

## **For Your Professor Demo** 🎓

This system demonstrates:
- ✅ **End-to-end AI pipeline** - Video → Intelligence
- ✅ **Real-time processing** - Progress tracking
- ✅ **Smart retrieval** - RAG-based Q&A
- ✅ **Production-ready UI** - Professional interface
- ✅ **Research paper implementations** - AMMGS, AutoMeet, CLIP-It
- ✅ **Practical applications** - Meeting intelligence at scale

---

**Ready? Let's go!** 🎬

```bash
python run_server.py
```

Then visit: **http://localhost:8000** ✨
