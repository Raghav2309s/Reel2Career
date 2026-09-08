from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from instagrapi import Client


# ============================================================
# PATHS / CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

SESSION_FILE = BASE_DIR / "session.json"

VAULT_DIR = BASE_DIR / "vault" / "reels"

MEDIA_DIR = BASE_DIR / "media"
VIDEO_DIR = MEDIA_DIR / "videos"
THUMBNAIL_DIR = MEDIA_DIR / "thumbnails"
FRAMES_DIR = MEDIA_DIR / "frames"
AUDIO_DIR = MEDIA_DIR / "audio"

STATE_DIR = BASE_DIR / "state"
STATE_FILE = STATE_DIR / "synced.json"

COLLECTION_NAME = "Reel2Career"

MAX_COLLECTION_ITEMS = 50


# ============================================================
# GENERAL HELPERS
# ============================================================

def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_filename(
    value: str,
    fallback: str = "reel",
) -> str:
    """
    Convert arbitrary Instagram text into a Windows-safe
    filename.
    """

    value = value.strip()

    value = re.sub(
        r'[<>:"/\\|?*\x00-\x1F]',
        "_",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    value = value.strip(" .")

    return value[:100] or fallback


def yaml_escape(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace('"', '\\"')
    )


def yaml_multiline(value: str) -> str:
    if not value:
        return "  "

    return "\n".join(
        f"  {line}"
        for line in value.splitlines()
    )


# ============================================================
# STATE MANAGEMENT
# ============================================================

def load_state() -> dict:
    """
    Load local ingestion state.

    Existing version-1 state is automatically accepted.
    """

    if not STATE_FILE.exists():
        return {
            "version": 2,
            "items": {},
        }

    try:
        state = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Invalid state file: {STATE_FILE}\n"
            f"{exc}"
        )

    if "items" not in state:
        state["items"] = {}

    state["version"] = max(
        int(state.get("version", 1)),
        2,
    )

    return state


def save_state(state: dict) -> None:
    """
    Atomically save state so an interrupted write does not
    corrupt synced.json.
    """

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_file = STATE_FILE.with_suffix(
        ".tmp"
    )

    temp_file.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temp_file.replace(STATE_FILE)


def get_existing_ingestion(
    existing_item: dict | None,
) -> dict:
    """
    Preserve existing processing flags.

    This allows future stages such as transcription,
    OCR, AI analysis and resource verification to be
    added without losing their state.
    """

    if existing_item:
        existing = existing_item.get(
            "ingestion",
            {},
        )
    else:
        existing = {}

    return {
        "metadata": bool(
            existing.get(
                "metadata",
                bool(existing_item),
            )
        ),
        "thumbnail": bool(
            existing.get(
                "thumbnail",
                bool(
                    existing_item
                    and existing_item.get(
                        "thumbnail"
                    )
                ),
            )
        ),
        "video": bool(
            existing.get(
                "video",
                bool(
                    existing_item
                    and existing_item.get(
                        "video"
                    )
                ),
            )
        ),
        "carousel": bool(
            existing.get(
                "carousel",
                bool(
                    existing_item
                    and existing_item.get(
                        "carousel_slides"
                    )
                ),
            )
        ),
        "transcription": bool(
            existing.get(
                "transcription",
                False,
            )
        ),
        "ocr": bool(
            existing.get(
                "ocr",
                False,
            )
        ),
        "ai_analysis": bool(
            existing.get(
                "ai_analysis",
                False,
            )
        ),
        "resource_verification": bool(
            existing.get(
                "resource_verification",
                False,
            )
        ),
    }


# ============================================================
# NETWORK / MEDIA DOWNLOAD
# ============================================================

def download_file(
    url: str | None,
    destination: Path,
) -> bool:

    if not url:
        return False

    try:
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        response = requests.get(
            url,
            timeout=60,
            stream=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                )
            },
        )

        response.raise_for_status()

        with destination.open(
            "wb"
        ) as file:

            for chunk in response.iter_content(
                chunk_size=128 * 1024
            ):

                if chunk:
                    file.write(chunk)

        return True

    except requests.RequestException as exc:

        print(
            "    Download failed: "
            f"{type(exc).__name__}: {exc}"
        )

        return False


