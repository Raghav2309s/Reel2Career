from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from backend.app.github_discovery import (
    GitHubHint,
    extract_github_owner_hints,
)
from backend.app.resource_verifier import GitHubRepositoryCandidate


@dataclass(frozen=True)
class RankedGitHubCandidate:
    candidate: GitHubRepositoryCandidate
    score: float
    signals: tuple[str, ...]


def _normalize(value: str) -> str:
    value = value.casefold().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _similarity(a: str, b: str) -> float:
    a = _normalize(a)
    b = _normalize(b)

    if not a or not b:
        return 0.0

    return SequenceMatcher(None, a, b).ratio()


def _repository_similarity(
    title: str,
    candidate_repository: str,
) -> float:
    return _similarity(title, candidate_repository)


def _owner_similarity(
    hint_owner: str,
    candidate_owner: str,
) -> float:
    return _similarity(hint_owner, candidate_owner)


def _evidence_identity_score(
    candidate: GitHubRepositoryCandidate,
    evidence_text: str,
) -> tuple[float, list[str]]:
    """
    Score explicit identity signals inside the local evidence.

    This is a RANKING signal only.
    It does NOT verify the repository.
    """

    if not evidence_text:
        return 0.0, []

    normalized_evidence = _normalize(evidence_text)

    score = 0.0
    signals: list[str] = []

    full_name = _normalize(
        f"{candidate.owner}/{candidate.repository}"
    )

    if full_name in normalized_evidence:
        score += 100.0
        signals.append("explicit-owner-repository")

    owner = _normalize(candidate.owner)
    repository = _normalize(candidate.repository)

    if owner and repository:
        owner_present = owner in normalized_evidence
        repo_present = repository in normalized_evidence

        if owner_present and repo_present:
            score += 60.0
            signals.append("owner-and-repository-evidence")

    return score, signals


def rank_github_candidates(
    title: str,
    hints: list[GitHubHint],
    candidates: list[GitHubRepositoryCandidate],
    *,
    evidence_text: str = "",
) -> list[RankedGitHubCandidate]:
    """
    Rank GitHub candidates using noisy resource evidence.

    Ranking only:
    - resource title
    - OCR GitHub hints
    - explicit identity appearing in evidence

    This function NEVER verifies identity.
    """

    if not candidates:
        return []

    owner_hints = extract_github_owner_hints(evidence_text)

    ranked: list[RankedGitHubCandidate] = []

    for candidate in candidates:
        score = 0.0
        signals: list[str] = []

        # ---------------------------------------------------------
        # 1. Resource title -> repository-name similarity
        # ---------------------------------------------------------

        repo_similarity = _repository_similarity(
            title,
            candidate.repository,
        )

        score += repo_similarity * 50.0

        if repo_similarity >= 0.95:
            score += 20.0
            signals.append("strong-repository-match")
        elif repo_similarity >= 0.80:
            signals.append("moderate-repository-match")

        # ---------------------------------------------------------
        # 2. OCR GitHub owner hints from damaged URLs
        # ---------------------------------------------------------

        for owner_hint in owner_hints:
            owner_similarity = _owner_similarity(
                owner_hint,
                candidate.owner,
            )

            if owner_similarity >= 0.95:
                score += owner_similarity * 100.0
                signals.append("strong-owner-evidence")
            elif owner_similarity >= 0.75:
                score += owner_similarity * 60.0
                signals.append("moderate-owner-evidence")

        # ---------------------------------------------------------
        # 3. OCR GitHub hints -> owner/repository similarity
        # ---------------------------------------------------------

        for hint in hints:
            owner_similarity = _owner_similarity(
                hint.owner,
                candidate.owner,
            )

            hint_repo_similarity = _similarity(
                hint.repository_fragment,
                candidate.repository,
            )

            hint_score = (
                owner_similarity * 80.0
                + hint_repo_similarity * 20.0
            )

            if (
                _normalize(hint.repository_fragment)
                == _normalize(candidate.repository)
            ):
                hint_score += 20.0

            if owner_similarity >= 0.90:
                signals.append("strong-owner-match")
            elif owner_similarity >= 0.75:
                signals.append("moderate-owner-match")

            if hint_repo_similarity >= 0.95:
                signals.append("strong-hint-repository-match")
            elif hint_repo_similarity >= 0.80:
                signals.append("moderate-hint-repository-match")

            score = max(score, hint_score)

        # ---------------------------------------------------------
        # 4. Explicit identity present in evidence
        # ---------------------------------------------------------

        evidence_score, evidence_signals = _evidence_identity_score(
            candidate,
            evidence_text,
        )

        if evidence_score:
            score += evidence_score
            signals.extend(evidence_signals)

        ranked.append(
            RankedGitHubCandidate(
                candidate=candidate,
                score=round(score, 2),
                signals=tuple(sorted(set(signals))),
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score,
            item.candidate.owner.casefold(),
            item.candidate.repository.casefold(),
        )
    )

    return ranked