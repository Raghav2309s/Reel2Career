from backend.app.database import SessionLocal, ReelResource, Resource, Evidence
from backend.app.ai_extracted import extract_local_evidence_block
from backend.app.github_client import search_repositories
from backend.app.resource_verifier import (
    GitHubRepositoryCandidate,
    verify_github_resource,
)

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

    print(f"RESOURCES: {len(rows)}")

    for rr, resource, evidence in rows:
        if resource.url:
            continue

        local_evidence = ""
        if evidence and rr.source_locator:
            local_evidence = extract_local_evidence_block(
                evidence.content,
                rr.source_locator,
            )

        print("\n" + "=" * 100)
        print(f"RESOURCE {resource.id}: {resource.title}")
        print(f"LOCATOR: {rr.source_locator}")
        print(f"EVIDENCE: {local_evidence}")

        try:
            results = search_repositories(resource.title)

            candidates = [
                GitHubRepositoryCandidate(
                    owner=item.owner,
                    repository=item.repository,
                    url=item.url,
                    description=item.description,
                    topics=item.topics,
                    archived=item.archived,
                )
                for item in results
            ]

            verification = verify_github_resource(
                resource.title,
                candidates,
                evidence_text=local_evidence,
            )

            print(f"RESULT: {verification.status}")
            print(f"SELECTED: {verification.candidate}")
            print(f"REASON: {verification.reason}")

        except Exception as exc:
            print(f"ERROR: {type(exc).__name__}: {exc}")

finally:
    db.close()
