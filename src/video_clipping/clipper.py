"""
Video Clipping Module for Meeting Intelligence Platform.

Handles slicing original video files into short clips based on timestamp ranges,
with audio-aware padding to prevent cutting off speech mid-word.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple


class VideoClipper:
    """
    Clips video segments with padding to ensure natural audio boundaries.

    Research Gap #3 Fix: Audio-aware padding prevents clips from cutting off
    mid-word or mid-breath. Uses start-2s to end+2s padding.
    """

    def __init__(self, clips_dir: str = "data/clips"):
        """
        Initialize the video clipper.

        Args:
            clips_dir: Directory to store generated clips
        """
        self.clips_dir = Path(clips_dir)
        self.clips_dir.mkdir(parents=True, exist_ok=True)

    def clip_video(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        job_id: str,
        padding_seconds: float = 2.0
    ) -> Optional[str]:
        """
        Clip a video segment with padding.

        Args:
            video_path: Path to the original video file
            start_time: Start time in seconds
            end_time: End time in seconds
            job_id: Job ID for organizing clips
            padding_seconds: Seconds to pad before/after (default 2.0)

        Returns:
            Path to the clipped video file, or None if failed
        """
        video_path = Path(video_path)
        if not video_path.exists():
            print(f"Video file not found: {video_path}")
            return None

        # Apply padding (don't go below 0)
        padded_start = max(0, start_time - padding_seconds)
        padded_end = end_time + padding_seconds
        duration = padded_end - padded_start

        # Create job-specific clip directory
        job_clip_dir = self.clips_dir / job_id
        job_clip_dir.mkdir(exist_ok=True)

        # Generate output filename
        start_str = f"{int(padded_start//3600):02d}:{int((padded_start%3600)//60):02d}:{padded_start%60:05.2f}"
        clip_filename = f"clip_{start_str.replace(':', '-')}_{duration:.1f}s.mp4"
        output_path = job_clip_dir / clip_filename

        # Skip if clip already exists
        if output_path.exists():
            return str(output_path)

        try:
            # FFmpeg command for fast copying (no re-encoding)
            cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-ss", str(padded_start),
                "-t", str(duration),
                "-c", "copy",  # Fast copy, no re-encoding
                "-avoid_negative_ts", "make_zero",
                "-y",  # Overwrite output
                str(output_path)
            ]

            print(f"Clipping video: {start_time:.1f}s - {end_time:.1f}s (padded: {padded_start:.1f}s - {padded_end:.1f}s)")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # 1 minute timeout
            )

            if result.returncode == 0:
                print(f"Clip created: {output_path}")
                return str(output_path)
            else:
                print(f"FFmpeg failed: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            print("FFmpeg timed out")
            return None
        except Exception as e:
            print(f"Error clipping video: {e}")
            return None

    def get_clip_url(self, clip_path: str) -> str:
        """
        Convert clip path to URL for serving.

        Args:
            clip_path: Absolute path to clip file

        Returns:
            Relative URL path for the clip
        """
        # Convert to relative path from clips directory
        clip_path = Path(clip_path)
        relative_path = clip_path.relative_to(self.clips_dir)
        return f"/clips/{relative_path}"