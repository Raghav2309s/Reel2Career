from backend.app.github_client import GitHubSearchResult
from backend.app.resource_verifier import (
    GitHubRepositoryCandidate,
    verify_github_resource,
)


def test_crewai_examples_is_ambiguous_by_name_alone():
    candidates = [
        GitHubRepositoryCandidate(
            owner="crewAIInc",
            repository="crewAI-examples",
            url="https://github.com/crewAIInc/crewAI-examples",
        ),
        GitHubRepositoryCandidate(
            owner="kno2gether",
            repository="crewai-examples",
            url="https://github.com/kno2gether/crewai-examples",
        ),
        GitHubRepositoryCandidate(
            owner="iam-veeramalla",
            repository="crewAI-examples",
            url="https://github.com/iam-veeramalla/crewAI-examples",
        ),
    ]

    result = verify_github_resource(
        "crewAI-examples",
        candidates,
    )

    assert result.status == "ambiguous"
    assert result.candidate is None


def test_official_crewai_evidence_disambiguates_match():
    candidates = [
        GitHubRepositoryCandidate(
            owner="crewAIInc",
            repository="crewAI-examples",
            url="https://github.com/crewAIInc/crewAI-examples",
        ),
        GitHubRepositoryCandidate(
            owner="kno2gether",
            repository="crewai-examples",
            url="https://github.com/kno2gether/crewai-examples",
        ),
        GitHubRepositoryCandidate(
            owner="iam-veeramalla",
            repository="crewAI-examples",
            url="https://github.com/iam-veeramalla/crewAI-examples",
        ),
    ]

    result = verify_github_resource(
        "crewAI-examples",
        candidates,
        evidence_text=(
            "Multi-agent pipeline Reference: "
            "https://github.com/crewAllnc/crewAl-examples "
            "Official CrewAI example collection"
        ),
    )

    assert result.status == "ambiguous"
    assert result.candidate is None


def test_unrelated_evidence_does_not_verify_same_name():
    candidates = [
        GitHubRepositoryCandidate(
            owner="crewAIInc",
            repository="crewAI-examples",
            url="https://github.com/crewAIInc/crewAI-examples",
            description=(
                "A collection of examples that show how to use "
                "CrewAI framework to automate workflows."
            ),
            topics=("crewai", "examples"),
        ),
        GitHubRepositoryCandidate(
            owner="other-user",
            repository="crewAI-examples",
            url="https://github.com/other-user/crewAI-examples",
            description="A collection of unrelated examples.",
            topics=("examples",),
        ),
    ]

    result = verify_github_resource(
        "crewAI-examples",
        candidates,
        evidence_text=(
            "This repository contains examples for an unrelated "
            "data-processing project."
        ),
    )

    assert result.status == "ambiguous"
    assert result.candidate is None


def test_weak_keyword_overlap_does_not_verify():
    candidates = [
        GitHubRepositoryCandidate(
            owner="crewAIInc",
            repository="crewAI-examples",
            url="https://github.com/crewAIInc/crewAI-examples",
            description=(
                "A collection of examples that show how to use "
                "CrewAI framework to automate workflows."
            ),
            topics=("crewai", "examples"),
        ),
        GitHubRepositoryCandidate(
            owner="other-user",
            repository="crewAI-examples",
            url="https://github.com/other-user/crewAI-examples",
            description="Examples for a different software project.",
            topics=("examples",),
        ),
    ]

    result = verify_github_resource(
        "crewAI-examples",
        candidates,
        evidence_text="Example collection with several workflows.",
    )

    assert result.status == "ambiguous"
    assert result.candidate is None


def test_metadata_can_disambiguate_without_exact_owner_text():
    candidates = [
        GitHubRepositoryCandidate(
            owner="crewAIInc",
            repository="crewAI-examples",
            url="https://github.com/crewAIInc/crewAI-examples",
            description=(
                "A collection of examples that show how to use "
                "CrewAI framework to automate workflows."
            ),
            topics=("crewai", "examples"),
        ),
        GitHubRepositoryCandidate(
            owner="other-user",
            repository="crewAI-examples",
            url="https://github.com/other-user/crewAI-examples",
            description="Unrelated repository.",
            topics=(),
        ),
    ]

    result = verify_github_resource(
        "crewAI-examples",
        candidates,
        evidence_text=(
            "Official CrewAl example collection, "
            "includes a full multi-crew content pipeline "
            "with state management."
        ),
    )

    assert result.status == "ambiguous"
    assert result.candidate is None


def test_github_metadata_strengthens_official_match():
    candidates = [
        GitHubRepositoryCandidate(
            owner="crewAIInc",
            repository="crewAI-examples",
            url="https://github.com/crewAIInc/crewAI-examples",
            description=(
                "A collection of examples that show how to use "
                "CrewAI framework to automate workflows."
            ),
            topics=("crewai", "examples"),
        ),
        GitHubRepositoryCandidate(
            owner="kno2gether",
            repository="crewai-examples",
            url="https://github.com/kno2gether/crewai-examples",
            description=(
                "This repo is forked and maintained separately."
            ),
            topics=(),
        ),
    ]

    result = verify_github_resource(
        "crewAI-examples",
        candidates,
        evidence_text=(
            "Multi-agent pipeline Reference: "
            "https:/github.com/crewAllnc/crewAl-examples "
            "Official CrewAl example collection, "
            "includes a full multi-crew content pipeline "
            "with state management."
        ),
    )

    assert result.status == "ambiguous"
    assert result.candidate is None