from __future__ import annotations

import gc
import os
import time
import unittest
import weakref

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QEventLoop, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

from word_voice.app import WordVoiceWindow


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


if __name__ == "__main__":
    unittest.main()
