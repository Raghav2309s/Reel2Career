"""
Reel2Career Pipeline Orchestrator

Orchestrates the complete media processing pipeline:
1. Sync Instagram collection to state/synced.json
2. Migrate synced state to SQLite
3. Extract media (frames, audio)
4. Transcribe audio
5. OCR images
6. Ingest evidence
7. Run AI analysis
8. Generate career synthesis

Discover all reels dynamically from state/synced.json and process them
idempotently with detailed per-reel state tracking.
"""

from pathlib import Path
import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import traceback

# Setup paths
BASE_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(APP_DIR))

try:
    import backend.app.database as database
    from backend.app.database import (
        SessionLocal,
        Reel,
        Evidence,
        Analysis,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    import database
    from database import (
        SessionLocal,
        Reel,
        Evidence,
        Analysis,
    )
from frames import extract_frames
from transcribe_audio import transcribe_audio
from ocr_extract import (
    process_video_frames,
    process_carousel_slides,
)
from ingest import (
    get_reel_by_id,
    ingest_transcript_from_file,
    ingest_ocr_results,
)
from migrate_state import migrate

# Import top-level functions
sys.path.insert(0, str(BASE_DIR))
from audio import extract_audio


# ============================================================
# CONSTANTS
# ============================================================

STATE_FILE = BASE_DIR / "state" / "synced.json"
TRANSCRIPTS_DIR = BASE_DIR / "vault" / "transcripts"
FRAMES_DIR = BASE_DIR / "media" / "frames"
AUDIO_DIR = BASE_DIR / "media" / "audio"
VIDEOS_DIR = BASE_DIR / "media" / "videos"
OCR_DIR = BASE_DIR / "vault" / "ocr"

TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
OCR_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# TYPES
# ============================================================

class ReelStatus:
    """Track processing status for a single reel."""

    def __init__(self, instagram_id: str, media_kind: str):
        self.instagram_id = instagram_id
        self.media_kind = media_kind  # "video" or "carousel"

        # Media stage
        self.media_exists = False
        self.video_path = None
        self.audio_extracted = False
        self.audio_path = None
        self.frames_extracted = False
        self.frame_count = 0
        self.carousel_slides = []

        # Evidence stage
        self.transcript_ingested = False
        self.ocr_ingested = False
        self.evidence_count = 0

        # AI stage
        self.ai_analyzed = False

        # Errors
        self.errors: List[str] = []
        self.skipped = False
        self.skip_reason = None

    def add_error(self, msg: str):
        self.errors.append(msg)

    def to_dict(self) -> dict:
        return {
            "instagram_id": self.instagram_id,
            "media_kind": self.media_kind,
            "media_exists": self.media_exists,
            "audio_extracted": self.audio_extracted,
            "frames_extracted": self.frames_extracted,
            "frame_count": self.frame_count,
            "transcript_ingested": self.transcript_ingested,
            "ocr_ingested": self.ocr_ingested,
            "evidence_count": self.evidence_count,
            "ai_analyzed": self.ai_analyzed,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "errors": self.errors,
        }

    @property
    def status(self) -> str:
        """Generate a status string."""
        if self.skipped:
            return f"SKIPPED ({self.skip_reason})"
        if self.errors:
            return f"FAILED ({len(self.errors)} error(s))"
        if self.ai_analyzed:
            return "[OK] AI_ANALYZED"
        if self.evidence_count > 0:
            return f"[OK] EVIDENCE ({self.evidence_count})"
        if self.frames_extracted or self.transcript_ingested:
            return "[OK] MEDIA_PROCESSED"
        if self.media_exists:
            return "[OK] MEDIA_FOUND"
        return "NO_MEDIA"


# ============================================================
# STAGE 1: DISCOVER REELS
# ============================================================

def discover_reels() -> Dict[str, dict]:
    """
    Discover all reels from state/synced.json.

    Returns:
        Dict mapping instagram_id -> reel metadata
    """

    if not STATE_FILE.exists():
        return {}

    try:
        data = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )
        items = data.get("items", {})
        return items
    except Exception as e:
        print(f"ERROR: Failed to read state/synced.json: {e}")
        return {}


# ============================================================
# STAGE 2: MIGRATE TO SQLITE
# ============================================================

def migrate_reels_to_db():
    """Run migrate_state.py to import all synced reels to SQLite."""

    print("\n" + "=" * 60)
    print("STAGE: Migrate Synced State to SQLite")
    print("=" * 60)

    try:
        migrate()
        print("\n[OK] Migration complete")
        return True
    except SystemExit as e:
        print(f"[FAIL] Migration failed: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Migration failed: {e}")
        traceback.print_exc()
        return False


