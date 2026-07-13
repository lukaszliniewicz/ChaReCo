from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    import tiktoken  # noqa: F401
except ImportError:
    sys.modules["tiktoken"] = SimpleNamespace(
        get_encoding=lambda _name: SimpleNamespace(encode=lambda text: list(text))
    )

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from chareco.gui import App


class GuiLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = App()

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()

    def test_empty_search_does_not_leave_ui_busy(self) -> None:
        self.window.search_input.setText("needle")
        self.window.perform_search()

        self.assertFalse(self.window.is_searching)
        self.assertTrue(self.window.search_button.isEnabled())

    def test_nested_partial_selection_propagates_to_all_ancestors(self) -> None:
        paths = {"a/b/one.py": "one", "a/b/two.py": "two"}
        self.window.file_contents = paths
        self.window.update_sidebar({path: 0 for path in paths})
        self.window.path_to_item_map["a/b/one.py"].setCheckState(0, Qt.CheckState.Checked)

        root = self.window.file_tree.topLevelItem(0)
        self.assertEqual(root.checkState(0), Qt.CheckState.PartiallyChecked)
        self.assertEqual(root.child(0).checkState(0), Qt.CheckState.PartiallyChecked)

    def test_line_numbers_include_blank_lines(self) -> None:
        self.window.line_numbers_checkbox.setChecked(True)
        self.assertEqual(self.window._apply_line_numbers("one\n\ntwo"), "1: one\n2: \n3: two")


if __name__ == "__main__":
    unittest.main()
