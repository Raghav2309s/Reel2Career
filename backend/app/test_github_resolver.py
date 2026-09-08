from backend.app.github_discovery import GitHubHint
from backend.app.github_resolver import resolve_github_resource
from backend.app.resource_verifier import GitHubRepositoryCandidate


def candidate(owner, repository):
    return GitHubRepositoryCandidate(
        owner=owner,
        repository=repository,
        url=f"https://github.com/{owner}/{repository}",
    )


# ---------------------------------------------------------
# 1. Explicit identity → verified
# ---------------------------------------------------------

result = resolve_github_resource(
    "Network-Intrusion-Detection-System",
    [],
    [
        candidate("jgera", "Network-Intrusion-Detection-System"),
        candidate("vicky60629", "Network-Intrusion-Detection-System"),
        candidate("hectorpadin1", "Network-Intrusion-Detection-System"),
    ],
    evidence_text="""
    Reference: https:/github.com/vicky60629/Network-Intrusion-
    Detection-System
    """,
)

print("=" * 90)
print("NETWORK INTRUSION")
print("STATUS:", result.status)
print("SELECTED:", result.selected)
print("TOP:", result.ranking[0])

assert result.status == "verified"
assert result.selected is not None
assert result.selected.owner == "vicky60629"


# ---------------------------------------------------------
# 2. OCR-corrupted owner/repo → ranked but ambiguous
# ---------------------------------------------------------

result = resolve_github_resource(
    "crewAI-examples",
    [
        GitHubHint(
            owner="crewAllnc",
            repository_fragment="crewAl-examples",
        )
    ],
    [
        candidate("crewAIInc", "crewAI-examples"),
        candidate("iam-veeramalla", "crewAI-examples"),
        candidate("kno2gether", "crewai-examples"),
    ],
    evidence_text="""
    Reference: https:/github.com/crewAllnc/crewAl-examples
    Official CrewAl example collection.
    """,
)

print("\n" + "=" * 90)
print("CREWAI")
print("STATUS:", result.status)
print("SELECTED:", result.selected)
print("TOP:", result.ranking[0])

assert result.status == "ambiguous"
assert result.selected is None
assert result.ranking[0].candidate.owner == "crewAIInc"


# ---------------------------------------------------------
# 3. Damaged repository but exact owner → still ambiguous
# ---------------------------------------------------------

result = resolve_github_resource(
    "Proctoring-AI",
    [
        GitHubHint(
            owner="vardanagarwal",
            repository_fragment="Proctoring-Al",
        )
    ],
    [
        candidate("vardanagarwal", "Proctoring-AI"),
        candidate("someone-else", "Proctoring-AI"),
    ],
    evidence_text="""
    Reference: https:/github.com/vardanagarwal/Proctoring-Al
    """,
)

print("\n" + "=" * 90)
print("PROCTORING")
print("STATUS:", result.status)
print("SELECTED:", result.selected)
print("TOP:", result.ranking[0])

assert result.status == "ambiguous"
assert result.selected is None
assert result.ranking[0].candidate.owner == "vardanagarwal"


print("\nGITHUB RESOLVER TESTS PASSED")