from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtGui import QImage


ROOT = Path(__file__).resolve().parents[1]


class PackagingRegressionTests(unittest.TestCase):
    def test_language_tags_data_is_collected(self) -> None:
        specification = (ROOT / "packaging" / "word_voice.spec").read_text(encoding="utf-8")
        self.assertIn('"language_tags"', specification)

    def test_build_runs_real_portable_tts_smoke(self) -> None:
        build_script = (ROOT / "scripts" / "build.ps1").read_text(encoding="utf-8")
        self.assertIn("verify_portable.py", build_script)
        self.assertTrue((ROOT / "scripts" / "verify_portable.py").is_file())

    def test_build_uses_current_version_name(self) -> None:
        specification = (ROOT / "packaging" / "word_voice.spec").read_text(encoding="utf-8")
        build_script = (ROOT / "scripts" / "build.ps1").read_text(encoding="utf-8")
        self.assertIn('app_name = "WordPdfVoice-v0.3.0"', specification)
        self.assertIn("dist\\WordPdfVoice-v0.3.0\\WordPdfVoice-v0.3.0.exe", build_script)

    def test_original_ui_stickers_are_transparent_and_packaged(self) -> None:
        specification = (ROOT / "packaging" / "word_voice.spec").read_text(encoding="utf-8")
        self.assertIn('ui_assets.glob("*.png")', specification)
        self.assertIn('"assets/ui"', specification)
        for filename in ("chibi-student.png", "headphone-dino.png", "cozy-cloud-cat.png"):
            image = QImage(str(ROOT / "assets" / "ui" / filename))
            self.assertFalse(image.isNull(), filename)
            self.assertTrue(image.hasAlphaChannel(), filename)
            self.assertEqual(0, image.pixelColor(0, 0).alpha(), filename)


if __name__ == "__main__":
    unittest.main()
