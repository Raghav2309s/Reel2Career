from pathlib import Path
import json
import re
import sys

BASE_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(APP_DIR))

from database import SessionLocal, Evidence


TRANSCRIPT_FILE = (
    BASE_DIR
    / "vault"
    / "transcripts"
    / "3938231075955764704.json"
)


def extract_frame_number(path):
    match = re.search(
        r"frame_(\d+)\.jpg$",
        path,
        re.IGNORECASE,
    )

    if not match:
        return None

    return int(match.group(1))


def upgrade_transcript(db):
    data = json.loads(
        TRANSCRIPT_FILE.read_text(
            encoding="utf-8"
        )
    )

    segments = data.get(
        "segments",
        []
    )

    rows = (
        db.query(Evidence)
        .filter(
            Evidence.evidence_type
            == "transcript"
        )
        .all()
    )

    updated = 0

    for row in rows:

        # Only upgrade the Reel 1 transcript.
        if row.reel_id != 1:
            continue

        existing = row.content

        structured = {
            "type": "transcript",
            "language": data.get(
                "language"
            ),
            "language_probability":
                data.get(
                    "language_probability"
                ),
            "duration":
                data.get("duration"),
            "segments": segments,
            "text": existing,
        }

        row.content = json.dumps(
            structured,
            ensure_ascii=False,
        )

        updated += 1

    return updated


def upgrade_ocr(db):

    rows = (
        db.query(Evidence)
        .filter(
            Evidence.evidence_type
            == "ocr"
        )
        .all()
    )

    updated = 0

    for row in rows:

        # Don't upgrade an already structured record.
        try:
            existing = json.loads(
                row.content
            )

            if isinstance(
                existing,
                dict
            ):
                continue

        except Exception:
            pass

        source = (
            row.source_path
            .replace("\\", "/")
        )

        frame_number = (
            extract_frame_number(source)
        )

        metadata = {
            "type": "ocr",
            "source": source,
            "frame_number":
                frame_number,
            "timestamp_seconds": None,
            "text": row.content,
        }

        # Video frames were generated at
        # one frame every five seconds.
        if (
            frame_number is not None
            and "3938231075955764704"
            in source
        ):
            metadata[
                "timestamp_seconds"
            ] = (
                frame_number - 1
            ) * 5

        # Carousel slides do not have a
        # video timestamp.
        if (
            "3957068783193726412"
            in source
        ):
            metadata[
                "timestamp_seconds"
            ] = None

            match = re.search(
                r"_(\d+)\.jpg$",
                source,
            )

            if match:
                metadata[
                    "slide_number"
                ] = int(
                    match.group(1)
                )

        row.content = json.dumps(
            metadata,
            ensure_ascii=False,
        )

        updated += 1

    return updated


def main():

    print(
        "=== Evidence Metadata Upgrade ==="
    )
    print()

    db = SessionLocal()

    try:

        transcript_count = (
            upgrade_transcript(db)
        )

        ocr_count = upgrade_ocr(db)

        db.commit()

        print(
            f"Transcript records upgraded: "
            f"{transcript_count}"
        )

        print(
            f"OCR records upgraded: "
            f"{ocr_count}"
        )

        print()
        print(
            "Evidence metadata upgrade complete."
        )

    except Exception:

        db.rollback()
        raise

    finally:

        db.close()


if __name__ == "__main__":
    main()