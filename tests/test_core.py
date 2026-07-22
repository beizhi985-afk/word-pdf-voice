from __future__ import annotations

import tempfile
import unittest
import wave
import sqlite3
from io import BytesIO
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from word_voice.models import ExtractedDocument, VocabularyEntry
from word_voice.samples import select_pronunciation_samples
from word_voice.storage import (
    ProjectWorkspace,
    VocabularyStore,
    create_database_backup,
    list_database_backups,
    list_imported_projects,
    migrate_legacy_workspace,
    open_imported_project,
    restore_database_backup,
)
from word_voice.speech import meaning_for_speech, speak_chinese
from word_voice.tts import AudioService, audio_filename


def entry(sequence: int, word: str, flags: tuple[str, ...] = ()) -> VocabularyEntry:
    return VocabularyEntry(sequence, word, "test", "释义", 1, flags)


class SampleSelectionTests(unittest.TestCase):
    def test_samples_are_unique_and_bounded(self) -> None:
        entries = [entry(index, f"word{index}") for index in range(1, 101)]
        selected = select_pronunciation_samples(entries, 30)
        self.assertEqual(30, len(selected))
        self.assertEqual(len(selected), len({item.sequence for item in selected}))

    def test_audio_filename_uses_sequence(self) -> None:
        first = audio_filename(entry(616, "present"))
        second = audio_filename(entry(804, "present"))
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("cet4_0616_"))


class RecordingEngine:
    def __init__(self, profile_key: str, accepts_legacy_default_cache: bool = False):
        self.profile_key = profile_key
        self.accepts_legacy_default_cache = accepts_legacy_default_cache
        self.calls = 0

    def synthesize(self, item: VocabularyEntry, output_path: Path) -> Path:
        self.calls += 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.profile_key, encoding="utf-8")
        return output_path


class AudioProfileCacheTests(unittest.TestCase):
    def test_changed_voice_or_speed_regenerates_cached_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = VocabularyStore(root / "test.sqlite3")
            item = entry(1, "alternative")
            store.import_document(
                ExtractedDocument(Path("sample.pdf"), "abc", 1, [item], [])
            )
            first_engine = RecordingEngine("kokoro-v1|af_sarah|0.90|en-us")
            first_service = AudioService(store, root / "audio", first_engine)

            first_service.ensure_audio(item)
            first_service.ensure_audio(item)

            self.assertEqual(1, first_engine.calls)
            second_engine = RecordingEngine("kokoro-v1|am_adam|0.70|en-us")
            second_service = AudioService(store, root / "audio", second_engine)
            result = second_service.ensure_audio(item)
            self.assertEqual(1, second_engine.calls)
            self.assertEqual(second_engine.profile_key, result.read_text(encoding="utf-8"))
            self.assertEqual(second_engine.profile_key, store.audio_profile(item.sequence))

    def test_v020_default_audio_is_reused_and_profile_is_backfilled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = VocabularyStore(root / "test.sqlite3")
            item = entry(1, "alternative")
            store.import_document(
                ExtractedDocument(Path("sample.pdf"), "abc", 1, [item], [])
            )
            existing = root / "audio" / "existing.wav"
            existing.parent.mkdir(parents=True)
            existing.write_bytes(b"legacy")
            store.mark_audio_ready(item.sequence, existing)
            engine = RecordingEngine(
                "kokoro-v1|af_sarah|0.90|en-us", accepts_legacy_default_cache=True
            )

            result = AudioService(store, root / "audio", engine).ensure_audio(item)

            self.assertEqual(existing, result)
            self.assertEqual(0, engine.calls)
            self.assertEqual(engine.profile_key, store.audio_profile(item.sequence))


