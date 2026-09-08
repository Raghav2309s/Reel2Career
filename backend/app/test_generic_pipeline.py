import json
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR / "backend" / "app"))
sys.path.insert(0, str(BASE_DIR))

from audio import extract_audio
from extract_frames import extract_frames
from transcribe import transcribe_audio
from ocr import process_video_frames, process_carousel_slides
from backend.app.ingest_evidence import ingest_all_evidence
from backend.app import database
from backend.app.database import Base, Reel, Evidence


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    import backend.app.database as database

    original_url = database.DATABASE_URL
    original_engine = database.engine
    original_session = database.SessionLocal

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
    try:
        yield db
    finally:
        db.close()
        database.DATABASE_URL = original_url
        database.engine = original_engine
        database.SessionLocal = original_session


def test_extract_audio_skips_existing_valid_wav(tmp_path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")
    output = tmp_path / "audio" / "result.wav"
    output.parent.mkdir()
    output.write_bytes(b"wav")

    assert extract_audio(video, output) is True
    assert output.read_bytes() == b"wav"


def test_extract_frames_is_idempotent(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    output_dir = tmp_path / "frames"
    output_dir.mkdir()
    existing = output_dir / "frame_0001.jpg"
    existing.write_bytes(b"frame")

    assert extract_frames(video, output_dir) == 1
    assert existing.exists()


def test_transcribe_audio_writes_json_and_txt(tmp_path, monkeypatch):
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    out_dir = tmp_path / "transcripts"

    class FakeInfo:
        language = "en"
        language_probability = 0.99
        duration = 12.5

    class FakeSegment:
        def __init__(self, text, start, end):
            self.text = text
            self.start = start
            self.end = end

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, path, beam_size=5, vad_filter=True, condition_on_previous_text=True):
            return [FakeSegment("hello world", 0.0, 2.0)], FakeInfo()

    monkeypatch.setattr("transcribe.WhisperModel", FakeModel)

    result = transcribe_audio("12345", audio, out_dir)

    assert result is True
    json_path = out_dir / "12345.json"
    txt_path = out_dir / "12345.txt"
    assert json_path.exists()
    assert txt_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["instagram_id"] == "12345"
    assert payload["text"] == "hello world"


def test_ocr_processes_video_and_carousel_frames(tmp_path):
    frames_dir = tmp_path / "media" / "frames"
    video_dir = frames_dir / "12345"
    video_dir.mkdir(parents=True)
    (video_dir / "frame_0001.jpg").write_bytes(b"img1")
    (frames_dir / "67890_01.jpg").write_bytes(b"img2")

    processed = process_video_frames(video_dir, base_dir=tmp_path)
    assert len(processed) == 1
    assert processed[0]["instagram_id"] == "12345"

    carousel = process_carousel_slides(frames_dir, "67890", base_dir=tmp_path)
    assert len(carousel) == 1
    assert carousel[0]["instagram_id"] == "67890"


def test_evidence_ingest_discovers_transcript_and_ocr(tmp_path, temp_db):
    reel = Reel(instagram_id="12345", media_kind="video")
    temp_db.add(reel)
    temp_db.commit()

    trans_dir = tmp_path / "vault" / "transcripts"
    trans_dir.mkdir(parents=True)
    (trans_dir / "12345.json").write_text(json.dumps({
        "instagram_id": "12345",
        "audio_file": "media/audio/12345.wav",
        "language": "en",
        "language_probability": 0.99,
        "duration": 8.0,
        "segments": [{"start": 0.0, "end": 2.0, "text": "hello world"}],
        "text": "hello world",
    }), encoding="utf-8")

    ocr_dir = tmp_path / "vault" / "ocr"
    ocr_dir.mkdir(parents=True)
    (ocr_dir / "ocr_results.json").write_text(json.dumps({
        "results": [{
            "source_type": "video_frame",
            "source_file": "media/frames/12345/frame_0001.jpg",
            "text": "hello",
            "instagram_id": "12345",
        }]
    }), encoding="utf-8")

    inserted = ingest_all_evidence(temp_db, base_dir=tmp_path)
    assert inserted >= 2
    assert temp_db.query(Evidence).filter(Evidence.reel_id == reel.id).count() >= 2


def test_pipeline_processes_one_failure_without_stopping_others(tmp_path, monkeypatch):
    from backend.app import process_pipeline

    items = {
        "1": {"media_kind": "video", "ingestion": {"metadata": True}},
        "2": {"media_kind": "video", "ingestion": {"metadata": True}},
    }

    monkeypatch.setattr(process_pipeline, "discover_reels", lambda: items)
    monkeypatch.setattr(process_pipeline, "migrate_reels_to_db", lambda: True)

    class DummySession:
        def close(self):
            pass

    monkeypatch.setattr(process_pipeline, "SessionLocal", lambda: DummySession())

    calls = []

    def fake_process(video_id):
        calls.append(video_id)
        if video_id == "2":
            raise RuntimeError("boom")
        return True

    monkeypatch.setattr(process_pipeline, "process_video_reel", fake_process)
    monkeypatch.setattr(process_pipeline, "transcribe_reel_audio", lambda *args, **kwargs: True)
    monkeypatch.setattr(process_pipeline, "ocr_reel_media", lambda *args, **kwargs: [])
    monkeypatch.setattr(process_pipeline, "ingest_reel_evidence", lambda *args, **kwargs: 0)

    statuses = process_pipeline.process_pipeline(run_ai_analysis=False)
    assert len(statuses) == 2
    assert "1" in statuses
    assert "2" in statuses
