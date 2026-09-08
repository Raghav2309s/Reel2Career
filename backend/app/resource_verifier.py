from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re


@dataclass(frozen=True)
class GitHubRepositoryCandidate:
    owner: str
    repository: str
    url: str
    description: str = ""
    topics: tuple[str, ...] = ()
    archived: bool = False


@dataclass(frozen=True)
class VerificationResult:
    status: str
    candidate: GitHubRepositoryCandidate | None
    reason: str


def _normalize(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _url_similarity_score(
    candidate: GitHubRepositoryCandidate,
    evidence_text: str,
) -> int:
    candidate_url = _normalize(candidate.url)
    evidence_urls = re.findall(
        r"https://[^\s]+",
        _normalize(evidence_text),
    )

    if not candidate_url or not evidence_urls:
        return 0

    similarity = max(
        SequenceMatcher(
            None,
            candidate_url,
            evidence_url.rstrip(".,;:)").strip(),
        ).ratio()
        for evidence_url in evidence_urls
    )

    if similarity < 0.85:
        return 0

    return int(similarity * 100)


def _topic_match_score(
    topic: str,
    evidence_text: str,
) -> int:
    normalized_topic = _normalize(topic)
    if not normalized_topic:
        return 0

    evidence_tokens = re.findall(
        r"[a-z0-9]+",
        _normalize(evidence_text),
    )

    if normalized_topic in evidence_tokens:
        return 5

    if any(
        token.startswith(normalized_topic)
        or normalized_topic.startswith(token)
        for token in evidence_tokens
    ):
        return 5

    if any(
        SequenceMatcher(
            None,
            normalized_topic,
            token,
        ).ratio() >= 0.8
        for token in evidence_tokens
    ):
        return 5

    return 0


def _evidence_score(
    candidate: GitHubRepositoryCandidate,
    evidence_text: str,
) -> int:
    """
    Score evidence only for explicit identity disambiguation.

    Weak signals such as owner-only mentions, descriptions,
    topics, or fuzzy similarity must not establish identity.
    """

    text = _normalize(evidence_text)
    full_name = _normalize(
        f"{candidate.owner}/{candidate.repository}"
    )

    if full_name in text:
        return 100

    return 0


def _has_explicit_identity_evidence(
    candidate: GitHubRepositoryCandidate,
    evidence_text: str,
) -> bool:
    if not evidence_text.strip():
        return False

    def compact(value: str) -> str:
        return re.sub(
            r"[^a-z0-9]+",
            "",
            value.casefold(),
        )

    candidate_owner = compact(candidate.owner)
    candidate_repository = compact(candidate.repository)

    evidence_compact = compact(evidence_text)

    return (
        candidate_owner in evidence_compact
        and candidate_repository in evidence_compact
    )


def verify_github_resource(
    title: str,
    candidates: list[GitHubRepositoryCandidate] | None = None,
    *,
    evidence_text: str = "",
) -> VerificationResult:
    """
    Verify a resource against GitHub candidates.

    Verification rules:

    1. Exactly one exact repository-name match -> verified.
    2. Multiple exact repository-name matches -> evidence may
       disambiguate.
    3. If no exact repository-name match exists, an explicit
       owner/repository identity in the evidence may verify a
       unique candidate.
    4. Partial OCR hints, owner-only matches, descriptions,
       topics, and fuzzy similarity never establish identity alone.

    This function never mutates the database and never performs
    network I/O.
    """

    if not title or not title.strip():
        return VerificationResult(
            status="invalid",
            candidate=None,
            reason="Empty resource title.",
        )

    candidates = candidates or []
    normalized_title = _normalize(title)

    exact_matches = [
        candidate
        for candidate in candidates
        if _normalize(candidate.repository) == normalized_title
    ]

    # Rule 1: unique exact repository-name match.
    if len(exact_matches) == 1:
        return VerificationResult(
            status="verified",
            candidate=exact_matches[0],
            reason="Exact repository-name match.",
        )

    # Rule 2: multiple exact repository-name matches.
    if len(exact_matches) > 1:
        if evidence_text.strip():
            scored = [
                (candidate, _evidence_score(candidate, evidence_text))
                for candidate in exact_matches
            ]

            highest_score = max(score for _, score in scored)

            winners = [
                candidate
                for candidate, score in scored
                if score == highest_score
            ]

            if highest_score > 0 and len(winners) == 1:
                return VerificationResult(
                    status="verified",
                    candidate=winners[0],
                    reason=(
                        "Evidence disambiguated multiple exact "
                        "repository-name matches."
                    ),
                )

        return VerificationResult(
            status="ambiguous",
            candidate=None,
            reason="Multiple repositories have the same repository name.",
        )

    # Rule 3: no exact title match. Evidence may identify one
    # candidate explicitly.
    if evidence_text.strip():
        explicit_matches = [
            candidate
            for candidate in candidates
            if _has_explicit_identity_evidence(
                candidate,
                evidence_text,
            )
        ]

        if len(explicit_matches) == 1:
            return VerificationResult(
                status="verified",
                candidate=explicit_matches[0],
                reason=(
                    "Explicit owner/repository identity found in evidence."
                ),
            )

        if len(explicit_matches) > 1:
            return VerificationResult(
                status="ambiguous",
                candidate=None,
                reason=(
                    "Evidence explicitly references multiple "
                    "candidate repositories."
                ),
            )

    return VerificationResult(
        status="not_found",
        candidate=None,
        reason="No exact repository-name match.",
    )


def verify_github_candidate(
    candidate: GitHubRepositoryCandidate,
    *,
    evidence_text: str = "",
) -> VerificationResult:
    """
    Verify one already-selected GitHub candidate.

    This does not use ranking scores.
    It checks whether the evidence contains the
    candidate's owner + repository identity.
    """

    if not candidate:
        return VerificationResult(
            status="invalid",
            candidate=None,
            reason="No candidate supplied.",
        )

    if _has_explicit_identity_evidence(
        candidate,
        evidence_text,
    ):
        return VerificationResult(
            status="verified",
            candidate=candidate,
            reason=(
                "Explicit owner/repository identity "
                "found in evidence."
            ),
        )

    return VerificationResult(
        status="ambiguous",
        candidate=None,
        reason=(
            "Candidate was ranked highly, but the evidence "
            "does not explicitly establish its identity."
        ),
    )
