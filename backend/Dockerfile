# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package management
RUN pip install uv

# Copy pyproject.toml and uv.lock
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv venv /opt/venv
RUN . /opt/venv/bin/activate && uv pip install -r pyproject.toml

# Copy backend code
COPY backend/ ./backend/

# Make virtual environment accessible
ENV PATH="/opt/venv/bin:$PATH"

# Expose port
EXPOSE 8000

# Run the FastAPI application
CMD ["uvicorn", "backend.routes:app", "--host", "0.0.0.0", "--port", "8000"]
