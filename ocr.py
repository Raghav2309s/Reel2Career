from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def run_tesseract(image_path: str | Path) -> str:
    image_path = Path(image_path)
    if not image_path.exists():
        return ""

    if not TESSERACT.exists():
        return ""

    command = [
        str(TESSERACT),
        str(image_path),
        "stdout",
        "--psm",
        "6",
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    if result.returncode != 0:
        return ""

    return result.stdout.strip()


def _infer_instagram_id_from_path(source_file: str | Path, fallback: str | None = None) -> str | None:
    source_file = str(source_file).replace("\\", "/")
    match = re.search(r"(?:^|/)(\d+)(?:_|/)", source_file)
    if match:
        return match.group(1)
    return fallback


def process_video_frames(
    frames_dir: str | Path,
    base_dir: str | Path | None = None,
    instagram_id: str | None = None,
) -> list[dict]:
    frames_dir = Path(frames_dir)
    if not frames_dir.exists():
        return []

    if base_dir is None:
        base_dir = BASE_DIR

    base_dir = Path(base_dir)
    results = []
    for frame_path in sorted(frames_dir.glob("frame_*.jpg")):
        text = run_tesseract(frame_path)
        relative_path = str(frame_path.relative_to(base_dir)) if frame_path.is_absolute() and base_dir in frame_path.parents else str(frame_path)
        reel_id = instagram_id or _infer_instagram_id_from_path(relative_path, frames_dir.name)
        results.append({
            "instagram_id": reel_id,
            "source_type": "video_frame",
            "source_file": relative_path,
            "text": text,
        })
    return results


def process_carousel_slides(
    carousel_dir: str | Path,
    reel_id: str | None = None,
    base_dir: str | Path | None = None,
) -> list[dict]:
    carousel_dir = Path(carousel_dir)
    if not carousel_dir.exists():
        return []

    if base_dir is None:
        base_dir = BASE_DIR

    base_dir = Path(base_dir)
    pattern = f"{reel_id}_*.jpg" if reel_id else "*.jpg"
    results = []
    for slide_path in sorted(carousel_dir.glob(pattern)):
        if reel_id is None:
            reel_id = _infer_instagram_id_from_path(slide_path.name) or slide_path.stem.rsplit("_", 1)[0]
        text = run_tesseract(slide_path)
        relative_path = str(slide_path.relative_to(base_dir)) if slide_path.is_absolute() and base_dir in slide_path.parents else str(slide_path)
        results.append({
            "instagram_id": reel_id,
            "source_type": "carousel_slide",
            "source_file": relative_path,
            "text": text,
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR media frames and carousel slides.")
    parser.add_argument("--frames-dir", type=str, default=str(BASE_DIR / "media" / "frames"))
    parser.add_argument("--reel-id", type=str, default=None)
    parser.add_argument("--output", type=str, default=str(BASE_DIR / "vault" / "ocr" / "ocr_results.json"))
    args = parser.parse_args()

    frames_dir = Path(args.frames_dir)
    results = []
    if frames_dir.exists():
        for video_dir in sorted(p for p in frames_dir.iterdir() if p.is_dir() and p.name.isdigit()):
            results.extend(process_video_frames(video_dir, base_dir=BASE_DIR, instagram_id=video_dir.name))
        carousel_results = process_carousel_slides(frames_dir, reel_id=args.reel_id, base_dir=BASE_DIR)
        results.extend(carousel_results)

    payload = {"version": 1, "results": results}
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()