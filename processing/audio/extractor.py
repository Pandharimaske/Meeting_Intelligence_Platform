import subprocess
from pathlib import Path


class AudioExtractor:
    """Extract audio from video files using ffmpeg command-line tool."""

    def __init__(self, output_dir: str = "data/audio"):
        """
        Initialize the AudioExtractor.

        Args:
            output_dir: Directory to save extracted audio files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_audio(self, video_path: str, output_format: str = "wav") -> str:
        """
        Extract audio from a video file using ffmpeg subprocess.

        Args:
            video_path: Path to the video file
            output_format: Output audio format (wav recommended for Whisper)

        Returns:
            Path to the extracted audio file

        Raises:
            FileNotFoundError: If video file doesn't exist
            RuntimeError: If audio extraction fails
        """
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Generate output filename based on input video name
        output_name = f"{video_path.stem}.{output_format}"
        output_path = self.output_dir / output_name

        try:
            # Use ffmpeg command-line to extract audio
            # -ac 1 = mono, -ar 16000 = 16kHz (required by WhisperX), -acodec pcm_s16le
            cmd = [
                "ffmpeg",
                "-i", str(video_path),
                "-ac", "1",              # Mono channel
                "-ar", "16000",          # 16kHz sample rate (required by WhisperX)
                "-acodec", "pcm_s16le",  # PCM format for compatibility
                "-y",                    # Overwrite output
                str(output_path)
            ]

            print(f"  Extracting audio: {video_path.name} → {output_name}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for extraction
            )

            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {result.stderr}")

            if not output_path.exists():
                raise RuntimeError(f"Audio extraction completed but output file not found: {output_path}")

            file_size = output_path.stat().st_size
            print(f"  ✅ Audio extracted: {output_path} ({file_size:,} bytes)")
            return str(output_path)

        except subprocess.TimeoutExpired:
            raise RuntimeError("Audio extraction timed out (exceeded 5 minutes). File may be too large.")
        except Exception as e:
            raise RuntimeError(f"Failed to extract audio: {type(e).__name__}: {e}")


def extract_audio_from_video(video_path: str, output_dir: str = "data/audio") -> str:
    """
    Convenience function to extract audio from a video file.

    Args:
        video_path: Path to the video file
        output_dir: Directory to save extracted audio files

    Returns:
        Path to the extracted audio file
    """
    extractor = AudioExtractor(output_dir=output_dir)
    return extractor.extract_audio(video_path)
