import ffmpeg
from pathlib import Path


class AudioExtractor:
    """Extract audio from video files using ffmpeg."""

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
        Extract audio from a video file.

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
            # Probe the file first to check for an audio stream
            probe = ffmpeg.probe(str(video_path))
            audio_streams = [s for s in probe['streams'] if s['codec_type'] == 'audio']
            if not audio_streams:
                raise RuntimeError(
                    f"No audio stream found in '{video_path.name}'. "
                    f"This file is video-only. Please provide the corresponding audio file directly."
                )

            # Extract audio using ffmpeg, resample to 16kHz mono (required by Whisper)
            (
                ffmpeg
                .input(str(video_path))
                .output(
                    str(output_path),
                    ac=1,            # Mono channel
                    ar=16000,        # 16kHz sample rate (Whisper requirement)
                    acodec='pcm_s16le'
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )

            print(f"  ✓ Audio extracted successfully: {output_path}")
            return str(output_path)

        except ffmpeg.Error as e:
            raise RuntimeError(f"Failed to extract audio from {video_path}: {e.stderr.decode()}")


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
