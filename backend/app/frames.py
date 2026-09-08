"""Frame extraction utilities for Reel2Career.

Provides functions to extract frames from video files using FFmpeg.
"""

from pathlib import Path
import subprocess


def extract_frames(
    video_path: Path,
    output_dir: Path,
    fps_rate: float = 1/5,
    force: bool = False,
) -> int:
    """
    Extract frames from a video file.

    Args:
        video_path: Path to the input video (MP4).
        output_dir: Directory where frames will be written as frame_XXXX.jpg.
        fps_rate: Frames per second. Default 1/5 = 1 frame every 5 seconds.
        force: If True, overwrite existing frames. If False, skip if dir exists with frames.

    Returns:
        Number of frames extracted. 0 if extraction failed or was skipped.

    Raises:
        FileNotFoundError: If video_path does not exist.
    """

    video_path = Path(video_path)
    output_dir = Path(output_dir)

    if not video_path.exists():
        raise FileNotFoundError(
            f"Video file not found: {video_path}"
        )

    # Check if frames already exist and we're not forcing
    existing_frames = sorted(
        output_dir.glob("frame_*.jpg")
    )
    if existing_frames and not force:
        return len(existing_frames)

    # Ensure output directory exists
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # FFmpeg command to extract frames
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps_rate}",
        "-q:v",
        "2",
        str(output_dir / "frame_%04d.jpg"),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute timeout
        )

        if result.returncode != 0:
            return 0

        frames = sorted(
            output_dir.glob("frame_*.jpg")
        )
        return len(frames)

    except subprocess.TimeoutExpired:
        return 0
    except Exception:
        return 0
