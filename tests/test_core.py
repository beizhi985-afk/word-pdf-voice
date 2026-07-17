from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from word_voice.models import ExtractedDocument, VocabularyEntry
from word_voice.samples import select_pronunciation_samples
from word_voice.storage import VocabularyStore
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


if __name__ == "__main__":
    unittest.main()

