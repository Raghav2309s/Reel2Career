from backend.app.github_discovery_service import discover_github_candidates
from backend.app.github_discovery import GitHubHint


# This test uses the cache created by the previous GitHub client test.
candidates = discover_github_candidates(
    "idempotent-payment-gateway",
    [],
    evidence_text="""
    Reference:
    https:/github.com/zgabrieloliveira/idémpotent*paymént-gateway
    """,
)

print("=" * 90)
print("DISCOVERED:", len(candidates))

for item in candidates:
    print(
        f"{item.owner}/{item.repository}"
        f" | archived={item.archived}"
    )

assert candidates

names = {
    (
        item.owner.casefold(),
        item.repository.casefold(),
    )
    for item in candidates
}

assert (
    "zgabrieloliveira",
    "idempotent-payment-gateway",
) in names

print("\nGITHUB DISCOVERY SERVICE TEST PASSED")