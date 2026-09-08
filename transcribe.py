from __future__ import annotations

import argparse
import json
from pathlib import Path


WhisperModel = None
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "vault" / "transcripts"


def transcribe_audio(
    instagram_id: str,
    audio_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    force: bool = False,
    model_name: str = "small",
    device: str = "cpu",
    compute_type: str = "int8",
) -> bool:
    """Transcribe an audio file and write JSON/TXT outputs for an Instagram reel."""

    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    output_dir = Path(output_dir) if output_dir is not None else DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{instagram_id}.json"
    text_path = output_dir / f"{instagram_id}.txt"

    if json_path.exists() and text_path.exists() and not force:
        return True

    global WhisperModel
    model_class = WhisperModel
    if model_class is None:
        from faster_whisper import WhisperModel as model_class

    model = model_class(
        model_name,
        device=device,
        compute_type=compute_type,
    )

    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=True,
    )

    results = []
    full_text_parts = []
    for segment in segments:
        text = (segment.text or "").strip()
        if not text:
            continue
        results.append({
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "text": text,
        })
        full_text_parts.append(text)

    transcript = {
        "instagram_id": str(instagram_id),
        "audio_file": str(audio_path.relative_to(BASE_DIR)) if audio_path.is_absolute() and BASE_DIR in audio_path.parents else audio_path.name,
        "language": getattr(info, "language", None),
        "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 4),
        "duration": float(getattr(info, "duration", 0.0) or 0.0),
        "segments": results,
        "text": " ".join(full_text_parts),
    }

    json_path.write_text(json.dumps(transcript, indent=2, ensure_ascii=False), encoding="utf-8")
    text_path.write_text(transcript["text"], encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe a WAV file into a reel transcript.")
    parser.add_argument("instagram_id", type=str)
    parser.add_argument("audio_path", type=str)
    parser.add_argument("output_dir", type=str, nargs="?", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    if not transcribe_audio(args.instagram_id, args.audio_path, args.output_dir):
        raise SystemExit(f"Transcription failed for {args.audio_path}")


if __name__ == "__main__":
    main()