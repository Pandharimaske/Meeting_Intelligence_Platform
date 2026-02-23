#!/usr/bin/env python3
"""
Setup script to initialize the Meeting Intelligence Platform API.
Run this once to set up the environment.
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd, description):
    """Run a shell command and report status."""
    print(f"\n{'='*60}")
    print(f"📦 {description}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(cmd, check=True, shell=True)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed: {e}")
        return False

def main():
    """Main setup routine."""
    print(f"\n{'='*60}")
    print("Meeting Intelligence Platform - Setup")
    print(f"{'='*60}")
    
    # Create data directories
    print("\n📁 Creating data directories...")
    for dir_path in ["data/videos", "data/audio", "data/transcripts", "data/jobs"]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {dir_path}")
    
    # Install dependencies
    if not run_command(
        f"{sys.executable} -m pip install -e .",
        "Installing dependencies"
    ):
        return False
    
    print(f"\n{'='*60}")
    print("✓ Setup Complete!")
    print(f"{'='*60}")
    print("\nNext steps:")
    print("1. Start the API server:")
    print("   python run_server.py")
    print("\n2. Open interactive API docs:")
    print("   http://localhost:8000/docs")
    print("\n3. Upload a video:")
    print("   curl -X POST http://localhost:8000/api/v1/videos/upload \\")
    print("     -F 'file=@your_video.mp4'")
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    main()
