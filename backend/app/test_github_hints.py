import re
from backend.app.database import SessionLocal, ReelResource, Resource, Evidence
from backend.app.ai_extracted import extract_local_evidence_block


GITHUB_HINT = re.compile(
    r'(?i)(?:https?://)?github\.com/([A-Za-z0-9_.-]+)[/\s]+([A-Za-z0-9_.*~-]+)'
)


def extract_github_hints(text: str):
    if not text:
        return []

    matches = []
    seen = set()

    for owner, repo in GITHUB_HINT.findall(text):
        repo = repo.rstrip(".,;:)]}'\"`")
        repo = repo.replace("*", "")
        repo = repo.rstrip("_")
        key = (owner.casefold(), repo.casefold())

        if key not in seen:
            seen.add(key)
            matches.append(f"{owner}/{repo}")

    return matches


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
        if resource.url:
            continue

        local_evidence = ""
        if evidence and rr.source_locator:
            local_evidence = extract_local_evidence_block(
                evidence.content,
                rr.source_locator,
            )

        print("=" * 100)
        print(f"RESOURCE {resource.id}: {resource.title}")
        print(f"LOCATOR: {rr.source_locator}")
        print("HINTS:", extract_github_hints(local_evidence))

finally:
    db.close()
