from backend.app.github_discovery import extract_github_owner_hints


cases = {
    "idempotent": """
    Reference:
    https:/github.com/zgabrieloliveira/idémpotent*paymént-gateway
    """,
    "observability": """
    Reference:
    https:/github.com/Keerthikeswaran/Al-Powered-
    Observability-and-Log-Analysis-System
    """,
    "proctoring": """
    Reference:
    https:/github.com/vardanagarwal/Proctoring-Al
    """,
}


for name, evidence in cases.items():
    owners = extract_github_owner_hints(evidence)

    print("=" * 80)
    print(name)
    print("OWNERS:", owners)

    assert owners


print("\nALL OWNER HINT TESTS PASSED")
