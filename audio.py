"""Generic audio extraction utilities for Reel2Career."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def extract_audio(
    video_path: str | Path,
    output_wav_path: str | Path,
    force: bool = False,
) -> bool:
    """Extract WAV audio from a video file.

    Reuses an existing valid output file unless force=True.
    Raises FileNotFoundError if the source video is missing.
    """

    video_path = Path(video_path)
    output_wav_path = Path(output_wav_path)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if output_wav_path.exists() and output_wav_path.stat().st_size > 0 and not force:
        return True

    output_wav_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH")

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "2",
        str(output_wav_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return False

    return output_wav_path.exists() and output_wav_path.stat().st_size > 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract audio from a video to WAV.")
    parser.add_argument("video_path", type=str)
    parser.add_argument("output_wav_path", type=str)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    video_path = Path(args.video_path)
    output_wav_path = Path(args.output_wav_path)

    if not extract_audio(video_path, output_wav_path, force=args.force):
        raise SystemExit(f"Audio extraction failed for {video_path}")


if __name__ == "__main__":
    main()
