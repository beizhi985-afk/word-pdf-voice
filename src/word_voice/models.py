from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


FLAG_LABELS = {
    "missing_phonetic": "缺少注音",
    "missing_meaning": "缺少释义",
    "duplicate_word": "重复拼写",
    "multiple_pronunciations": "包含多个读音",
    "suspicious_word": "单词格式可疑",
    "low_confidence": "识别置信度较低",
    "layout_extracted": "来自复杂版面识别",
}


@dataclass(slots=True)
class VocabularyEntry:
    sequence: int
    word: str
    phonetic: str
    meaning: str
    page: int
    flags: tuple[str, ...] = field(default_factory=tuple)
    pronunciation_override: str = ""
    confidence: float = 1.0
    source_bbox: tuple[float, float, float, float] | None = None
    extraction_method: str = "table"

    @property
    def has_issue(self) -> bool:
        return bool(self.flags)

    @property
    def flag_text(self) -> str:
        return "、".join(FLAG_LABELS.get(flag, flag) for flag in self.flags)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["flags"] = list(self.flags)
        return data


@dataclass(slots=True)
class ExtractionIssue:
    page: int
    code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExtractedDocument:
    source_path: Path
    source_hash: str
    page_count: int
    entries: list[VocabularyEntry]
    issues: list[ExtractionIssue]
    extraction_method: str = "table"
    requires_review: bool = False

    @property
    def min_sequence(self) -> int | None:
        return min((entry.sequence for entry in self.entries), default=None)

    @property
    def max_sequence(self) -> int | None:
        return max((entry.sequence for entry in self.entries), default=None)

    @property
    def flagged_count(self) -> int:
        return sum(entry.has_issue for entry in self.entries)

    def summary(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_hash": self.source_hash,
            "page_count": self.page_count,
            "entry_count": len(self.entries),
            "min_sequence": self.min_sequence,
            "max_sequence": self.max_sequence,
            "flagged_count": self.flagged_count,
            "extraction_issue_count": len(self.issues),
            "extraction_method": self.extraction_method,
            "requires_review": self.requires_review,
        }

