from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable

from .models import ExtractedDocument, ExtractionIssue, VocabularyEntry


class ExtractionError(RuntimeError):
    """Raised when a vocabulary PDF cannot be parsed safely."""


ProgressCallback = Callable[[int, int], None]


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_cell(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _is_header(row: list[str]) -> bool:
    return len(row) == 4 and row[0].replace(" ", "") == "序号" and row[1] == "单词"


def _looks_like_word(word: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z.' -]*", word))


def _add_flags(entries: list[VocabularyEntry]) -> list[VocabularyEntry]:
    word_counts = Counter(entry.word.casefold() for entry in entries)
    result: list[VocabularyEntry] = []
    for entry in entries:
        flags: list[str] = []
        if not entry.phonetic:
            flags.append("missing_phonetic")
        if not entry.meaning:
            flags.append("missing_meaning")
        if word_counts[entry.word.casefold()] > 1:
            flags.append("duplicate_word")
        if "," in entry.phonetic or "/" in entry.phonetic:
            flags.append("multiple_pronunciations")
        if not _looks_like_word(entry.word):
            flags.append("suspicious_word")
        result.append(
            VocabularyEntry(
                sequence=entry.sequence,
                word=entry.word,
                phonetic=entry.phonetic,
                meaning=entry.meaning,
                page=entry.page,
                flags=tuple(flags),
                pronunciation_override=entry.pronunciation_override,
            )
        )
    return result


def _validate_sequences(entries: list[VocabularyEntry]) -> None:
    if not entries:
        raise ExtractionError("没有从 PDF 中提取到有效词条。")
    sequences = [entry.sequence for entry in entries]
    counts = Counter(sequences)
    duplicates = sorted(sequence for sequence, count in counts.items() if count > 1)
    expected = set(range(min(sequences), max(sequences) + 1))
    missing = sorted(expected.difference(sequences))
    if duplicates or missing:
        details: list[str] = []
        if duplicates:
            details.append(f"重复序号：{duplicates[:20]}")
        if missing:
            details.append(f"缺失序号：{missing[:20]}")
        raise ExtractionError("；".join(details))


def extract_vocabulary_pdf(
    pdf_path: str | Path,
    progress: ProgressCallback | None = None,
) -> ExtractedDocument:
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.casefold() != ".pdf":
        raise ExtractionError("请选择 PDF 文件。")

    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency message
        raise ExtractionError("缺少 pdfplumber，请先安装项目依赖。") from exc

    entries: list[VocabularyEntry] = []
    issues: list[ExtractionIssue] = []
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            numeric_rows_on_page = 0
            for table in tables:
                for raw_row in table:
                    if not raw_row:
                        continue
                    row = [normalize_cell(cell) for cell in raw_row]
                    if _is_header(row):
                        continue
                    if len(row) != 4:
                        if any(row):
                            issues.append(
                                ExtractionIssue(page_number, "column_count", repr(row))
                            )
                        continue
                    if not row[0].isdigit():
                        if any(row):
                            issues.append(
                                ExtractionIssue(page_number, "non_numeric_row", repr(row))
                            )
                        continue
                    entries.append(
                        VocabularyEntry(
                            sequence=int(row[0]),
                            word=row[1],
                            phonetic=row[2],
                            meaning=row[3],
                            page=page_number,
                        )
                    )
                    numeric_rows_on_page += 1
            if numeric_rows_on_page == 0:
                issues.append(
                    ExtractionIssue(page_number, "empty_page", "本页没有提取到数字序号词条")
                )
            if progress:
                progress(page_number, page_count)

    _validate_sequences(entries)
    entries.sort(key=lambda item: item.sequence)
    entries = _add_flags(entries)
    return ExtractedDocument(
        source_path=path,
        source_hash=file_sha256(path),
        page_count=page_count,
        entries=entries,
        issues=issues,
    )


def write_csv(entries: Iterable[VocabularyEntry], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "sequence",
                "word",
                "phonetic",
                "meaning",
                "page",
                "flags",
                "pronunciation_override",
            ],
        )
        writer.writeheader()
        for entry in entries:
            data = entry.to_dict()
            data["flags"] = ",".join(entry.flags)
            writer.writerow(data)
    return path


def write_json(document: ExtractedDocument, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": document.summary(),
        "issues": [issue.to_dict() for issue in document.issues],
        "entries": [entry.to_dict() for entry in document.entries],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

