"""Cancellable background search workers."""

from __future__ import annotations

import re
from threading import Event

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal


class WorkerSignals(QObject):
    finished = pyqtSignal(int)
    result = pyqtSignal(int, object)
    progress = pyqtSignal(int, int, int)
    error = pyqtSignal(int, str)


class SearchWorker(QRunnable):
    def __init__(
        self,
        job_id: int,
        files: list[tuple[str, str]],
        search_text: str,
        *,
        case_sensitive: bool = False,
        whole_word: bool = False,
        use_regex: bool = False,
        cancel_event: Event | None = None,
    ) -> None:
        super().__init__()
        self.job_id = job_id
        self.files = files
        self.search_text = search_text
        self.case_sensitive = case_sensitive
        self.whole_word = whole_word
        self.use_regex = use_regex
        self.cancel_event = cancel_event or Event()
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            flags = 0 if self.case_sensitive else re.IGNORECASE
            pattern_text = self.search_text if self.use_regex else re.escape(self.search_text)
            if self.whole_word:
                pattern_text = rf"\b(?:{pattern_text})\b"
            try:
                pattern = re.compile(pattern_text, flags)
            except re.error as error:
                self.signals.error.emit(self.job_id, f"Invalid regular expression: {error}")
                return

            results: list[tuple[str, list[re.Match[str]]]] = []
            total_files = len(self.files)
            for index, (file_path, content) in enumerate(self.files, start=1):
                if self.cancel_event.is_set():
                    return
                matches = list(pattern.finditer(content))
                if matches:
                    results.append((file_path, matches))
                self.signals.progress.emit(self.job_id, index, total_files)

            if not self.cancel_event.is_set():
                self.signals.result.emit(self.job_id, results)
        except Exception as error:  # Keep one malformed file from wedging the UI.
            self.signals.error.emit(self.job_id, str(error))
        finally:
            self.signals.finished.emit(self.job_id)
