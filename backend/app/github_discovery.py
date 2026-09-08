import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GitHubHint:
    owner: str
    repository_fragment: str

    @property
    def full_hint(self) -> str:
        return f"{self.owner}/{self.repository_fragment}"


_GITHUB_HINT_RE = re.compile(
    r"(?i)(?:https?://)?github\.com/"
    r"([A-Za-z0-9_.-]+)"
    r"[/\s]+"
    r"([A-Za-z0-9_.*~-]+)"
)


def _clean_repository_fragment(value: str) -> str:
    value = value.strip()
    value = value.rstrip(".,;:)]}'\"`")
    value = value.replace("*", "")

    # OCR commonly adds "_" at the end of a repository name.
    value = value.rstrip("_")

    return value


def _is_usable_repository_fragment(value: str) -> bool:
    if not value:
        return False

    if len(value) < 6:
        return False

    # A trailing hyphen strongly suggests OCR stopped at a line wrap.
    if value.endswith("-"):
        return False

    generic_fragments = {
        "id",
        "app",
        "api",
        "web",
        "test",
        "main",
        "server",
        "client",
        "repo",
    }

    return value.casefold() not in generic_fragments


def extract_github_hints(text: str) -> list[GitHubHint]:
    if not text:
        return []

    hints: list[GitHubHint] = []
    seen: set[tuple[str, str]] = set()

    for owner, repository in _GITHUB_HINT_RE.findall(text):
        repository = _clean_repository_fragment(repository)

        if not _is_usable_repository_fragment(repository):
            continue

        key = (owner.casefold(), repository.casefold())

        if key in seen:
            continue

        seen.add(key)

        hints.append(
            GitHubHint(
                owner=owner,
                repository_fragment=repository,
            )
        )

    return hints


def extract_github_owner_hints(text: str) -> list[str]:
    """
    Extract GitHub owner-like fragments from noisy OCR evidence.

    This function intentionally extracts only the owner portion.
    It does not repair or construct repository identity.
    """

    if not text:
        return []

    owners: list[str] = []
    seen: set[str] = set()

    for owner, _repository in _GITHUB_HINT_RE.findall(text):
        key = owner.casefold()

        if key in seen:
            continue

        seen.add(key)
        owners.append(owner)

    return owners
