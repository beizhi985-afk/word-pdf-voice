from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from word_voice.models import ExtractedDocument, VocabularyEntry
from word_voice.samples import select_pronunciation_samples
from word_voice.storage import (
    ProjectWorkspace,
    VocabularyStore,
    list_imported_projects,
    migrate_legacy_workspace,
    open_imported_project,
)
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


if __name__ == "__main__":
    unittest.main()

