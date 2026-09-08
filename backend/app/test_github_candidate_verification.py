from backend.app.resource_verifier import (
    GitHubRepositoryCandidate,
    verify_github_candidate,
)


def candidate(owner, repository):
    return GitHubRepositoryCandidate(
        owner=owner,
        repository=repository,
        url=f"https://github.com/{owner}/{repository}",
    )


# Explicit identity with line wrapping
result = verify_github_candidate(
    candidate(
        "vicky60629",
        "Network-Intrusion-Detection-System",
    ),
    evidence_text="""
    Reference: https:/github.com/vicky60629/Network-Intrusion-
    Detection-System
    """,
)

print("=" * 90)
print("EXPLICIT IDENTITY")
print(result)

assert result.status == "verified"
assert result.candidate is not None
assert result.candidate.owner == "vicky60629"


# OCR-corrupted repository name
result = verify_github_candidate(
    candidate(
        "vardanagarwal",
        "Proctoring-AI",
    ),
    evidence_text="""
    Reference: https:/github.com/vardanagarwal/Proctoring-Al
    """,
)

print("\n" + "=" * 90)
print("OCR-CORRUPTED REPOSITORY")
print(result)

assert result.status == "ambiguous"
assert result.candidate is None


# Owner only
result = verify_github_candidate(
    candidate(
        "PrefectHQ",
        "fastmcp",
    ),
    evidence_text="""
    PrefectHQ provides workflow orchestration tools.
    """,
)

print("\n" + "=" * 90)
print("OWNER ONLY")
print(result)

assert result.status == "ambiguous"
assert result.candidate is None


print("\nSINGLE-CANDIDATE VERIFICATION TESTS PASSED")