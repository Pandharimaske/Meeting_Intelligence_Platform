from pathlib import Path
from pyannote.audio import Pipeline


class SpeakerDiarizer:
    """Perform speaker diarization using pyannote.audio."""

    def __init__(self, use_auth_token: str = None):
        """
        Initialize the SpeakerDiarizer.

        Args:
            use_auth_token: HuggingFace API token for accessing pyannote models
                           Get token from https://huggingface.co/settings/tokens
        """
        self.use_auth_token = use_auth_token
        self.pipeline = None

    def _load_pipeline(self):
        """Load the diarization pipeline."""
        if self.pipeline is None:
            try:
                self.pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.0",
                    use_auth_token=self.use_auth_token
                )
            except Exception as e:
                raise RuntimeError(f"Failed to load diarization pipeline: {str(e)}")

    def diarize(self, audio_path: str) -> dict:
        """
        Perform speaker diarization on audio file.

        Args:
            audio_path: Path to the audio file

        Returns:
            Dictionary with diarization results

        Raises:
            FileNotFoundError: If audio file doesn't exist
            RuntimeError: If diarization fails
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            self._load_pipeline()

            print(f"  Diarizing audio: {audio_path}")
            diarization = self.pipeline(str(audio_path))

            # Extract speaker segments
            speakers = {}
            segments = []
            total_duration = 0.0

            for turn, _, speaker in diarization.itertracks(yield_label=True):
                # pyannote returns labels like SPEAKER_00, SPEAKER_01 — format to readable form
                speaker_label = f"Speaker {speaker.split('_')[-1].lstrip('0') or '0'}"

                segment_duration = turn.end - turn.start
                total_duration += segment_duration

                segment_info = {
                    "speaker": speaker_label,
                    "start": turn.start,
                    "end": turn.end,
                    "duration": segment_duration
                }
                segments.append(segment_info)

                if speaker_label not in speakers:
                    speakers[speaker_label] = {
                        "total_duration": 0.0,
                        "segment_count": 0
                    }

                speakers[speaker_label]["total_duration"] += segment_duration
                speakers[speaker_label]["segment_count"] += 1

            print(f"  ✓ Diarization complete! Detected {len(speakers)} unique speaker(s)")

            return {
                "segments": segments,
                "speakers": speakers,
                "total_speakers": len(speakers),
                "total_duration": total_duration   # BUG FIX: was accidentally set to audio_path
            }

        except Exception as e:
            raise RuntimeError(f"Diarization failed: {str(e)}")


def perform_diarization(audio_path: str, use_auth_token: str = None) -> dict:
    """
    Convenience function to perform diarization.

    Args:
        audio_path: Path to the audio file
        use_auth_token: HuggingFace API token

    Returns:
        Dictionary with diarization results
    """
    diarizer = SpeakerDiarizer(use_auth_token=use_auth_token)
    return diarizer.diarize(audio_path)
