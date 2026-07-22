from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PySide6.QtWidgets import QApplication

from word_voice.app import APP_STYLE, ImportPreviewDialog
from word_voice.extractor import extract_vocabulary_pdf


def main() -> int:
    if len(sys.argv) != 2:
        print("用法：preview_complex_import.py <PDF>")
        return 2
    document = extract_vocabulary_pdf(Path(sys.argv[1]))
    application = QApplication.instance() or QApplication(sys.argv)
    application.setStyleSheet(APP_STYLE)
    dialog = ImportPreviewDialog(document)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
