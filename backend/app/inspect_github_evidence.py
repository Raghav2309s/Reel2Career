from backend.app.database import (
    SessionLocal,
    ReelResource,
    Resource,
    Evidence,
)
from backend.app.ai_extracted import extract_local_evidence_block


RESOURCE_IDS = [37, 40, 41, 42, 43, 84]

db = SessionLocal()

try:
    rows = (
        db.query(ReelResource, Resource, Evidence)
        .join(
            Resource,
            ReelResource.resource_id == Resource.id,
        )
        .outerjoin(
            Evidence,
            Evidence.id == ReelResource.source_evidence_id,
        )
        .filter(
            ReelResource.reel_id == 7,
            Resource.id.in_(RESOURCE_IDS),
        )
        .order_by(Resource.id)
        .all()
    )

    print(f"FOUND: {len(rows)} resources")

    for rr, resource, evidence in rows:
        print("\n" + "=" * 100)
        print(f"RESOURCE {resource.id}: {resource.title}")
        print(f"LOCATOR: {rr.source_locator}")
        print(f"EVIDENCE ID: {rr.source_evidence_id}")

        if not evidence:
            print("NO EVIDENCE RECORD")
            continue

        if not rr.source_locator:
            print("NO SOURCE LOCATOR")
            continue

        block = extract_local_evidence_block(
            evidence.content,
            rr.source_locator,
        )

        if not block:
            print("LOCAL EVIDENCE BLOCK: EMPTY")
        else:
            print("LOCAL EVIDENCE BLOCK:")
            print(block)

finally:
    db.close()