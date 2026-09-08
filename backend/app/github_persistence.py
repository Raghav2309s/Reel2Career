from __future__ import annotations

from backend.app.github_resolver import GitHubResolution


def apply_github_resolution(
    resource,
    resolution: GitHubResolution,
) -> bool:
    if resolution.status != "verified":
        return False

    candidate = resolution.selected
    if candidate is None:
        raise ValueError("Verified GitHub resolution must have a selected candidate.")

    github_url = candidate.url
    github_identity = (
        f"github:{candidate.owner.casefold()}/{candidate.repository.casefold()}"
    )

    # Never overwrite an existing conflicting URL.
    if resource.url is not None and resource.url != github_url:
        raise ValueError(
            "Refusing GitHub persistence because the existing resource URL "
            "conflicts with the verified GitHub URL."
        )

    # Never overwrite an existing conflicting identity.
    if resource.identity_key is not None and resource.identity_key != github_identity:
        raise ValueError(
            "Refusing GitHub persistence because the existing identity key "
            "conflicts with the verified GitHub identity."
        )

    changed = False

    if resource.url is None:
        resource.url = github_url
        changed = True

    if resource.identity_key is None:
        resource.identity_key = github_identity
        changed = True

    if resource.verification_status != "verified":
        resource.verification_status = "verified"
        changed = True

    return changed