from backend.app.github_discovery import extract_github_hints
from backend.app.resource_verifier import (
    GitHubRepositoryCandidate,
    verify_github_resource,
)


def candidate(owner, repository, description="", topics=(), archived=False):
    return GitHubRepositoryCandidate(
        owner=owner,
        repository=repository,
        url=f"https://github.com/{owner}/{repository}",
        description=description,
        topics=topics,
        archived=archived,
    )


def run_case(name, title, evidence, candidates, expected_status, expected_repo=None):
    hints = extract_github_hints(evidence)

    result = verify_github_resource(
        title,
        candidates,
        evidence_text=evidence,
    )

    print("=" * 90)
    print(name)
    print("TITLE:       ", title)
    print("HINTS:       ", [hint.full_hint for hint in hints])
    print("RESULT:      ", result.status)
    print("SELECTED:    ", result.candidate)
    print("REASON:      ", result.reason)

    assert result.status == expected_status

    if expected_repo is not None:
        assert result.candidate is not None
        assert (
            f"{result.candidate.owner}/{result.candidate.repository}"
            == expected_repo
        )


# 1. Prefect: owner + repository evidence should disambiguate.
run_case(
    "Prefect fastmcp",
    "PrefectHQ fastmcp",
    """
    1. MCP tool server Reference:
    https:/github.com/PrefectHQ/fastmcp_
    The framework most MCP servers are built on right now.
    """,
    [
        candidate("PrefectHQ", "fastmcp"),
        candidate("punkpeye", "fastmcp"),
    ],
    "verified",
    "PrefectHQ/fastmcp",
)


# 2. CrewAI: OCR corrupts the owner, but official wording supports
# the correct repository.
run_case(
    "CrewAI examples",
    "crewAI-examples",
    """
    2. Multi-agent pipeline Reference:
    https:/github.com/crewAllnc/crewAl-examples
    Official CrewAl example collection.
    """,
    [
        candidate("crewAIInc", "crewAI-examples", archived=True),
        candidate("iam-veeramalla", "crewAI-examples"),
        candidate("kno2gether", "crewai-examples"),
    ],
    "verified",
    "crewAIInc/crewAI-examples",
)


# 3. Payment gateway: exact title should select the matching repository
# when only one exact candidate is supplied.
run_case(
    "Idempotent payment gateway",
    "idempotent-payment-gateway",
    """
    6. Non-toy payments backend Reference:
    https:/github.com/zgabrieloliveira/idémpotent*paymént-gateway
    Solves the double-charge/race-condition problem.
    """,
    [
        candidate(
            "zgabrieloliveira",
            "idempotent-payment-gateway",
            description="Payment gateway with idempotency and concurrency protection.",
        ),
    ],
    "verified",
    "zgabrieloliveira/idempotent-payment-gateway",
)


# 4. Truncated OCR hint must not manufacture a candidate.
run_case(
    "Truncated observability hint",
    "AI-Powered-Observability-and-Log-Analysis-System",
    """
    9. AI-assisted observability dashboard
    Reference: https:/github.com/Keerthikeswaran/AI-Powered-
    Prometheus + Grafana + Loki wired to an LLM.
    """,
    [
        candidate(
            "KeerthiKeswaran",
            "AI-Powered-Observability-and-Log-Analysis-System",
        ),
    ],
    "verified",
    "KeerthiKeswaran/AI-Powered-Observability-and-Log-Analysis-System",
)


# 5. Unrelated leaked repository must NOT be allowed to verify
# Proctoring-AI.
run_case(
    "Proctoring leaked next-item reference",
    "Proctoring-AI",
    """
    13. Real-time proctoring/attention detection
    Reference: https://github.com/vardanagarwal/Proctoring-AI
    Eye tracking, head pose and person-counting.
    https://github.com/di-sukharev/opencommit
    """,
    [
        candidate("vardanagarwal", "Proctoring-AI"),
        candidate("di-sukharev", "opencommit"),
    ],
    "verified",
    "vardanagarwal/Proctoring-AI",
)


# 6. Same repository name with no distinguishing evidence must remain ambiguous.
run_case(
    "Ambiguous same-name repositories",
    "crewAI-examples",
    "A collection of CrewAI examples.",
    [
        candidate("crewAIInc", "crewAI-examples"),
        candidate("iam-veeramalla", "crewAI-examples"),
    ],
    "ambiguous",
)


print("\nALL INTEGRATION TESTS PASSED")
