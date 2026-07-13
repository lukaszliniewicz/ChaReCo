"""Qt wrapper for the pure repository-analysis service."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from chareco.core.models import AnalysisOptions
from chareco.core.service import AnalysisCancelled, run_analysis


logger = logging.getLogger(__name__)


class AnalysisThread(QThread):
    """One cancellable, self-contained analysis job."""

    progress_signal = pyqtSignal(str, int)
    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)
    cancelled_signal = pyqtSignal()

    def __init__(self, options: AnalysisOptions, pat: str | None = None) -> None:
        super().__init__()
        self.options = options
        self._pat = pat or None

    def request_cancel(self) -> None:
        self.requestInterruption()

    def run(self) -> None:
        try:
            result = run_analysis(
                self.options,
                pat=self._pat,
                progress=self.progress_signal.emit,
                is_cancelled=self.isInterruptionRequested,
            )
        except AnalysisCancelled:
            self.cancelled_signal.emit()
        except Exception as error:
            logger.exception("Analysis failed")
            self.error_signal.emit(str(error))
        else:
            self.finished_signal.emit(result)
        finally:
            self._pat = None
