from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
import wave
import zipfile
from contextlib import closing
from pathlib import Path

from word_voice.anki_export import AnkiExportError, export_anki_deck
from word_voice.models import ExtractedDocument, VocabularyEntry
from word_voice.storage import VocabularyStore


@unittest.skipUnless(importlib.util.find_spec("genanki"), "需要 genanki")
class AnkiExportTests(unittest.TestCase):
    def test_package_contains_collection_and_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = VocabularyEntry(1, "example", "ig'zɑ:mpl", "<古> n.例子", 1)
            store = VocabularyStore(root / "project.sqlite3")
            store.import_document(
                ExtractedDocument(Path("sample.pdf"), "hash", 1, [entry], [])
            )
            audio = root / "cet4_0001_example.wav"
            with wave.open(str(audio), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(24000)
                output.writeframes(b"\x00\x00" * 2400)
            store.mark_audio_ready(1, audio)
            result = export_anki_deck([entry], store, root / "sample.apkg", "测试")
            self.assertEqual(1, result.exported_count)
            self.assertEqual(0, result.skipped_count)
            with zipfile.ZipFile(result.path) as package:
                names = set(package.namelist())
                self.assertIn("collection.anki2", names)
                self.assertIn("media", names)
                self.assertIn("0", names)
                package.extract("collection.anki2", root / "unpacked")
            with closing(sqlite3.connect(root / "unpacked" / "collection.anki2")) as connection:
                fields = connection.execute("SELECT flds FROM notes").fetchone()[0]
            self.assertIn("&lt;古&gt; n.例子", fields)
            self.assertNotIn("<古>", fields)

    def test_missing_audio_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = VocabularyEntry(1, "example", "", "n.例子", 1)
            store = VocabularyStore(root / "project.sqlite3")
            store.import_document(
                ExtractedDocument(Path("sample.pdf"), "hash", 1, [entry], [])
            )
            with self.assertRaises(AnkiExportError):
                export_anki_deck([entry], store, root / "sample.apkg")

    def test_ready_only_export_skips_entries_without_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ready = VocabularyEntry(1, "example", "", "n.例子", 1)
            missing = VocabularyEntry(2, "absent", "", "adj.缺少的", 1)
            store = VocabularyStore(root / "project.sqlite3")
            store.import_document(
                ExtractedDocument(Path("sample.pdf"), "hash", 1, [ready, missing], [])
            )
            audio = root / "cet4_0001_example.wav"
            with wave.open(str(audio), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(24000)
                output.writeframes(b"\x00\x00" * 2400)
            store.mark_audio_ready(1, audio)

            result = export_anki_deck(
                [ready, missing], store, root / "ready.apkg", "已有音频", ready_only=True
            )

            self.assertEqual(1, result.exported_count)
            self.assertEqual(1, result.skipped_count)
            with zipfile.ZipFile(result.path) as package:
                media_members = set(package.namelist()) - {"collection.anki2", "media"}
                self.assertEqual({"0"}, media_members)

    def test_ready_only_export_requires_at_least_one_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = VocabularyEntry(1, "example", "", "n.例子", 1)
            store = VocabularyStore(root / "project.sqlite3")
            store.import_document(
                ExtractedDocument(Path("sample.pdf"), "hash", 1, [entry], [])
            )
            with self.assertRaises(AnkiExportError):
                export_anki_deck([entry], store, root / "sample.apkg", ready_only=True)


if __name__ == "__main__":
    unittest.main()

