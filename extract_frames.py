from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    fps_rate: float = 1 / 5,
    force: bool = False,
) -> int:
    """Extract one frame every N seconds from a video.

    The operation is idempotent: if valid frames already exist, they are reused.
    """

    video_path = Path(video_path)
    output_dir = Path(output_dir)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    existing_frames = sorted(output_dir.glob("frame_*.jpg"))
    if existing_frames and not force:
        return len(existing_frames)

    output_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH")

    command = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps_rate}",
        "-q:v",
        "2",
        str(output_dir / "frame_%04d.jpg"),
    ]

    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return 0

    frames = sorted(output_dir.glob("frame_*.jpg"))
    return len(frames)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract still frames from a video.")
    parser.add_argument("video_path", type=str)
    parser.add_argument("output_dir", type=str)
    parser.add_argument("--fps", type=float, default=1 / 5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    count = extract_frames(args.video_path, args.output_dir, fps_rate=args.fps, force=args.force)
    print(f"Extracted {count} frames")


if __name__ == "__main__":
    main()