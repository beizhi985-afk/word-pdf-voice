from __future__ import annotations

import csv
import hashlib
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from .models import ExtractedDocument, ExtractionIssue, VocabularyEntry


class ExtractionError(RuntimeError):
    """Raised when a vocabulary PDF cannot be parsed safely."""


class ExtractionCancelled(ExtractionError):
    """Raised when the user cancels document analysis."""


ProgressCallback = Callable[[int, int], None]
CancelCallback = Callable[[], bool]

_CJK_PATTERN = re.compile(r"[\u3400-\u9fff]")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")


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


def _check_cancelled(cancelled: CancelCallback | None) -> None:
    if cancelled and cancelled():
        raise ExtractionCancelled("已取消文档分析。")


def _add_flags(entries: list[VocabularyEntry]) -> list[VocabularyEntry]:
    word_counts = Counter(entry.word.casefold() for entry in entries)
    result: list[VocabularyEntry] = []
    for entry in entries:
        flags: list[str] = list(entry.flags)
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
        if entry.confidence < 0.75:
            flags.append("low_confidence")
        result.append(
            VocabularyEntry(
                sequence=entry.sequence,
                word=entry.word,
                phonetic=entry.phonetic,
                meaning=entry.meaning,
                page=entry.page,
                flags=tuple(dict.fromkeys(flags)),
                pronunciation_override=entry.pronunciation_override,
                confidence=entry.confidence,
                source_bbox=entry.source_bbox,
                extraction_method=entry.extraction_method,
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


def _table_signature(page) -> bool:
    text = normalize_cell(page.extract_text() or "").replace(" ", "")
    return sum(label in text for label in ("序号", "单词", "注音", "释义")) >= 3


def _extract_table_document(
    path: Path,
    pdf,
    progress: ProgressCallback | None,
    cancelled: CancelCallback | None,
) -> ExtractedDocument:
    entries: list[VocabularyEntry] = []
    issues: list[ExtractionIssue] = []
    page_count = len(pdf.pages)
    for page_number, page in enumerate(pdf.pages, start=1):
        _check_cancelled(cancelled)
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
                        issues.append(ExtractionIssue(page_number, "column_count", repr(row)))
                    continue
                if not row[0].isdigit():
                    if any(row):
                        issues.append(ExtractionIssue(page_number, "non_numeric_row", repr(row)))
                    continue
                entries.append(
                    VocabularyEntry(
                        sequence=int(row[0]),
                        word=row[1],
                        phonetic=row[2],
                        meaning=row[3],
                        page=page_number,
                        confidence=1.0,
                        extraction_method="table",
                    )
                )
                numeric_rows_on_page += 1
        if numeric_rows_on_page == 0:
            issues.append(ExtractionIssue(page_number, "empty_page", "本页没有提取到数字序号词条"))
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
        extraction_method="table",
        requires_review=False,
    )


def _group_words_into_lines(
    words: Sequence[Mapping[str, object]],
    tolerance: float = 4.0,
) -> list[list[Mapping[str, object]]]:
    rows: list[tuple[float, list[Mapping[str, object]]]] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        top = float(word["top"])
        if rows and abs(rows[-1][0] - top) <= tolerance:
            rows[-1][1].append(word)
            average_top = sum(float(item["top"]) for item in rows[-1][1]) / len(rows[-1][1])
            rows[-1] = (average_top, rows[-1][1])
        else:
            rows.append((top, [word]))
    return [sorted(row, key=lambda item: float(item["x0"])) for _, row in rows]


def _split_bilingual_line(text: str) -> tuple[str, str] | None:
    match = _CJK_PATTERN.search(text)
    if match is None:
        return None
    english = normalize_cell(text[: match.start()]).strip(" -—:：;；")
    meaning = normalize_cell(text[match.start() :])
    english = re.sub(r"^\d+[.)、]\s*", "", english).strip()
    if len(_LATIN_PATTERN.findall(english)) < 2 or not meaning:
        return None
    if len(english) > 140 or len(meaning) > 260:
        return None
    return english, meaning


def _layout_candidate(
    row: Sequence[Mapping[str, object]],
    page_number: int,
    column_start: float,
) -> VocabularyEntry | None:
    text = " ".join(str(word["text"]) for word in row)
    pair = _split_bilingual_line(text)
    if pair is None:
        return None
    english, meaning = pair
    x0 = min(float(word["x0"]) for word in row)
    top = min(float(word["top"]) for word in row)
    x1 = max(float(word["x1"]) for word in row)
    bottom = max(float(word["bottom"]) for word in row)
    confidence = 0.95
    if x0 > column_start + 24:
        confidence -= 0.12
    if len(english) > 60:
        confidence -= 0.12
    if any(character.isdigit() for character in english):
        confidence -= 0.10
    if len(meaning) > 100:
        confidence -= 0.08
    if re.search(r"[^A-Za-z0-9\s.'’\-=/…(),（）:+]", english):
        confidence -= 0.10
    return VocabularyEntry(
        sequence=0,
        word=english,
        phonetic="",
        meaning=meaning,
        page=page_number,
        confidence=max(0.35, min(confidence, 0.99)),
        source_bbox=(round(x0, 2), round(top, 2), round(x1, 2), round(bottom, 2)),
        extraction_method="layout",
    )


def _extract_layout_document(
    path: Path,
    pdf,
    progress: ProgressCallback | None,
    cancelled: CancelCallback | None,
) -> ExtractedDocument:
    page_count = len(pdf.pages)
    candidates_by_page: list[list[VocabularyEntry]] = []
    issues: list[ExtractionIssue] = []
    for page_number, page in enumerate(pdf.pages, start=1):
        _check_cancelled(cancelled)
        words = page.extract_words(
            x_tolerance=2,
            y_tolerance=3,
            keep_blank_chars=False,
            use_text_flow=False,
        )
        midpoint = float(page.width) / 2
        page_candidates: list[VocabularyEntry] = []
        columns = (
            (0.0, midpoint),
            (midpoint, float(page.width) + 1),
        )
        for lower, upper in columns:
            column_words = [
                word
                for word in words
                if lower <= (float(word["x0"]) + float(word["x1"])) / 2 < upper
            ]
            column_start = min((float(word["x0"]) for word in column_words), default=lower)
            for row in _group_words_into_lines(column_words):
                candidate = _layout_candidate(row, page_number, column_start)
                if candidate is not None:
                    page_candidates.append(candidate)
        candidates_by_page.append(page_candidates)
        if progress:
            progress(page_number, page_count)

    counts = [len(items) for items in candidates_by_page if items]
    median_count = statistics.median(counts) if counts else 0
    minimum_density = max(4, int(median_count * 0.25)) if median_count >= 20 else 1
    entries: list[VocabularyEntry] = []
    for page_number, page_candidates in enumerate(candidates_by_page, start=1):
        if median_count >= 20 and len(page_candidates) < minimum_density:
            issues.append(
                ExtractionIssue(
                    page_number,
                    "low_vocabulary_density",
                    f"候选词条仅 {len(page_candidates)} 条，已作为说明页跳过",
                )
            )
            continue
        entries.extend(page_candidates)

    if not entries:
        raise ExtractionError(
            "没有识别出可配对的英文与中文内容；如果这是扫描件，请安装 OCR 扩展后重试。"
        )
    for sequence, entry in enumerate(entries, start=1):
        entry.sequence = sequence
    entries = _add_flags(entries)
    return ExtractedDocument(
        source_path=path,
        source_hash=file_sha256(path),
        page_count=page_count,
        entries=entries,
        issues=issues,
        extraction_method="layout",
        requires_review=True,
    )


def extract_vocabulary_pdf(
    pdf_path: str | Path,
    progress: ProgressCallback | None = None,
    cancelled: CancelCallback | None = None,
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

    with pdfplumber.open(path) as pdf:
        _check_cancelled(cancelled)
        probe_pages = pdf.pages[: min(5, len(pdf.pages))]
        is_structured_table = any(_table_signature(page) for page in probe_pages)
        if is_structured_table:
            return _extract_table_document(path, pdf, progress, cancelled)
        return _extract_layout_document(path, pdf, progress, cancelled)


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
                "confidence",
                "source_bbox",
                "extraction_method",
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

