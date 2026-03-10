# Contributing to Meeting Intelligence Platform

Thank you for your interest in contributing! This document provides guidelines and instructions for developers.

## Development Setup

### Prerequisites
- Python 3.11+
- FFmpeg
- Git
- Virtual environment manager (venv or conda)

### Installation for Development

```bash
# Clone repository
git clone https://github.com/Pandharimaske/Meeting_Intelligence_Platform.git
cd Meeting_Intelligence_Platform

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode with all extras
pip install -e ".[dev]"
# Or with UV
uv sync --all-extras
```

### Project Structure

```
src/
├── audio_extraction/        # FFmpeg audio extraction
├── audio_to_text/          # Whisper ASR
├── chunking/               # Text chunking strategies
├── diarization/            # Speaker identification
├── report_generation/      # MoM generation with RAG
├── vector_store/           # FAISS embeddings
└── video_clipping/         # FFmpeg video clipping

app/
├── api.py                  # FastAPI application
└── __init__.py

static/
└── app.html                # Web UI

config.py                   # Settings management
run_server.py              # Application entry point
```

## Development Workflow

### 1. Creating a Feature Branch

```bash
git checkout -b feature/your-feature-name
# Or for bug fixes:
git checkout -b fix/issue-title
```

### 2. Making Changes

Follow these guidelines:

- **Code Style**: Use black for formatting, isort for imports
- **Type Hints**: Add type hints to all functions
- **Docstrings**: Use Google-style docstrings
- **Tests**: Add tests for new functionality
- **Commits**: Use clear, descriptive commit messages

### 3. Code Quality

Format and check your code:

```bash
# Format code
black src/ app/ config.py

# Sort imports
isort src/ app/ config.py

# Type checking
mypy --strict src/ app/

# Linting
pylint src/ app/
```

### 4. Running Tests

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src --cov=app

# Specific test file
pytest tests/test_audio_extraction.py
```

### 5. Commit and Push

```bash
git add .
git commit -m "feat: Add feature description

Detailed explanation of changes if needed.
"
git push origin feature/your-feature-name
```

### 6. Create Pull Request

- Open PR on GitHub
- Fill out PR template
- Ensure CI/CD passes
- Request review from maintainers

## Code Standards

### Python

```python
# Good: Type hints and docstrings
def process_audio(file_path: str, sample_rate: int = 16000) -> np.ndarray:
    """
    Extract audio from file and resample to target sample rate.
    
    Args:
        file_path: Path to audio file
        sample_rate: Target sample rate in Hz
        
    Returns:
        Audio array with shape (channels, samples)
        
    Raises:
        FileNotFoundError: If file doesn't exist
        AudioError: If decoding fails
    """
    ...
```

### API Routes

```python
# Good: Clear documentation and error handling
@app.post("/api/v1/upload", tags=["Upload"])
async def upload_video(file: UploadFile = File(...)) -> Dict:
    """
    Upload and process a meeting video.
    
    Returns job_id for tracking progress.
    """
    if not file.filename.endswith(('.mp4', '.mov', '.avi')):
        raise HTTPException(status_code=400, detail="Invalid file format")
    ...
```

## Testing

### Test Structure

```python
# tests/test_audio_extraction.py
import pytest
from src.audio_extraction.extractor import extract_audio_from_video

@pytest.fixture
def sample_video():
    """Fixture providing test video path."""
    return "tests/data/sample.mp4"

def test_extract_audio(sample_video):
    """Test audio extraction works correctly."""
    result = extract_audio_from_video(sample_video)
    assert result is not None
    assert result.shape[0] == 1  # mono
```

### Coverage Requirements

- Aim for >80% code coverage
- All public APIs must be tested
- Error cases must be covered

## Documentation

### README
- Keep up to date with major changes
- Include example usage
- Document API changes

### Docstrings
- Use Google-style format
- Include Args, Returns, Raises
- Add examples for complex functions

### Commit Messages
- Use conventional commits
- Format: `type(scope): description`
- Examples:
  - `feat(chunking): Add recursive chunking strategy`
  - `fix(api): Handle missing job ID gracefully`
  - `docs: Update installation instructions`

## Performance Optimization

### Guidelines

1. **Profiling First**
   ```bash
   python -m cProfile -s cumtime run_server.py
   ```

2. **Async Operations**
   - Use `async/await` for I/O operations
   - Keep CPU-bound work in thread pool

3. **Caching**
   - Cache expensive computations
   - Use Redis for distributed caching

4. **Database**
   - Add indexes for frequently queried fields
   - Use connection pooling

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync

COPY . .

CMD ["python", "run_server.py"]
```

### Environment Variables

All configuration via `.env` file:

```bash
# Copy template
cp .env.example .env

# Fill in your values
nano .env
```

## Troubleshooting Development

### Virtual Environment Issues

```bash
# Recreate environment
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Import Errors

```bash
# Reinstall in development mode
pip install -e .
```

### Port Already in Use

```bash
lsof -ti:8000 | xargs kill -9
```

## Release Process

### Version Bumping

```bash
# Update version in pyproject.toml
# Update CHANGELOG.md
git tag v1.2.3
git push origin v1.2.3
```

## Getting Help

- **Questions:** GitHub Discussions
- **Bugs:** GitHub Issues
- **Documentation:** See docs/ folder
- **Chat:** GitHub Issues

## Code of Conduct

- Be respectful and inclusive
- Provide constructive feedback
- Follow project values

## License

By contributing, you agree your code will be licensed under MIT.

---

Thank you for making Meeting Intelligence Platform better! 🙏
