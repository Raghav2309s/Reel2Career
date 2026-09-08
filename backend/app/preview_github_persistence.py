from backend.app.database import (
    SessionLocal,
    ReelResource,
    Resource,
    Evidence,
)
from backend.app.ai_extracted import extract_local_evidence_block
from backend.app.github_discovery import extract_github_hints
from backend.app.github_resolver import resolve_github_resource
from backend.app.github_benchmark_fixtures import FIXTURES


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
            Resource.id.in_(FIXTURES.keys()),
        )
        .order_by(Resource.id)
        .all()
    )

    print("GITHUB PERSISTENCE PREVIEW")
    print("=" * 100)

    for rr, resource, evidence in rows:
        local_evidence = ""

        if evidence and rr.source_locator:
            local_evidence = extract_local_evidence_block(
                evidence.content,
                rr.source_locator,
            )

        hints = extract_github_hints(local_evidence)
        candidates = FIXTURES.get(resource.id, [])

        result = resolve_github_resource(
            resource.title,
            hints,
            candidates,
            evidence_text=local_evidence,
        )

        print(f"\nRESOURCE {resource.id}: {resource.title}")
        print(f"CURRENT URL: {resource.url}")
        print(f"CURRENT IDENTITY: {resource.identity_key}")
        print(f"CURRENT STATUS: {resource.verification_status}")

        print(f"RESOLUTION: {result.status}")

        if result.selected:
            selected_url = result.selected.url
            selected_identity = (
                f"github:"
                f"{result.selected.owner.casefold()}/"
                f"{result.selected.repository.casefold()}"
            )

            print(f"WOULD SET URL: {selected_url}")
            print(f"WOULD SET IDENTITY: {selected_identity}")
            print("WOULD SET STATUS: verified")
            print(
                "WOULD UPDATE: yes"
            )
        else:
            print("WOULD SET URL: no")
            print("WOULD SET IDENTITY: no")
            print(
                "WOULD SET STATUS: no change"
            )
            print("WOULD UPDATE: no")

finally:
    db.close()

print("\nPREVIEW COMPLETE — DATABASE WAS NOT MODIFIED")