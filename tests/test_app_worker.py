from __future__ import annotations

import gc
import os
import tempfile
import threading
import time
import unittest
import weakref
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QEventLoop, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

from word_voice.app import (
    BUILTIN_STICKERS,
    HEALING_PHRASES,
    ContinuousPlaybackWorker,
    WordVoiceWindow,
    choose_rotating_value,
    import_custom_sticker,
)
from word_voice.models import ExtractedDocument, VocabularyEntry
from word_voice.storage import ProjectWorkspace, VocabularyStore, list_imported_projects


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

    def test_v040_learning_controls_and_assets_are_visible(self) -> None:
        window = WordVoiceWindow()
        labels = {button.text() for button in window.findChildren(QPushButton)}
        self.assertEqual("单词文档配音 v0.4.0", window.windowTitle())
        self.assertEqual("选择词汇", window.choose_button.text())
        self.assertEqual("还没有选择词汇 PDF", window.summary_label.text())
        self.assertEqual("只看已有音频", window.audio_ready_only.text())
        self.assertEqual("af_sarah", window.voice.currentData())
        self.assertEqual("序号从小到大", window.sort_order.currentText())
        self.assertIn(window.opening_phrase, HEALING_PHRASES)
        self.assertTrue(Path(window.sticker_name).is_file())
        self.assertEqual(5, len(BUILTIN_STICKERS))
        self.assertNotIn("crayon-shinnosuke.png", BUILTIN_STICKERS)
        self.assertFalse(window.windowIcon().isNull())
        self.assertEqual("换一句", window.phrase_button.text())
        self.assertFalse(window.sticker_label.pixmap().isNull())
        self.assertIn("打开音频文件夹", labels)
        self.assertIn("导出已有音频", labels)
        self.assertIn("导出全部 Anki", labels)
        self.assertIn("从所选开始", labels)
        self.assertIn("停止播放", labels)
        self.assertIn("认识", labels)
        self.assertIn("模糊", labels)
        self.assertIn("不认识", labels)
        self.assertIn("＋我的贴纸", labels)
        self.assertEqual(5, window.repeat_count.count())
        self.assertEqual("只听英文", window.play_mode.currentText())
        window.close()

    def test_continuous_worker_repeats_advances_and_reads_meaning(self) -> None:
        class FakeService:
            def ensure_audio(self, item):
                return Path(f"{item.sequence}.wav")

        entries = [
            VocabularyEntry(1, "one", "", "一", 1),
            VocabularyEntry(2, "two", "", "二", 1),
        ]
        played: list[str] = []
        spoken: list[str] = []
        current: list[tuple[int, int]] = []
        finished: list[tuple[int, int, bool]] = []
        worker = ContinuousPlaybackWorker(
            FakeService(),
            entries,
            repeat_count=3,
            pause_seconds=0,
            include_meaning=True,
            stop_event=threading.Event(),
            audio_player=lambda path: played.append(path.name),
            meaning_speaker=lambda meaning, _stop: spoken.append(meaning) or True,
        )
        worker.current.connect(lambda sequence, _position, _total, repeat, _word: current.append((sequence, repeat)))
        worker.finished.connect(lambda done, failed, stopped: finished.append((done, failed, stopped)))

        worker.run()

        self.assertEqual(["1.wav"] * 3 + ["2.wav"] * 3, played)
        self.assertEqual(["一", "二"], spoken)
        self.assertEqual([(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)], current)
        self.assertEqual([(2, 0, False)], finished)

    def test_user_can_import_a_custom_sticker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "my-sticker.png"
            image = QImage(24, 24, QImage.Format_ARGB32)
            image.fill(0xFFFFCCAA)
            self.assertTrue(image.save(str(source)))
            custom_root = root / "custom"
            with patch("word_voice.app.custom_stickers_root", return_value=custom_root):
                custom_root.mkdir()
                imported = import_custom_sticker(source)
            self.assertTrue(imported.is_file())
            self.assertEqual(custom_root, imported.parent)

    def test_no_imported_project_prompts_for_a_new_pdf_without_starting_analysis(self) -> None:
        window = WordVoiceWindow()
        with (
            patch("word_voice.app.list_imported_projects", return_value=[]),
            patch("word_voice.app.list_database_backups", return_value=[]),
            patch.object(QMessageBox, "information") as information,
            patch.object(QFileDialog, "getOpenFileName", return_value=("", "")) as picker,
        ):
            window.choose_vocabulary()

        information.assert_called_once()
        picker.assert_called_once()
        self.assertIsNone(window.document)
        self.assertIsNone(window.store)
        window.close()

    def test_existing_import_can_be_selected_without_reanalyzing_the_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            projects_root = Path(directory) / "projects"
            workspace = ProjectWorkspace.create(projects_root / "saved")
            store = VocabularyStore(workspace.database_path)
            store.import_document(
                ExtractedDocument(
                    Path(directory) / "no-longer-present.pdf",
                    "cached",
                    1,
                    [VocabularyEntry(1, "cached", "", "已缓存", 1)],
                    [],
                )
            )
            project = list_imported_projects(projects_root)[0]
            window = WordVoiceWindow()

            window.load_imported_project(project)

            self.assertEqual("no-longer-present.pdf", window.summary_label.text())
            self.assertEqual(1, window.table.rowCount())
            self.assertEqual("cached", window.table.item(0, 1).text())
            self.assertEqual("已载入已导入的词汇", window.status_label.text())
            window.close()

    def test_rotating_value_avoids_immediate_repeat(self) -> None:
        selected = choose_rotating_value(("first", "second"), "first", lambda values: values[0])
        self.assertEqual("second", selected)

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
            descending_widths = tuple(
                window.table.horizontalHeader().sectionSize(column) for column in range(6)
            )
            window.sort_order.setCurrentIndex(0)
            window.refresh_table()
            ascending = [int(window.table.item(row, 0).text()) for row in range(3)]
            ascending_widths = tuple(
                window.table.horizontalHeader().sectionSize(column) for column in range(6)
            )

            self.assertEqual([10, 2, 1], descending)
            self.assertEqual([1, 2, 10], ascending)
            self.assertEqual(descending_widths, ascending_widths)
            window.close()


if __name__ == "__main__":
    unittest.main()