# ============================================================
# INSTAGRAM MEDIA HELPERS
# ============================================================

def get_post_url(post) -> str:

    code = getattr(
        post,
        "code",
        None,
    )

    if code:
        return (
            "https://www.instagram.com/p/"
            f"{code}/"
        )

    return ""


def get_reel_date(post) -> str:

    taken_at = getattr(
        post,
        "taken_at",
        None,
    )

    if not taken_at:
        return ""

    if taken_at.tzinfo is None:
        taken_at = taken_at.replace(
            tzinfo=timezone.utc
        )

    return taken_at.isoformat()


def get_author(post) -> str:

    user = getattr(
        post,
        "user",
        None,
    )

    return getattr(
        user,
        "username",
        "",
    )


def get_caption(post) -> str:

    return (
        getattr(
            post,
            "caption_text",
            None,
        )
        or ""
    ).strip()


def get_media_kind(post) -> str:
    """
    Normalize Instagram's media representation.

    media_type:
      1 = image
      2 = video
      8 = carousel

    product_type is also checked because it gives
    a more explicit description for some posts.
    """

    media_type = getattr(
        post,
        "media_type",
        None,
    )

    product_type = getattr(
        post,
        "product_type",
        None,
    )

    if (
        product_type
        == "carousel_container"
        or media_type == 8
    ):
        return "carousel"

    if (
        product_type == "clips"
        or media_type == 2
    ):
        return "video"

    if media_type == 1:
        return "image"

    return "unknown"


# ============================================================
# VIDEO INGESTION
# ============================================================

def acquire_video(
    post,
    media_id: str,
    existing_path: str = "",
) -> str:

    if existing_path:
        existing_file = (
            BASE_DIR / existing_path
        )

        if existing_file.exists():
            print(
                "    Video already exists."
            )

            return existing_path

    video_url = getattr(
        post,
        "video_url",
        None,
    )

    if not video_url:
        print(
            "    No video URL exposed by Instagram."
        )

        return ""

    video_file = (
        VIDEO_DIR
        / f"{media_id}.mp4"
    )

    print("    Downloading video...")

    if not download_file(
        video_url,
        video_file,
    ):
        return ""

    return (
        video_file
        .relative_to(BASE_DIR)
        .as_posix()
    )


# ============================================================
# THUMBNAIL INGESTION
# ============================================================

def acquire_thumbnail(
    post,
    media_id: str,
    existing_path: str = "",
) -> str:

    if existing_path:

        existing_file = (
            BASE_DIR / existing_path
        )

        if existing_file.exists():
            print(
                "    Thumbnail already exists."
            )

            return existing_path

    thumbnail_url = getattr(
        post,
        "thumbnail_url",
        None,
    )

    if not thumbnail_url:

        print(
            "    No thumbnail URL exposed."
        )

        return ""

    thumbnail_file = (
        THUMBNAIL_DIR
        / f"{media_id}.jpg"
    )

    print(
        "    Downloading thumbnail..."
    )

    if not download_file(
        thumbnail_url,
        thumbnail_file,
    ):
        return ""

    return (
        thumbnail_file
        .relative_to(BASE_DIR)
        .as_posix()
    )


# ============================================================
# CAROUSEL INGESTION
# ============================================================

