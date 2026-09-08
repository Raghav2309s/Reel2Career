from __future__ import annotations

from backend.app.github_client import search_repositories
from backend.app.github_discovery import (
    GitHubHint,
    extract_github_owner_hints,
)
from backend.app.resource_verifier import GitHubRepositoryCandidate


def discover_github_candidates(
    title: str,
    hints: list[GitHubHint],
    *,
    evidence_text: str = "",
) -> list[GitHubRepositoryCandidate]:
    """
    Discover GitHub candidates from the resource title and OCR hints.

    Network/cache layer only.
    No database mutation.
    """

    discovered: dict[tuple[str, str], GitHubRepositoryCandidate] = {}

    queries: list[str] = []

    if title and title.strip():
        queries.append(title.strip())

    for hint in hints:
        repository = hint.repository_fragment.strip()

        if repository and repository not in queries:
            queries.append(repository)

    # Owner-only OCR evidence can still help select better candidates
    # after repository-name discovery, but it is not enough to construct
    # a repository identity by itself.
    owner_hints = extract_github_owner_hints(evidence_text)

    for query in queries:
        try:
            results = search_repositories(query)

        except Exception:
            # Discovery failure should not crash the AI extraction pipeline.
            continue

        for item in results:
            key = (
                item.owner.casefold(),
                item.repository.casefold(),
            )

            discovered[key] = GitHubRepositoryCandidate(
                owner=item.owner,
                repository=item.repository,
                url=item.url,
                description=item.description,
                topics=item.topics,
                archived=item.archived,
            )

    # Keep the variable intentionally visible for diagnostics.
    # Owner hints are consumed by the ranker through evidence_text.
    _ = owner_hints

    return list(discovered.values())