# 🚀 Quick Start Guide - Meeting Intelligence Platform

## 📋 Prerequisites

Before you start, ensure you have:
- **Python 3.11+** installed
- **FFmpeg** installed (for video processing)
- **API key** for LLM (OpenRouter, Anthropic, or OpenAI)
- **HuggingFace token** (optional, for speaker diarization)

### Install FFmpeg

**Windows (using winget):**
```bash
winget install FFmpeg
```

**macOS (using Homebrew):**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install ffmpeg
```

---

## ⚙️ Setup

### 1. Install Dependencies

```bash
cd Meeting_Intelligence_Platform

# Using UV (recommended - fast)
uv sync

# Or using pip
pip install -e .
```

### 2. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your API keys
nano .env
# or
code .env
```

**Required for chat to work:**
```env
LLM_BACKEND=openrouter          # or: anthropic, openai
OPENROUTER_API_KEY=sk-or-...    # Your API key
LLM_MODEL=arcee-ai/trinity-large...
```

**Optional for speaker diarization:**
```env
ENABLE_DIARIZATION=true
HUGGINGFACE_TOKEN=hf_...
```

---

## 🎯 Running the Server

### Start the Application

```bash
python run_server.py
```

You should see:
```
✓ FAISS store loaded — 500 vectors
✓ Loaded 3 jobs from cache
INFO:     Uvicorn running on http://localhost:8000
```

### Open in Browser

Navigate to: **http://localhost:8000**

You should see the beautiful dark UI with:
- 📤 Upload zone on the left
- 📁 Recent Meetings sidebar
- 🎥 Main content area (empty initially)

---

## 📹 Usage - Step by Step

### Step 1: Upload a Meeting

#### Option A: Using Web Interface (Recommended)

1. **Click the upload zone** or drag-and-drop a file
2. **Supported formats:**
   - Video: `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`
   - Audio: `.mp3`, `.wav`, `.m4a`
   - Transcript: `.srt`, `.vtt`, `.txt`

3. **Click "Process Meeting"** button
4. Watch the progress bar as the pipeline processes:
   - 🎤 Transcribing (15-30 min for 1 hour video)
   - 📝 Chunking (1-2 min)
   - 🔍 Indexing (2-3 min)
   - 📋 Generating Minutes (2-3 min)

#### Option B: Using API (Command Line)

```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -F "file=@meeting.mp4"

# Response:
# {
#   "job_id": "uuid-here",
#   "status": "uploading",
#   "message": "Processing started..."
# }
```

### Step 2: Wait for Processing ⏳

Monitor progress in the UI:
- **Transcribing** → Audio converted to text
- **Chunking** → Text split into semantic chunks
- **Indexing** → Chunks embedded and indexed for search
- **Generating MoM** → AI creates minutes of meeting

Once **completed** ✅, you'll see:
- ✅ Green checkmark in pipeline
- 📊 3 tabs appear: Transcript | Minutes | AI Chat

---

## 👀 View Results

### Tab 1: Transcript

**Shows:**
- ✅ Full meeting transcript with timestamps
- 👤 Speaker labels (Speaker 0, Speaker 1, etc.)
- ✂️ Scissors button to create clips from segments
- ⏱️ Clickable timestamps to seek in video

**Example:**
```
[00:01:30] Speaker 0: Thanks everyone for joining...
[00:02:15] Speaker 1: Great, let's start with the agenda...
[Click to seek] [▂ Create Clip]
```

---

### Tab 2: Minutes of Meeting 📋

**Contains:**
- 📌 **Agenda** - Main topics discussed
- 🗝️ **Key Points** - Important statements with timestamps
- ✅ **Decisions** - What was decided
- 📌 **Action Items** - Tasks assigned to people
- 📝 **Summary** - Overall meeting recap

**Example:**
```
## AGENDA
- Q3 Budget Planning
- Timeline Review
- Team Expansion

## KEY DECISIONS
- Approved $500K budget [00:15:30]
- Selected AWS over GCP [00:18:45]

## ACTION ITEMS
- John (Engineering): Prepare migration plan by Friday [00:22:00]
- Sarah (Product): Feature prioritization by Wednesday [00:23:30]
```

---

### Tab 3: AI Chat 💬

**Ask questions about the meeting!**

#### Text-Only Questions (Default)

Ask and get answers:
```
You:  "What were the key decisions?"

AI:  "The team made three key decisions:
    
    ## Decisions
    
    1. **Approved** $500K budget for Q2
    2. **Selected** AWS for infrastructure
    3. **Decided** on 6-week MVP timeline
    
    [00:15:30] [00:18:45] [00:21:10]"
```

**Try asking:**
- "What was decided about the budget?"
- "Who is responsible for the action items?"
- "Summarize the meeting"
- "What did John say about the timeline?"

---

#### Clip-Request Questions (Video Only)

Ask to see video segments:
```
You:  "Show me the budget discussion"
      or
      "Play the part about timeline"
      or
      "Can you show me where they decided on AWS?"

AI:  Answer + [Inline Video Clip Cards]
     
     [00:15:30 – 00:16:45] | John Smith
     "We need $500k for Q2 based on..."
     [▶ Play Clip]  [→ Seek]
```

**Keywords that trigger clip display:**
- show, play, display, clip, video, segment
- watch, see, recording, footage, playback
- visual, screenshot, screen, whiteboard
- "skip to", "jump to", "go to", "part where", "moment when"

**Example clip request:**
```
You:  "Show me when they talked about marketing"
You:  "Play the decision about the deadline"
You:  "Can you show the part about budget?"
```

