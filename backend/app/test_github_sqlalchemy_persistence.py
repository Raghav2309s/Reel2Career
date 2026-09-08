import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base, Resource
from backend.app.github_persistence import apply_github_resolution
from backend.app.github_resolver import GitHubResolution
from backend.app.resource_verifier import (
    GitHubRepositoryCandidate,
    VerificationResult,
)


def candidate(owner, repository):
    return GitHubRepositoryCandidate(
        owner=owner,
        repository=repository,
        url=f"https://github.com/{owner}/{repository}",
    )


candidate_obj = candidate(
    "PrefectHQ",
    "fastmcp",
)

resolution = GitHubResolution(
    status="verified",
    selected=candidate_obj,
    ranking=(),
    verification=VerificationResult(
        status="verified",
        candidate=candidate_obj,
        reason="test",
    ),
    reason="test",
)


temp_dir = tempfile.mkdtemp()
db_path = os.path.join(temp_dir, "test.db")

try:
    engine = create_engine(f"sqlite:///{db_path}")

    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    db = Session()

    resource = Resource(
        title="fastmcp (PrefectHQ)",
        url=None,
        identity_key=None,
        verification_status="unverified",
        description="",
    )

    db.add(resource)
    db.commit()

    print("BEFORE:")
    print(resource.id, resource.verification_status)

    changed = apply_github_resolution(
        resource,
        resolution,
    )

    print("\nAFTER APPLY:")
    print(resource.id)
    print(resource.url)
    print(resource.identity_key)
    print(resource.verification_status)
    print("CHANGED:", changed)

    db.commit()

    db.expire_all()

    reloaded = (
        db.query(Resource)
        .filter(Resource.id == resource.id)
        .one()
    )

    print("\nAFTER COMMIT + RELOAD:")
    print(reloaded.id)
    print(reloaded.url)
    print(reloaded.identity_key)
    print(reloaded.verification_status)

    assert changed is True

    assert reloaded.url == (
        "https://github.com/PrefectHQ/fastmcp"
    )

    assert reloaded.identity_key == (
        "github:prefecthq/fastmcp"
    )

    assert reloaded.verification_status == "verified"

    print("\nSQLALCHEMY GITHUB PERSISTENCE TEST PASSED")

    db.close()

finally:
    try:
        os.remove(db_path)
    except OSError:
        pass

    try:
        os.rmdir(temp_dir)
    except OSError:
        pass