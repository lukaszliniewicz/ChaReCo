from __future__ import annotations

import unittest

from chareco.core.search import SearchWorker


class SearchWorkerTests(unittest.TestCase):
    def test_invalid_regex_still_finishes(self) -> None:
        worker = SearchWorker(7, [("sample.py", "content")], "[", use_regex=True)
        events = []
        worker.signals.error.connect(lambda job_id, error: events.append(("error", job_id, error)))
        worker.signals.finished.connect(lambda job_id: events.append(("finished", job_id)))

        worker.run()

        self.assertEqual(events[0][0:2], ("error", 7))
        self.assertEqual(events[-1], ("finished", 7))

    def test_whole_word_search_does_not_match_substrings(self) -> None:
        worker = SearchWorker(
            3,
            [("sample.py", "cat scatter cat")],
            "cat",
            whole_word=True,
        )
        results = []
        worker.signals.result.connect(lambda _job_id, value: results.extend(value))

        worker.run()

        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0][1]), 2)


if __name__ == "__main__":
    unittest.main()