# ============================================================
# STAGE 3: CHECK MEDIA AVAILABILITY
# ============================================================

def check_media_availability(
    status: ReelStatus,
    instagram_id: str,
    media_kind: str,
) -> bool:
    """
    Check if media files exist for this reel.

    Args:
        status: ReelStatus object to update.
        instagram_id: Instagram ID.
        media_kind: "video" or "carousel".

    Returns:
        True if media exists and was found, False otherwise.
    """

    if media_kind == "video":
        video_path = VIDEOS_DIR / f"{instagram_id}.mp4"
        if video_path.exists():
            status.media_exists = True
            status.video_path = video_path
            return True
        else:
            status.skip_reason = "no video file"
            return False

    elif media_kind == "carousel":
        # Check for carousel slides matching pattern
        carousel_slides = sorted(
            FRAMES_DIR.glob(f"{instagram_id}_*.jpg")
        )
        if carousel_slides:
            status.media_exists = True
            status.carousel_slides = carousel_slides
            return True
        else:
            status.skip_reason = "no carousel slides"
            return False

    else:
        status.skip_reason = f"unknown media kind: {media_kind}"
        return False


# ============================================================
# STAGE 4: EXTRACT AUDIO & FRAMES
# ============================================================

def process_video_reel(
    db,
    status: ReelStatus,
    instagram_id: str,
) -> bool:
    """
    Process a video reel: extract audio and frames.

    Args:
        db: SQLAlchemy session.
        status: ReelStatus object to update.
        instagram_id: Instagram ID.

    Returns:
        True if processing succeeded, False otherwise.
    """

    print(f"\n  [VIDEO] Processing audio & frames...")

    # Extract audio
    audio_path = AUDIO_DIR / f"{instagram_id}.wav"
    try:
        success = extract_audio(
            status.video_path,
            audio_path,
            force=False,
        )
        if success:
            status.audio_extracted = True
            status.audio_path = audio_path
            print(f"    [OK] Audio extracted: {audio_path.name}")
        else:
            status.add_error("audio extraction failed")
            print(f"    [FAIL] Audio extraction failed")
    except Exception as e:
        status.add_error(f"audio extraction error: {e}")
        print(f"    [FAIL] Audio extraction error: {e}")

    # Extract frames
    frames_output_dir = FRAMES_DIR / instagram_id
    try:
        frame_count = extract_frames(
            status.video_path,
            frames_output_dir,
            fps_rate=1/5,
            force=False,
        )
        if frame_count > 0:
            status.frames_extracted = True
            status.frame_count = frame_count
            print(f"    [OK] Frames extracted: {frame_count} frames")
        else:
            status.add_error("frame extraction failed")
            print(f"    [FAIL] Frame extraction failed")
    except Exception as e:
        status.add_error(f"frame extraction error: {e}")
        print(f"    [FAIL] Frame extraction error: {e}")

    # We extracted audio/frames; mark as processed even if one failed
    return status.audio_extracted or status.frames_extracted


def process_carousel_reel(
    db,
    status: ReelStatus,
    instagram_id: str,
) -> bool:
    """
    Process a carousel reel: no audio/transcription, just OCR.

    Args:
        db: SQLAlchemy session.
        status: ReelStatus object to update.
        instagram_id: Instagram ID.

    Returns:
        True if processing can continue, False otherwise.
    """

    print(f"\n  [CAROUSEL] Ready for OCR")
    # Carousel reels don't need audio extraction
    # Frames will be OCR'd in the OCR stage
    return True


# ============================================================
# STAGE 5: TRANSCRIBE AUDIO
# ============================================================

def transcribe_reel_audio(
    status: ReelStatus,
    instagram_id: str,
) -> bool:
    """
    Transcribe audio for a video reel.

    Args:
        status: ReelStatus object to update.
        instagram_id: Instagram ID.

    Returns:
        True if transcription succeeded or was skipped, False if it failed.
    """

    if not status.audio_extracted or not status.audio_path:
        # No audio to transcribe (carousel reel)
        return True

    print(f"    Transcribing audio...")

    output_json = TRANSCRIPTS_DIR / f"{instagram_id}.json"
    output_text = TRANSCRIPTS_DIR / f"{instagram_id}.txt"

    try:
        success = transcribe_audio(
            status.audio_path,
            output_json,
            output_text,
            force=False,
        )

        if success and output_json.exists():
            status.transcript_ingested = True
            print(f"      [OK] Transcription complete")
            return True
        else:
            status.add_error("transcription failed")
            print(f"      [FAIL] Transcription failed")
            return False

    except Exception as e:
        status.add_error(f"transcription error: {e}")
        print(f"      [FAIL] Transcription error: {e}")
        return False


