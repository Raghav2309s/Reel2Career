from backend.app.database import SessionLocal, ReelResource, Resource, Evidence
from backend.app.ai_extracted import extract_local_evidence_block

db = SessionLocal()

try:
    rows = (
        db.query(ReelResource, Resource, Evidence)
        .join(Resource, ReelResource.resource_id == Resource.id)
        .outerjoin(Evidence, Evidence.id == ReelResource.source_evidence_id)
        .filter(ReelResource.reel_id == 7)
        .order_by(ReelResource.id)
        .all()
    )

    for rr, resource, evidence in rows:
        print("=" * 100)
        print(f"RESOURCE {resource.id}: {resource.title}")
        print(f"LOCATOR: {rr.source_locator}")

        if evidence and rr.source_locator:
            block = extract_local_evidence_block(
                evidence.content,
                rr.source_locator,
            )
            print("LOCAL BLOCK:")
            print(block)
        else:
            print("NO LOCAL BLOCK")

finally:
    db.close()
