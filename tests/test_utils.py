from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chareco.core import utils


class UtilsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_comma_rules_are_applied_and_output_is_deterministic(self) -> None:
        self.write("z.py", "z")
        self.write("a.md", "a")
        self.write("skip.txt", "skip")

        _content, positions, _files = utils.concatenate_files(self.root, include=[".py,.md"])

        self.assertEqual(list(positions), ["a.md", "z.py"])

    def test_notebooks_follow_include_and_exclude_filters(self) -> None:
        self.write("notes.ipynb", "{}")
        with patch.object(utils, "convert_notebook_to_markdown", return_value="# notebook"):
            _content, positions, _files = utils.concatenate_files(self.root, include=[".py"])
            self.assertNotIn("notes.ipynb", positions)

            _content, positions, files = utils.concatenate_files(self.root, include=[".ipynb"])
            self.assertEqual(files["notes.ipynb"], "# notebook")

    def test_excluded_directories_and_git_metadata_do_not_appear(self) -> None:
        self.write(".git/config", "secret")
        self.write("node_modules/dependency/index.js", "dependency")
        self.write("src/main.py", "main")

        structure = utils.get_structure(self.root, exclude_folders=["node_modules"])
        _content, positions, _files = utils.concatenate_files(
            self.root, exclude_folders=["node_modules"]
        )

        self.assertNotIn(".git", structure)
        self.assertNotIn("node_modules", structure)
        self.assertEqual(list(positions), ["src/main.py"])

    def test_limits_skip_oversized_content(self) -> None:
        self.write("small.py", "small")
        self.write("large.py", "x" * 64)

        _content, positions, _files = utils.concatenate_files(
            self.root, max_file_bytes=16, max_total_bytes=16
        )

        self.assertEqual(list(positions), ["small.py"])

    def test_total_output_limit_is_marked(self) -> None:
        self.write("a.py", "aaaa")
        self.write("b.py", "bbbb")

        content, positions, _files = utils.concatenate_files(
            self.root, max_file_bytes=16, max_total_bytes=5
        )

        self.assertEqual(list(positions), ["a.py"])
        self.assertIn("[Output limit reached; remaining files were skipped.]", content)


if __name__ == "__main__":
    unittest.main()
