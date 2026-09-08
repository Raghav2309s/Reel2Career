"""OCR utilities for Reel2Career.

Provides functions to extract text from images using Tesseract OCR.
"""

from pathlib import Path
import subprocess
import json


def get_tesseract_path() -> Path:
    """Get the path to the Tesseract executable.

    Returns:
        Path to tesseract.exe.

    Raises:
        FileNotFoundError: If Tesseract is not found.
    """

    tesseract_path = Path(
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

    if not tesseract_path.exists():
        raise FileNotFoundError(
            f"Tesseract not found: {tesseract_path}"
        )

    return tesseract_path


def run_ocr_on_image(image_path: Path) -> str:
    """
    Extract text from an image using Tesseract OCR.

    Args:
        image_path: Path to the input image (JPEG, PNG, etc.).

    Returns:
        Extracted text, or empty string if OCR failed.
    """

    image_path = Path(image_path)

    if not image_path.exists():
        return ""

    try:
        tesseract_path = get_tesseract_path()

        command = [
            str(tesseract_path),
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

    except Exception:
        return ""


def ocr_images(images: list, source_type: str) -> list:
    """
    Extract text from a list of images.

    Args:
        images: List of Path objects to images.
        source_type: Type of source ('video_frame' or 'carousel_slide').

    Returns:
        List of dicts with keys: source_type, source_file, text.
    """

    results = []

    for image_path in images:

        text = run_ocr_on_image(image_path)

        result = {
            "source_type": source_type,
            "source_file": str(image_path),
            "text": text,
        }

        results.append(result)

    return results


def process_video_frames(
    frames_dir: Path,
    base_dir: Path = None,
    force: bool = False,
) -> list:
    """
    Process all video frames in a directory via OCR.

    Args:
        frames_dir: Directory containing frame_*.jpg files.
        base_dir: Base directory for relative paths in results. If None, uses frames_dir.parent.
        force: If True, reprocess. If False, skip if OCR already done (via cache file).

    Returns:
        List of OCR result dicts.
    """

    frames_dir = Path(frames_dir)

    if not frames_dir.exists():
        return []

    if base_dir is None:
        base_dir = frames_dir.parent

    frames = sorted(
        frames_dir.glob("frame_*.jpg")
    )

    if not frames:
        return []

    results = []

    for frame_path in frames:
        text = run_ocr_on_image(frame_path)

        relative_path = str(
            frame_path.relative_to(base_dir)
        )

        result = {
            "source_type": "video_frame",
            "source_file": relative_path,
            "text": text,
        }

        results.append(result)

    return results


def process_carousel_slides(
    carousel_dir: Path,
    reel_id: str,
    base_dir: Path = None,
    force: bool = False,
) -> list:
    """
    Process all carousel slides matching a reel ID via OCR.

    Args:
        carousel_dir: Directory containing carousel slide images.
        reel_id: Instagram reel ID to search for (pattern: {reel_id}_*.jpg).
        base_dir: Base directory for relative paths. If None, uses carousel_dir.
        force: If True, reprocess. If False, skip if already done.

    Returns:
        List of OCR result dicts.
    """

    carousel_dir = Path(carousel_dir)

    if not carousel_dir.exists():
        return []

    if base_dir is None:
        base_dir = carousel_dir

    # Find carousel slides matching pattern
    carousel_slides = sorted(
        carousel_dir.glob(f"{reel_id}_*.jpg")
    )

    if not carousel_slides:
        return []

    results = []

    for slide_path in carousel_slides:
        text = run_ocr_on_image(slide_path)

        relative_path = str(
            slide_path.relative_to(base_dir)
        )

        result = {
            "source_type": "carousel_slide",
            "source_file": relative_path,
            "text": text,
        }

        results.append(result)

    return results
