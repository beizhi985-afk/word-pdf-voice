from __future__ import annotations

import unittest
from pathlib import Path


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
        self.assertIn('app_name = "WordPdfVoice-v0.2.1"', specification)
        self.assertIn("dist\\WordPdfVoice-v0.2.1\\WordPdfVoice-v0.2.1.exe", build_script)


if __name__ == "__main__":
    unittest.main()
