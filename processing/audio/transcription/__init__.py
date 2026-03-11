# Re-export the WhisperX-based converter so both of these work:
#   from processing.audio.transcription import convert_audio_to_text
#   from processing.audio.transcription.converter import convert_audio_to_text
from .converter import AudioToTextConverter, convert_audio_to_text

__all__ = ["AudioToTextConverter", "convert_audio_to_text"]
