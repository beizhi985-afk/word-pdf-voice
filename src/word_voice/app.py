from __future__ import annotations

import os
import random
import re
import shutil
import sys
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap
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
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
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
from .speech import chinese_voice_available, speak_chinese
from .storage import (
    DatabaseBackup,
    ImportedProject,
    ProjectWorkspace,
    VocabularyStore,
    create_database_backup,
    custom_stickers_root,
    list_database_backups,
    list_imported_projects,
    open_imported_project,
    prepare_default_workspace,
    restore_database_backup,
)
from .tts import AudioService, KokoroOnnxEngine, TtsConfig


APP_STYLE = """
QWidget { color: #4b4052; font-family: "Microsoft YaHei UI"; font-size: 13px; }
QWidget#page { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
    stop:0 #fff8f2, stop:0.48 #fffdf9, stop:1 #f8f1ff); }
QLabel { background: transparent; }
QFrame#heroCard { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 #fff0e7, stop:0.55 #fff7ed, stop:1 #f2eaff);
    border: 1px solid #efd9d5; border-radius: 24px; }
QFrame#card, QFrame#summaryCard, QFrame#tableCard, QFrame#statusCard {
    background: rgba(255, 255, 255, 238); border: 1px solid #eadfe7; border-radius: 17px; }
QFrame#phraseBubble { background: rgba(255, 255, 255, 205); border: 1px solid #f2d8cf;
    border-radius: 13px; }
QFrame#metricCoral { background: #fff0e8; border: 1px solid #f6d4c5; border-radius: 12px; }
QFrame#metricLilac { background: #f4eeff; border: 1px solid #ddd0f4; border-radius: 12px; }
QFrame#metricMint { background: #ecf8f1; border: 1px solid #cce9d9; border-radius: 12px; }
QFrame#metricSun { background: #fff8df; border: 1px solid #f1dfaa; border-radius: 12px; }
QLabel#eyebrow { color: #a65f78; background: #fff9f5; border: 1px solid #f1d8d0;
    border-radius: 10px; padding: 4px 10px; font-size: 11px; font-weight: 700; }
QLabel#heroTitle { color: #493949; font-size: 28px; font-weight: 800; }
QLabel#heroSubtitle { color: #806e7c; font-size: 13px; }
QLabel#phraseMark { color: #e88379; font-size: 18px; font-weight: 800; }
QLabel#phraseText { color: #6d5668; font-size: 13px; font-weight: 600; }
QLabel#sectionTitle { color: #574657; font-size: 15px; font-weight: 800; }
QLabel#documentTitle { color: #514351; font-size: 14px; font-weight: 700; }
QLabel#muted, QLabel#documentMeta, QLabel#tableCount { color: #8a7887; }
QLabel#metricValue { color: #4f414f; font-size: 18px; font-weight: 800; }
QLabel#metricLabel { color: #8b7987; font-size: 11px; }
QPushButton { background: #fffdfc; border: 1px solid #dfd0d9; border-radius: 10px;
    padding: 8px 13px; font-weight: 600; }
QPushButton:hover { background: #fff4ef; border-color: #d8aeb8; }
QPushButton:pressed { background: #f8e8e4; }
QPushButton:disabled { color: #b8aeb5; background: #f5f1f3; border-color: #e8e1e5; }
QPushButton[kind="primary"] { color: white; background: #e9837e; border: none; font-weight: 800; }
QPushButton[kind="primary"]:hover { background: #d97170; }
QPushButton[kind="lavender"] { color: #654f83; background: #f1e9ff; border-color: #d7c6ef; }
QPushButton[kind="lavender"]:hover { background: #e8dcfa; }
QPushButton[kind="mint"] { color: #46735f; background: #eaf7ef; border-color: #c6e4d2; }
QPushButton[kind="sun"] { color: #826a32; background: #fff6d9; border-color: #ecd998; }
QPushButton[kind="ghost"] { color: #a16f81; background: transparent; border: none; padding: 4px 7px; }
QLineEdit, QComboBox, QDoubleSpinBox, QTextEdit { background: #fffdfc; border: 1px solid #dfd1da;
    border-radius: 9px; padding: 7px 9px; selection-background-color: #f4c6c0; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QTextEdit:focus { border: 1px solid #dc908f; }
QCheckBox { spacing: 7px; color: #6d5e6b; }
QListWidget { background: #fffdfc; border: 1px solid #eadde5; border-radius: 12px; outline: none; }
QListWidget::item { padding: 11px 12px; border-bottom: 1px solid #f0e7ec; }
QListWidget::item:selected { color: #493d49; background: #ffe9e2; }
QTableWidget { background: #fffefd; alternate-background-color: #fffaf7; border: none;
    gridline-color: #f0e7ec; selection-background-color: #ffe9e2; selection-color: #493d49; }
QHeaderView::section { color: #675568; background: #f8eff5; border: none;
    border-bottom: 1px solid #e7d9e2; padding: 9px; font-weight: 800; }
QProgressBar { background: #eee5eb; border: none; border-radius: 5px; height: 9px; text-align: center; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 #ee978c, stop:1 #b79add); border-radius: 5px; }
"""