# ============================================================
# STAGE 6: OCR
# ============================================================

def ocr_reel_media(
    status: ReelStatus,
    instagram_id: str,
) -> List[dict]:
    """
    Extract text from reel media via OCR.

    Args:
        status: ReelStatus object to update.
        instagram_id: Instagram ID.

    Returns:
        List of OCR result dicts.
    """

    results = []

    if status.media_kind == "video" and status.frames_extracted:
        frames_dir = FRAMES_DIR / instagram_id
        print(f"    OCR'ing video frames ({status.frame_count})...")

        try:
            frame_results = process_video_frames(
                frames_dir,
                base_dir=BASE_DIR,
                force=False,
            )
            results.extend(frame_results)
            print(f"      [OK] OCR complete: {len(frame_results)} results")
        except Exception as e:
            status.add_error(f"video OCR error: {e}")
            print(f"      [FAIL] Video OCR error: {e}")

    elif status.media_kind == "carousel" and status.carousel_slides:
        print(
            f"    OCR'ing carousel slides "
            f"({len(status.carousel_slides)})..."
        )

        try:
            slide_results = process_carousel_slides(
                FRAMES_DIR,
                instagram_id,
                base_dir=BASE_DIR,
                force=False,
            )
            results.extend(slide_results)
            print(f"      [OK] OCR complete: {len(slide_results)} results")
        except Exception as e:
            status.add_error(f"carousel OCR error: {e}")
            print(f"      [FAIL] Carousel OCR error: {e}")

    status.ocr_ingested = len(results) > 0
    return results


# ============================================================
# STAGE 7: INGEST EVIDENCE
# ============================================================

def ingest_reel_evidence(
    db,
    status: ReelStatus,
    instagram_id: str,
    ocr_results: List[dict],
) -> int:
    """
    Ingest transcript and OCR evidence for a reel.

    Args:
        db: SQLAlchemy session.
        status: ReelStatus object to update.
        instagram_id: Instagram ID.
        ocr_results: List of OCR result dicts.

    Returns:
        Number of evidence records added.
    """

    total_added = 0

    # Ingest transcript
    transcript_path = TRANSCRIPTS_DIR / f"{instagram_id}.json"
    if transcript_path.exists():
        try:
            added = ingest_transcript_from_file(
                db,
                transcript_path,
                BASE_DIR,
            )
            total_added += added
            if added > 0:
                print(f"      [OK] Transcript ingested")
        except Exception as e:
            status.add_error(f"transcript ingest error: {e}")
            print(f"      [FAIL] Transcript ingest error: {e}")

    # Ingest OCR
    if ocr_results:
        try:
            added = ingest_ocr_results(
                db,
                ocr_results,
                BASE_DIR,
            )
            total_added += added
            if added > 0:
                print(f"      [OK] OCR ingested ({added} records)")
        except Exception as e:
            status.add_error(f"OCR ingest error: {e}")
            print(f"      [FAIL] OCR ingest error: {e}")

    status.evidence_count = total_added

    try:
        db.commit()
    except Exception as e:
        status.add_error(f"database commit error: {e}")
        print(f"      [FAIL] Database commit error: {e}")
        db.rollback()
        return 0

    return total_added


# ============================================================
# STAGE 8: AI ANALYSIS
# ============================================================

def analyze_reel_with_ai(
    db,
    status: ReelStatus,
    instagram_id: str,
) -> bool:
    """
    Run AI analysis on a reel if sufficient evidence exists.

    Args:
        db: SQLAlchemy session.
        status: ReelStatus object to update.
        instagram_id: Instagram ID.

    Returns:
        True if AI analysis was run and succeeded, False otherwise.
    """

    if status.evidence_count == 0:
        print(f"    No evidence; skipping AI analysis")
        return False

    print(f"    Running AI analysis...")

    try:
        # Import ai_extract here to avoid circular imports
        from ai_extract import main as ai_main

        # TODO: Ideally refactor ai_extract to expose a function
        # For now, we call the CLI entry point which processes ALL reels
        # This is not ideal but works for now
        print(f"      (AI analysis runs as batch; see report)")
        return True

    except Exception as e:
        status.add_error(f"AI analysis error: {e}")
        print(f"      [FAIL] AI analysis error: {e}")
        return False


# ============================================================
# STAGE 9: UPDATE STATE FILE
# ============================================================

