import re
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal

class WorkerSignals(QObject):
    finished = pyqtSignal()
    result = pyqtSignal(object)
    progress = pyqtSignal(int)
    error = pyqtSignal(str)

class SearchWorker(QRunnable):
    def __init__(self, file_paths, search_text, case_sensitive=False, whole_word=False, use_regex=False):
        super().__init__()
        self.file_paths = file_paths
        self.search_text = search_text
        self.case_sensitive = case_sensitive
        self.whole_word = whole_word
        self.use_regex = use_regex
        self.signals = WorkerSignals()

    def run(self):
        try:
            results = []
            total_files = len(self.file_paths)

            flags = 0 if self.case_sensitive else re.IGNORECASE
            
            pattern_text = self.search_text
            if not self.use_regex:
                pattern_text = re.escape(self.search_text)
                if self.whole_word:
                    pattern_text = r'\b' + pattern_text + r'\b'
            
            try:
                pattern = re.compile(pattern_text, flags)
            except re.error:
                self.signals.error.emit("Invalid regular expression pattern")
                return

            for i, (file_path, content) in enumerate(self.file_paths):
                matches = list(pattern.finditer(content))
                if matches:
                    results.append((file_path, matches))
                            
                self.signals.progress.emit(int((i + 1) / total_files * 100))
                
            self.signals.result.emit(results)
            self.signals.finished.emit()
            
        except Exception as e:
            self.signals.error.emit(str(e))

#
