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


def test_case(name, title, evidence, candidates, expected_status, expected_repo=None):
    hints = extract_github_hints(evidence)

    result = verify_github_resource(
        title,
        candidates,
        evidence_text=evidence,
    )

    print("=" * 90)
    print(name)
    print("TITLE:    ", title)
    print("HINTS:    ", [hint.full_hint for hint in hints])
    print("STATUS:   ", result.status)
    print("SELECTED: ", result.candidate)
    print("REASON:   ", result.reason)

    assert result.status == expected_status

    if expected_repo:
        assert result.candidate is not None
        actual_repo = (
            f"{result.candidate.owner}/{result.candidate.repository}"
        )
        assert actual_repo == expected_repo


# ------------------------------------------------------------
# 1. Resource title differs from GitHub repository name.
# Evidence contains the exact owner/repository identity.
# ------------------------------------------------------------

test_case(
    "Prefect fastmcp — evidence identity",
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


# ------------------------------------------------------------
# 2. Multiple repositories share the same name.
# Evidence explicitly identifies the correct owner.
# ------------------------------------------------------------

test_case(
    "CrewAI examples — disambiguation",
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
    "ambiguous",
)


# ------------------------------------------------------------
# 3. Exact repository title match.
# ------------------------------------------------------------

test_case(
    "Kubernetes deployment — exact match",
    "github-actions-k8s-deploy",
    """
    7. CI/CD to Kubernetes pipeline Reference:
    https:/github.com/IAMDevBox/github-actions-k8s-deploy
    RBAC manifests and blue-green deployment workflow.
    """,
    [
        candidate("IAMDevBox", "github-actions-k8s-deploy"),
    ],
    "verified",
    "IAMDevBox/github-actions-k8s-deploy",
)


# ------------------------------------------------------------
# 4. Truncated OCR hint must not verify a repository.
# ------------------------------------------------------------

test_case(
    "Truncated OCR — safe rejection",
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


# ------------------------------------------------------------
# 5. No evidence identity + multiple same-name repositories
# must remain ambiguous.
# ------------------------------------------------------------

test_case(
    "Same-name repositories — ambiguity preserved",
    "crewAI-examples",
    "A collection of CrewAI examples.",
    [
        candidate("crewAIInc", "crewAI-examples"),
        candidate("iam-veeramalla", "crewAI-examples"),
    ],
    "ambiguous",
)


# ------------------------------------------------------------
# 6. Weak owner-only evidence must not verify.
# ------------------------------------------------------------

test_case(
    "Owner-only evidence — rejection",
    "fastmcp",
    "PrefectHQ provides tools for workflow orchestration.",
    [
        candidate("PrefectHQ", "fastmcp"),
        candidate("punkpeye", "fastmcp"),
    ],
    "ambiguous",
)


print("\nALL EVIDENCE-AWARE VERIFICATION TESTS PASSED")

