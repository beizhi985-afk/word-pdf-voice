from __future__ import annotations

import gc
import os
import tempfile
import time
import unittest
import weakref
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QEventLoop, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication, QPushButton

from word_voice.app import WordVoiceWindow
from word_voice.models import ExtractedDocument, VocabularyEntry
from word_voice.storage import VocabularyStore


class FinishingWorker(QObject):
    finished = Signal()

    @Slot()
    def run(self) -> None:
        QThread.msleep(100)
        self.finished.emit()


class WorkerLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_window_retains_worker_until_thread_finishes(self) -> None:
        window = WordVoiceWindow()
        worker = FinishingWorker()
        worker_reference = weakref.ref(worker)
        loop = QEventLoop()
        completed: list[bool] = []
        worker.finished.connect(lambda: completed.append(True))
        worker.finished.connect(loop.quit)
        window._start_worker(worker, worker.run, (worker.finished,))

        del worker
        gc.collect()
        self.assertIsNotNone(worker_reference())
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        self.assertEqual([True], completed)

        deadline = time.monotonic() + 1
        while window._threads and time.monotonic() < deadline:
            self.application.processEvents()
            time.sleep(0.01)
        self.assertFalse(window._threads)
        self.assertFalse(window._active_workers)
        window.close()

    def test_v021_controls_are_visible(self) -> None:
        window = WordVoiceWindow()
        labels = {button.text() for button in window.findChildren(QPushButton)}
        self.assertEqual("单词文档配音 v0.2.1", window.windowTitle())
        self.assertEqual("只看已有音频", window.audio_ready_only.text())
        self.assertEqual("af_sarah", window.voice.currentData())
        self.assertEqual("序号从小到大", window.sort_order.currentText())
        self.assertIn("打开音频文件夹", labels)
        self.assertIn("导出已有音频", labels)
        self.assertIn("导出全部 Anki", labels)
        window.close()

    def test_sequence_sort_uses_numbers_in_both_directions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VocabularyStore(Path(directory) / "test.sqlite3")
            entries = [
                VocabularyEntry(1, "one", "", "", 1),
                VocabularyEntry(10, "ten", "", "", 1),
                VocabularyEntry(2, "two", "", "", 1),
            ]
            store.import_document(ExtractedDocument(Path("sample.pdf"), "abc", 1, entries, []))
            window = WordVoiceWindow()
            window.store = store

            window.sort_order.setCurrentIndex(1)
            window.refresh_table()
            descending = [int(window.table.item(row, 0).text()) for row in range(3)]
            window.sort_order.setCurrentIndex(0)
            window.refresh_table()
            ascending = [int(window.table.item(row, 0).text()) for row in range(3)]

            self.assertEqual([10, 2, 1], descending)
            self.assertEqual([1, 2, 10], ascending)
            window.close()


if __name__ == "__main__":
    unittest.main()
