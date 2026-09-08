from pathlib import Path
import json


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state" / "synced.json"

CAROUSEL_ID = "3957068783193726412"


def main():
    if not STATE_FILE.exists():
        raise SystemExit(
            f"State file not found: {STATE_FILE}"
        )

    state = json.loads(
        STATE_FILE.read_text(encoding="utf-8")
    )

    item = state.get("items", {}).get(CAROUSEL_ID)

    if item is None:
        raise SystemExit(
            f"Media {CAROUSEL_ID} was not found in synced.json."
        )

    item["media_kind"] = "carousel"

    item["ingestion"] = {
        "metadata": True,
        "thumbnail": bool(item.get("thumbnail")),
        "video": bool(item.get("video")),
        "carousel": False,
        "transcription": False,
        "ocr": False,
        "ai_analysis": False,
        "resource_verification": False,
    }

    state["version"] = 2

    STATE_FILE.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("Carousel state prepared.")
    print(f"Media: {CAROUSEL_ID}")
    print("media_kind: carousel")
    print("carousel: False")
    print("Ready for targeted carousel extraction.")


if __name__ == "__main__":
    main()