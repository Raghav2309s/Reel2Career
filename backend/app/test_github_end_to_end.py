from backend.app.github_candidate_ranker import rank_github_candidates
from backend.app.github_discovery import extract_github_hints
from backend.app.resource_verifier import (
    GitHubRepositoryCandidate,
    verify_github_resource,
)


def candidate(owner, repository):
    return GitHubRepositoryCandidate(
        owner=owner,
        repository=repository,
        url=f"https://github.com/{owner}/{repository}",
    )


cases = [
    {
        "name": "Prefect fastmcp",
        "title": "PrefectHQ fastmcp",
        "evidence": """
        1. MCP tool server Reference:
        https:/github.com/PrefectHQ/fastmcp_
        """,
        "candidates": [
            candidate("PrefectHQ", "fastmcp"),
            candidate("punkpeye", "fastmcp"),
        ],
        "expected": "verified",
        "expected_repo": "PrefectHQ/fastmcp",
    },
    {
        "name": "CrewAI OCR",
        "title": "crewAI-examples",
        "evidence": """
        2. Multi-agent pipeline Reference:
        https:/github.com/crewAllnc/crewAl-examples
        Official CrewAl example collection.
        """,
        "candidates": [
            candidate("crewAIInc", "crewAI-examples"),
            candidate("iam-veeramalla", "crewAI-examples"),
            candidate("kno2gether", "crewai-examples"),
        ],
        "expected": "ambiguous",
        "expected_repo": None,
    },
    {
        "name": "Idempotent payment gateway",
        "title": "idempotent-payment-gateway",
        "evidence": """
        6. Non-toy payments backend Reference:
        https:/github.com/zgabrieloliveira/idémpotent*paymént-gateway
        Solves the double-charge/race-condition problem.
        """,
        "candidates": [
            candidate("faiza788", "idempotent-payment-gateway"),
            candidate("manasvi0209", "idempotent-payment-gateway"),
            candidate("Omenn6", "idempotent-payment-gateway"),
            candidate("rahulbitsgoa", "idempotent-payment-gateway"),
            candidate("Xprofess0r", "Idempotent-Payment-Gateway"),
            candidate("zgabrieloliveira", "idempotent-payment-gateway"),
        ],
        "expected": "ambiguous",
        "expected_repo": None,
    },
    {
        "name": "Network intrusion detection",
        "title": "Network-Intrusion-Detection-System",
        "evidence": """
        10. ML-based intrusion detection
        Reference: https:/github.com/vicky60629/Network-Intrusion-
        Detection-System
        Classifies traffic across multiple attack types.
        """,
        "candidates": [
            candidate("jgera", "Network-Intrusion-Detection-System"),
            candidate("vicky60629", "Network-Intrusion-Detection-System"),
            candidate("hectorpadin1", "Network-Intrusion-Detection-System"),
        ],
        "expected": "ambiguous",
        "expected_repo": None,
    },
    {
        "name": "Proctoring",
        "title": "Proctoring-AI",
        "evidence": """
        13. Real-time proctoring/attention detection
        Reference: https:/github.com/vardanagarwal/Proctoring-Al
        Eye tracking, mouth-open detection, head pose, and person-counting.
        """,
        "candidates": [
            candidate("vardanagarwal", "Proctoring-AI"),
            candidate("someone-else", "Proctoring-AI"),
        ],
        "expected": "ambiguous",
        "expected_repo": None,
    },
]


for case in cases:
    print("\n" + "=" * 100)
    print(case["name"])

    hints = extract_github_hints(case["evidence"])

    ranked = rank_github_candidates(
        case["title"],
        hints,
        case["candidates"],
        evidence_text=case["evidence"],
    )

    print("TOP RANK:")
    if ranked:
        top = ranked[0]
        print(
            f"{top.score:.2f} "
            f"{top.candidate.owner}/{top.candidate.repository} "
            f"{top.signals}"
        )
    else:
        print("none")

    result = verify_github_resource(
        case["title"],
        [item.candidate for item in ranked],
        evidence_text=case["evidence"],
    )

    print("VERIFIER:", result.status)
    print("SELECTED:", result.candidate)
    print("REASON:", result.reason)

    assert result.status == case["expected"]

    if case["expected_repo"]:
        assert result.candidate is not None
        actual = (
            f"{result.candidate.owner}/"
            f"{result.candidate.repository}"
        )
        assert actual == case["expected_repo"]


print("\nEND-TO-END GITHUB TESTS PASSED")