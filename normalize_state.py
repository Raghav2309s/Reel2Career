from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state" / "synced.json"


def main():
    state = json.loads(
        STATE_FILE.read_text(encoding="utf-8")
    )

    for media_id, item in state["items"].items():

        media_kind = item.get("media_kind")

        if not media_kind:
            if item.get("video"):
                media_kind = "video"
            elif item.get("carousel_slides"):
                media_kind = "carousel"
            else:
                media_kind = "image"

            item["media_kind"] = media_kind

        if "media_type" not in item:
            if media_kind == "video":
                item["media_type"] = 2
            elif media_kind == "carousel":
                item["media_type"] = 8
            else:
                item["media_type"] = 1

        ingestion = item.setdefault(
            "ingestion",
            {}
        )

        ingestion.setdefault(
            "metadata",
            True
        )

        ingestion.setdefault(
            "thumbnail",
            bool(item.get("thumbnail"))
        )

        ingestion.setdefault(
            "video",
            bool(item.get("video"))
        )

        ingestion.setdefault(
            "carousel",
            bool(item.get("carousel_slides"))
        )

        ingestion.setdefault(
            "transcription",
            False
        )

        ingestion.setdefault(
            "ocr",
            False
        )

        ingestion.setdefault(
            "ai_analysis",
            False
        )

        ingestion.setdefault(
            "resource_verification",
            False
        )

        item.setdefault(
            "carousel_slides",
            []
        )

        item.setdefault(
            "processing",
            {}
        )

    state["version"] = 2

    STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print("State normalization complete.")
    print(
        f"Normalized {len(state['items'])} media items."
    )


if __name__ == "__main__":
    main()