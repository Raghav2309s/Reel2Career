from backend.app.github_discovery import extract_github_hints


CASES = [
    (
        "https:/github.com/PrefectHQ/fastmcp_",
        ["PrefectHQ/fastmcp"],
    ),
    (
        "https:/github.com/crewAllnc/crewAl-examples",
        ["crewAllnc/crewAl-examples"],
    ),
    (
        "https:/github.com/zgabrieloliveira/idémpotent*paymént-gateway",
        [],
    ),
    (
        "https:/github.com/Keerthikeswaran/Al-Powered-",
        [],
    ),
    (
        "https:/github.com/vicky60629/Network-Intrusion-",
        [],
    ),
    (
        "https:/github.com/MaitreeVaria/Indian-Sign-Language-",
        [],
    ),
    (
        "https:/github.com/IAMDevBox/github-actions-k8s-deploy",
        ["IAMDevBox/github-actions-k8s-deploy"],
    ),
]


for text, expected in CASES:
    actual = [hint.full_hint for hint in extract_github_hints(text)]

    print("=" * 80)
    print("INPUT:   ", text)
    print("EXPECTED:", expected)
    print("ACTUAL:  ", actual)

    assert actual == expected


print("\nALL DISCOVERY TESTS PASSED")
