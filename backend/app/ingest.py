"""Evidence ingestion utilities for Reel2Career.

Provides functions to ingest transcripts and OCR results from media processing.
"""

from pathlib import Path
import json
import sys
import re

# Allow importing database.py
BASE_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(APP_DIR))

from database import (
    SessionLocal,
    Reel,
    Evidence,
)


def get_reel_by_id(db, instagram_id: str):
    """
    Get a Reel from the database by Instagram ID.

    Args:
        db: SQLAlchemy session.
        instagram_id: Instagram reel ID string.

    Returns:
        Reel object, or None if not found.
    """

    reel = (
        db.query(Reel)
        .filter(
            Reel.instagram_id == str(instagram_id)
        )
        .first()
    )

    return reel


def evidence_exists(
    db,
    reel_id: int,
    evidence_type: str,
    source_path: str,
) -> bool:
    """
    Check if evidence already exists.

    Args:
        db: SQLAlchemy session.
        reel_id: Reel ID from database.
        evidence_type: Type of evidence (e.g., 'transcript', 'ocr').
        source_path: Source file path.

    Returns:
        True if evidence already exists, False otherwise.
    """

    return (
        db.query(Evidence)
        .filter(
            Evidence.reel_id == reel_id,
            Evidence.evidence_type == evidence_type,
            Evidence.source_path == source_path,
        )
        .first()
        is not None
    )


def add_evidence(
    db,
    reel_id: int,
    evidence_type: str,
    source_path: str,
    content: str,
    confidence: float,
) -> bool:
    """
    Add evidence to the database, avoiding duplicates.

    Args:
        db: SQLAlchemy session.
        reel_id: Reel ID from database.
        evidence_type: Type of evidence.
        source_path: Source file path (relative).
        content: Text content of evidence.
        confidence: Confidence score (0-1).

    Returns:
        True if evidence was added, False if it already existed.
    """

    if evidence_exists(
        db,
        reel_id,
        evidence_type,
        source_path,
    ):
        return False

    row = Evidence(
        reel_id=reel_id,
        evidence_type=evidence_type,
        source_path=source_path,
        content=content,
        confidence=confidence,
    )

    db.add(row)

    return True