HEALING_PHRASES = (
    "慢一点也没关系，你正在把陌生变成熟悉。",
    "今天记住一个词，也是在悄悄靠近更大的世界。",
    "每一次认真听读，都会在未来给你一个温柔的回声。",
    "不必一下子很厉害，保持前进就已经很了不起。",
    "把今天的小进步收好，它会在某天变成自信。",
    "学累了就休息一下，回来时我们继续并肩前进。",
    "你读过的每一个单词，都在为新的可能铺路。",
    "允许自己慢慢来，语言本来就是一场温柔的相遇。",
    "今天也给努力学习的自己一个小小的拥抱。",
    "听见一个词，理解一个词，世界就亮起一点点。",
    "不用和别人比，你只需要比昨天多会一点点。",
    "愿你在一个个单词里，遇见更辽阔的自己。",
)

BUILTIN_STICKERS = (
    "chibi-student.png",
    "cozy-cloud-cat.png",
    "moon-rabbit-study.png",
    "clever-fox-study.png",
    "sprout-robot-study.png",
)
UI_STICKERS = BUILTIN_STICKERS

LEARNING_LABELS = {
    "unrated": "未标记",
    "known": "认识",
    "unsure": "模糊",
    "unknown": "不认识",
}


def choose_rotating_value(
    values: tuple[str, ...],
    previous: str = "",
    chooser=None,
) -> str:
    candidates = tuple(value for value in values if value != previous) or values
    select = chooser or random.SystemRandom().choice
    return select(candidates)


def _resource_roots() -> list[Path]:
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
        roots.append(Path(sys.executable).resolve().parent)
    roots.append(Path(__file__).resolve().parents[2])
    return roots


def bundled_ui_asset_path(filename: str) -> Path | None:
    return next(
        (root / "assets" / "ui" / filename for root in _resource_roots() if (root / "assets" / "ui" / filename).is_file()),
        None,
    )


def available_sticker_paths() -> tuple[Path, ...]:
    builtins = tuple(
        path for name in BUILTIN_STICKERS if (path := bundled_ui_asset_path(name)) is not None
    )
    custom_root = custom_stickers_root()
    try:
        custom = tuple(
            sorted(
                (
                    path
                    for path in custom_root.iterdir()
                    if path.is_file()
                    and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}
                ),
                key=lambda path: path.name.casefold(),
            )
        ) if custom_root.is_dir() else ()
    except OSError:
        custom = ()
    return builtins + custom


def import_custom_sticker(source: str | Path) -> Path:
    source_path = Path(source).expanduser().resolve()
    image = QImage(str(source_path))
    if image.isNull():
        raise ValueError("所选文件不是可以读取的图片")
    root = custom_stickers_root()
    root.mkdir(parents=True, exist_ok=True)
    safe_stem = re.sub(r"[^0-9a-zA-Z\u3400-\u9fff-]+", "-", source_path.stem).strip("-")
    safe_stem = safe_stem[:60] or "custom-sticker"
    suffix = source_path.suffix.casefold()
    destination = root / f"{safe_stem}{suffix}"
    number = 2
    while destination.exists() and destination.resolve() != source_path:
        destination = root / f"{safe_stem}-{number}{suffix}"
        number += 1
    if destination.resolve() != source_path:
        shutil.copy2(source_path, destination)
    return destination


def _play_wav_sync(path: Path) -> None:
    if not hasattr(sys, "getwindowsversion"):
        raise RuntimeError("当前播放入口仅支持 Windows")
    import winsound

    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_SYNC)


def _stop_windows_sound() -> None:
    if not hasattr(sys, "getwindowsversion"):
        return
    import winsound

    try:
        winsound.PlaySound(None, winsound.SND_PURGE)
    except RuntimeError:
        winsound.PlaySound(None, 0)


def bundled_model_paths() -> tuple[Path, Path] | None:
    candidates_root = _resource_roots()
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
            self.progress.emit(0, 0, "正在准备项目数据...")
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


class ContinuousPlaybackWorker(QObject):
    current = Signal(int, int, int, int, str)
    item_error = Signal(str)
    finished = Signal(int, int, bool)

    def __init__(
        self,
        service: AudioService,
        entries: list[VocabularyEntry],
        repeat_count: int,
        pause_seconds: float,
        include_meaning: bool,
        stop_event: threading.Event,
        audio_player=None,
        meaning_speaker=None,
    ):
        super().__init__()
        self.service = service
        self.entries = entries
        self.repeat_count = max(1, min(5, repeat_count))
        self.pause_seconds = max(0.0, pause_seconds)
        self.include_meaning = include_meaning
        self.stop_event = stop_event
        self.audio_player = audio_player or _play_wav_sync
        self.meaning_speaker = meaning_speaker or speak_chinese

    @Slot()
    def run(self) -> None:
        completed = 0
        failed = 0
        try:
            for position, entry in enumerate(self.entries, start=1):
                if self.stop_event.is_set():
                    break
                try:
                    path = self.service.ensure_audio(entry)
                    for repeat_index in range(1, self.repeat_count + 1):
                        if self.stop_event.is_set():
                            break
                        self.current.emit(
                            entry.sequence,
                            position,
                            len(self.entries),
                            repeat_index,
                            entry.word,
                        )
                        self.audio_player(path)
                    if self.stop_event.is_set():
                        break
                    if self.include_meaning:
                        self.meaning_speaker(entry.meaning, self.stop_event)
                    if self.stop_event.is_set():
                        break
                    completed += 1
                except Exception as exc:
                    failed += 1
                    self.item_error.emit(f"{entry.word}：{exc}")
                if position < len(self.entries) and self.pause_seconds:
                    if self.stop_event.wait(self.pause_seconds):
                        break
            self.finished.emit(completed, failed, self.stop_event.is_set())
        except Exception as exc:
            self.item_error.emit(str(exc))
            self.finished.emit(completed, failed + 1, self.stop_event.is_set())


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


