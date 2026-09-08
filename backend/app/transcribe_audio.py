"""Transcription utilities for Reel2Career.

Provides functions to transcribe audio files using faster-whisper.
"""

from pathlib import Path
import json
import time


def transcribe_audio(
    audio_path: Path,
    output_json_path: Path,
    output_text_path: Path = None,
    force: bool = False,
    model_name: str = "small",
    device: str = "cpu",
    compute_type: str = "int8",
) -> bool:
    """
    Transcribe audio using faster-whisper model.

    Args:
        audio_path: Path to the input audio (WAV or MP3).
        output_json_path: Path where transcription JSON will be written.
        output_text_path: Optional path where transcription text will be written.
        force: If True, overwrite existing transcription.
        model_name: Whisper model name (e.g., 'small', 'medium').
        device: Device to use ('cpu' or 'cuda').
        compute_type: Compute type ('int8', 'float16', 'float32').

    Returns:
        True if transcription succeeded, False otherwise.

    Raises:
        FileNotFoundError: If audio_path does not exist.
    """

    audio_path = Path(audio_path)
    output_json_path = Path(output_json_path)

    if not audio_path.exists():
        raise FileNotFoundError(
            f"Audio file not found: {audio_path}"
        )

    # Check if transcription already exists and we're not forcing
    if output_json_path.exists() and not force:
        return True

    # Ensure output directory exists
    output_json_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        from faster_whisper import WhisperModel

        # Load model
        model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )

        # Transcribe
        segments, info = model.transcribe(
            str(audio_path),
            language="en",
        )

        # Build result
        result = {
            "audio_file": str(audio_path.name),
            "model": model_name,
            "language": info.language,
            "duration": info.duration,
            "segments": [],
        }

        for segment in segments:
            result["segments"].append({
                "id": segment.id,
                "seek": segment.seek,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "tokens": list(segment.tokens) if segment.tokens else [],
                "temperature": segment.temperature,
                "avg_logprob": segment.avg_logprob,
                "compression_ratio": segment.compression_ratio,
                "no_speech_prob": segment.no_speech_prob,
            })

        # Build full text
        full_text = " ".join([
            segment["text"].strip()
            for segment in result["segments"]
        ])

        # Write JSON
        output_json_path.write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )

        # Write text if requested
        if output_text_path:
            output_text_path = Path(output_text_path)
            output_text_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            output_text_path.write_text(
                full_text,
                encoding="utf-8",
            )

        return True

    except ImportError:
        # faster_whisper not installed
        return False
    except Exception:
        # Transcription failed
        return False
