from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(APP_DIR))

try:
    import backend.app.database as database
    from backend.app.database import Evidence, Reel, SessionLocal
except ImportError:  # pragma: no cover - direct script execution fallback
    import database
    from database import Evidence, Reel, SessionLocal


def load_json(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Required file not found:\n{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def discover_evidence_files(base_dir: Path | str | None = None) -> dict[str, list[Path]]:
    base_dir = Path(base_dir) if base_dir is not None else BASE_DIR

    transcripts_dir = base_dir / "vault" / "transcripts"
    ocr_dir = base_dir / "vault" / "ocr"
    reels_dir = base_dir / "vault" / "reels"

    files = {
        "transcripts": sorted(transcripts_dir.glob("*.json")) if transcripts_dir.exists() else [],
        "ocr": sorted(ocr_dir.glob("*.json")) if ocr_dir.exists() else [],
        "reels": sorted(reels_dir.glob("*.md")) if reels_dir.exists() else [],
    }

    return files


def _resolve_reel(
    db,
    instagram_id: str | None,
    source_path: str | None = None,
    source_type: str | None = None,
):
    if not instagram_id:
        if source_path:
            normalized = source_path.replace("\\", "/")
            match = re.search(r"(?:^|/)(\d+)(?:_|/|\.json|\.jpg|\.md)", normalized)
            if match:
                instagram_id = match.group(1)

        if not instagram_id:
            if source_type == "video_frame":
                match = re.search(r"(?:^|/)(\d+)/frame_", source_path or "")
                if match:
                    instagram_id = match.group(1)

            elif source_type == "carousel_slide":
                match = re.search(r"(?:^|/)(\d+)_", source_path or "")
                if match:
                    instagram_id = match.group(1)

    if not instagram_id:
        return None

    return db.query(Reel).filter(
        Reel.instagram_id == str(instagram_id)
    ).first()


def evidence_exists(db, reel_id, evidence_type, source_path):
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
    reel_id,
    evidence_type,
    source_path,
    content,
    confidence,
):
    if not source_path:
        return False

    if not content:
        return False

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


def _extract_frontmatter_value(frontmatter: str, key: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(key)}:\s*(.*?)(?=\n[a-zA-Z_][a-zA-Z0-9_]*:\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )

    match = pattern.search(frontmatter)

    if not match:
        return ""

    value = match.group(1).strip()

    if value == "|":
        return ""

    return value


def _extract_caption(markdown: str) -> str:
    frontmatter_match = re.match(
        r"^---\s*\n(.*?)\n---\s*\n",
        markdown,
        re.DOTALL,
    )

    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)

        caption_match = re.search(
            r"^caption:\s*\|\s*\n(.*?)(?=^[a-zA-Z_][a-zA-Z0-9_]*:\s|\Z)",
            frontmatter,
            re.MULTILINE | re.DOTALL,
        )

        if caption_match:
            lines = caption_match.group(1).splitlines()

            caption_lines = []

            for line in lines:
                if line.startswith("  "):
                    caption_lines.append(line[2:])
                elif line.strip():
                    caption_lines.append(line.strip())

            caption = "\n".join(caption_lines).strip()

            if caption:
                return caption

    body_match = re.search(
        r"^## Caption\s*\n(.*?)(?=^## |\Z)",
        markdown,
        re.MULTILINE | re.DOTALL,
    )

    if body_match:
        caption = body_match.group(1).strip()

        if caption and caption != "_No caption._":
            return caption

    return ""


