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
    migrate_legacy_workspace,
)
from word_voice.tts import audio_filename


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


class StorageTests(unittest.TestCase):
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

