from backend.app.github_discovery import extract_github_hints
from backend.app.github_discovery_service import discover_github_candidates
from backend.app.github_resolver import resolve_github_resource


cases = [
    (
        "crewAI-examples",
        """
        2. Multi-agent pipeline Reference:
        https:/github.com/crewAllnc/crewAl-examples
        Official CrewAl example collection.
        """,
        "ambiguous",
    ),
    (
        "idempotent-payment-gateway",
        """
        6. Non-toy payments backend Reference:
        https:/github.com/zgabrieloliveira/idémpotent*paymént-gateway
        Solves the double-charge/race-condition problem.
        """,
        "ambiguous",
    ),
    (
        "Network-Intrusion-Detection-System",
        """
        10. ML-based intrusion detection
        Reference: https:/github.com/vicky60629/Network-Intrusion-
        Detection-System
        Classifies traffic across multiple attack types.
        """,
        "verified",
    ),
]


for title, evidence, expected in cases:
    hints = extract_github_hints(evidence)

    candidates = discover_github_candidates(
        title,
        hints,
        evidence_text=evidence,
    )

    result = resolve_github_resource(
        title,
        hints,
        candidates,
        evidence_text=evidence,
    )

    print("=" * 90)
    print(title)
    print("HINTS:", [hint.full_hint for hint in hints])
    print("CANDIDATES:", len(candidates))
    print("STATUS:", result.status)

    if result.selected:
        print(
            "SELECTED:",
            f"{result.selected.owner}/"
            f"{result.selected.repository}",
        )

    print("REASON:", result.reason)

    assert result.status == expected

    if expected == "verified":
        assert result.selected is not None


print("\nGITHUB AI INTEGRATION TEST PASSED")