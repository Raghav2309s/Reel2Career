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

    print(f"RESOURCES: {len(rows)}")

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

        print("\n" + "=" * 100)
        print(f"RESOURCE {resource.id}: {resource.title}")
        print(f"STATUS: {result.status}")
        print(
            f"SELECTED: "
            f"{result.selected.owner}/{result.selected.repository}"
            if result.selected
            else "SELECTED: None"
        )
        print(f"REASON: {result.reason}")

        if result.ranking:
            top = result.ranking[0]
            print(
                f"TOP CANDIDATE: "
                f"{top.candidate.owner}/"
                f"{top.candidate.repository}"
            )
            print(f"TOP SCORE: {top.score}")
            print(f"TOP SIGNALS: {top.signals}")

finally:
    db.close()