def acquire_carousel(
    post,
    media_id: str,
    existing_paths: list[str],
) -> list[str]:

    resources = getattr(
        post,
        "resources",
        None,
    )

    if not resources:

        print(
            "    No carousel resources found."
        )

        return existing_paths

    print(
        "    Carousel resources: "
        f"{len(resources)}"
    )

    downloaded_paths = []

    for index, resource in enumerate(
        resources,
        start=1,
    ):

        expected_file = (
            FRAMES_DIR
            / f"{media_id}_{index:02d}.jpg"
        )

        expected_relative = (
            expected_file
            .relative_to(BASE_DIR)
            .as_posix()
        )

        # Reuse existing slide.
        if expected_file.exists():

            print(
                f"    Slide {index}/"
                f"{len(resources)} already exists."
            )

            downloaded_paths.append(
                expected_relative
            )

            continue

        # Prefer the resource thumbnail.
        resource_url = getattr(
            resource,
            "thumbnail_url",
            None,
        )

        # Some resource objects may expose video URLs.
        # We don't use those here because this branch
        # is specifically preserving carousel resources.
        if not resource_url:

            print(
                f"    Slide {index}: "
                "no image URL exposed."
            )

            continue

        print(
            f"    Downloading slide "
            f"{index}/{len(resources)}..."
        )

        if download_file(
            resource_url,
            expected_file,
        ):

            downloaded_paths.append(
                expected_relative
            )

        else:

            print(
                f"    Slide {index} failed."
            )

    return downloaded_paths


# ============================================================
# MARKDOWN GENERATION
# ============================================================

def build_markdown(
    post,
    note_name: str,
    thumbnail_path: str,
    video_path: str,
    carousel_paths: list[str],
    synced_at: str,
) -> str:

    caption = get_caption(post)
    author = get_author(post)
    url = get_post_url(post)

    reel_date = get_reel_date(post)

    media_kind = get_media_kind(post)

    media_type = getattr(
        post,
        "media_type",
        "",
    )

    escaped_title = yaml_escape(
        note_name
    )

    escaped_author = yaml_escape(
        author
    )

    escaped_url = yaml_escape(
        url
    )

    caption_yaml = yaml_multiline(
        caption
    )

    carousel_yaml = "\n".join(
        (
            f'  - "{yaml_escape(path)}"'
        )
        for path in carousel_paths
    )

    if not carousel_yaml:
        carousel_yaml = "  []"

    if carousel_paths:

        carousel_markdown = "\n".join(
            (
                f"{index}. `{path}`"
            )
            for index, path
            in enumerate(
                carousel_paths,
                start=1,
            )
        )

    else:

        carousel_markdown = (
            "_No carousel slides downloaded._"
        )

    if video_path:

        video_markdown = (
            f"`{video_path}`"
        )

    else:

        video_markdown = (
            "_No video downloaded._"
        )

    if caption:

        caption_markdown = caption

    else:

        caption_markdown = "_No caption._"

    return f"""---
title: "{escaped_title}"
author: "{escaped_author}"
url: "{escaped_url}"
caption: |
{caption_yaml}
media_kind: "{media_kind}"
media_type: "{media_type}"
reel_date: "{reel_date}"
saved_to_reel2career: "{synced_at}"
collection: "{COLLECTION_NAME}"
thumbnail: "{yaml_escape(thumbnail_path)}"
video: "{yaml_escape(video_path)}"
carousel_slides:
{carousel_yaml}
tags:
  - instagram
  - reel2career
---

# {note_name}

## Source

- **Instagram:** {url}
- **Creator:** @{author}
- **Media kind:** {media_kind}
- **Media type:** {media_type}
- **Reel date:** {reel_date}
- **Added to Reel2Career workflow:** {synced_at}

## Caption

{caption_markdown}

## Media

### Video

{video_markdown}

### Carousel Slides

{carousel_markdown}

## AI Analysis

_Not processed yet._

## Career Relevance

_Not processed yet._

## Recommended Actions

_Not processed yet._

## Resources

_Not processed yet._
"""


# ============================================================
# INGESTION COMPLETENESS
# ============================================================

def is_fully_media_ingested(
    media_kind: str,
    ingestion: dict,
) -> bool:

    if media_kind == "video":
        return bool(
            ingestion.get("video")
        )

    if media_kind == "carousel":
        return bool(
            ingestion.get("carousel")
        )

    if media_kind == "image":
        return bool(
            ingestion.get("thumbnail")
        )

    return bool(
        ingestion.get("metadata")
    )


