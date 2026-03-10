# Re-export the WhisperX-based converter so both of these work:
#   from src.audio_to_text import convert_audio_to_text
#   from src.audio_to_text.converter import convert_audio_to_text
from .converter import AudioToTextConverter, convert_audio_to_text

__all__ = ["AudioToTextConverter", "convert_audio_to_text"]