def ingest_transcript_from_file(
    db,
    transcript_json_path: Path,
    base_dir: Path = None,
) -> int:
    """
    Ingest a single transcript JSON file.

    Args:
        db: SQLAlchemy session.
        transcript_json_path: Path to transcript JSON.
        base_dir: Base directory for relative paths. If None, uses BASE_DIR.

    Returns:
        Number of evidence records added (0 or 1).
    """

    transcript_json_path = Path(transcript_json_path)

    if not transcript_json_path.exists():
        return 0

    if base_dir is None:
        base_dir = BASE_DIR

    try:
        data = json.loads(
            transcript_json_path.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return 0

    # Extract Instagram ID from file name or JSON
    # Expected format: vault/transcripts/{instagram_id}.json
    instagram_id = data.get("instagram_id")

    if not instagram_id:
        # Try extracting from file name
        # Format: {instagram_id}.json
        instagram_id = transcript_json_path.stem

    if not instagram_id:
        return 0

    reel = get_reel_by_id(db, instagram_id)

    if not reel:
        return 0

    relative_path = str(
        transcript_json_path.relative_to(base_dir)
    )

    # Get transcript text - look in multiple places
    content = data.get("text", "").strip()

    if not content:
        # Try extracting from segments
        segments = data.get("segments", [])
        if segments:
            content = " ".join([
                s.get("text", "").strip()
                for s in segments
                if s.get("text", "").strip()
            ])

    if not content:
        return 0

    inserted = add_evidence(
        db=db,
        reel_id=reel.id,
        evidence_type="transcript",
        source_path=relative_path,
        content=content,
        confidence=0.75,
    )

    return 1 if inserted else 0


def ingest_ocr_results(
    db,
    ocr_results: list,
    base_dir: Path = None,
) -> int:
    """
    Ingest OCR results.

    Args:
        db: SQLAlchemy session.
        ocr_results: List of OCR result dicts with keys:
            source_type, source_file, text
        base_dir: Base directory for resolving relative paths.

    Returns:
        Number of evidence records added.
    """

    if base_dir is None:
        base_dir = BASE_DIR

    inserted_count = 0

    for item in ocr_results:

        source_type = item.get("source_type", "").strip()
        source_path = item.get("source_file", "").strip()
        content = item.get("text", "").strip()

        if not source_path or not content:
            continue

        # Extract Instagram ID from source path
        # Video frames: media/frames/{instagram_id}/frame_*.jpg
        # Carousel: media/frames/{instagram_id}_*.jpg

        instagram_id = None

        # Try video frame pattern
        if source_type == "video_frame":
            # Path format: media/frames/{instagram_id}/frame_*.jpg
            parts = source_path.split("/")
            if len(parts) >= 3 and parts[0] == "media" and parts[1] == "frames":
                instagram_id = parts[2]

        # Try carousel pattern
        elif source_type == "carousel_slide":
            # Path format: media/frames/{instagram_id}_*.jpg
            # Extract ID before underscore
            if "media/frames" in source_path or "media\\frames" in source_path:
                # Normalize separators
                normalized = source_path.replace("\\", "/")
                parts = normalized.split("/")
                if parts:
                    filename = parts[-1]  # {instagram_id}_*.jpg
                    match = re.match(r"^(\d+)_", filename)
                    if match:
                        instagram_id = match.group(1)

        if not instagram_id:
            continue

        reel = get_reel_by_id(db, instagram_id)

        if not reel:
            continue

        inserted = add_evidence(
            db=db,
            reel_id=reel.id,
            evidence_type="ocr",
            source_path=source_path,
            content=content,
            confidence=0.70,
        )

        if inserted:
            inserted_count += 1

    return inserted_count


def discover_and_ingest_transcripts(
    db,
    transcripts_dir: Path = None,
    base_dir: Path = None,
) -> int:
    """
    Discover and ingest all transcript files in the transcripts directory.

    Args:
        db: SQLAlchemy session.
        transcripts_dir: Directory containing transcript JSON files.
                        If None, defaults to vault/transcripts/.
        base_dir: Base directory for relative paths.

    Returns:
        Total number of evidence records added.
    """

    if base_dir is None:
        base_dir = BASE_DIR

    if transcripts_dir is None:
        transcripts_dir = base_dir / "vault" / "transcripts"

    transcripts_dir = Path(transcripts_dir)

    if not transcripts_dir.exists():
        return 0

    # Find all *.json files
    transcript_files = sorted(
        transcripts_dir.glob("*.json")
    )

    total_inserted = 0

    for transcript_path in transcript_files:
        inserted = ingest_transcript_from_file(
            db,
            transcript_path,
            base_dir,
        )
        total_inserted += inserted

    return total_inserted


def ingest_evidence_batch(
    db,
    transcripts: list = None,
    ocr_results: list = None,
    base_dir: Path = None,
) -> dict:
    """
    Ingest transcripts and OCR results in a batch operation.

    Args:
        db: SQLAlchemy session.
        transcripts: List of transcript file paths to ingest.
        ocr_results: List of OCR result dicts to ingest.
        base_dir: Base directory for relative paths.

    Returns:
        Dict with keys: transcript_count, ocr_count
    """

    if base_dir is None:
        base_dir = BASE_DIR

    results = {
        "transcript_count": 0,
        "ocr_count": 0,
    }

    if transcripts:
        for transcript_path in transcripts:
            inserted = ingest_transcript_from_file(
                db,
                transcript_path,
                base_dir,
            )
            results["transcript_count"] += inserted

    if ocr_results:
        inserted = ingest_ocr_results(
            db,
            ocr_results,
            base_dir,
        )
        results["ocr_count"] = inserted

    return results
