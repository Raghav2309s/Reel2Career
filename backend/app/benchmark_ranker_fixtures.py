from backend.app.database import (
    SessionLocal,
    ReelResource,
    Resource,
    Evidence,
)
from backend.app.ai_extracted import extract_local_evidence_block
from backend.app.github_discovery import extract_github_hints
from backend.app.github_candidate_ranker import rank_github_candidates
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

        ranked = rank_github_candidates(
            resource.title,
            hints,
            candidates,
            evidence_text=local_evidence,
        )

        print("\n" + "=" * 100)
        print(f"RESOURCE {resource.id}: {resource.title}")
        print(f"LOCATOR: {rr.source_locator}")
        print(
            f"HINTS: "
            f"{[hint.full_hint for hint in hints]}"
        )
        print(f"CANDIDATES: {len(candidates)}")

        if not ranked:
            print("RANKING: no candidates")
            continue

        print("RANKED CANDIDATES:")

        for index, item in enumerate(ranked[:10], start=1):
            print(
                f"  {index}. "
                f"{item.score:7.2f} "
                f"{item.candidate.owner}/"
                f"{item.candidate.repository} "
                f"| signals={item.signals}"
            )

finally:
    db.close()