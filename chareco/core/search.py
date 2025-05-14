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
            
            for i, (file_path, content) in enumerate(self.file_paths):
                if self.use_regex:
                    flags = 0 if self.case_sensitive else re.IGNORECASE
                    try:
                        pattern = re.compile(self.search_text, flags)
                        matches = list(pattern.finditer(content))
                        if matches:
                            results.append((file_path, matches))
                    except re.error:
                        self.signals.error.emit("Invalid regular expression pattern")
                        return
                else:
                    search_flags = 0
                    if not self.case_sensitive:
                        content_lower = content.lower()
                        search_text_lower = self.search_text.lower()
                    else:
                        content_lower = content
                        search_text_lower = self.search_text
                        
                    if self.whole_word:
                        word_pattern = r'\b' + re.escape(search_text_lower) + r'\b'
                        matches = list(re.finditer(word_pattern, content_lower, 0 if self.case_sensitive else re.IGNORECASE))
                        if matches:
                            results.append((file_path, matches))
                    else:
                        start = 0
                        matches = []
                        while True:
                            start = content_lower.find(search_text_lower, start)
                            if start == -1:
                                break
                            
                            class SimpleMatch:
                                def __init__(self, start, end):
                                    self.start_pos = start
                                    self.end_pos = end
                                def start(self):
                                    return self.start_pos
                                def end(self):
                                    return self.end_pos
                            
                            matches.append(SimpleMatch(start, start + len(self.search_text)))
                            start += 1
                            
                        if matches:
                            results.append((file_path, matches))
                            
                self.signals.progress.emit(int((i + 1) / total_files * 100))
                
            self.signals.result.emit(results)
            self.signals.finished.emit()
            
        except Exception as e:
            self.signals.error.emit(str(e))

#