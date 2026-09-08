from pathlib import Path

from backend.app.database import SessionLocal, Resource


UPDATES = {
    41: {
        "url": "https://github.com/vicky60629/Network-Intrusion-Detection-System",
        "identity_key": "github:vicky60629/network-intrusion-detection-system",
        "verification_status": "verified",
    },
    42: {
        "url": "https://github.com/MaitreeVaria/Indian-Sign-Language-Detection",
        "identity_key": "github:maitreevaria/indian-sign-language-detection",
        "verification_status": "verified",
    },
}


BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_FILE = BASE_DIR / "data" / "reel2career.db"
BACKUP_FILE = (
    BASE_DIR
    / "data"
    / "reel2career.backup-before-github-persistence.db"
)


if not DATABASE_FILE.exists():
    raise FileNotFoundError(
        f"Database not found: {DATABASE_FILE}"
    )

if not BACKUP_FILE.exists():
    raise FileNotFoundError(
        f"Backup not found: {BACKUP_FILE}"
    )


db = SessionLocal()

try:
    print("GITHUB PERSISTENCE")
    print("=" * 90)

    for resource_id, update in UPDATES.items():
        resource = (
            db.query(Resource)
            .filter(Resource.id == resource_id)
            .first()
        )

        if resource is None:
            raise RuntimeError(
                f"Resource {resource_id} does not exist."
            )

        print(f"\nRESOURCE {resource.id}: {resource.title}")
        print(f"BEFORE URL: {resource.url}")
        print(
            f"BEFORE IDENTITY: "
            f"{resource.identity_key}"
        )
        print(
            f"BEFORE STATUS: "
            f"{resource.verification_status}"
        )

        # Safety check: these resources should currently be unresolved.
        if resource.url is not None:
            raise RuntimeError(
                f"Resource {resource_id} already has a URL."
            )

        if resource.identity_key is not None:
            raise RuntimeError(
                f"Resource {resource_id} already has an identity key."
            )

        # Apply only the verified values.
        resource.url = update["url"]
        resource.identity_key = update["identity_key"]
        resource.verification_status = update[
            "verification_status"
        ]

        print(f"AFTER URL: {resource.url}")
        print(
            f"AFTER IDENTITY: "
            f"{resource.identity_key}"
        )
        print(
            f"AFTER STATUS: "
            f"{resource.verification_status}"
        )

    db.commit()

    print("\nCOMMIT SUCCESSFUL")

finally:
    db.close()

print("\nONLY RESOURCES 41 AND 42 WERE UPDATED.")