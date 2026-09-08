from backend.app.database import SessionLocal, ReelResource, Resource, Evidence
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
        .filter(
            ReelResource.reel_id == 7,
            Resource.url.is_(None),
        )
        .order_by(ReelResource.id)
        .all()
    )

    print(f"UNRESOLVED: {len(rows)}")
    print()

    for rr, resource, evidence in rows:
        try:
            search_results = search_repositories(resource.title)

            candidates = [
                GitHubRepositoryCandidate(
                    owner=item.owner,
                    repository=item.repository,
                    url=item.url,
                    description=item.description,
                    topics=item.topics,
                    archived=item.archived,
                )
                for item in search_results
            ]

            result = verify_github_resource(
                resource.title,
                candidates,
                evidence_text=evidence.content if evidence else "",
            )

            candidate_text = (
                f"{result.candidate.owner}/{result.candidate.repository}"
                if result.candidate
                else "-"
            )

            print(
                f"{resource.id:>3} | "
                f"{resource.title:<55} | "
                f"{result.status:<10} | "
                f"{candidate_text}"
            )

        except Exception as exc:
            print(
                f"{resource.id:>3} | "
                f"{resource.title:<55} | "
                f"ERROR      | {exc}"
            )

finally:
    db.close()