def ingest_reel_markdown(
    db,
    reel_path: Path,
    base_dir: Path | str | None = None,
) -> int:
    reel_path = Path(reel_path)

    if not reel_path.exists():
        return 0

    base_dir = Path(base_dir) if base_dir is not None else BASE_DIR

    try:
        markdown = reel_path.read_text(encoding="utf-8")
    except Exception:
        return 0

    instagram_id_match = re.search(
        r"(?:^|[\s-])(\d{10,})(?:\.md)?$",
        reel_path.name,
    )

    instagram_id = (
        instagram_id_match.group(1)
        if instagram_id_match
        else None
    )

    if not instagram_id:
        frontmatter_match = re.match(
            r"^---\s*\n(.*?)\n---\s*\n",
            markdown,
            re.DOTALL,
        )

        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)

            url_match = re.search(
                r'^url:\s*"https://www\.instagram\.com/p/[^"]+"',
                frontmatter,
                re.MULTILINE,
            )

            if url_match:
                # The filename normally provides the ID.
                # Do not invent an Instagram ID from the shortcode.
                pass

    reel = _resolve_reel(
        db,
        instagram_id,
        source_path=str(reel_path.relative_to(base_dir)),
    )

    if reel is None:
        return 0

    caption = _extract_caption(markdown)

    if not caption:
        return 0

    relative = str(reel_path.relative_to(base_dir))

    inserted = add_evidence(
        db,
        reel.id,
        "caption",
        relative,
        caption,
        1.0,
    )

    return 1 if inserted else 0


def ingest_transcript_file(
    db,
    transcript_path: Path,
    base_dir: Path | str | None = None,
) -> int:
    transcript_path = Path(transcript_path)

    if not transcript_path.exists():
        return 0

    base_dir = Path(base_dir) if base_dir is not None else BASE_DIR

    try:
        data = load_json(transcript_path)
    except Exception:
        return 0

    instagram_id = str(
        data.get("instagram_id") or transcript_path.stem
    ).strip()

    if not instagram_id:
        return 0

    reel = _resolve_reel(
        db,
        instagram_id,
        source_path=str(transcript_path.relative_to(base_dir)),
    )

    if reel is None:
        return 0

    content = (data.get("text") or "").strip()

    if not content:
        segments = data.get("segments") or []

        content = " ".join(
            segment.get("text", "").strip()
            for segment in segments
            if segment.get("text", "").strip()
        )

    if not content:
        return 0

    relative = str(transcript_path.relative_to(base_dir))

    inserted = add_evidence(
        db,
        reel.id,
        "transcript",
        relative,
        content,
        0.75,
    )

    return 1 if inserted else 0


def ingest_ocr_file(
    db,
    ocr_path: Path,
    base_dir: Path | str | None = None,
) -> int:
    ocr_path = Path(ocr_path)

    if not ocr_path.exists():
        return 0

    base_dir = Path(base_dir) if base_dir is not None else BASE_DIR

    try:
        data = load_json(ocr_path)
    except Exception:
        return 0

    inserted_count = 0

    for item in data.get("results", []):
        source_type = str(
            item.get("source_type") or ""
        ).strip()

        source_path = str(
            item.get("source_file") or ""
        ).strip()

        if not source_path:
            continue

        content = str(
            item.get("text") or ""
        ).strip()

        if not content:
            continue

        instagram_id = str(
            item.get("instagram_id") or ""
        ).strip()

        reel = _resolve_reel(
            db,
            instagram_id,
            source_path,
            source_type,
        )

        if reel is None:
            continue

        inserted = add_evidence(
            db,
            reel.id,
            "ocr",
            source_path,
            content,
            0.70,
        )

        if inserted:
            inserted_count += 1

    return inserted_count


def ingest_all_evidence(
    db,
    base_dir: Path | str | None = None,
) -> int:
    base_dir = Path(base_dir) if base_dir is not None else BASE_DIR

    files = discover_evidence_files(base_dir)

    inserted_total = 0

    for reel_path in files["reels"]:
        inserted_total += ingest_reel_markdown(
            db,
            reel_path,
            base_dir,
        )

    for transcript_path in files["transcripts"]:
        inserted_total += ingest_transcript_file(
            db,
            transcript_path,
            base_dir,
        )

    for ocr_path in files["ocr"]:
        inserted_total += ingest_ocr_file(
            db,
            ocr_path,
            base_dir,
        )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return inserted_total


def main():
    print("=== Reel2Career Evidence Ingestion ===")

    db = SessionLocal()

    try:
        inserted = ingest_all_evidence(db)
        db.commit()

        print(f"Evidence inserted: {inserted}")
        print(
            f"Total evidence rows: "
            f"{db.query(Evidence).count()}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
