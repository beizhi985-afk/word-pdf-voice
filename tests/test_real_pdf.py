from __future__ import annotations

import os
import unittest
from pathlib import Path

from word_voice.extractor import extract_vocabulary_pdf


class RealPdfRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        value = os.environ.get("WORD_VOICE_TEST_PDF", "")
        if not value or not Path(value).is_file():
            raise unittest.SkipTest("设置 WORD_VOICE_TEST_PDF 后运行真实 PDF 回归测试")
        cls.document = extract_vocabulary_pdf(value)
        cls.by_sequence = {entry.sequence: entry for entry in cls.document.entries}

    def test_complete_sequence(self) -> None:
        self.assertEqual(107, self.document.page_count)
        self.assertEqual(4450, len(self.document.entries))
        self.assertEqual(list(range(1, 4451)), [entry.sequence for entry in self.document.entries])

    def test_known_edge_cases_are_preserved(self) -> None:
        self.assertEqual("a.m", self.by_sequence[583].word)
        self.assertIn("missing_phonetic", self.by_sequence[583].flags)
        self.assertEqual("present", self.by_sequence[616].word)
        self.assertEqual("present", self.by_sequence[804].word)
        self.assertIn("duplicate_word", self.by_sequence[616].flags)
        self.assertIn("duplicate_word", self.by_sequence[804].flags)

    def test_first_and_last_entries(self) -> None:
        self.assertEqual("alternative", self.by_sequence[1].word)
        self.assertEqual("busy", self.by_sequence[4450].word)


if __name__ == "__main__":
    unittest.main()

