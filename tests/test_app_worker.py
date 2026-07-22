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
    ImportPreviewDialog,
    WordVoiceWindow,
    choose_rotating_value,
    import_custom_sticker,
    run_portable_extract_smoke,
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

    def test_v050_focus_layout_keeps_learning_controls_and_secondary_menus(self) -> None:
        window = WordVoiceWindow()
        labels = {button.text() for button in window.findChildren(QPushButton)}
        action_labels = {action.text() for action in window.more_menu.actions()}
        self.assertEqual("单词文档配音 v0.6.0", window.windowTitle())
        self.assertEqual("选择词汇", window.choose_button.text())
        self.assertEqual("还没有选择词汇", window.summary_label.text())
        self.assertEqual("已有音频", window.audio_ready_only.text())
        self.assertTrue(window.all_filter_button.isChecked())
        self.assertTrue(window.audio_ready_only.isCheckable())
        self.assertEqual("af_sarah", window.voice.currentData())
        self.assertEqual("序号从小到大", window.sort_order.currentText())
        self.assertIn(window.opening_phrase, HEALING_PHRASES)
        self.assertTrue(Path(window.sticker_name).is_file())
        self.assertEqual(5, len(BUILTIN_STICKERS))
        self.assertNotIn("crayon-shinnosuke.png", BUILTIN_STICKERS)
        self.assertFalse(window.windowIcon().isNull())
        self.assertFalse(window.sticker_label.pixmap().isNull())
        self.assertEqual(4, window.table.columnCount())
        self.assertEqual("序号", window.table.horizontalHeaderItem(0).text())
        self.assertEqual("中文释义", window.table.horizontalHeaderItem(3).text())
        self.assertIn("▶", labels)
        self.assertIn("认识", labels)
        self.assertIn("模糊", labels)
        self.assertIn("不认识", labels)
        self.assertEqual("⚙  学习设置", window.learning_settings_button.text())
        self.assertIn("音频工具", action_labels)
        self.assertIn("导出 Anki", action_labels)
        self.assertIn("备份与恢复", action_labels)
        self.assertEqual(5, window.repeat_count.count())
        self.assertEqual("只听英文", window.play_mode.currentText())
        self.assertFalse(window.cancel_analysis_button.isVisible())
        window.close()

    def test_layout_results_require_confirmation_before_import(self) -> None:
        document = ExtractedDocument(
            Path("complex.pdf"),
            "hash",
            2,
            [
                VocabularyEntry(
                    1,
                    "take notes",
                    "",
                    "做笔记",
                    2,
                    confidence=0.92,
                    extraction_method="layout",
                ),
                VocabularyEntry(
                    2,
                    "uncertain phrase",
                    "",
                    "待检查",
                    2,
                    confidence=0.64,
                    extraction_method="layout",
                ),
            ],
            [],
            extraction_method="layout",
            requires_review=True,
        )
        dialog = ImportPreviewDialog(document)

        dialog._keep_high_confidence()
        reviewed = dialog.reviewed_document()

        self.assertEqual(["take notes"], [entry.word for entry in reviewed.entries])
        self.assertEqual([1], [entry.sequence for entry in reviewed.entries])
        self.assertFalse(reviewed.requires_review)
        dialog.close()

    def test_portable_extract_smoke_writes_machine_readable_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            document = ExtractedDocument(
                Path("complex.pdf"),
                "hash",
                2,
                [VocabularyEntry(1, "word", "", "释义", 2)],
                [],
                extraction_method="layout",
            )
            with patch("word_voice.app.extract_vocabulary_pdf", return_value=document):
                result = run_portable_extract_smoke(Path("complex.pdf"), output)

            self.assertEqual(0, result)
            self.assertTrue(output.is_file())
            self.assertIn('"extraction_method": "layout"', output.read_text(encoding="utf-8"))

    def test_cancelled_import_restores_existing_project_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VocabularyStore(Path(directory) / "project.sqlite3")
            document = ExtractedDocument(
                Path("saved.pdf"),
                "saved",
                1,
                [VocabularyEntry(1, "saved", "", "已保存", 1)],
                [],
            )
            store.import_document(document)
            window = WordVoiceWindow()
            window.document = document
            window.store = store
            window.pdf_path = Path("new.pdf")
            window.summary_label.setText("new.pdf")

            window._on_analysis_cancelled("已取消文档分析。")

            self.assertEqual(Path("saved.pdf"), window.pdf_path)
            self.assertEqual("saved · 1 词", window.summary_label.text())
            self.assertEqual("已取消文档分析。", window.status_label.text())
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

            self.assertEqual("no-longer-present · 1 词", window.summary_label.text())
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
                window.table.horizontalHeader().sectionSize(column) for column in range(4)
            )
            window.sort_order.setCurrentIndex(0)
            window.refresh_table()
            ascending = [int(window.table.item(row, 0).text()) for row in range(3)]
            ascending_widths = tuple(
                window.table.horizontalHeader().sectionSize(column) for column in range(4)
            )

            self.assertEqual([10, 2, 1], descending)
            self.assertEqual([1, 2, 10], ascending)
            self.assertEqual(descending_widths, ascending_widths)
            window.close()

    def test_v050_player_tracks_selected_word_and_focus_filter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VocabularyStore(Path(directory) / "test.sqlite3")
            entries = [
                VocabularyEntry(1, "known", "nəʊn", "认识", 1),
                VocabularyEntry(2, "unsure", "ʌnˈʃʊə", "模糊", 1),
                VocabularyEntry(3, "unknown", "ʌnˈnəʊn", "不认识", 1),
            ]
            store.import_document(
                ExtractedDocument(Path("sample.pdf"), "abc", 1, entries, [])
            )
            store.set_learning_status(1, "known")
            store.set_learning_status(2, "unsure")
            store.set_learning_status(3, "unknown")
            window = WordVoiceWindow()
            window.store = store
            window.refresh_table()
            window.table.selectRow(1)
            window._update_player_entry()

            self.assertEqual("unsure", window.player_word.text())
            self.assertEqual("ʌnˈʃʊə", window.player_phonetic.text())
            self.assertEqual("模糊", window.player_meaning.text())
            window._set_learning_filter("focus")
            visible_sequences = [int(window.table.item(row, 0).text()) for row in range(window.table.rowCount())]
            self.assertEqual([2, 3], visible_sequences)
            self.assertTrue(window.focus_filter_button.isChecked())
            window.close()

    def test_v050_transport_controls_keep_focus_player_shape(self) -> None:
        window = WordVoiceWindow()

        self.assertEqual("continuousPlayButton", window.continuous_play_button.objectName())
        self.assertEqual((60, 60), (window.continuous_play_button.width(), window.continuous_play_button.height()))
        self.assertEqual("transport", window.previous_button.property("kind"))
        self.assertEqual("transport", window.next_button.property("kind"))
        self.assertEqual((44, 44), (window.previous_button.width(), window.previous_button.height()))
        self.assertEqual((44, 44), (window.next_button.width(), window.next_button.height()))
        window.close()


if __name__ == "__main__":
    unittest.main()
