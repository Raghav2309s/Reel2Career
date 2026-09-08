from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from database import (
    SessionLocal,
    init_db,
    Reel,
    Media,
    CarouselSlide,
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]

STATE_FILE = (
    BASE_DIR
    / "state"
    / "synced.json"
)


# ============================================================
# HELPERS
# ============================================================

def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value
        )
    except (TypeError, ValueError):
        return None


def absolute_path(relative_path):
    if not relative_path:
        return None

    return (
        BASE_DIR / relative_path
    )


def file_size(relative_path):
    if not relative_path:
        return None

    path = absolute_path(
        relative_path
    )

    if path and path.exists():
        return path.stat().st_size

    return None


# ============================================================
# MIGRATION
# ============================================================

def migrate():
    print("=== Reel2Career SQLite Migration ===")
    print()

    if not STATE_FILE.exists():
        raise SystemExit(
            f"State file not found:\n{STATE_FILE}"
        )

    init_db()

    state = json.loads(
        STATE_FILE.read_text(
            encoding="utf-8"
        )
    )

    items = state.get(
        "items",
        {}
    )

    print(
        f"Found {len(items)} items in synced.json."
    )

    print()

    db = SessionLocal()

    try:

        imported = 0
        skipped = 0
        updated = 0

        for media_id, item in items.items():

            print(
                f"Processing {media_id}..."
            )

            # ------------------------------------------------
            # Check whether Reel already exists
            # ------------------------------------------------

            existing = db.scalar(
                select(Reel).where(
                    Reel.instagram_id
                    == str(media_id)
                )
            )

            if existing:

                reel = existing

                print(
                    "    Reel already exists."
                )

                updated += 1

            else:

                reel = Reel(
                    instagram_id=str(
                        media_id
                    ),
                    shortcode=item.get(
                        "shortcode"
                    ),
                    author=item.get(
                        "author"
                    ),
                    url=item.get(
                        "url"
                    ),
                    media_kind=item.get(
                        "media_kind",
                        "unknown",
                    ),
                    media_type=item.get(
                        "media_type"
                    ),
                    caption="",
                    reel_date=parse_datetime(
                        item.get(
                            "reel_date"
                        )
                    ),
                    saved_to_reel2career=(
                        parse_datetime(
                            item.get(
                                "saved_to_reel2career"
                            )
                        )
                    ),
                    synced_at=(
                        parse_datetime(
                            item.get(
                                "synced_at"
                            )
                        )
                        or datetime.utcnow()
                    ),
                    metadata_ingested=(
                        item.get(
                            "ingestion",
                            {}
                        ).get(
                            "metadata",
                            True,
                        )
                    ),
                    thumbnail_ingested=(
                        item.get(
                            "ingestion",
                            {}
                        ).get(
                            "thumbnail",
                            False,
                        )
                    ),
                    video_ingested=(
                        item.get(
                            "ingestion",
                            {}
                        ).get(
                            "video",
                            False,
                        )
                    ),
                    carousel_ingested=(
                        item.get(
                            "ingestion",
                            {}
                        ).get(
                            "carousel",
                            False,
                        )
                    ),
                    transcription_complete=(
                        item.get(
                            "ingestion",
                            {}
                        ).get(
                            "transcription",
                            False,
                        )
                    ),
                    ocr_complete=(
                        item.get(
                            "ingestion",
                            {}
                        ).get(
                            "ocr",
                            False,
                        )
                    ),
                    ai_analysis_complete=(
                        item.get(
                            "ingestion",
                            {}
                        ).get(
                            "ai_analysis",
                            False,
                        )
                    ),
                    resource_verification_complete=(
                        item.get(
                            "ingestion",
                            {}
                        ).get(
                            "resource_verification",
                            False,
                        )
                    ),
                )

                db.add(reel)

                db.flush()

                imported += 1

                print(
                    "    Reel inserted."
                )

            # ------------------------------------------------
            # Media
            # ------------------------------------------------

            media_paths = []

            thumbnail = item.get(
                "thumbnail"
            )

            video = item.get(
                "video"
            )

            if thumbnail:
                media_paths.append(
                    (
                        "thumbnail",
                        thumbnail,
                        "image/jpeg",
                    )
                )

            if video:
                media_paths.append(
                    (
                        "video",
                        video,
                        "video/mp4",
                    )
                )

            for (
                media_type,
                path,
                mime_type,
            ) in media_paths:

                existing_media = db.scalar(
                    select(Media).where(
                        Media.reel_id
                        == reel.id,
                        Media.file_path
                        == path,
                    )
                )

                if existing_media:
                    continue

                db.add(
                    Media(
                        reel_id=reel.id,
                        media_type=media_type,
                        file_path=path,
                        mime_type=mime_type,
                        file_size=file_size(
                            path
                        ),
                    )
                )

                print(
                    f"    Media registered: "
                    f"{media_type}"
                )

            # ------------------------------------------------
            # Carousel slides
            # ------------------------------------------------

            carousel_paths = item.get(
                "carousel_slides",
                []
            )

            for position, path in enumerate(
                carousel_paths,
                start=1,
            ):

                existing_slide = db.scalar(
                    select(
                        CarouselSlide
                    ).where(
                        CarouselSlide.reel_id
                        == reel.id,
                        CarouselSlide.position
                        == position,
                    )
                )

                if existing_slide:
                    continue

                db.add(
                    CarouselSlide(
                        reel_id=reel.id,
                        position=position,
                        file_path=path,
                    )
                )

                print(
                    f"    Carousel slide "
                    f"{position}: registered"
                )

            db.commit()

        print()

        print(
            "=== Migration Complete ==="
        )

        print(
            f"Imported: {imported}"
        )

        print(
            f"Updated:  {updated}"
        )

        print(
            f"Skipped:  {skipped}"
        )

        print()

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()


if __name__ == "__main__":
    migrate()