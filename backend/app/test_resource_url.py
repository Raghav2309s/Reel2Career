import unittest

from ai_extract import normalize_resource_url


class NormalizeResourceUrlTests(unittest.TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(normalize_resource_url(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(normalize_resource_url(""))

    def test_whitespace_returns_none(self):
        self.assertIsNone(normalize_resource_url("   "))

    def test_complete_https_url(self):
        self.assertEqual(
            normalize_resource_url(
                "https://github.com/bearer/bearer"
            ),
            "https://github.com/bearer/bearer",
        )

    def test_complete_markdown_url(self):
        self.assertEqual(
            normalize_resource_url(
                "[https://github.com/bearer/bearer]"
                "(https://github.com/bearer/bearer)"
            ),
            "https://github.com/bearer/bearer",
        )

    def test_labeled_markdown_url(self):
        self.assertEqual(
            normalize_resource_url(
                "[Bearer](https://github.com/bearer/bearer)"
            ),
            "https://github.com/bearer/bearer",
        )

    def test_truncated_https_url(self):
        self.assertIsNone(
            normalize_resource_url(
                "https://app.emergent.sh/..."
            )
        )

    def test_truncated_markdown_url(self):
        self.assertIsNone(
            normalize_resource_url(
                "[https://app.emergent.sh/?utm_shift=redire]"
                "(https://app.emergent.sh/?utm_shift=redire)..."
            )
        )

    def test_http_url_rejected(self):
        self.assertIsNone(
            normalize_resource_url(
                "http://example.com"
            )
        )

    def test_bare_domain_rejected(self):
        self.assertIsNone(
            normalize_resource_url(
                "example.com"
            )
        )

    def test_www_domain_rejected(self):
        self.assertIsNone(
            normalize_resource_url(
                "www.example.com"
            )
        )

    def test_javascript_url_rejected(self):
        self.assertIsNone(
            normalize_resource_url(
                "javascript:alert(1)"
            )
        )

    def test_malformed_markdown_rejected(self):
        self.assertIsNone(
            normalize_resource_url(
                "[broken markdown"
            )
        )

    def test_truncated_markdown_both_sides(self):
        self.assertIsNone(
            normalize_resource_url(
                "[https://example.com/...]"
                "(https://example.com/...)"
            )
        )


    def test_case_a_complete_bare_domain_recovered(self):
        from ai_extract import validate_https_resource_url

        url = validate_https_resource_url(
            {
                "url": None,
            },
            [
                {
                    "evidence_id": 1,
                    "quote": "Based on: Bearer — github.com/bearer/bearer",
                }
            ],
            {
                1: {
                    "search_text": (
                        "Based on: Bearer — github.com/bearer/bearer"
                    ),
                }
            },
            "resources[1]",
        )
        self.assertEqual(
            url,
            "https://github.com/bearer/bearer",
        )

    def test_case_b_complete_https_recovered(self):
        from ai_extract import validate_https_resource_url

        url = validate_https_resource_url(
            {
                "url": None,
            },
            [
                {
                    "evidence_id": 1,
                    "quote": "https://github.com/bearer/bearer",
                }
            ],
            {
                1: {
                    "search_text": (
                        "https://github.com/bearer/bearer"
                    ),
                }
            },
            "resources[1]",
        )
        self.assertEqual(
            url,
            "https://github.com/bearer/bearer",
        )

    def test_case_c_truncated_url_rejected(self):
        from ai_extract import validate_https_resource_url

        url = validate_https_resource_url(
            {
                "url": None,
            },
            [
                {
                    "evidence_id": 1,
                    "quote": "app.emergent.sh/?utm_shift=redire...",
                }
            ],
            {
                1: {
                    "search_text": (
                        "app.emergent.sh/?utm_shift=redire..."
                    ),
                }
            },
            "resources[1]",
        )
        self.assertIsNone(url)

    def test_ungrounded_complete_url_becomes_none(self):
        from ai_extract import validate_https_resource_url

        url = validate_https_resource_url(
            {
                "url": "https://github.com/bearer/bearer",
            },
            [
                {
                    "evidence_id": 1,
                    "quote": "Use Bearer to scan the repo",
                }
            ],
            {
                1: {
                    "search_text": "Use Bearer to scan the repo",
                }
            },
            "resources[1]",
        )
        self.assertIsNone(url)

    def test_grounded_complete_url_kept(self):
        from ai_extract import validate_https_resource_url

        url = validate_https_resource_url(
            {
                "url": "https://github.com/bearer/bearer",
            },
            [
                {
                    "evidence_id": 1,
                    "quote": "https://github.com/bearer/bearer",
                }
            ],
            {
                1: {
                    "search_text": (
                        "Repo: https://github.com/bearer/bearer"
                    ),
                }
            },
            "resources[1]",
        )
        self.assertEqual(
            url,
            "https://github.com/bearer/bearer",
        )


if __name__ == "__main__":
    unittest.main()
