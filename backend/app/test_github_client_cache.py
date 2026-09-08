from pathlib import Path

from backend.app.github_client import (
    CACHE_DIR,
    search_repositories,
)


repository_name = "idempotent-payment-gateway"

first = search_repositories(
    repository_name,
    force_refresh=True,
)

print("FIRST RESULT COUNT:", len(first))

cache_files = list(
    CACHE_DIR.glob("idempotent-payment-gateway*.json")
)

print("CACHE FILES:", cache_files)

assert first
assert cache_files

second = search_repositories(
    repository_name,
    force_refresh=False,
)

print("SECOND RESULT COUNT:", len(second))

assert len(second) == len(first)

print("\nGITHUB CLIENT CACHE TEST PASSED")