class BackupDialog(QDialog):
    def __init__(
        self,
        project: ImportedProject | None,
        backups: list[DatabaseBackup],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.project = project
        self.backups = backups
        self.restored_workspace: Path | None = None
        self.setWindowTitle("数据库备份与恢复")
        self.resize(650, 420)
        layout = QVBoxLayout(self)
        title = QLabel("保护你的词汇、修改和学习标记")
        title.setObjectName("heroTitle")
        title.setStyleSheet("font-size: 20px;")
        intro = QLabel("软件每天自动保留一次备份；恢复前还会保存当前数据库。")
        intro.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(intro)
        self.backup_list = QListWidget()
        layout.addWidget(self.backup_list, 1)
        actions = QHBoxLayout()
        self.create_button = QPushButton("立即备份")
        self.create_button.setProperty("kind", "mint")
        self.create_button.setEnabled(project is not None)
        self.create_button.clicked.connect(self._create_backup)
        restore_button = QPushButton("恢复所选")
        restore_button.setProperty("kind", "primary")
        restore_button.clicked.connect(self._restore_selected)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.reject)
        actions.addWidget(self.create_button)
        actions.addStretch()
        actions.addWidget(close_button)
        actions.addWidget(restore_button)
        layout.addLayout(actions)
        self._refresh()

    def _refresh(self) -> None:
        if self.project is not None:
            self.backups = list_database_backups(self.project.workspace)
        self.backup_list.clear()
        for index, backup in enumerate(self.backups):
            item = QListWidgetItem(
                f"{backup.workspace.root.name}\n{backup.display_time} · {backup.reason}"
            )
            item.setData(Qt.UserRole, index)
            self.backup_list.addItem(item)
        if self.backups:
            self.backup_list.setCurrentRow(0)

    def _create_backup(self) -> None:
        if self.project is None:
            return
        try:
            path = create_database_backup(self.project.workspace.database_path, "manual")
            if path is None:
                raise RuntimeError("当前数据库还没有可备份的数据")
            self._refresh()
            QMessageBox.information(self, "备份完成", f"已经保存：\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "备份失败", str(exc))

    def _restore_selected(self) -> None:
        item = self.backup_list.currentItem()
        if item is None:
            QMessageBox.information(self, "请选择备份", "请先选择一份要恢复的数据库备份。")
            return
        backup = self.backups[int(item.data(Qt.UserRole))]
        answer = QMessageBox.question(
            self,
            "确认恢复",
            f"将把“{backup.workspace.root.name}”恢复到 {backup.display_time}。\n"
            "当前数据库会先自动备份，是否继续？",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            restore_database_backup(backup)
            self.restored_workspace = backup.workspace.root
            QMessageBox.information(self, "恢复完成", "数据库已经恢复并通过完整性检查。")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "恢复失败", str(exc))


class StickerManagerDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.last_imported: Path | None = None
        self.setWindowTitle("我的贴纸")
        self.resize(560, 390)
        layout = QVBoxLayout(self)
        title = QLabel("加入你喜欢的学习贴纸")
        title.setObjectName("heroTitle")
        title.setStyleSheet("font-size: 20px;")
        intro = QLabel("支持 PNG、JPG、JPEG 和 WebP；图片只保存在这台电脑。")
        intro.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(intro)
        self.sticker_list = QListWidget()
        layout.addWidget(self.sticker_list, 1)
        actions = QHBoxLayout()
        add_button = QPushButton("添加贴纸")
        add_button.setProperty("kind", "mint")
        add_button.clicked.connect(self._add_sticker)
        delete_button = QPushButton("删除所选")
        delete_button.clicked.connect(self._delete_selected)
        close_button = QPushButton("完成")
        close_button.setProperty("kind", "primary")
        close_button.clicked.connect(self.accept)
        actions.addWidget(add_button)
        actions.addWidget(delete_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addLayout(actions)
        self._refresh()

    def _refresh(self) -> None:
        self.sticker_list.clear()
        for path in available_sticker_paths():
            item = QListWidgetItem(
                f"{'内置原创' if path.name in BUILTIN_STICKERS else '我的贴纸'} · {path.name}"
            )
            item.setData(Qt.UserRole, str(path))
            self.sticker_list.addItem(item)

    def _add_sticker(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self,
            "选择贴纸图片",
            "",
            "图片 (*.png *.jpg *.jpeg *.webp)",
        )
        if not source:
            return
        try:
            self.last_imported = import_custom_sticker(source)
            self._refresh()
            QMessageBox.information(self, "添加成功", "新贴纸已经加入轮换列表。")
        except Exception as exc:
            QMessageBox.warning(self, "无法添加贴纸", str(exc))

    def _delete_selected(self) -> None:
        item = self.sticker_list.currentItem()
        if item is None:
            return
        path = Path(str(item.data(Qt.UserRole)))
        if path.name in BUILTIN_STICKERS:
            QMessageBox.information(self, "内置贴纸", "内置原创贴纸不会从安装包中删除。")
            return
        answer = QMessageBox.question(self, "删除贴纸", f"确定删除“{path.name}”吗？")
        if answer == QMessageBox.Yes:
            try:
                path.unlink(missing_ok=True)
                self._refresh()
            except OSError as exc:
                QMessageBox.warning(self, "删除失败", str(exc))


class VocabularyChoiceDialog(QDialog):
    def __init__(
        self,
        projects: list[ImportedProject],
        backups: list[DatabaseBackup] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.projects = projects
        self.backups = backups or []
        self.import_new_requested = False
        self.restored_workspace: Path | None = None
        self.setWindowTitle("选择词汇")
        self.resize(650, 430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel("选择一份已经导入的词汇")
        title.setObjectName("heroTitle")
        title.setStyleSheet("font-size: 20px;")
        intro = QLabel("打开后直接使用已有词条和音频；也可以继续导入新的 PDF。")
        intro.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(intro)

        self.project_list = QListWidget()
        self.project_list.setWordWrap(True)
        self.project_list.setSpacing(2)
        for index, project in enumerate(projects):
            item = QListWidgetItem(
                f"{project.display_name}\n"
                f"{project.entry_count} 个词 · {project.page_count} 页 · "
                f"已有音频 {project.audio_ready_count}"
            )
            item.setData(Qt.UserRole, index)
            self.project_list.addItem(item)
        if projects:
            self.project_list.setCurrentRow(0)
        self.project_list.itemDoubleClicked.connect(lambda *_: self._open_selected())
        layout.addWidget(self.project_list, 1)

        actions = QHBoxLayout()
        self.import_button = QPushButton("导入新 PDF")
        self.import_button.setProperty("kind", "mint")
        self.import_button.clicked.connect(self._request_import)
        backup_button = QPushButton("备份与恢复")
        backup_button.clicked.connect(self._manage_backups)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        self.open_button = QPushButton("打开所选")
        self.open_button.setProperty("kind", "primary")
        self.open_button.setEnabled(bool(projects))
        self.open_button.clicked.connect(self._open_selected)
        actions.addWidget(self.import_button)
        actions.addWidget(backup_button)
        actions.addStretch()
        actions.addWidget(cancel_button)
        actions.addWidget(self.open_button)
        layout.addLayout(actions)

    @property
    def selected_project(self) -> ImportedProject | None:
        item = self.project_list.currentItem()
        if item is None:
            return None
        index = int(item.data(Qt.UserRole))
        return self.projects[index] if 0 <= index < len(self.projects) else None

    def _request_import(self) -> None:
        self.import_new_requested = True
        self.accept()

    def _open_selected(self) -> None:
        if self.selected_project is not None:
            self.accept()

    def _manage_backups(self) -> None:
        project = self.selected_project
        backups = list_database_backups(project.workspace) if project else self.backups
        dialog = BackupDialog(project, backups, self)
        if dialog.exec() == QDialog.Accepted and dialog.restored_workspace is not None:
            self.restored_workspace = dialog.restored_workspace
            self.accept()


class WordVoiceWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"单词文档配音 v{__version__}")
        # Keep the first launch usable on 1280×800 displays running at 125% scaling.
        self.resize(1000, 680)
        self.setMinimumSize(900, 600)
        self.pdf_path: Path | None = None
        self.document = None
        self.workspace: ProjectWorkspace | None = None
        self.store: VocabularyStore | None = None
        self.stop_event = threading.Event()
        self.playback_stop_event = threading.Event()
        self._continuous_running = False
        self._threads: list[QThread] = []
        self._active_workers: dict[QThread, QObject] = {}
        self._settings = QSettings("WordPdfVoice", "WordPdfVoice")
        self.opening_phrase = choose_rotating_value(
            HEALING_PHRASES, str(self._settings.value("ui/last_phrase", ""))
        )
        sticker_paths = tuple(str(path) for path in available_sticker_paths())
        self.sticker_name = choose_rotating_value(
            sticker_paths, str(self._settings.value("ui/last_sticker", ""))
        ) if sticker_paths else ""
        self._settings.setValue("ui/last_phrase", self.opening_phrase)
        self._settings.setValue("ui/last_sticker", self.sticker_name)
        self._build_ui()
        icon_path = bundled_ui_asset_path("app-icon.png")
        if icon_path is not None:
            self.setWindowIcon(QIcon(str(icon_path)))

    def _card(self, object_name: str = "card", shadow: bool = False) -> QFrame:
        frame = QFrame()
        frame.setObjectName(object_name)
        if shadow:
            effect = QGraphicsDropShadowEffect(frame)
            effect.setBlurRadius(28)
            effect.setOffset(0, 7)
            effect.setColor(QColor(105, 75, 100, 35))
            frame.setGraphicsEffect(effect)
        return frame

    def _metric_chip(self, title: str, object_name: str) -> tuple[QFrame, QLabel]:
        frame = self._card(object_name)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 7, 14, 7)
        layout.setSpacing(0)
        value = QLabel("--")
        value.setObjectName("metricValue")
        value.setAlignment(Qt.AlignCenter)
        label = QLabel(title)
        label.setObjectName("metricLabel")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(value)
        layout.addWidget(label)
        return frame, value

    def _set_sticker(self) -> None:
        path = Path(self.sticker_name) if self.sticker_name else None
        if path is None or not path.is_file():
            self.sticker_label.setText("✦")
            self.sticker_label.setPixmap(QPixmap())
            return
        pixmap = QPixmap(str(path))
        self.sticker_label.setPixmap(
            pixmap.scaled(
                self.sticker_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    @Slot()
    def rotate_sticker(self) -> None:
        sticker_paths = tuple(str(path) for path in available_sticker_paths())
        if not sticker_paths:
            return
        self.sticker_name = choose_rotating_value(sticker_paths, self.sticker_name)
        self._settings.setValue("ui/last_sticker", self.sticker_name)
        self._set_sticker()

    @Slot()
    def manage_stickers(self) -> None:
        dialog = StickerManagerDialog(self)
        dialog.exec()
        if dialog.last_imported is not None and dialog.last_imported.is_file():
            self.sticker_name = str(dialog.last_imported)
            self._settings.setValue("ui/last_sticker", self.sticker_name)
        elif not Path(self.sticker_name).is_file():
            paths = available_sticker_paths()
            self.sticker_name = str(paths[0]) if paths else ""
        self._set_sticker()

    @Slot()
    def rotate_phrase(self) -> None:
        self.opening_phrase = choose_rotating_value(HEALING_PHRASES, self.opening_phrase)
        self._settings.setValue("ui/last_phrase", self.opening_phrase)
        self.phrase_label.setText(self.opening_phrase)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("page")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(11)

        hero = self._card("heroCard", shadow=True)
        hero.setFixedHeight(160)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 15, 20, 15)
        hero_layout.setSpacing(16)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(5)
        badge = QLabel(f"VOCAB VOICE · v{__version__}")
        badge.setObjectName("eyebrow")
        badge.setMaximumWidth(158)
        hero_copy.addWidget(badge, 0, Qt.AlignLeft)
        title = QLabel("把单词，变成会说话的小伙伴")
        title.setObjectName("heroTitle")
        subtitle = QLabel("选择词汇 · 连续学习 · 熟悉度标记 · 导出 Anki")
        subtitle.setObjectName("heroSubtitle")
        hero_copy.addWidget(title)
        hero_copy.addWidget(subtitle)
        phrase_bubble = self._card("phraseBubble")
        phrase_layout = QHBoxLayout(phrase_bubble)
        phrase_layout.setContentsMargins(11, 5, 8, 5)
        phrase_layout.setSpacing(7)
        phrase_mark = QLabel("♡")
        phrase_mark.setObjectName("phraseMark")
        self.phrase_label = QLabel(self.opening_phrase)
        self.phrase_label.setObjectName("phraseText")
        self.phrase_label.setMinimumWidth(0)
        self.phrase_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.phrase_button = QPushButton("换一句")
        self.phrase_button.setProperty("kind", "ghost")
        self.phrase_button.clicked.connect(self.rotate_phrase)
        phrase_layout.addWidget(phrase_mark)
        phrase_layout.addWidget(self.phrase_label, 1)
        phrase_layout.addWidget(self.phrase_button)
        hero_copy.addWidget(phrase_bubble)
        hero_layout.addLayout(hero_copy, 1)

        hero_side = QVBoxLayout()
        hero_side.setSpacing(3)
        hero_side.setAlignment(Qt.AlignCenter)
        self.sticker_label = QLabel()
        self.sticker_label.setFixedSize(154, 66)
        self.sticker_label.setAlignment(Qt.AlignCenter)
        hero_side.addWidget(self.sticker_label, 0, Qt.AlignCenter)
        sticker_actions = QHBoxLayout()
        sticker_actions.setSpacing(2)
        self.sticker_button = QPushButton("换贴纸")
        self.sticker_button.setProperty("kind", "ghost")
        self.sticker_button.clicked.connect(self.rotate_sticker)
        manage_sticker_button = QPushButton("＋我的贴纸")
        manage_sticker_button.setProperty("kind", "ghost")
        manage_sticker_button.clicked.connect(self.manage_stickers)
        sticker_actions.addWidget(self.sticker_button)
        sticker_actions.addWidget(manage_sticker_button)
        hero_side.addLayout(sticker_actions)
        self.choose_button = QPushButton("选择词汇")
        self.choose_button.setProperty("kind", "primary")
        self.choose_button.setFixedSize(154, 34)
        self.choose_button.clicked.connect(self.choose_vocabulary)
        hero_side.addWidget(self.choose_button, 0, Qt.AlignCenter)
        hero_layout.addLayout(hero_side)
        self._set_sticker()
        root.addWidget(hero)

        summary_card = self._card("summaryCard")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(17, 9, 14, 9)
        summary_copy = QVBoxLayout()
        summary_copy.setSpacing(2)
        summary_title = QLabel("当前学习文档")
        summary_title.setObjectName("sectionTitle")
        self.summary_label = QLabel("还没有选择词汇 PDF")
        self.summary_label.setObjectName("documentTitle")
        self.summary_meta = QLabel("点击右上角“选择词汇”，打开已有内容或导入新的 PDF")
        self.summary_meta.setObjectName("documentMeta")
        summary_copy.addWidget(summary_title)
        summary_copy.addWidget(self.summary_label)
        summary_copy.addWidget(self.summary_meta)
        summary_layout.addLayout(summary_copy, 1)
        page_chip, self.page_metric = self._metric_chip("页数", "metricLilac")
        entry_chip, self.entry_metric = self._metric_chip("词条", "metricCoral")
        issue_chip, self.issue_metric = self._metric_chip("需留意", "metricSun")
        audio_chip, self.audio_metric = self._metric_chip("已有音频", "metricMint")
        for chip in (page_chip, entry_chip, issue_chip, audio_chip):
            chip.setMinimumWidth(82)
            summary_layout.addWidget(chip)
        root.addWidget(summary_card)

        toolbar_card = self._card()
        toolbar = QVBoxLayout(toolbar_card)
        toolbar.setContentsMargins(14, 8, 14, 8)
        toolbar.setSpacing(6)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        search_label = QLabel("搜索")
        search_label.setObjectName("sectionTitle")
        filter_row.addWidget(search_label)
        self.search = QLineEdit()
        self.search.setPlaceholderText("输入单词、音标或释义…")
        self.search.setMinimumWidth(220)
        self.search.setMaximumWidth(480)
        self.search.textChanged.connect(self.refresh_table)
        filter_row.addWidget(self.search, 1)
        self.issues_only = QCheckBox("只看异常")
        self.issues_only.toggled.connect(self.refresh_table)
        filter_row.addWidget(self.issues_only)
        self.audio_ready_only = QCheckBox("只看已有音频")
        self.audio_ready_only.toggled.connect(self.refresh_table)
        filter_row.addWidget(self.audio_ready_only)
        filter_row.addSpacing(10)
        filter_row.addWidget(QLabel("学习范围"))
        self.learning_filter = QComboBox()
        self.learning_filter.addItem("全部词汇", "all")
        self.learning_filter.addItem("重点复习 · 模糊＋不认识", "focus")
        self.learning_filter.addItem("只看不认识", "unknown")
        self.learning_filter.currentIndexChanged.connect(self.refresh_table)
        filter_row.addWidget(self.learning_filter)
        filter_row.addStretch()
        toolbar.addLayout(filter_row)

        settings_row = QHBoxLayout()
        settings_row.setSpacing(8)
        settings_row.addWidget(QLabel("声音"))
        self.voice = QComboBox()
        for label, voice_id in (
            ("美式女声 · Sarah", "af_sarah"),
            ("美式女声 · Heart", "af_heart"),
            ("美式男声 · Adam", "am_adam"),
            ("英式女声 · Emma", "bf_emma"),
        ):
            self.voice.addItem(label, voice_id)
        self.voice.setToolTip("更换声音后，下次试听或生成会重新制作对应音频")
        settings_row.addWidget(self.voice)
        settings_row.addSpacing(12)
        settings_row.addWidget(QLabel("语速"))
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.6, 1.3)
        self.speed.setSingleStep(0.1)
        self.speed.setDecimals(2)
        self.speed.setSuffix(" 倍")
        self.speed.setValue(0.9)
        self.speed.setToolTip("改变语速后，下次试听或生成会重新制作对应音频")
        settings_row.addWidget(self.speed)
        settings_row.addSpacing(12)
        settings_row.addWidget(QLabel("排序"))
        self.sort_order = QComboBox()
        self.sort_order.addItem("序号从小到大", "asc")
        self.sort_order.addItem("序号从大到小", "desc")
        settings_row.addWidget(self.sort_order)
        settings_row.addStretch()
        toolbar.addLayout(settings_row)

        study_row = QHBoxLayout()
        study_row.setSpacing(7)
        study_label = QLabel("连续学习")
        study_label.setObjectName("sectionTitle")
        study_row.addWidget(study_label)
        study_row.addWidget(QLabel("重复"))
        self.repeat_count = QComboBox()
        for count in range(1, 6):
            self.repeat_count.addItem(f"{count} 次", count)
        saved_repeat = max(1, min(5, int(self._settings.value("playback/repeat", 1))))
        self.repeat_count.setCurrentIndex(saved_repeat - 1)
        study_row.addWidget(self.repeat_count)
        study_row.addWidget(QLabel("间隔"))
        self.pause_seconds = QDoubleSpinBox()
        self.pause_seconds.setRange(0.0, 10.0)
        self.pause_seconds.setSingleStep(0.5)
        self.pause_seconds.setDecimals(1)
        self.pause_seconds.setSuffix(" 秒")
        self.pause_seconds.setValue(float(self._settings.value("playback/pause", 1.0)))
        study_row.addWidget(self.pause_seconds)
        self.play_mode = QComboBox()
        self.play_mode.addItem("只听英文", "english")
        self.play_mode.addItem("英文＋中文释义", "bilingual")
        saved_mode = str(self._settings.value("playback/mode", "english"))
        self.play_mode.setCurrentIndex(1 if saved_mode == "bilingual" else 0)
        study_row.addWidget(self.play_mode)
        self.continuous_play_button = QPushButton("从所选开始")
        self.continuous_play_button.setProperty("kind", "primary")
        self.continuous_play_button.clicked.connect(self.start_continuous_playback)
        study_row.addWidget(self.continuous_play_button)
        stop_play_button = QPushButton("停止播放")
        stop_play_button.clicked.connect(self.stop_continuous_playback)
        study_row.addWidget(stop_play_button)
        study_row.addStretch()
        for label, status, kind in (
            ("认识", "known", "mint"),
            ("模糊", "unsure", "sun"),
            ("不认识", "unknown", "lavender"),
        ):
            button = QPushButton(label)
            button.setProperty("kind", kind)
            button.clicked.connect(lambda _checked=False, value=status: self.mark_selected(value))
            study_row.addWidget(button)
        toolbar.addLayout(study_row)
        root.addWidget(toolbar_card)

        table_card = self._card("tableCard", shadow=True)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(12, 10, 12, 12)
        table_heading = QHBoxLayout()
        table_title = QLabel("词汇小队")
        table_title.setObjectName("sectionTitle")
        self.table_count_label = QLabel("显示 0 条")
        self.table_count_label.setObjectName("tableCount")
        table_heading.addWidget(table_title)
        table_heading.addStretch()
        table_heading.addWidget(self.table_count_label)
        table_layout.addLayout(table_heading)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("序号", "单词", "注音", "释义", "页码", "状态"))
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        header_view = self.table.horizontalHeader()
        for column in (0, 1, 2, 4, 5):
            header_view.setSectionResizeMode(column, QHeaderView.Interactive)
        for column, width in {0: 62, 1: 120, 2: 150, 4: 70, 5: 92}.items():
            header_view.resizeSection(column, width)
        header_view.setSectionResizeMode(3, QHeaderView.Stretch)
        header_view.setStretchLastSection(False)
        self.table.doubleClicked.connect(self.play_selected)
        table_layout.addWidget(self.table)
        root.addWidget(table_card, 1)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        for label, handler, kind in (
            ("试听所选", self.play_selected, "primary"),
            ("编辑词条", self.edit_selected, ""),
            ("生成 30 词样本", self.generate_samples, "sun"),
            ("生成全部", self.generate_all, "lavender"),
            ("停止全部", self.stop_all_tasks, ""),
            ("打开音频文件夹", self.open_audio_folder, ""),
        ):
            button = QPushButton(label)
            if kind:
                button.setProperty("kind", kind)
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch()
        ready_export_button = QPushButton("导出已有音频")
        ready_export_button.setProperty("kind", "mint")
        ready_export_button.clicked.connect(self.export_ready_anki)
        actions.addWidget(ready_export_button)
        export_button = QPushButton("导出全部 Anki")
        export_button.setProperty("kind", "lavender")
        export_button.clicked.connect(self.export_anki)
        actions.addWidget(export_button)
        root.addLayout(actions)

        footer = self._card("statusCard")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(13, 8, 13, 8)
        status_mark = QLabel("♡")
        status_mark.setObjectName("phraseMark")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.status_label = QLabel("准备好啦，点击右上角选择词汇吧")
        self.status_label.setObjectName("muted")
        footer_layout.addWidget(status_mark)
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
    def choose_vocabulary(self) -> None:
        projects = list_imported_projects()
        backups = list_database_backups()
        if not projects and not backups:
            QMessageBox.information(
                self,
                "还没有词汇文档",
                "目前没有已经导入的词汇，请选择一个 PDF 开始导入。",
            )
            self.import_new_pdf()
            return
        dialog = VocabularyChoiceDialog(projects, backups, self)
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.import_new_requested:
            self.import_new_pdf()
            return
        if dialog.restored_workspace is not None:
            restored = next(
                (
                    project
                    for project in list_imported_projects()
                    if project.workspace.root == dialog.restored_workspace
                ),
                None,
            )
            if restored is not None:
                self.load_imported_project(restored)
            else:
                self._show_error("备份已恢复，但暂时无法读取这份词汇，请重新打开软件后再试。")
            return
        project = dialog.selected_project
        if project is not None:
            self.load_imported_project(project)

    def import_new_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择英语词汇 PDF", "", "PDF (*.pdf)")
        if not path:
            return
        self.load_pdf(Path(path))

    def load_imported_project(self, project: ImportedProject) -> None:
        self.choose_button.setEnabled(False)
        self.summary_label.setText(project.display_name)
        self.summary_meta.setText("正在载入已导入的词汇…")
        self.status_label.setText("正在载入已导入的词汇…")
        self.progress.setValue(0)
        try:
            document, workspace, store = open_imported_project(project)
            self._activate_document(document, workspace, store)
            self.status_label.setText("已载入已导入的词汇")
        except Exception as exc:
            self.choose_button.setEnabled(True)
            self.progress.setValue(0)
            self._show_error(f"无法打开这份词汇：{exc}")

    def load_pdf(self, pdf_path: Path) -> None:
        if not pdf_path.is_file():
            self._show_error(f"找不到 PDF：{pdf_path}")
            return
        self.pdf_path = pdf_path
        self.choose_button.setEnabled(False)
        self.summary_label.setText(pdf_path.name)
        self.summary_meta.setText("正在认识这份词汇，请稍等一下…")
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
        self._activate_document(document, workspace, store)
        if migration.performed:
            self.status_label.setText(f"已从 v0.1 复制 {migration.copied_audio} 条音频到 v0.2")
        else:
            self.status_label.setText("文档分析完成")

    def _activate_document(self, document, workspace, store) -> None:
        self.document = document
        self.pdf_path = document.source_path
        self.workspace = workspace
        self.store = store
        self.choose_button.setEnabled(True)
        self._refresh_summary()
        self.progress.setValue(100)
        self.refresh_table()

    def _refresh_summary(self) -> None:
        if not self.document or not self.store:
            return
        counts = self.store.audio_counts()
        self.summary_label.setText(self.document.source_path.name)
        self.summary_meta.setText("解析完成，可以连续播放、标记熟悉度、生成或导出学习卡组")
        self.page_metric.setText(str(self.document.page_count))
        self.entry_metric.setText(str(len(self.document.entries)))
        self.issue_metric.setText(str(self.document.flagged_count))
        self.audio_metric.setText(str(counts["ready"]))

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
            learning_filter=str(self.learning_filter.currentData()),
        )
        self.table_count_label.setText(f"显示 {len(entries)} 条")
        statuses = self.store.audio_status_map()
        learning_statuses = self.store.learning_status_map()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(entries))
        for row_index, entry in enumerate(entries):
            state = {"ready": "已有音频", "failed": "生成失败"}.get(
                statuses.get(entry.sequence), ""
            )
            learning = learning_statuses.get(entry.sequence, "unrated")
            parts = [entry.flag_text, state]
            if learning != "unrated":
                parts.append(LEARNING_LABELS.get(learning, learning))
            status = " · ".join(part for part in parts if part)
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
        if self._continuous_running:
            QMessageBox.information(self, "正在连续播放", "请先停止连续播放，再单独试听。")
            return
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

    def _entries_from_selected_row(self) -> list[VocabularyEntry]:
        if not self.store or self.table.currentRow() < 0:
            return []
        entries: list[VocabularyEntry] = []
        for row in range(self.table.currentRow(), self.table.rowCount()):
            item = self.table.item(row, 0)
            entry = self.store.get_entry(int(item.text())) if item else None
            if entry is not None:
                entries.append(entry)
        return entries

    @Slot()
    def start_continuous_playback(self) -> None:
        if self._continuous_running:
            QMessageBox.information(self, "正在连续播放", "请先停止当前连续播放任务。")
            return
        entries = self._entries_from_selected_row()
        if not entries:
            QMessageBox.information(self, "请选择起点", "请先选择一个单词作为连续播放起点。")
            return
        service = self._audio_service()
        if service is None:
            return
        include_meaning = self.play_mode.currentData() == "bilingual"
        if include_meaning and not chinese_voice_available():
            QMessageBox.warning(
                self,
                "没有中文语音",
                "这台电脑没有可用的 Windows 中文语音，本次将继续只播放英文。",
            )
            include_meaning = False
        repeat_count = int(self.repeat_count.currentData())
        pause_seconds = float(self.pause_seconds.value())
        self._settings.setValue("playback/repeat", repeat_count)
        self._settings.setValue("playback/pause", pause_seconds)
        self._settings.setValue("playback/mode", str(self.play_mode.currentData()))
        self.playback_stop_event.clear()
        _stop_windows_sound()
        self._continuous_running = True
        self.continuous_play_button.setEnabled(False)
        worker = ContinuousPlaybackWorker(
            service,
            entries,
            repeat_count,
            pause_seconds,
            include_meaning,
            self.playback_stop_event,
        )
        worker.current.connect(self._on_continuous_current)
        worker.item_error.connect(self._on_continuous_item_error)
        worker.finished.connect(self._on_continuous_finished)
        self._start_worker(worker, worker.run, (worker.finished,))

    @Slot(int, int, int, int, str)
    def _on_continuous_current(
        self,
        sequence: int,
        position: int,
        total: int,
        repeat_index: int,
        word: str,
    ) -> None:
        self._select_sequence(sequence)
        self.progress.setValue(int(position / total * 100) if total else 0)
        self.status_label.setText(
            f"连续播放 {position}/{total}：{word} · 第 {repeat_index} 次"
        )

    @Slot(str)
    def _on_continuous_item_error(self, message: str) -> None:
        self.status_label.setText(f"已跳过：{message}")

    @Slot(int, int, bool)
    def _on_continuous_finished(self, completed: int, failed: int, stopped: bool) -> None:
        self._continuous_running = False
        self.continuous_play_button.setEnabled(True)
        self.status_label.setText(
            f"{'连续播放已停止' if stopped else '连续播放完成'}：完成 {completed}，跳过 {failed}"
        )
        self._refresh_summary()
        self.refresh_table()

    def _select_sequence(self, sequence: int) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and int(item.text()) == sequence:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                return

    @Slot()
    def stop_continuous_playback(self) -> None:
        self.playback_stop_event.set()
        _stop_windows_sound()
        if self._continuous_running:
            self.status_label.setText("正在停止连续播放…")

    def mark_selected(self, status: str) -> None:
        entry = self.selected_entry()
        if not entry or not self.store:
            return
        self.store.set_learning_status(entry.sequence, status)
        self.refresh_table()
        self._select_sequence(entry.sequence)
        self.status_label.setText(f"{entry.word} 已标记为“{LEARNING_LABELS[status]}”")

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
    def stop_all_tasks(self) -> None:
        self.stop_event.set()
        self.playback_stop_event.set()
        _stop_windows_sound()
        self.status_label.setText("正在停止生成或播放任务…")

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
    window.showNormal()
    window.raise_()
    window.activateWindow()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
