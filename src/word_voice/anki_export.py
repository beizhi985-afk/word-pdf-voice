from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import VocabularyEntry
from .storage import VocabularyStore


class AnkiExportError(RuntimeError):
    pass


ANKI_MODEL_ID = 1965721701
ANKI_DECK_ID = 1965721702


@dataclass(frozen=True, slots=True)
class AnkiExportResult:
    path: Path
    exported_count: int
    skipped_count: int


def export_anki_deck(
    entries: Iterable[VocabularyEntry],
    store: VocabularyStore,
    output_path: str | Path,
    deck_name: str = "英语四级乱序词汇 4450",
    ready_only: bool = False,
) -> AnkiExportResult:
    try:
        import genanki
    except ImportError as exc:
        raise AnkiExportError("缺少 genanki，请先安装项目依赖。") from exc

    items = list(entries)
    missing: list[int] = []
    ready_items: list[VocabularyEntry] = []
    media_files: list[str] = []
    audio_by_sequence: dict[int, Path] = {}
    for entry in items:
        status, audio_path, _ = store.audio_record(entry.sequence)
        path = Path(audio_path) if audio_path else None
        if status != "ready" or not path or not path.is_file():
            missing.append(entry.sequence)
            continue
        audio_by_sequence[entry.sequence] = path
        media_files.append(str(path))
        ready_items.append(entry)
    if missing and not ready_only:
        preview = ", ".join(map(str, missing[:20]))
        raise AnkiExportError(f"还有 {len(missing)} 条没有音频，示例序号：{preview}")
    if not ready_items:
        raise AnkiExportError("目前还没有可导出的音频，请先生成或试听至少一个单词。")
    items = ready_items

    model = genanki.Model(
        ANKI_MODEL_ID,
        "Word PDF Voice v0.2",
        fields=[
            {"name": "Sequence"},
            {"name": "Word"},
            {"name": "Phonetic"},
            {"name": "Meaning"},
            {"name": "SourcePage"},
            {"name": "Audio"},
        ],
        templates=[
            {
                "name": "Vocabulary Card",
                "qfmt": """
                <div class="word">{{Word}}</div>
                <div class="phonetic">{{Phonetic}}</div>
                <div class="audio">{{Audio}}</div>
                """,
                "afmt": """
                {{FrontSide}}
                <hr id="answer">
                <div class="meaning">{{Meaning}}</div>
                <div class="source">序号 {{Sequence}} · PDF 第 {{SourcePage}} 页</div>
                """,
            }
        ],
        css="""
        .card { font-family: Arial, "Microsoft YaHei", sans-serif; text-align: center;
                color: #14213d; background: #f7f9fc; padding: 28px; }
        .word { font-size: 42px; font-weight: 700; margin: 18px 0 8px; }
        .phonetic { font-size: 22px; color: #52606d; margin-bottom: 18px; }
        .audio { margin: 14px 0; }
        .meaning { font-size: 22px; line-height: 1.65; color: #1f2933; margin: 24px auto;
                   max-width: 720px; }
        .source { font-size: 13px; color: #829ab1; margin-top: 24px; }
        """,
    )
    deck = genanki.Deck(ANKI_DECK_ID, deck_name)
    for entry in items:
        audio_path = audio_by_sequence[entry.sequence]
        note = genanki.Note(
            model=model,
            fields=[
                str(entry.sequence),
                html.escape(entry.word),
                html.escape(entry.phonetic),
                html.escape(entry.meaning),
                str(entry.page),
                f"[sound:{audio_path.name}]",
            ],
            guid=genanki.guid_for("word-pdf-voice", str(entry.sequence)),
            tags=["CET4", "word-pdf-voice"],
        )
        deck.add_note(note)

    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    package = genanki.Package(deck)
    package.media_files = media_files
    package.write_to_file(str(destination))
    return AnkiExportResult(destination, len(items), len(missing))