# ============================================================
# MAIN SYNC
# ============================================================

def main() -> None:

    # Ensure directories exist.
    for directory in (
        VAULT_DIR,
        VIDEO_DIR,
        THUMBNAIL_DIR,
        FRAMES_DIR,
        AUDIO_DIR,
        STATE_DIR,
    ):

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    # Session required.
    if not SESSION_FILE.exists():

        raise SystemExit(
            "session.json not found. "
            "Run login.py first."
        )

    print(
        "=== Reel2Career Sync ==="
    )

    print()

    # --------------------------------------------------------
    # Instagram client
    # --------------------------------------------------------

    client = Client()

    client.load_settings(
        str(SESSION_FILE)
    )

    session_id = (
        client.settings
        .get("authorization_data", {})
        .get("sessionid")
    )

    if not session_id:

        raise SystemExit(
            "No session ID found in session.json."
        )

    client.login_by_sessionid(
        session_id
    )

    print(
        "Instagram session loaded."
    )

    # --------------------------------------------------------
    # Locate collection
    # --------------------------------------------------------

    collections = client.collections()

    collection = next(
        (
            item
            for item in collections
            if item.name == COLLECTION_NAME
        ),
        None,
    )

    if collection is None:

        raise SystemExit(
            f"Collection '{COLLECTION_NAME}' "
            "not found."
        )

    print(
        f"Collection: {collection.name}"
    )

    # --------------------------------------------------------
    # Retrieve saved media
    # --------------------------------------------------------

    posts = client.collection_medias(
        collection.id,
        amount=MAX_COLLECTION_ITEMS,
    )

    print(
        "Instagram reports "
        f"{collection.media_count} saves."
    )

    print(
        f"Retrieved {len(posts)} saves."
    )

    # --------------------------------------------------------
    # State
    # --------------------------------------------------------

    state = load_state()

    synced = state.setdefault(
        "items",
        {},
    )

    new_count = 0
    updated_count = 0
    skipped_count = 0
    failed_count = 0

    # --------------------------------------------------------
    # Process each media item
    # --------------------------------------------------------

    for index, post in enumerate(
        posts,
        start=1,
    ):

        media_id = str(
            post.pk
        )

        print()

        print(
            f"[{index}/{len(posts)}] "
            f"Media {media_id}"
        )

        media_kind = get_media_kind(
            post
        )

        existing_item = synced.get(
            media_id
        )

        ingestion = (
            get_existing_ingestion(
                existing_item
            )
        )

        # ----------------------------------------------------
        # Existing saved timestamp
        # ----------------------------------------------------

        if existing_item:

            synced_at = (
                existing_item.get(
                    "saved_to_reel2career"
                )
                or now_utc()
            )

        else:

            synced_at = now_utc()

        # ----------------------------------------------------
        # Existing media status
        # ----------------------------------------------------

        if existing_item:

            print(
                f"    Media kind: {media_kind}"
            )

            if is_fully_media_ingested(
                media_kind,
                ingestion,
            ):

                # Metadata and media are already complete.
                # We don't touch the item.
                print(
                    "    Already fully ingested."
                )

                skipped_count += 1

                continue

            print(
                "    Existing item requires "
                "additional media ingestion."
            )

        else:

            print(
                f"    New media: {media_kind}"
            )

        # ----------------------------------------------------
        # Existing paths
        # ----------------------------------------------------

        existing_thumbnail = ""

        existing_video = ""

        existing_carousel = []

        if existing_item:

            existing_thumbnail = (
                existing_item.get(
                    "thumbnail",
                    "",
                )
            )

            existing_video = (
                existing_item.get(
                    "video",
                    "",
                )
            )

            existing_carousel = (
                existing_item.get(
                    "carousel_slides",
                    [],
                )
            )

        # ----------------------------------------------------
        # Acquire thumbnail
        # ----------------------------------------------------

        thumbnail_path = (
            acquire_thumbnail(
                post,
                media_id,
                existing_thumbnail,
            )
        )

        # ----------------------------------------------------
        # Acquire video
        # ----------------------------------------------------

        video_path = ""

        if media_kind == "video":

            video_path = acquire_video(
                post,
                media_id,
                existing_video,
            )

        else:

            video_path = existing_video

        # ----------------------------------------------------
        # Acquire carousel
        # ----------------------------------------------------

        carousel_paths = []

        if media_kind == "carousel":

            carousel_paths = (
                acquire_carousel(
                    post,
                    media_id,
                    existing_carousel,
                )
            )

        else:

            carousel_paths = (
                existing_carousel
            )

        # ----------------------------------------------------
        # Update ingestion flags
        # ----------------------------------------------------

        ingestion["metadata"] = True

        ingestion["thumbnail"] = bool(
            thumbnail_path
        )

        if media_kind == "video":

            ingestion["video"] = bool(
                video_path
            )

        elif media_kind != "video":

            ingestion["video"] = bool(
                existing_video
            )

        if media_kind == "carousel":

            ingestion["carousel"] = (
                len(carousel_paths) > 0
            )

        elif media_kind != "carousel":

            ingestion["carousel"] = bool(
                existing_carousel
            )

        # ----------------------------------------------------
        # Build note
        # ----------------------------------------------------

        caption = get_caption(
            post
        )

        if caption:

            title_source = (
                caption.splitlines()[0]
            )

        else:

            title_source = (
                f"Instagram Media {media_id}"
            )

        title = safe_filename(
            title_source,
            fallback=(
                f"media-{media_id}"
            ),
        )

        note_name = (
            f"{title} - {media_id}"
        )

        markdown = build_markdown(
            post=post,
            note_name=note_name,
            thumbnail_path=thumbnail_path,
            video_path=video_path,
            carousel_paths=carousel_paths,
            synced_at=synced_at,
        )

        note_file = (
            VAULT_DIR
            / f"{note_name}.md"
        )

        note_file.write_text(
            markdown,
            encoding="utf-8",
        )

        # ----------------------------------------------------
        # Preserve future processing state
        # ----------------------------------------------------

        previous_processing = {}

        if existing_item:

            previous_processing = (
                existing_item.get(
                    "processing",
                    {},
                )
            )

        # ----------------------------------------------------
        # Save state
        # ----------------------------------------------------

        synced[media_id] = {
            "instagram_id": media_id,
            "shortcode": getattr(
                post,
                "code",
                "",
            ),
            "author": get_author(
                post
            ),
            "url": get_post_url(
                post
            ),
            "media_kind": media_kind,
            "media_type": getattr(
                post,
                "media_type",
                "",
            ),
            "note": str(
                note_file.relative_to(
                    BASE_DIR
                )
            ),
            "thumbnail": thumbnail_path,
            "video": video_path,
            "carousel_slides": (
                carousel_paths
            ),
            "reel_date": get_reel_date(
                post
            ),
            "saved_to_reel2career": (
                synced_at
            ),
            "synced_at": (
                now_utc()
            ),
            "ingestion": ingestion,
            "processing": (
                previous_processing
            ),
        }

        save_state(
            state
        )

        # ----------------------------------------------------
        # Counters
        # ----------------------------------------------------

        if existing_item:

            updated_count += 1

            print(
                "    Updated ingestion state."
            )

        else:

            new_count += 1

            print(
                "    New item synced."
            )

        print(
            f"    Media kind: {media_kind}"
        )

        if thumbnail_path:

            print(
                "    Thumbnail: OK"
            )

        if video_path:

            print(
                "    Video: OK"
            )

        if carousel_paths:

            print(
                "    Carousel slides: "
                f"{len(carousel_paths)}"
            )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    print()

    print(
        "=== Sync Complete ==="
    )

    print(
        f"New:       {new_count}"
    )

    print(
        f"Updated:   {updated_count}"
    )

    print(
        f"Skipped:   {skipped_count}"
    )

    print(
        f"Failed:    {failed_count}"
    )


if __name__ == "__main__":
    main()