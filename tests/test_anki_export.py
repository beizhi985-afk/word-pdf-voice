from __future__ import annotations

import importlib.util
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

from word_voice.anki_export import AnkiExportError, export_anki_deck
from word_voice.models import ExtractedDocument, VocabularyEntry
from word_voice.storage import VocabularyStore


@unittest.skipUnless(importlib.util.find_spec("genanki"), "需要 genanki")
class AnkiExportTests(unittest.TestCase):
    def test_package_contains_collection_and_audio(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = VocabularyEntry(1, "example", "ig'zɑ:mpl", "n.例子", 1)
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
            destination = export_anki_deck([entry], store, root / "sample.apkg", "测试")
            with zipfile.ZipFile(destination) as package:
                names = set(package.namelist())
                self.assertIn("collection.anki2", names)
                self.assertIn("media", names)
                self.assertIn("0", names)

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


if __name__ == "__main__":
    unittest.main()

