from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json
import time
from urllib.parse import quote
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = BASE_DIR / "data" / "github_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class GitHubSearchResult:
    owner: str
    repository: str
    url: str
    description: str = ""
    topics: tuple[str, ...] = ()
    archived: bool = False


class GitHubClientError(Exception):
    """Raised when GitHub lookup cannot be completed."""


def _cache_path(repository_name: str) -> Path:
    safe_name = "".join(
        character
        if character.isalnum() or character in "-_."
        else "_"
        for character in repository_name.strip().casefold()
    )

    return CACHE_DIR / f"{safe_name}.json"


def _load_cache(
    repository_name: str,
) -> list[GitHubSearchResult] | None:
    path = _cache_path(repository_name)

    if not path.exists():
        return None

    try:
        age = time.time() - path.stat().st_mtime

        if age > CACHE_TTL_SECONDS:
            return None

        payload = json.loads(
            path.read_text(encoding="utf-8")
        )

        results = []

        for item in payload:
            results.append(
                GitHubSearchResult(
                    owner=item["owner"],
                    repository=item["repository"],
                    url=item["url"],
                    description=item.get(
                        "description",
                        "",
                    ),
                    topics=tuple(
                        item.get("topics", [])
                    ),
                    archived=bool(
                        item.get(
                            "archived",
                            False,
                        )
                    ),
                )
            )

        return results

    except Exception:
        return None


def _save_cache(
    repository_name: str,
    results: list[GitHubSearchResult],
) -> None:
    path = _cache_path(repository_name)

    payload = []

    for result in results:
        item = asdict(result)
        item["topics"] = list(result.topics)
        payload.append(item)

    path.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )


def search_repositories(
    repository_name: str,
    *,
    timeout: float = 10.0,
    force_refresh: bool = False,
) -> list[GitHubSearchResult]:
    """
    Search GitHub for repositories matching a repository name.

    Cached results are used for seven days by default.

    Network I/O only.
    No database mutation.
    """

    if not repository_name or not repository_name.strip():
        return []

    normalized_name = repository_name.strip()

    if not force_refresh:
        cached = _load_cache(normalized_name)

        if cached is not None:
            return cached

    query = quote(
        f"{normalized_name} in:name"
    )

    url = (
        "https://api.github.com/search/repositories"
        f"?q={query}&per_page=10"
    )

    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "Reel2Career",
        },
        method="GET",
    )

    try:
        with urlopen(
            request,
            timeout=timeout,
        ) as response:
            payload = json.load(response)

    except Exception as exc:
        raise GitHubClientError(
            f"GitHub repository search failed: {exc}"
        ) from exc

    results: list[GitHubSearchResult] = []

    for item in payload.get(
        "items",
        [],
    ):
        owner = item.get(
            "owner",
            {},
        ).get("login")

        repository = item.get("name")
        html_url = item.get("html_url")

        if (
            not owner
            or not repository
            or not html_url
        ):
            continue

        raw_topics = item.get(
            "topics"
        ) or []

        topics = tuple(
            topic
            for topic in raw_topics
            if isinstance(topic, str)
            and topic.strip()
        )

        results.append(
            GitHubSearchResult(
                owner=owner,
                repository=repository,
                url=html_url,
                description=(
                    item.get(
                        "description"
                    )
                    or ""
                ),
                topics=topics,
                archived=bool(
                    item.get(
                        "archived",
                        False,
                    )
                ),
            )
        )

    _save_cache(
        normalized_name,
        results,
    )

    return results