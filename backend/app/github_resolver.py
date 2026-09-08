from __future__ import annotations

from dataclasses import dataclass

from backend.app.github_candidate_ranker import (
    RankedGitHubCandidate,
    rank_github_candidates,
)
from backend.app.github_discovery import GitHubHint
from backend.app.resource_verifier import (
    GitHubRepositoryCandidate,
    VerificationResult,
    verify_github_candidate,
)


@dataclass(frozen=True)
class GitHubResolution:
    status: str
    selected: GitHubRepositoryCandidate | None
    ranking: tuple[RankedGitHubCandidate, ...]
    verification: VerificationResult
    reason: str


def resolve_github_resource(
    title: str,
    hints: list[GitHubHint],
    candidates: list[GitHubRepositoryCandidate],
    *,
    evidence_text: str = "",
) -> GitHubResolution:
    """
    Rank candidates, then strictly verify only the top candidate.

    Ranking is probabilistic/noisy.
    Verification remains evidence-based.
    """

    ranked = rank_github_candidates(
        title,
        hints,
        candidates,
        evidence_text=evidence_text,
    )

    if not ranked:
        verification = VerificationResult(
            status="not_found",
            candidate=None,
            reason="No GitHub candidates available.",
        )

        return GitHubResolution(
            status="not_found",
            selected=None,
            ranking=(),
            verification=verification,
            reason="No GitHub candidates available.",
        )

    top_candidate = ranked[0].candidate

    verification = verify_github_candidate(
        top_candidate,
        evidence_text=evidence_text,
    )

    if verification.status == "verified":
        return GitHubResolution(
            status="verified",
            selected=top_candidate,
            ranking=tuple(ranked),
            verification=verification,
            reason=verification.reason,
        )

    return GitHubResolution(
        status="ambiguous",
        selected=None,
        ranking=tuple(ranked),
        verification=verification,
        reason=verification.reason,
    )