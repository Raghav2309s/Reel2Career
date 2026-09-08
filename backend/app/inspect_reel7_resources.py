from backend.app.database import SessionLocal, ReelResource, Resource, Evidence

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
        print("EVIDENCE:")

        if evidence:
            print(evidence.content[:1000])
        else:
            print("(no evidence)")

finally:
    db.close()