class StorageTests(unittest.TestCase):
    def test_v032_database_is_backed_up_and_migrated_with_learning_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "project.sqlite3"
            with closing(sqlite3.connect(database)) as connection:
                connection.executescript(
                    """
                    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE entries (
                        sequence INTEGER PRIMARY KEY,
                        source_word TEXT NOT NULL, source_phonetic TEXT NOT NULL,
                        source_meaning TEXT NOT NULL, word TEXT NOT NULL,
                        phonetic TEXT NOT NULL, meaning TEXT NOT NULL,
                        page INTEGER NOT NULL, flags_json TEXT NOT NULL DEFAULT '[]',
                        pronunciation_override TEXT NOT NULL DEFAULT '',
                        manually_edited INTEGER NOT NULL DEFAULT 0,
                        audio_status TEXT NOT NULL DEFAULT 'missing',
                        audio_path TEXT NOT NULL DEFAULT '', audio_error TEXT NOT NULL DEFAULT '',
                        audio_profile TEXT NOT NULL DEFAULT ''
                    );
                    INSERT INTO entries(
                        sequence, source_word, source_phonetic, source_meaning,
                        word, phonetic, meaning, page
                    ) VALUES (1, 'old', '', '旧数据', 'old', '', '旧数据', 1);
                    """
                )
                connection.commit()

            store = VocabularyStore(database)

            self.assertEqual("unrated", store.learning_status(1))
            self.assertEqual("0.6.0", store.get_metadata("data_version"))
            backups = list_database_backups(ProjectWorkspace.create(Path(directory)))
            self.assertTrue(any("before v040 migration" in item.reason for item in backups))

    def test_learning_status_filters_focus_words(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VocabularyStore(Path(directory) / "project.sqlite3")
            store.import_document(
                ExtractedDocument(
                    Path("sample.pdf"),
                    "abc",
                    1,
                    [entry(1, "known"), entry(2, "unsure"), entry(3, "unknown")],
                    [],
                )
            )
            store.set_learning_status(1, "known")
            store.set_learning_status(2, "unsure")
            store.set_learning_status(3, "unknown")

            focus = store.list_entries(learning_filter="focus")

            self.assertEqual([2, 3], [item.sequence for item in focus])
            self.assertEqual({"unrated": 0, "known": 1, "unsure": 1, "unknown": 1}, store.learning_counts())

    def test_database_backup_can_restore_learning_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = ProjectWorkspace.create(Path(directory) / "saved")
            store = VocabularyStore(workspace.database_path)
            store.import_document(
                ExtractedDocument(Path("sample.pdf"), "abc", 1, [entry(1, "word")], [])
            )
            store.set_learning_status(1, "unknown")
            backup_path = create_database_backup(workspace.database_path, "manual")
            self.assertIsNotNone(backup_path)
            store.set_learning_status(1, "known")
            backup = next(
                item
                for item in list_database_backups(workspace)
                if item.path == backup_path
            )

            restore_database_backup(backup)
            restored = VocabularyStore(workspace.database_path)

            self.assertEqual("unknown", restored.learning_status(1))

    def test_imported_projects_can_be_discovered_and_opened_without_source_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            projects_root = Path(directory) / "projects"
            workspace = ProjectWorkspace.create(projects_root / "saved-words")
            store = VocabularyStore(workspace.database_path)
            document = ExtractedDocument(
                source_path=Path(directory) / "missing-source.pdf",
                source_hash="saved-hash",
                page_count=3,
                entries=[entry(1, "ready"), entry(2, "flagged", ("missing_phonetic",))],
                issues=[],
            )
            store.import_document(document)
            audio = workspace.audio_dir / "ready.wav"
            audio.write_bytes(b"audio")
            store.mark_audio_ready(1, audio)

            projects = list_imported_projects(projects_root)

            self.assertEqual(1, len(projects))
            project = projects[0]
            self.assertEqual("missing-source.pdf", project.display_name)
            self.assertEqual(2, project.entry_count)
            self.assertEqual(1, project.flagged_count)
            self.assertEqual(1, project.audio_ready_count)
            loaded_document, loaded_workspace, loaded_store = open_imported_project(project)
            self.assertEqual([1, 2], [item.sequence for item in loaded_document.entries])
            self.assertEqual(workspace.root, loaded_workspace.root)
            self.assertEqual("ready", loaded_store.get_entry(1).word)

    def test_manual_edits_survive_reimport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VocabularyStore(Path(directory) / "test.sqlite3")
            document = ExtractedDocument(
                source_path=Path("sample.pdf"),
                source_hash="abc",
                page_count=1,
                entries=[entry(1, "original")],
                issues=[],
            )
            store.import_document(document)
            store.update_entry(1, "corrected", "kə'rektid", "已修正")
            changed_source = ExtractedDocument(
                source_path=Path("sample.pdf"),
                source_hash="def",
                page_count=1,
                entries=[entry(1, "source-changed")],
                issues=[],
            )
            store.import_document(changed_source)
            saved = store.get_entry(1)
            self.assertIsNotNone(saved)
            self.assertEqual("corrected", saved.word)
            self.assertEqual("已修正", saved.meaning)

    def test_layout_metadata_survives_database_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = VocabularyStore(Path(directory) / "test.sqlite3")
            document = ExtractedDocument(
                source_path=Path("complex.pdf"),
                source_hash="layout-hash",
                page_count=2,
                entries=[
                    VocabularyEntry(
                        1,
                        "take notes",
                        "",
                        "做笔记",
                        2,
                        ("missing_phonetic",),
                        confidence=0.82,
                        source_bbox=(36.0, 40.0, 180.0, 54.0),
                        extraction_method="layout",
                    )
                ],
                issues=[],
                extraction_method="layout",
            )

            store.import_document(document)
            saved = store.get_entry(1)

            self.assertIsNotNone(saved)
            self.assertEqual(0.82, saved.confidence)
            self.assertEqual((36.0, 40.0, 180.0, 54.0), saved.source_bbox)
            self.assertEqual("layout", saved.extraction_method)
            self.assertEqual("layout", store.get_metadata("extraction_method"))

    def test_confirmed_reimport_removes_tail_and_invalidates_changed_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = VocabularyStore(root / "test.sqlite3")
            store.import_document(
                ExtractedDocument(
                    Path("sample.pdf"),
                    "before",
                    1,
                    [entry(1, "old"), entry(2, "removed")],
                    [],
                )
            )
            audio = root / "old.wav"
            audio.write_bytes(b"audio")
            store.mark_audio_ready(1, audio)

            store.import_document(
                ExtractedDocument(
                    Path("sample.pdf"),
                    "after",
                    1,
                    [entry(1, "changed")],
                    [],
                )
            )

            self.assertEqual(1, store.entry_count())
            self.assertIsNone(store.get_entry(2))
            self.assertEqual(("missing", "", ""), store.audio_record(1))

    def test_list_entries_can_show_only_ready_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = VocabularyStore(root / "test.sqlite3")
            document = ExtractedDocument(
                source_path=Path("sample.pdf"),
                source_hash="abc",
                page_count=1,
                entries=[entry(1, "ready"), entry(2, "missing")],
                issues=[],
            )
            store.import_document(document)
            audio = root / "ready.wav"
            audio.write_bytes(b"audio")
            store.mark_audio_ready(1, audio)

            results = store.list_entries(audio_ready_only=True)

            self.assertEqual([1], [item.sequence for item in results])

    def test_v02_migration_copies_database_and_audio_independently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = ProjectWorkspace.create(root / "v0.1")
            target = ProjectWorkspace.create(root / "v0.2")
            legacy_store = VocabularyStore(legacy.database_path)
            document = ExtractedDocument(
                source_path=Path("sample.pdf"),
                source_hash="abc",
                page_count=1,
                entries=[entry(1, "original")],
                issues=[],
            )
            legacy_store.import_document(document)
            legacy_store.update_entry(1, "corrected", "test", "已修正")
            source_audio = legacy.audio_dir / "cet4_0001_corrected.wav"
            with wave.open(str(source_audio), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(24000)
                output.writeframes(b"\x00\x00" * 240)
            legacy_store.mark_audio_ready(1, source_audio)

            migration = migrate_legacy_workspace(legacy.root, target)

            self.assertTrue(migration.performed)
            self.assertEqual(1, migration.copied_audio)
            target_store = VocabularyStore(target.database_path)
            migrated_entry = target_store.get_entry(1)
            self.assertIsNotNone(migrated_entry)
            self.assertEqual("corrected", migrated_entry.word)
            status, migrated_path, _ = target_store.audio_record(1)
            self.assertEqual("ready", status)
            self.assertTrue(Path(migrated_path).is_relative_to(target.audio_dir))
            source_audio.unlink()
            self.assertTrue(Path(migrated_path).is_file())
            self.assertFalse(migrate_legacy_workspace(legacy.root, target).performed)


class SpeechTests(unittest.TestCase):
    def test_chinese_meaning_is_cleaned_for_speech(self) -> None:
        self.assertEqual(
            "附近的，在附近，在附近",
            meaning_for_speech("adj.附近的 adv.在附近 prep.在...附近"),
        )

    def test_chinese_audio_path_is_passed_without_command_line_parsing(self) -> None:
        captured: dict[str, object] = {}

        class InputSink:
            def write(self, data: bytes) -> None:
                captured["input"] = data

            def close(self) -> None:
                return None

        class FakeProcess:
            stdin = InputSink()
            stderr = BytesIO()
            returncode = 0

            def poll(self):
                return 0

        def fake_popen(command, **kwargs):
            captured["command"] = command
            captured["env"] = kwargs["env"]
            return FakeProcess()

        with (
            patch("word_voice.speech.platform.system", return_value="Windows"),
            patch("word_voice.speech.subprocess.Popen", side_effect=fake_popen),
            patch("word_voice.speech.play_wav_sync", return_value=True) as player,
        ):
            self.assertTrue(speak_chinese("中文释义"))

        command = captured["command"]
        environment = captured["env"]
        output_path = Path(environment["WORD_VOICE_CHINESE_WAV"])
        self.assertNotIn(str(output_path), " ".join(command))
        player.assert_called_once_with(output_path, None)
        self.assertEqual("中文释义".encode("utf-8"), captured["input"])
        self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()

