from __future__ import annotations

import unittest
from unittest.mock import patch

from chareco.core.models import AnalysisOptions
from chareco.core import service


class AnalysisServiceTests(unittest.TestCase):
    def test_pat_is_rejected_for_lookalike_github_host(self) -> None:
        options = AnalysisOptions(
            source_path="https://github.com.evil.example/org/repo.git",
            is_local=False,
        )

        with patch.object(service.porcelain, "clone") as clone:
            with self.assertRaises(ValueError):
                service._clone_repository(options, "unused", "secret-token")

        clone.assert_not_called()

    def test_manifest_source_strips_url_credentials(self) -> None:
        self.assertEqual(
            service.display_source("https://user:password@example.com/project.git"),
            "https://example.com/project.git",
        )


if __name__ == "__main__":
    unittest.main()
