import sys
from pathlib import Path

from src.audio_extraction.extractor import extract_audio_from_video
from src.audio_to_text.converter import convert_audio_to_text


class MeetingIntelligencePipeline:
    """Pipeline for processing video files to extract audio and generate text transcripts."""

    def __init__(self, whisper_model_size: str = "base", enable_diarization: bool = False, huggingface_token: str = None):
        """
        Initialize the pipeline.

        Args:
            whisper_model_size: Whisper model size (tiny, base, small, medium, large)
            enable_diarization: Enable speaker diarization
            huggingface_token: HuggingFace API token for diarization
        """
        self.whisper_model_size = whisper_model_size
        self.enable_diarization = enable_diarization
        self.huggingface_token = huggingface_token
        self.audio_output_dir = "data/audio"
        self.transcript_output_dir = "data/transcripts"

    def process_video(self, video_path: str) -> dict:
        """
        Process a video file: extract audio and generate transcript.

        Args:
            video_path: Path to the video file

        Returns:
            Dictionary with audio path and transcript results

        Raises:
            FileNotFoundError: If video file doesn't exist
            RuntimeError: If processing fails
        """
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        print(f"\n{'='*60}")
        print(f"Processing: {video_path.name}")
        print(f"{'='*60}")

        # Step 1: Extract audio from video
        print("\n[Step 1/2] Extracting audio from video...")
        try:
            audio_path = extract_audio_from_video(str(video_path), output_dir=self.audio_output_dir)
        except RuntimeError as e:
            if "video-only" in str(e).lower() or "no audio stream" in str(e).lower():
                raise  # re-raise with the helpful message as-is
            raise RuntimeError(f"Audio extraction failed: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Audio extraction failed: {str(e)}")

        # Step 2: Convert audio to text
        print("\n[Step 2/2] Converting audio to text using Whisper...")
        try:
            transcript_result = convert_audio_to_text(
                audio_path,
                model_size=self.whisper_model_size,
                output_dir=self.transcript_output_dir,
                enable_diarization=self.enable_diarization,
                huggingface_token=self.huggingface_token
            )
        except Exception as e:
            raise RuntimeError(f"Audio-to-text conversion failed: {str(e)}")

        # Compile results
        results = {
            "video_file": str(video_path),
            "audio_file": audio_path,
            "transcript_text_file": transcript_result["text_file"],
            "transcript_json_file": transcript_result["json_file"],
            "transcript_text": transcript_result["text"],
            "language": transcript_result["language"],
            "segments": transcript_result["segments"],
            "speaker_segments": transcript_result.get("speaker_segments", []),
            "speakers": transcript_result.get("speakers", {}),
            "total_speakers": transcript_result.get("total_speakers", 0),
            "diarization_enabled": self.enable_diarization
        }

        return results

    def print_summary(self, results: dict) -> None:
        """Print a summary of processing results."""
        print(f"\n{'='*60}")
        print("PROCESSING COMPLETE")
        print(f"{'='*60}")
        print(f"\nInput:")
        print(f"  Video: {results['video_file']}")
        print(f"\nOutput:")
        print(f"  Audio: {results['audio_file']}")
        print(f"  Transcript (text): {results['transcript_text_file']}")
        print(f"  Transcript (JSON): {results['transcript_json_file']}")
        print(f"\nTranscript Details:")
        print(f"  Language: {results.get('language', 'unknown')}")
        print(f"  Segments: {len(results.get('segments', []))}")

        if results.get('diarization_enabled') and results.get('total_speakers', 0) > 0:
            print(f"  Speakers detected: {results['total_speakers']}")
            if results.get('speakers'):
                print(f"\n  Speaker Summary:")
                for speaker, info in results['speakers'].items():
                    duration = info.get('total_duration', 0)
                    segments = info.get('segment_count', 0)
                    print(f"    {speaker}: {duration:.1f}s ({segments} segments)")

        preview = results.get('transcript_text', '')[:150]
        if preview:
            print(f"\nTranscript Preview:")
            print(f"  {preview}...")


def print_usage():
    """Print usage instructions."""
    print(f"\n{'='*60}")
    print("Meeting Intelligence Platform - Video to Text Pipeline")
    print(f"{'='*60}")
    print("\nUsage:")
    print("  python main.py <video_file_path> [options]")
    print("\nArguments:")
    print("  video_file_path  - Path to the video file (required)")
    print("\nOptions:")
    print("  --model {size}   - Whisper model: tiny, base, small, medium, large")
    print("                     (default: base)")
    print("  --diarize        - Enable speaker diarization")
    print("  --token {token}  - HuggingFace API token for diarization")
    print("\nExamples:")
    print("  python main.py data/videos/meeting.mp4")
    print("  python main.py data/videos/meeting.mp4 --model small")
    print("  python main.py data/videos/meeting.mp4 --diarize --token hf_xxx")


def main():
    if len(sys.argv) < 2:
        print_usage()
        print("Error: Video file path is required")
        sys.exit(1)

    video_file = sys.argv[1]
    model_size = "base"
    enable_diarization = False
    huggingface_token = None

    # Parse options
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--model" and i + 1 < len(sys.argv):
            model_size = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--diarize":
            enable_diarization = True
            i += 1
        elif sys.argv[i] == "--token" and i + 1 < len(sys.argv):
            huggingface_token = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    # Validate model size
    valid_models = ["tiny", "base", "small", "medium", "large"]
    if model_size not in valid_models:
        print(f"Error: Invalid model size '{model_size}'")
        print(f"Valid options: {', '.join(valid_models)}")
        sys.exit(1)

    # Warn if diarization requested without token
    if enable_diarization and not huggingface_token:
        print("Warning: Diarization enabled but no HuggingFace token provided.")
        print("Get a token from: https://huggingface.co/settings/tokens")
        print("Use: python main.py <video> --diarize --token <your_token>\n")

    try:
        pipeline = MeetingIntelligencePipeline(
            whisper_model_size=model_size,
            enable_diarization=enable_diarization,
            huggingface_token=huggingface_token
        )
        results = pipeline.process_video(video_file)
        pipeline.print_summary(results)

    except FileNotFoundError as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
