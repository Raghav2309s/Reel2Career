from types import SimpleNamespace

from backend.app.database import Resource
from backend.app.github_persistence import apply_github_resolution
from backend.app.github_resolver import GitHubResolution
from backend.app.resource_verifier import GitHubRepositoryCandidate, VerificationResult


def candidate(owner, repository):
    return GitHubRepositoryCandidate(
        owner=owner,
        repository=repository,
        url=f"https://github.com/{owner}/{repository}",
    )


verified_candidate = candidate(
    "vicky60629",
    "Network-Intrusion-Detection-System",
)

verified_resolution = GitHubResolution(
    status="verified",
    selected=verified_candidate,
    ranking=(),
    verification=VerificationResult(
        status="verified",
        candidate=verified_candidate,
        reason="test",
    ),
    reason="test",
)

resource = SimpleNamespace(
    url=None,
    identity_key=None,
    verification_status="unverified",
)

changed = apply_github_resolution(
    resource,
    verified_resolution,
)

print("=" * 90)
print("VERIFIED RESOURCE")
print(resource.url)
print(resource.identity_key)
print(resource.verification_status)
print("CHANGED:", changed)

assert changed is True
assert resource.url == (
    "https://github.com/"
    "vicky60629/"
    "Network-Intrusion-Detection-System"
)
assert resource.identity_key == (
    "github:vicky60629/"
    "network-intrusion-detection-system"
)
assert resource.verification_status == "verified"


# ---------------------------------------------------------
# Ambiguous must not modify anything
# ---------------------------------------------------------

ambiguous_resolution = GitHubResolution(
    status="ambiguous",
    selected=None,
    ranking=(),
    verification=VerificationResult(
        status="ambiguous",
        candidate=None,
        reason="test",
    ),
    reason="test",
)

resource = SimpleNamespace(
    url=None,
    identity_key=None,
    verification_status="unverified",
)

changed = apply_github_resolution(
    resource,
    ambiguous_resolution,
)

print("\n" + "=" * 90)
print("AMBIGUOUS RESOURCE")
print(resource.url)
print(resource.identity_key)
print(resource.verification_status)
print("CHANGED:", changed)

assert changed is False
assert resource.url is None
assert resource.identity_key is None
assert resource.verification_status == "unverified"


# ---------------------------------------------------------
# Existing durable identity must not be replaced
# ---------------------------------------------------------

resource = SimpleNamespace(
    url=(
        "https://github.com/"
        "vicky60629/"
        "Network-Intrusion-Detection-System"
    ),
    identity_key=(
        "github:vicky60629/"
        "network-intrusion-detection-system"
    ),
    verification_status="verified",
)

changed = apply_github_resolution(
    resource,
    verified_resolution,
)

print("\n" + "=" * 90)
print("EXISTING DURABLE RESOURCE")
print(resource.url)
print(resource.identity_key)
print(resource.verification_status)
print("CHANGED:", changed)

assert changed is False
assert resource.url == (
    "https://github.com/"
    "vicky60629/"
    "Network-Intrusion-Detection-System"
)
assert resource.identity_key == (
    "github:vicky60629/"
    "network-intrusion-detection-system"
)


print("\n" + "=" * 90)
print("CONFLICTING EXISTING URL")

conflicting = Resource(
    title="Conflicting Resource",
    url="https://example.com/wrong-repo",
    identity_key=None,
    verification_status="unverified",
)

try:
    apply_github_resolution(conflicting, verified_resolution)
    raise AssertionError("Conflicting URL should have been rejected.")
except ValueError as exc:
    print("REJECTED:", exc)

print("CONFLICT TEST PASSED")


print("\nGITHUB PERSISTENCE TESTS PASSED")