---

## 🎬 Create Video Clips

### Method 1: From Transcript Segment

1. Open **Transcript tab**
2. Find a segment you like
3. Click the **scissors button ✂️** on the segment
4. Clip plays in inline card with download option

### Method 2: From Chat Sources

1. Ask for clips in **AI Chat**
2. Relevant segments appear as cards
3. Click **▶ Play Clip** button
4. Video clip generated and plays instantly

### Method 3: From Clips Tab

1. Click **Clips tab** (if video available)
2. Browse all indexed segments
3. Select and play any clip

---

## 💾 Reusing Previous Meetings (Caching)

### Find Previous Meetings

1. **Left sidebar** shows "Recent Meetings"
2. All previous meetings are listed with:
   - ✅ Completed (green dot)
   - ⏳ Processing (amber dot)
   - ❌ Failed (red dot)

### Open a Cached Meeting

1. **Click any meeting** in sidebar
2. **Instantly loads** (no re-processing!)
3. All tabs available:
   - Transcript ✅
   - Minutes ✅
   - Chat ✅ (instant search from cached vectors)

### Life Cycle

```
Upload video
    ↓
[Processing...]  5-10 minutes
    ↓
✅ Completed & cached
    ↓
Refresh browser / Restart server
    ↓
✅ Meeting still there!
    ↓
Click to open
    ↓
⚡ Instant load (< 1 second)
```

### Clear Cache (if needed)

Delete specific meeting:
```bash
rm -rf data/jobs/{job_id}
```

Or clear all:
```bash
rm -rf data/jobs/jobs.json
```

---

## 🔍 Advanced: Using the API

### Get All Jobs

```bash
curl "http://localhost:8000/api/v1/jobs"
```

Response:
```json
{
  "jobs": [
    {
      "job_id": "uuid",
      "status": "completed",
      "filename": "meeting.mp4",
      "created_at": "2026-03-10T10:30:00",
      "transcript_available": true,
      "mom_available": true
    }
  ]
}
```

### Get Specific Job Details

```bash
curl "http://localhost:8000/api/v1/jobs/{job_id}"
```

### Ask a Chat Question

```bash
curl -X POST "http://localhost:8000/api/v1/jobs/{job_id}/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What were the decisions?",
    "history": []
  }'
```

Response:
```json
{
  "answer": "The team made 3 decisions...",
  "sources": [
    {
      "start_timestamp": "00:15:30",
      "text": "...",
      "score": 0.95,
      "primary_speaker": "John"
    }
  ],
  "wants_clip": false
}
```

### Generate a Video Clip

```bash
curl "http://localhost:8000/api/v1/jobs/{job_id}/clips/600/750"
# Returns: {"clip_url": "/clips/...", "start_time": 600, "end_time": 750}
```

---

## 📊 File Organization

After processing, files are organized:

```
data/
├── jobs/
│   ├── jobs.json                 # Job database (persistent)
│   └── {job_id}/
│       ├── meeting.mp4           # Original video
│       ├── chunks.json           # Semantic chunks
│       ├── vector_store/         # FAISS index (for fast search)
│       ├── transcripts/
│       │   ├── transcript.json   # Full transcript
│       │   └── transcript.txt    # Plain text
│       └── mom.json              # Minutes of Meeting
├── audio/                        # Extracted audio
├── transcripts/                  # Backup transcripts
├── clips/                        # Generated video clips
└── videos/                       # Uploaded videos
```

---

## 🛠️ Troubleshooting

### Issue: "No video for this job"

**Cause:** You uploaded audio or SRT file (no video to clip)
**Solution:** Upload an MP4/MOV video file for clipping support

### Issue: Chat says "No vector store found"

**Cause:** Job not fully processed yet
**Solution:** Wait for pipeline to complete (check green checkmark)

### Issue: Processing very slow

**Cause:** Large video file or slow CPU
**Solution:**
- For testing, use short video clips (< 5 min)
- GPU acceleration coming in future version

### Issue: "API key invalid"

**Cause:** Incorrect LLM credentials in .env
**Solution:**
1. Check `.env` has correct API key
2. Make sure key has right permissions
3. Restart server: `python run_server.py`

### Clear Cache and Start Fresh

```bash
# Option 1: Delete all jobs
rm -rf data/jobs/jobs.json

# Option 2: Delete everything
rm -rf data/

# Then restart
python run_server.py
```

---

## 📱 Browser Tips

- **Best experience:** Chrome, Edge, Safari (latest)
- **Mobile:** Responsive design works on tablets
- **Dark theme:** Built-in (no light mode yet)
- **Keyboard:** Press `Enter` in chat to send messages

---

## 🚀 Next Steps

1. ✅ Start server: `python run_server.py`
2. ✅ Open browser: `http://localhost:8000`  
3. ✅ Upload a meeting video (test: < 5 min video)
4. ✅ Wait for processing
5. ✅ Explore tabs: Transcript → Minutes → Chat
6. ✅ Ask questions in chat
7. ✅ Create clips from segments
8. ✅ Refresh browser (everything cached!)

---

## 💡 Pro Tips

- **Bookmark common questions** you ask meetings
- **Use Chrome DevTools** to monitor API calls
- **Save clips** by right-clicking video and "Save video"
- **Export transcript** as JSON from API
- **Batch process** meetings using API (coming soon)

---

## 📞 Need Help?

Check the full [README.md](README.md) for technical details
Or review [CONTRIBUTING.md](CONTRIBUTING.md) for development setup

Happy meeting analyzing! 🎉