def update_state_file(
    instagram_id: str,
    status: ReelStatus,
):
    """
    Update ingestion flags in state/synced.json.

    Args:
        instagram_id: Instagram ID.
        status: ReelStatus object with updated state.
    """

    if not STATE_FILE.exists():
        return

    try:
        data = json.loads(
            STATE_FILE.read_text(encoding="utf-8")
        )

        items = data.get("items", {})
        item = items.get(instagram_id, {})

        ingestion = item.get("ingestion", {})

        # Update ingestion flags based on what we did
        if status.audio_extracted:
            # For now we mark video as ingested if we extracted audio
            pass  # Will update more granularly below

        if status.frames_extracted:
            ingestion["video"] = True

        if status.transcript_ingested:
            ingestion["transcription"] = True

        if status.ocr_ingested:
            ingestion["ocr"] = True

        item["ingestion"] = ingestion
        items[instagram_id] = item
        data["items"] = items

        STATE_FILE.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8",
        )

    except Exception as e:
        print(f"  WARNING: Failed to update state file: {e}")


# ============================================================
# MAIN ORCHESTRATION
# ============================================================

def process_pipeline(
    run_ai_analysis: bool = True,
    run_synthesis: bool = False,
):
    """
    Execute the complete pipeline.

    Args:
        run_ai_analysis: If True, run AI analysis after evidence ingestion.
        run_synthesis: If True, run career synthesis at the end.
    """

    print("\n" + "=" * 70)
    print("REEL2CAREER PIPELINE ORCHESTRATION")
    print("=" * 70)

    start_time = time.time()

    # ========================================
    # PHASE 1: DISCOVERY
    # ========================================

    print("\n" + "=" * 60)
    print("PHASE: Discovery")
    print("=" * 60)

    print("\nDiscovering synced reels...")
    reels = discover_reels()
    synced_count = len(reels)
    print(f"OK Found {synced_count} synced reels")

    video_count = sum(
        1 for r in reels.values()
        if r.get("media_kind") == "video"
    )
    carousel_count = sum(
        1 for r in reels.values()
        if r.get("media_kind") == "carousel"
    )
    print(f"  - Video reels: {video_count}")
    print(f"  - Carousel reels: {carousel_count}")

    # ========================================
    # PHASE 2: MIGRATION
    # ========================================

    if not migrate_reels_to_db():
        print("\n[FAIL] FAILED: Migration to SQLite failed")
        return {}

    # ========================================
    # PHASE 3: PROCESSING
    # ========================================

    print("\n" + "=" * 60)
    print("PHASE: Media Processing")
    print("=" * 60)

    db = SessionLocal()
    status_map: Dict[str, ReelStatus] = {}

    for instagram_id, reel_meta in reels.items():
        media_kind = reel_meta.get("media_kind", "unknown")

        print(f"\n[{instagram_id}] {media_kind.upper()}")

        status = ReelStatus(instagram_id, media_kind)

        try:
            # Step 1: Check media availability
            print("  Checking media availability...")
            if not check_media_availability(status, instagram_id, media_kind):
                status.skipped = True
                print(f"  [FAIL] SKIPPED: {status.skip_reason}")
                status_map[instagram_id] = status
                continue

            print(f"  [OK] Media found")

            # Step 2: Process media (extract frames/audio)
            if media_kind == "video":
                process_video_reel(db, status, instagram_id)
            elif media_kind == "carousel":
                process_carousel_reel(db, status, instagram_id)

            # Step 3: Transcribe (video only)
            if media_kind == "video":
                print("  Transcribing...")
                transcribe_reel_audio(status, instagram_id)

            # Step 4: OCR
            print("  Extracting text via OCR...")
            ocr_results = ocr_reel_media(status, instagram_id)

            # Step 5: Ingest evidence
            print("  Ingesting evidence...")
            ingest_reel_evidence(db, status, instagram_id, ocr_results)

            # Step 6: Update state file
            update_state_file(instagram_id, status)

        except Exception as e:
            status.add_error(f"unexpected error: {e}")
            print(f"  [FAIL] ERROR: {e}")
            traceback.print_exc()

        status_map[instagram_id] = status

    if hasattr(db, "close"):
        db.close()

    # ========================================
    # PHASE 4: AI ANALYSIS (BATCH)
    # ========================================

    if run_ai_analysis:
        print("\n" + "=" * 60)
        print("PHASE: AI Analysis")
        print("=" * 60)

        print("\nRunning AI analysis on all evidence-ready reels...")

        try:
            # Import and run AI extract
            # We'll just import the main here
            from ai_extract import main as ai_main

            # Call ai_extract which processes all reels with evidence
            ai_main()

            # Update status_map to mark analyzed reels
            db = SessionLocal()
            for instagram_id, status in status_map.items():
                reel = get_reel_by_id(db, instagram_id)
                if reel:
                    analysis_count = db.query(
                        Analysis
                    ).filter(
                        Analysis.reel_id == reel.id
                    ).count()
                    if analysis_count > 0:
                        status.ai_analyzed = True

            db.close()

        except Exception as e:
            print(f"[FAIL] AI analysis failed: {e}")
            traceback.print_exc()

    pipeline_status_map = status_map

    # ========================================
    # PHASE 5: SYNTHESIS (OPTIONAL)
    # ========================================

    if run_synthesis:
        print("\n" + "=" * 60)
        print("PHASE: Career Synthesis")
        print("=" * 60)

        try:
            from career_synthesis import generate_career_synthesis

            db = SessionLocal()
            synthesis = generate_career_synthesis(db)
            db.close()

            print("\n[OK] Career synthesis generated")
            print(f"  Identified interests: {len(synthesis['career_interests'])}")
            print(
                f"  Recurring skills: "
                f"{len(synthesis['recurring_skills'])}"
            )

        except Exception as e:
            print(f"[FAIL] Career synthesis failed: {e}")

    # ========================================
    # PHASE 6: REPORTING
    # ========================================

    print("\n" + "=" * 70)
    print("FINAL REPORT")
    print("=" * 70)

    # Print table
    print("\n{:<20} {:<10} {:<8} {:<12} {:<6} {:<8} {:<3} {:<20}".format(
        "ID", "TYPE", "MEDIA", "TRANSCRIPT", "OCR", "EVIDENCE", "AI", "STATUS"
    ))
    print("-" * 107)

    analyzed_count = 0
    evidence_count = 0
    transcribed_count = 0
    ocr_count = 0
    skipped_count = 0
    failed_count = 0

    for instagram_id, status in status_map.items():
        media = "[OK]" if status.media_exists else "[FAIL]"
        transcript = "[OK]" if status.transcript_ingested else "[FAIL]"
        ocr = "[OK]" if status.ocr_ingested else "[FAIL]"
        evidence = str(status.evidence_count)
        ai = "[OK]" if status.ai_analyzed else "[FAIL]"

        print("{:<20} {:<10} {:<8} {:<12} {:<6} {:<8} {:<3} {:<20}".format(
            instagram_id[-15:],  # Last 15 chars of ID
            status.media_kind,
            media,
            transcript,
            ocr,
            evidence,
            ai,
            status.status[:19],
        ))

        if status.ai_analyzed:
            analyzed_count += 1
        if status.evidence_count > 0:
            evidence_count += 1
        if status.transcript_ingested:
            transcribed_count += 1
        if status.ocr_ingested:
            ocr_count += 1
        if status.skipped:
            skipped_count += 1
        if status.errors:
            failed_count += 1

    print("-" * 107)

    elapsed = time.time() - start_time

    print(f"\nSUMMARY:")
    print(f"  Total synced: {synced_count}")
    print(f"    - Video: {video_count}")
    print(f"    - Carousel: {carousel_count}")
    print(f"  Media ready: {sum(1 for s in status_map.values() if s.media_exists)}")
    print(f"  Transcribed: {transcribed_count}")
    print(f"  OCR processed: {ocr_count}")
    print(f"  Evidence ready: {evidence_count}")
    print(f"  AI analyzed: {analyzed_count}")
    print(f"  Skipped: {skipped_count}")
    print(f"  Failed: {failed_count}")
    print(f"\n  Elapsed: {elapsed:.1f}s")

    # Print errors if any
    errors = [
        (iid, s.errors)
        for iid, s in status_map.items()
        if s.errors
    ]

    if errors:
        print("\nERRORS:")
        for instagram_id, error_list in errors:
            print(f"  [{instagram_id[-15:]}]")
            for error in error_list:
                print(f"    - {error}")

    print("\n" + "=" * 70)
    print("[OK] PIPELINE COMPLETE")
    print("=" * 70 + "\n")

    return pipeline_status_map


# ============================================================
# CLI ENTRY POINT
# ============================================================

def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Reel2Career Pipeline Orchestrator"
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI analysis",
    )
    parser.add_argument(
        "--synthesis",
        action="store_true",
        help="Run career synthesis at the end",
    )

    args = parser.parse_args()

    process_pipeline(
        run_ai_analysis=not args.no_ai,
        run_synthesis=args.synthesis,
    )


if __name__ == "__main__":
    main()
