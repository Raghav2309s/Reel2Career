from backend.app.database import SessionLocal, ReelResource, Resource, Evidence
from backend.app.ai_extracted import extract_local_evidence_block
from backend.app.github_discovery import extract_github_hints
from backend.app.github_client import search_repositories
from backend.app.github_candidate_ranker import rank_github_candidates

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

        hints = extract_github_hints(local_evidence)

        print("\n" + "=" * 100)
        print(f"RESOURCE {resource.id}: {resource.title}")
        print(f"LOCATOR: {rr.source_locator}")
        print(f"HINTS: {[hint.full_hint for hint in hints]}")

        candidates = {}

        # Search by resource title.
        try:
            title_results = search_repositories(resource.title)

            for item in title_results:
                key = (
                    item.owner.casefold(),
                    item.repository.casefold(),
                )
                candidates[key] = item

        except Exception as exc:
            print(
                f"TITLE SEARCH ERROR: "
                f"{type(exc).__name__}: {exc}"
            )

        # Search by OCR-derived repository hints.
        for hint in hints:
            query = hint.repository_fragment

            try:
                hint_results = search_repositories(query)

                for item in hint_results:
                    key = (
                        item.owner.casefold(),
                        item.repository.casefold(),
                    )
                    candidates[key] = item

            except Exception as exc:
                print(
                    f"HINT SEARCH ERROR [{query}]: "
                    f"{type(exc).__name__}: {exc}"
                )

        candidate_list = list(candidates.values())

        print(f"CANDIDATES: {len(candidate_list)}")

        if not candidate_list:
            print("RANKING: no candidates")
            continue

        ranked = rank_github_candidates(
            resource.title,
            hints,
            candidate_list,
            evidence_text=local_evidence,
        )

        print("RANKED CANDIDATES:")

        for index, item in enumerate(ranked[:10], start=1):
            print(
                f"  {index}. "
                f"{item.score:7.2f} "
                f"{item.candidate.owner}/"
                f"{item.candidate.repository}"
                f" | archived={item.candidate.archived}"
                f" | signals={item.signals}"
            )

finally:
    db.close()
