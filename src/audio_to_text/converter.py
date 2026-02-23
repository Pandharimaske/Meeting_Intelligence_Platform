import whisper
from pathlib import Path
import json
from src.diarization.speaker_diarization import perform_diarization


class AudioToTextConverter:
    """Convert audio files to text using OpenAI's Whisper model."""

    def __init__(self, model_size: str = "base", enable_diarization: bool = False, huggingface_token: str = None):
        """
        Initialize the AudioToTextConverter.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
                       Larger models are more accurate but slower
            enable_diarization: Enable speaker diarization (requires HuggingFace token)
            huggingface_token: HuggingFace API token for diarization
        """
        self.model_size = model_size
        self.enable_diarization = enable_diarization
        self.huggingface_token = huggingface_token
        self.model = whisper.load_model(model_size)

    def _merge_diarization_with_transcript(self, transcript: dict, diarization: dict) -> dict:
        """
        Merge diarization results with Whisper transcript to attribute speech to speakers.

        Args:
            transcript: Whisper transcription result
            diarization: Diarization result from pyannote

        Returns:
            Enhanced transcript with speaker attribution
        """
        segments = transcript.get("segments", [])
        diar_segments = diarization.get("segments", [])

        # Attribute each segment to a speaker based on time overlap
        for segment in segments:
            seg_start = segment["start"]
            seg_end = segment["end"]

            # Find speaker with maximum overlap
            best_speaker = "Unknown"
            max_overlap = 0

            for diar_seg in diar_segments:
                diar_start = diar_seg["start"]
                diar_end = diar_seg["end"]

                # Calculate overlap
                overlap_start = max(seg_start, diar_start)
                overlap_end = min(seg_end, diar_end)
                overlap = max(0, overlap_end - overlap_start)

                if overlap > max_overlap:
                    max_overlap = overlap
                    best_speaker = diar_seg["speaker"]

            segment["speaker"] = best_speaker

        # Build speaker-grouped transcript
        speaker_transcript = []
        current_speaker = None
        current_text = []

        for segment in segments:
            speaker = segment.get("speaker", "Unknown")
            if speaker != current_speaker:
                if current_text:
                    speaker_transcript.append({
                        "speaker": current_speaker,
                        "text": " ".join(current_text)
                    })
                current_speaker = speaker
                current_text = [segment["text"]]
            else:
                current_text.append(segment["text"])

        if current_text:
            speaker_transcript.append({
                "speaker": current_speaker,
                "text": " ".join(current_text)
            })

        return {
            "segments": segments,
            "speaker_segments": speaker_transcript,
            "speakers": diarization.get("speakers", {}),
            "total_speakers": diarization.get("total_speakers", 0)
        }

    def convert_audio_to_text(self, audio_path: str, output_dir: str = "data/transcripts") -> dict:
        """
        Convert audio file to text using Whisper.

        Args:
            audio_path: Path to the audio file
            output_dir: Directory to save transcript files

        Returns:
            Dictionary containing transcript and metadata

        Raises:
            FileNotFoundError: If audio file doesn't exist
            RuntimeError: If transcription fails
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        try:
            print(f"  Transcribing audio: {audio_path}")
            print(f"  Using model: whisper-{self.model_size}")

            # Transcribe audio
            result = self.model.transcribe(str(audio_path), language="en")

            # Perform diarization if enabled
            diarization_result = None
            if self.enable_diarization:
                print("  Running speaker diarization...")
                try:
                    diarization_result = perform_diarization(str(audio_path), use_auth_token=self.huggingface_token)
                    merged = self._merge_diarization_with_transcript(result, diarization_result)
                    result["segments"] = merged["segments"]
                    result["speaker_segments"] = merged["speaker_segments"]
                    result["speakers"] = merged["speakers"]
                    result["total_speakers"] = merged["total_speakers"]
                except Exception as e:
                    print(f"  Warning: Diarization failed, continuing with transcript only: {str(e)}")

            # Save transcript as text file
            transcript_text_path = output_path / f"{audio_path.stem}.txt"
            with open(transcript_text_path, "w") as f:
                if diarization_result and "speaker_segments" in result:
                    for item in result["speaker_segments"]:
                        f.write(f"{item['speaker']}: {item['text']}\n\n")
                else:
                    f.write(result["text"])

            # Save detailed transcript as JSON
            transcript_json_path = output_path / f"{audio_path.stem}.json"
            with open(transcript_json_path, "w") as f:
                json.dump(result, f, indent=2, default=str)

            print(f"  ✓ Transcription complete!")
            print(f"  Text transcript: {transcript_text_path}")
            print(f"  JSON transcript: {transcript_json_path}")
            if diarization_result:
                print(f"  Speakers detected: {result.get('total_speakers', 0)}")

            return {
                "text": result.get("text", " ".join([s["text"] for s in result.get("segments", [])])),
                "text_file": str(transcript_text_path),
                "json_file": str(transcript_json_path),
                "language": result.get("language", "en"),
                "segments": result.get("segments", []),
                "speaker_segments": result.get("speaker_segments", []),
                "speakers": result.get("speakers", {}),
                "total_speakers": result.get("total_speakers", 0),
                "diarization_enabled": self.enable_diarization
            }

        except Exception as e:
            raise RuntimeError(f"Failed to transcribe audio {audio_path}: {str(e)}")


def convert_audio_to_text(
    audio_path: str,
    model_size: str = "base",
    output_dir: str = "data/transcripts",
    enable_diarization: bool = False,
    huggingface_token: str = None
) -> dict:
    """
    Convenience function to convert audio to text.

    Args:
        audio_path: Path to the audio file
        model_size: Whisper model size (tiny, base, small, medium, large)
        output_dir: Directory to save transcript files
        enable_diarization: Enable speaker diarization
        huggingface_token: HuggingFace API token for diarization

    Returns:
        Dictionary containing transcript and metadata
    """
    converter = AudioToTextConverter(
        model_size=model_size,
        enable_diarization=enable_diarization,
        huggingface_token=huggingface_token
    )
    return converter.convert_audio_to_text(audio_path, output_dir=output_dir)
