from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from word_voice.extractor import ExtractionCancelled, extract_vocabulary_pdf


@unittest.skipUnless(importlib.util.find_spec("reportlab"), "需要 reportlab 生成测试 PDF")
class ComplexPdfExtractionTests(unittest.TestCase):
    def _build_two_column_pdf(self, path: Path) -> None:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen.canvas import Canvas

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        canvas = Canvas(str(path), pagesize=(595, 842))
        canvas.setFont("STSong-Light", 10)
        canvas.drawString(36, 800, "阅读方法")
        canvas.drawString(36, 780, "Step one 第一步")
        canvas.showPage()
        for page_number in (2, 3):
            canvas.setFont("STSong-Light", 10)
            for index in range(12):
                y = 800 - index * 24
                canvas.drawString(36, y, f"left phrase {page_number}-{index} 左侧释义{index}")
            for index in range(13):
                y = 800 - index * 24
                canvas.drawString(308, y, f"right phrase {page_number}-{index} 右侧释义{index}")
            canvas.showPage()
        canvas.save()

    def test_two_column_document_uses_layout_order_and_skips_note_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "complex.pdf"
            self._build_two_column_pdf(pdf_path)

            document = extract_vocabulary_pdf(pdf_path)

            self.assertEqual("layout", document.extraction_method)
            self.assertTrue(document.requires_review)
            self.assertEqual(50, len(document.entries))
            self.assertEqual("left phrase 2-0", document.entries[0].word)
            self.assertEqual("left phrase 2-11", document.entries[11].word)
            self.assertEqual("right phrase 2-0", document.entries[12].word)
            self.assertTrue(
                any(issue.code == "low_vocabulary_density" and issue.page == 1 for issue in document.issues)
            )
            self.assertTrue(all(entry.source_bbox for entry in document.entries))

    def test_analysis_can_be_cancelled_before_work_starts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "complex.pdf"
            self._build_two_column_pdf(pdf_path)

            with self.assertRaises(ExtractionCancelled):
                extract_vocabulary_pdf(pdf_path, cancelled=lambda: True)


if __name__ == "__main__":
    unittest.main()
