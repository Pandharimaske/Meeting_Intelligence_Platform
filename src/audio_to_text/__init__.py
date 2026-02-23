import whisper
from pathlib import Path
import json


class AudioToTextConverter:
    """Convert audio files to text using OpenAI's Whisper model."""
    
    def __init__(self, model_size: str = "base"):
        """
        Initialize the AudioToTextConverter.
        
        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
                       Larger models are more accurate but slower
        """
        self.model_size = model_size
        self.model = whisper.load_model(model_size)
    
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
            print(f"Transcribing audio: {audio_path}")
            print(f"Using model: whisper-{self.model_size}")
            
            # Transcribe audio
            result = self.model.transcribe(str(audio_path), language="en")
            
            # Save transcript as text file
            transcript_text_path = output_path / f"{audio_path.stem}.txt"
            with open(transcript_text_path, "w") as f:
                f.write(result["text"])
            
            # Save detailed transcript as JSON
            transcript_json_path = output_path / f"{audio_path.stem}.json"
            with open(transcript_json_path, "w") as f:
                json.dump(result, f, indent=2)
            
            print(f"✓ Transcription complete!")
            print(f"  Text transcript: {transcript_text_path}")
            print(f"  JSON transcript: {transcript_json_path}")
            
            return {
                "text": result["text"],
                "text_file": str(transcript_text_path),
                "json_file": str(transcript_json_path),
                "language": result.get("language", "en"),
                "segments": result.get("segments", [])
            }
            
        except Exception as e:
            raise RuntimeError(f"Failed to transcribe audio {audio_path}: {str(e)}")


def convert_audio_to_text(audio_path: str, model_size: str = "base", output_dir: str = "data/transcripts") -> dict:
    """
    Convenience function to convert audio to text.
    
    Args:
        audio_path: Path to the audio file
        model_size: Whisper model size (tiny, base, small, medium, large)
        output_dir: Directory to save transcript files
        
    Returns:
        Dictionary containing transcript and metadata
    """
    converter = AudioToTextConverter(model_size=model_size)
    return converter.convert_audio_to_text(audio_path, output_dir=output_dir)
