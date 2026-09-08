import unittest

from backend.app.resource_verifier import (
    GitHubRepositoryCandidate,
    VerificationResult,
    verify_github_resource,
)


class TestResourceVerifier(unittest.TestCase):

    def setUp(self):
        self.crewai = GitHubRepositoryCandidate(
            owner="crewAIInc",
            repository="crewAI-examples",
            url="https://github.com/crewAIInc/crewAI-examples",
        )

    def test_empty_title_is_invalid(self):
        result = verify_github_resource("")

        self.assertEqual(result.status, "invalid")
        self.assertIsNone(result.candidate)

    def test_whitespace_title_is_invalid(self):
        result = verify_github_resource("   ")

        self.assertEqual(result.status, "invalid")
        self.assertIsNone(result.candidate)

    def test_exact_repository_match_is_verified(self):
        result = verify_github_resource(
            "crewAI-examples",
            [self.crewai],
        )

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.candidate, self.crewai)

    def test_repository_match_is_case_insensitive(self):
        result = verify_github_resource(
            "CrewAI-Examples",
            [self.crewai],
        )

        self.assertEqual(result.status, "verified")
        self.assertEqual(result.candidate, self.crewai)

    def test_no_match_is_not_found(self):
        result = verify_github_resource(
            "fastmcp",
            [self.crewai],
        )

        self.assertEqual(result.status, "not_found")
        self.assertIsNone(result.candidate)

    def test_duplicate_repository_names_are_ambiguous(self):
        second = GitHubRepositoryCandidate(
            owner="another-owner",
            repository="crewAI-examples",
            url="https://github.com/another-owner/crewAI-examples",
        )

        result = verify_github_resource(
            "crewAI-examples",
            [self.crewai, second],
        )

        self.assertEqual(result.status, "ambiguous")
        self.assertIsNone(result.candidate)

    def test_result_is_immutable(self):
        result = VerificationResult(
            status="verified",
            candidate=self.crewai,
            reason="Exact repository-name match.",
        )

        with self.assertRaises(Exception):
            result.status = "not_found"


if __name__ == "__main__":
    unittest.main()
