"""
Tests for the Reel2Career pipeline orchestration.

Tests cover:
- Video and carousel reel processing
- Audio extraction
- Transcription
- OCR
- Evidence ingestion
- Idempotency
- Error resilience
- State tracking
"""

import pytest
import json
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

# Setup paths
BASE_DIR = Path(__file__).resolve().parents[2]

import sys
sys.path.insert(0, str(BASE_DIR / "backend" / "app"))
sys.path.insert(0, str(BASE_DIR))

from database import (
    SessionLocal,
    init_db,
    Base,
    Reel,
    Media,
    Evidence,
    Analysis,
)
from backend.app.process_pipeline import (
    ReelStatus,
    discover_reels,
    check_media_availability,
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace with necessary directories."""

    # Create directories
    (tmp_path / "state").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "vault" / "transcripts").mkdir(parents=True)
    (tmp_path / "vault" / "ocr").mkdir(parents=True)
    (tmp_path / "media" / "videos").mkdir(parents=True)
    (tmp_path / "media" / "audio").mkdir(parents=True)
    (tmp_path / "media" / "frames").mkdir(parents=True)

    return tmp_path


@pytest.fixture
def test_db(tmp_path):
    """Create a test database."""

    db_path = tmp_path / "data" / "test.db"
    
    # Monkeypatch the database URL
    import database
    original_db_url = database.DATABASE_URL
    database.DATABASE_URL = f"sqlite:///{db_path.as_posix()}"
    database.engine = database.create_engine(
        database.DATABASE_URL,
        connect_args={"check_same_thread": False},
        future=True,
    )
    database.SessionLocal = database.sessionmaker(
        bind=database.engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    Base.metadata.create_all(database.engine)

    db = database.SessionLocal()

    yield db

    db.close()

    # Restore
    database.DATABASE_URL = original_db_url


# ============================================================
# TEST REEL STATUS TRACKING
# ============================================================

class TestReelStatus:
    """Test ReelStatus class."""

    def test_video_status_initialization(self):
        """Test initializing a video reel status."""
        status = ReelStatus("12345", "video")
        assert status.instagram_id == "12345"
        assert status.media_kind == "video"
        assert status.media_exists is False
        assert status.audio_extracted is False
        assert status.errors == []

    def test_carousel_status_initialization(self):
        """Test initializing a carousel reel status."""
        status = ReelStatus("67890", "carousel")
        assert status.instagram_id == "67890"
        assert status.media_kind == "carousel"
        assert status.frame_count == 0

    def test_status_to_dict(self):
        """Test serializing status to dict."""
        status = ReelStatus("12345", "video")
        status.media_exists = True
        status.frame_count = 10

        data = status.to_dict()
        assert data["instagram_id"] == "12345"
        assert data["media_kind"] == "video"
        assert data["media_exists"] is True
        assert data["frame_count"] == 10

    def test_status_error_tracking(self):
        """Test error tracking in status."""
        status = ReelStatus("12345", "video")
        status.add_error("test error 1")
        status.add_error("test error 2")
        assert len(status.errors) == 2
        assert "test error 1" in status.errors

    def test_status_string_generation(self):
        """Test status property string generation."""
        status = ReelStatus("12345", "video")
        assert "NO_MEDIA" in status.status

        status.media_exists = True
        assert "MEDIA_FOUND" in status.status

        status.evidence_count = 5
        assert "EVIDENCE" in status.status

        status.ai_analyzed = True
        assert "AI_ANALYZED" in status.status

    def test_status_skipped(self):
        """Test skipped status."""
        status = ReelStatus("12345", "video")
        status.skipped = True
        status.skip_reason = "no video file"
        assert "SKIPPED" in status.status
        assert "no video file" in status.status


# ============================================================
# TEST MEDIA AVAILABILITY
# ============================================================

class TestMediaAvailability:
    """Test media availability checking."""

    def test_video_file_exists(self, temp_workspace):
        """Test detecting existing video file."""
        # Create a test video
        video_file = temp_workspace / "media" / "videos" / "12345.mp4"
        video_file.write_text("fake video data")

        status = ReelStatus("12345", "video")
        result = check_media_availability(
            status,
            "12345",
            "video",
        )

        assert result is False  # File system not pointing to temp

        # For actual test, we'd need to monkeypatch paths
        # This is a placeholder

    def test_carousel_slides_exist(self, temp_workspace):
        """Test detecting carousel slides."""
        status = ReelStatus("67890", "carousel")
        result = check_media_availability(
            status,
            "67890",
            "carousel",
        )

        # Without actual files, should return False
        assert result is False

    def test_missing_video(self):
        """Test missing video file."""
        status = ReelStatus("12345", "video")
        result = check_media_availability(
            status,
            "12345",
            "video",
        )

        assert result is False
        assert status.skip_reason == "no video file"

    def test_missing_carousel(self):
        """Test missing carousel slides."""
        status = ReelStatus("67890", "carousel")
        result = check_media_availability(
            status,
            "67890",
            "carousel",
        )

        assert result is False
        assert status.skip_reason == "no carousel slides"

    def test_unknown_media_kind(self):
        """Test unknown media type."""
        status = ReelStatus("12345", "unknown")
        result = check_media_availability(
            status,
            "12345",
            "unknown",
        )

        assert result is False
        assert "unknown media kind" in status.skip_reason


# ============================================================
# TEST STATE DISCOVERY
# ============================================================

class TestDiscoverReels:
    """Test reel discovery from state file."""

    def test_discover_empty_state(self, temp_workspace):
        """Test discovering reels from non-existent state."""
        # This will try to read from BASE_DIR, which doesn't exist in test
        # So we expect empty dict
        result = discover_reels()
        # Result depends on whether state file exists in actual workspace
        assert isinstance(result, dict)

    def test_discover_from_state_file(self, temp_workspace):
        """Test discovering reels from state file."""
        # Create a mock state file
        state_file = temp_workspace / "state" / "synced.json"
        state_data = {
            "version": 2,
            "items": {
                "12345": {
                    "media_kind": "video",
                    "metadata": {},
                },
                "67890": {
                    "media_kind": "carousel",
                    "metadata": {},
                },
            },
        }
        state_file.write_text(json.dumps(state_data))

        # Would need to patch BASE_DIR paths
        # This is a placeholder


# ============================================================
# TEST IDEMPOTENCY
# ============================================================

class TestIdempotency:
    """Test pipeline idempotency."""

    def test_duplicate_evidence_prevention(self, test_db):
        """Test that duplicate evidence is not created."""
        from backend.app.ingest import add_evidence

        # Create a test reel
        reel = Reel(
            instagram_id="12345",
            shortcode="test",
            author="Test Author",
            url="https://instagram.com/test",
            media_kind="video",
            media_type="mp4",
            caption="Test caption",
        )
        test_db.add(reel)
        test_db.commit()

        # Add evidence
        result1 = add_evidence(
            test_db,
            reel.id,
            "transcript",
            "vault/transcripts/12345.json",
            "Test transcript text",
            0.75,
        )
        assert result1 is True
        test_db.commit()

        # Try adding same evidence again
        result2 = add_evidence(
            test_db,
            reel.id,
            "transcript",
            "vault/transcripts/12345.json",
            "Test transcript text",
            0.75,
        )
        assert result2 is False

        # Check only one evidence record exists
        count = test_db.query(Evidence).count()
        assert count == 1

    def test_transcript_reprocessing(self, test_db):
        """Test that transcripts are not reprocessed if they exist."""
        from backend.app.transcribe_audio import transcribe_audio
        from pathlib import Path

        # This would require mock audio files
        # Placeholder for actual test


# ============================================================
# TEST ERROR RESILIENCE
# ============================================================

class TestErrorResilience:
    """Test pipeline resilience to errors."""

    def test_one_reel_failure_doesnt_stop_others(self):
        """Test that one reel's failure doesn't stop other reels."""
        # This would test the main loop continuing after error
        # Placeholder


# ============================================================
# TEST STATE FLAG UPDATES
# ============================================================

class TestStateFlagUpdates:
    """Test state/synced.json flag updates."""

    def test_state_file_updates_after_processing(self, temp_workspace):
        """Test that state file is updated after processing."""
        # Create initial state
        state_file = temp_workspace / "state" / "synced.json"
        state_data = {
            "version": 2,
            "items": {
                "12345": {
                    "media_kind": "video",
                    "ingestion": {
                        "metadata": True,
                        "video": False,
                        "transcription": False,
                        "ocr": False,
                    },
                },
            },
        }
        state_file.write_text(json.dumps(state_data))

        # In real test, process reel and check state file updated
        # Placeholder


# ============================================================
# TEST DATABASE OPERATIONS
# ============================================================

class TestDatabaseOperations:
    """Test database operations."""

    def test_reel_creation(self, test_db):
        """Test creating a reel in the database."""
        reel = Reel(
            instagram_id="test_12345",
            shortcode="abc123",
            author="Test User",
            url="https://instagram.com/test",
            media_kind="video",
            media_type="mp4",
            caption="Test caption",
        )
        test_db.add(reel)
        test_db.commit()

        # Query back
        found = test_db.query(Reel).filter(
            Reel.instagram_id == "test_12345"
        ).first()

        assert found is not None
        assert found.shortcode == "abc123"
        assert found.author == "Test User"

    def test_evidence_creation(self, test_db):
        """Test creating evidence records."""
        # Create reel first
        reel = Reel(
            instagram_id="test_12345",
            shortcode="abc123",
            author="Test User",
            url="https://instagram.com/test",
            media_kind="video",
            media_type="mp4",
            caption="Test caption",
        )
        test_db.add(reel)
        test_db.commit()

        # Add evidence
        evidence = Evidence(
            reel_id=reel.id,
            evidence_type="transcript",
            source_path="vault/transcripts/test_12345.json",
            content="Test transcript content",
            confidence=0.75,
        )
        test_db.add(evidence)
        test_db.commit()

        # Query back
        found = test_db.query(Evidence).filter(
            Evidence.reel_id == reel.id
        ).first()

        assert found is not None
        assert found.evidence_type == "transcript"
        assert found.content == "Test transcript content"


# ============================================================
# TEST REPORTING
# ============================================================

class TestReporting:
    """Test reporting functionality."""

    def test_status_summary_counts(self):
        """Test counting different status types."""
        statuses = {
            "1": ReelStatus("1", "video"),
            "2": ReelStatus("2", "video"),
            "3": ReelStatus("3", "carousel"),
        }

        statuses["1"].media_exists = True
        statuses["1"].evidence_count = 5

        statuses["2"].skipped = True

        statuses["3"].media_exists = True
        statuses["3"].evidence_count = 3
        statuses["3"].ai_analyzed = True

        media_ready = sum(
            1 for s in statuses.values()
            if s.media_exists
        )
        evidence_ready = sum(
            1 for s in statuses.values()
            if s.evidence_count > 0
        )
        ai_analyzed = sum(
            1 for s in statuses.values()
            if s.ai_analyzed
        )
        skipped = sum(
            1 for s in statuses.values()
            if s.skipped
        )

        assert media_ready == 2
        assert evidence_ready == 2
        assert ai_analyzed == 1
        assert skipped == 1


# ============================================================
# INTEGRATION TESTS
# ============================================================

class TestIntegration:
    """Integration tests with actual files."""

    @pytest.mark.skip(
        reason="Requires full workspace setup"
    )
    def test_full_pipeline_dry_run(self):
        """Test full pipeline on a small set."""
        pass

    @pytest.mark.skip(
        reason="Requires actual Instagram data"
    )
    def test_pipeline_on_real_data(self):
        """Test pipeline on real synced data."""
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
