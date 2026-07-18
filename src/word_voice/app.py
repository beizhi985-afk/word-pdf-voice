from __future__ import annotations

import os
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .anki_export import AnkiExportError, export_anki_deck
from .extractor import extract_vocabulary_pdf
from .models import VocabularyEntry
from .samples import select_pronunciation_samples
from .storage import ProjectWorkspace, VocabularyStore, prepare_default_workspace
from .tts import AudioService, KokoroOnnxEngine, TtsConfig


APP_STYLE = """
QWidget { background: #eef2f7; color: #17233c; font-family: "Microsoft YaHei UI"; font-size: 13px; }
QFrame#card { background: white; border: 1px solid #dbe3ee; border-radius: 10px; }
QLabel#title { font-size: 27px; font-weight: 700; }
QLabel#subtitle, QLabel#muted { color: #66758b; }
QPushButton { background: white; border: 1px solid #c8d2e1; border-radius: 7px; padding: 8px 14px; }
QPushButton:hover { background: #f7f9fc; border-color: #9fb0c7; }
QPushButton#primary { background: #2457c5; color: white; border: none; font-weight: 700; }
QPushButton#primary:hover { background: #173f96; }
QLineEdit, QComboBox, QDoubleSpinBox, QTextEdit { background: white; border: 1px solid #c8d2e1;
    border-radius: 6px; padding: 6px; }
QTableWidget { background: white; alternate-background-color: #f8fafc; border: none;
    gridline-color: #e5eaf1; selection-background-color: #dce8ff; selection-color: #17233c; }
QHeaderView::section { background: #f1f5f9; border: none; border-bottom: 1px solid #dbe3ee;
    padding: 8px; font-weight: 700; }
QProgressBar { background: #dbe3ee; border: none; border-radius: 5px; height: 10px; text-align: center; }
QProgressBar::chunk { background: #2457c5; border-radius: 5px; }
"""


def bundled_model_paths() -> tuple[Path, Path] | None:
    candidates_root: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates_root.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
        candidates_root.append(Path(sys.executable).resolve().parent)
    candidates_root.append(Path(__file__).resolve().parents[2])
    model_dir = next(
        (root / "models" for root in candidates_root if (root / "models").is_dir()),
        candidates_root[0] / "models",
    )
    model = next(
        (
            path
            for path in (
                model_dir / "kokoro-v1.0.int8.onnx",
                model_dir / "kokoro-v1.0.onnx",
            )
            if path.is_file()
        ),
        None,
    )
    voices = model_dir / "voices-v1.0.bin"
    if not model or not voices.is_file():
        return None
    return model, voices


def run_portable_tts_smoke(
    output_path: Path,
    voice: str = "af_sarah",
    speed: float = 0.9,
) -> int:
    """Generate one real WAV so a packaged build can prove its runtime is complete."""
    error_path = output_path.with_suffix(output_path.suffix + ".error.txt")
    try:
        paths = bundled_model_paths()
        if not paths:
            raise RuntimeError("便携版缺少 Kokoro 模型或声音文件")
        language = "en-gb" if voice.startswith("b") else "en-us"
        config = TtsConfig(paths[0], paths[1], voice, speed, language)
        entry = VocabularyEntry(1, "alternative", "", "便携版发音测试", 1)
        KokoroOnnxEngine(config).synthesize(entry, output_path)
        if error_path.is_file():
            error_path.unlink()
        return 0
    except Exception:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        error_path.write_text(traceback.format_exc(), encoding="utf-8")
        return 1


class ExtractionWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object, object, object, object)
    error = Signal(str)

    def __init__(self, pdf_path: Path):
        super().__init__()
        self.pdf_path = pdf_path

    @Slot()
    def run(self) -> None:
        try:
            document = extract_vocabulary_pdf(
                self.pdf_path,
                progress=lambda current, total: self.progress.emit(
                    current, total, f"正在分析第 {current}/{total} 页"
                ),
            )
            self.progress.emit(0, 0, "正在准备 v0.2 项目数据...")
            workspace, migration = prepare_default_workspace(self.pdf_path)
            store = VocabularyStore(workspace.database_path)
            store.import_document(document)
            self.finished.emit(document, workspace, store, migration)
        except Exception as exc:
            self.error.emit(f"文档分析失败：{exc}")


class GenerationWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(int, int)
    error = Signal(str)

    def __init__(
        self,
        service: AudioService,
        entries: list[VocabularyEntry],
        stop_event: threading.Event,
    ):
        super().__init__()
        self.service = service
        self.entries = entries
        self.stop_event = stop_event

    @Slot()
    def run(self) -> None:
        try:
            completed, failed = self.service.generate_many(
                self.entries,
                progress=lambda index, total, entry, state: self.progress.emit(
                    index,
                    total,
                    f"{entry.word}：{'完成' if state == 'ready' else '失败'}",
                ),
                should_stop=self.stop_event.is_set,
            )
            self.finished.emit(completed, failed)
        except Exception as exc:
            self.error.emit(str(exc))


class PlayWorker(QObject):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, service: AudioService, entry: VocabularyEntry):
        super().__init__()
        self.service = service
        self.entry = entry

    @Slot()
    def run(self) -> None:
        try:
            path = self.service.ensure_audio(self.entry)
            if not hasattr(sys, "getwindowsversion"):
                raise RuntimeError("当前播放入口仅支持 Windows")
            import winsound

            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            self.finished.emit(f"正在播放：{self.entry.word}")
        except Exception as exc:
            self.error.emit(str(exc))


class EntryEditDialog(QDialog):
    def __init__(self, entry: VocabularyEntry, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"编辑词条 {entry.sequence}")
        self.resize(620, 360)
        layout = QFormLayout(self)
        self.word = QLineEdit(entry.word)
        self.phonetic = QLineEdit(entry.phonetic)
        self.meaning = QTextEdit(entry.meaning)
        self.override = QLineEdit(entry.pronunciation_override)
        self.override.setPlaceholderText("可选：Kokoro 音素；不了解时留空")
        layout.addRow("单词", self.word)
        layout.addRow("注音", self.phonetic)
        layout.addRow("释义", self.meaning)
        layout.addRow("发音覆盖", self.override)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)


class WordVoiceWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"单词文档配音 v{__version__}")
        self.resize(1180, 780)
        self.setMinimumSize(980, 640)
        self.pdf_path: Path | None = None
        self.document = None
        self.workspace: ProjectWorkspace | None = None
        self.store: VocabularyStore | None = None
        self.stop_event = threading.Event()
        self._threads: list[QThread] = []
        self._active_workers: dict[QThread, QObject] = {}
        self._build_ui()

    def _card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        return frame

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("单词文档配音")
        title.setObjectName("title")
        subtitle = QLabel("英文词汇 PDF → 逐词播放 → Anki")
        subtitle.setObjectName("subtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        header.addStretch()
        self.choose_button = QPushButton("选择 PDF")
        self.choose_button.setObjectName("primary")
        self.choose_button.clicked.connect(self.choose_pdf)
        header.addWidget(self.choose_button)
        root.addLayout(header)

        summary_card = self._card()
        summary_layout = QVBoxLayout(summary_card)
        summary_title = QLabel("当前文档")
        summary_title.setFont(QFont("Microsoft YaHei UI", 11, QFont.Bold))
        self.summary_label = QLabel("尚未导入文档")
        self.summary_label.setObjectName("muted")
        summary_layout.addWidget(summary_title)
        summary_layout.addWidget(self.summary_label)
        root.addWidget(summary_card)

        toolbar_card = self._card()
        toolbar = QHBoxLayout(toolbar_card)
        toolbar.addWidget(QLabel("搜索"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("单词、注音或释义")
        self.search.setMaximumWidth(280)
        self.search.textChanged.connect(self.refresh_table)
        toolbar.addWidget(self.search)
        self.issues_only = QCheckBox("只看异常")
        self.issues_only.toggled.connect(self.refresh_table)
        toolbar.addWidget(self.issues_only)
        self.audio_ready_only = QCheckBox("只看已有音频")
        self.audio_ready_only.toggled.connect(self.refresh_table)
        toolbar.addWidget(self.audio_ready_only)
        toolbar.addSpacing(10)
        toolbar.addWidget(QLabel("声音"))
        self.voice = QComboBox()
        for label, voice_id in (
            ("美式女声 · Sarah", "af_sarah"),
            ("美式女声 · Heart", "af_heart"),
            ("美式男声 · Adam", "am_adam"),
            ("英式女声 · Emma", "bf_emma"),
        ):
            self.voice.addItem(label, voice_id)
        self.voice.setToolTip("更换声音后，下次试听或生成会重新制作对应音频")
        toolbar.addWidget(self.voice)
        toolbar.addWidget(QLabel("语速"))
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.6, 1.3)
        self.speed.setSingleStep(0.1)
        self.speed.setDecimals(2)
        self.speed.setSuffix(" 倍")
        self.speed.setValue(0.9)
        self.speed.setToolTip("改变语速后，下次试听或生成会重新制作对应音频")
        toolbar.addWidget(self.speed)
        toolbar.addSpacing(10)
        toolbar.addWidget(QLabel("排序"))
        self.sort_order = QComboBox()
        self.sort_order.addItem("序号从小到大", "asc")
        self.sort_order.addItem("序号从大到小", "desc")
        toolbar.addWidget(self.sort_order)
        toolbar.addStretch()
        root.addWidget(toolbar_card)

        table_card = self._card()
        table_layout = QVBoxLayout(table_card)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("序号", "单词", "注音", "释义", "页码", "状态"))
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        header_view = self.table.horizontalHeader()
        for column in (0, 1, 2, 4, 5):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.doubleClicked.connect(self.play_selected)
        table_layout.addWidget(self.table)
        root.addWidget(table_card, 1)

        actions = QHBoxLayout()
        for label, handler in (
            ("试听所选", self.play_selected),
            ("编辑词条", self.edit_selected),
            ("生成 30 词样本", self.generate_samples),
            ("生成全部", self.generate_all),
            ("停止", self.stop_generation),
            ("打开音频文件夹", self.open_audio_folder),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch()
        ready_export_button = QPushButton("导出已有音频")
        ready_export_button.clicked.connect(self.export_ready_anki)
        actions.addWidget(ready_export_button)
        export_button = QPushButton("导出全部 Anki")
        export_button.setObjectName("primary")
        export_button.clicked.connect(self.export_anki)
        actions.addWidget(export_button)
        root.addLayout(actions)

        footer = self._card()
        footer_layout = QHBoxLayout(footer)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.status_label = QLabel("请选择目标 PDF")
        self.status_label.setObjectName("muted")
        footer_layout.addWidget(self.progress, 1)
        footer_layout.addWidget(self.status_label)
        root.addWidget(footer)
        self.voice.currentIndexChanged.connect(self._on_tts_settings_changed)
        self.speed.valueChanged.connect(self._on_tts_settings_changed)
        self.sort_order.currentIndexChanged.connect(self.refresh_table)

    def _start_worker(self, worker: QObject, run_signal, finish_signals: tuple) -> None:
        thread = QThread(self)
        worker.moveToThread(thread)
        # Qt 的信号连接不会可靠地替 Python 侧保存工作对象。若这里只保留
        # QThread，打包后的 worker 可能在 thread.started 触发前被垃圾回收。
        self._active_workers[thread] = worker
        thread.started.connect(run_signal)
        for signal in finish_signals:
            signal.connect(thread.quit)
            signal.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._release_worker(thread))
        self._threads.append(thread)
        thread.start()

    def _release_worker(self, thread: QThread) -> None:
        self._active_workers.pop(thread, None)
        if thread in self._threads:
            self._threads.remove(thread)

    @Slot()
    def choose_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择英语词汇 PDF", "", "PDF (*.pdf)")
        if not path:
            return
        self.load_pdf(Path(path))

    def load_pdf(self, pdf_path: Path) -> None:
        if not pdf_path.is_file():
            self._show_error(f"找不到 PDF：{pdf_path}")
            return
        self.pdf_path = pdf_path
        self.choose_button.setEnabled(False)
        self.summary_label.setText(f"正在分析：{pdf_path.name}")
        self.status_label.setText("正在分析文档...")
        self.progress.setValue(0)
        worker = ExtractionWorker(self.pdf_path)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_document)
        worker.error.connect(self._on_extraction_error)
        self._start_worker(worker, worker.run, (worker.finished, worker.error))

    @Slot(int, int, str)
    def _on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.setValue(int(current / total * 100) if total else 0)
        self.status_label.setText(message)

    @Slot(object, object, object, object)
    def _on_document(self, document, workspace, store, migration) -> None:
        self.document = document
        self.workspace = workspace
        self.store = store
        self.choose_button.setEnabled(True)
        self._refresh_summary()
        if migration.performed:
            self.status_label.setText(f"已从 v0.1 复制 {migration.copied_audio} 条音频到 v0.2")
        else:
            self.status_label.setText("文档分析完成")
        self.progress.setValue(100)
        self.refresh_table()

    def _refresh_summary(self) -> None:
        if not self.document or not self.store:
            return
        counts = self.store.audio_counts()
        self.summary_label.setText(
            f"{self.document.source_path.name} · {self.document.page_count} 页 · "
            f"{len(self.document.entries)} 条 · 异常 {self.document.flagged_count} 条 · "
            f"已有音频 {counts['ready']} 条"
        )

    @Slot(str)
    def _on_extraction_error(self, message: str) -> None:
        self.choose_button.setEnabled(True)
        self.progress.setValue(0)
        self._show_error(message)

    @Slot()
    def refresh_table(self) -> None:
        self.table.setRowCount(0)
        if not self.store:
            return
        entries = self.store.list_entries(
            search=self.search.text().strip(),
            issues_only=self.issues_only.isChecked(),
            audio_ready_only=self.audio_ready_only.isChecked(),
        )
        statuses = self.store.audio_status_map()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(entries))
        for row_index, entry in enumerate(entries):
            state = {"ready": "已有音频", "failed": "生成失败"}.get(statuses.get(entry.sequence), "")
            status = entry.flag_text or state
            values = (entry.sequence, entry.word, entry.phonetic, entry.meaning, entry.page, status)
            for column, value in enumerate(values):
                item = QTableWidgetItem()
                if column in (0, 4):
                    item.setData(Qt.DisplayRole, int(value))
                else:
                    item.setText(str(value))
                if column in (0, 4):
                    item.setTextAlignment(Qt.AlignCenter)
                if entry.has_issue:
                    item.setBackground(QColor("#fff7ed"))
                self.table.setItem(row_index, column, item)
        self.table.setSortingEnabled(True)
        order = Qt.DescendingOrder if self.sort_order.currentData() == "desc" else Qt.AscendingOrder
        self.table.sortItems(0, order)

    @Slot()
    def _on_tts_settings_changed(self) -> None:
        self.status_label.setText("声音或语速已更改；下次试听或生成时会重新制作对应音频")

    def selected_entry(self) -> VocabularyEntry | None:
        if not self.store or self.table.currentRow() < 0:
            QMessageBox.information(self, "请选择词条", "请先在表格中选择一个单词。")
            return None
        sequence_item = self.table.item(self.table.currentRow(), 0)
        return self.store.get_entry(int(sequence_item.text())) if sequence_item else None

    def _model_paths(self) -> tuple[Path, Path] | None:
        paths = bundled_model_paths()
        if not paths:
            QMessageBox.warning(self, "尚未准备语音模型", "请先运行 scripts/setup_models.py。")
            return None
        return paths

    def _audio_service(self) -> AudioService | None:
        if not self.store or not self.workspace:
            QMessageBox.information(self, "请先选择 PDF", "请先导入目标 PDF。")
            return None
        paths = self._model_paths()
        if not paths:
            return None
        voice_id = str(self.voice.currentData())
        language = "en-gb" if voice_id.startswith("b") else "en-us"
        config = TtsConfig(paths[0], paths[1], voice_id, self.speed.value(), language)
        return AudioService(self.store, self.workspace.audio_dir, KokoroOnnxEngine(config))

    @Slot()
    def play_selected(self) -> None:
        entry = self.selected_entry()
        service = self._audio_service()
        if not entry or not service:
            return
        self.status_label.setText(f"正在准备 {entry.word}...")
        worker = PlayWorker(service, entry)
        worker.finished.connect(self._on_played)
        worker.error.connect(self._show_error)
        self._start_worker(worker, worker.run, (worker.finished, worker.error))

    @Slot(str)
    def _on_played(self, message: str) -> None:
        self.status_label.setText(message)
        self._refresh_summary()
        self.refresh_table()

    @Slot()
    def edit_selected(self) -> None:
        entry = self.selected_entry()
        if not entry or not self.store:
            return
        dialog = EntryEditDialog(entry, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.store.update_entry(
            entry.sequence,
            dialog.word.text(),
            dialog.phonetic.text(),
            dialog.meaning.toPlainText(),
            dialog.override.text(),
        )
        self.refresh_table()
        self.status_label.setText(f"已保存序号 {entry.sequence}")

    @Slot()
    def generate_samples(self) -> None:
        if not self.store:
            QMessageBox.information(self, "请先选择 PDF", "请先导入目标 PDF。")
            return
        self._start_generation(select_pronunciation_samples(self.store.list_entries(), 30))

    @Slot()
    def generate_all(self) -> None:
        if not self.store:
            QMessageBox.information(self, "请先选择 PDF", "请先导入目标 PDF。")
            return
        answer = QMessageBox.question(self, "生成全部", "将为全部词条生成本地音频，是否继续？")
        if answer != QMessageBox.Yes:
            return
        self._start_generation(self.store.list_entries())

    def _start_generation(self, entries: list[VocabularyEntry]) -> None:
        service = self._audio_service()
        if not service:
            return
        self.stop_event.clear()
        self.progress.setValue(0)
        worker = GenerationWorker(service, entries, self.stop_event)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_generation_finished)
        worker.error.connect(self._show_error)
        self._start_worker(worker, worker.run, (worker.finished, worker.error))

    @Slot(int, int)
    def _on_generation_finished(self, completed: int, failed: int) -> None:
        self.status_label.setText(f"生成结束：完成 {completed}，失败 {failed}")
        self._refresh_summary()
        self.refresh_table()

    @Slot()
    def stop_generation(self) -> None:
        self.stop_event.set()
        self.status_label.setText("将在当前单词完成后停止")

    @Slot()
    def open_audio_folder(self) -> None:
        if not self.workspace:
            QMessageBox.information(self, "请先选择 PDF", "请先导入目标 PDF。")
            return
        try:
            os.startfile(self.workspace.audio_dir)
        except OSError as exc:
            self._show_error(f"无法打开音频文件夹：{exc}")

    @Slot()
    def export_ready_anki(self) -> None:
        self._export_anki(ready_only=True)

    @Slot()
    def export_anki(self) -> None:
        self._export_anki(ready_only=False)

    def _export_anki(self, ready_only: bool) -> None:
        if not self.store:
            QMessageBox.information(self, "请先选择 PDF", "请先导入目标 PDF。")
            return
        ready_count = self.store.audio_counts()["ready"]
        if ready_only and not ready_count:
            QMessageBox.information(self, "还没有音频", "请先生成或试听至少一个单词。")
            return
        default_name = (
            f"CET4-已有音频-{ready_count}.apkg" if ready_only else "CET4-4450.apkg"
        )
        output, _ = QFileDialog.getSaveFileName(
            self, "导出 Anki 卡组", default_name, "Anki 卡组 (*.apkg)"
        )
        if not output:
            return
        try:
            result = export_anki_deck(
                self.store.list_entries(),
                self.store,
                output,
                deck_name=(
                    "英语四级乱序词汇 · 已生成音频"
                    if ready_only
                    else "英语四级乱序词汇 4450"
                ),
                ready_only=ready_only,
            )
            QMessageBox.information(
                self,
                "导出完成",
                f"已导出 {result.exported_count} 条词卡：\n{result.path}",
            )
            self.status_label.setText(f"已导出 {result.exported_count} 条：{result.path}")
        except AnkiExportError as exc:
            QMessageBox.warning(self, "暂时不能导出", str(exc))
        except Exception as exc:
            self._show_error(str(exc))

    @Slot(str)
    def _show_error(self, message: str) -> None:
        self.status_label.setText(message)
        QMessageBox.critical(self, "操作失败", message)


def main() -> int:
    arguments = sys.argv[1:]
    if "--smoke-tts" in arguments:
        argument_index = arguments.index("--smoke-tts")
        if argument_index + 1 >= len(arguments):
            return 2
        voice = arguments[argument_index + 2] if argument_index + 2 < len(arguments) else "af_sarah"
        try:
            speed = float(arguments[argument_index + 3]) if argument_index + 3 < len(arguments) else 0.9
        except ValueError:
            return 2
        return run_portable_tts_smoke(Path(arguments[argument_index + 1]), voice, speed)
    application = QApplication.instance() or QApplication(sys.argv)
    application.setStyleSheet(APP_STYLE)
    window = WordVoiceWindow()
    window.show()
    pdf_argument = next(
        (Path(argument) for argument in sys.argv[1:] if argument.lower().endswith(".pdf")),
        None,
    )
    if pdf_argument is not None:
        QTimer.singleShot(0, lambda path=pdf_argument: window.load_pdf(path))
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
