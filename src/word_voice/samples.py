from __future__ import annotations

from .models import VocabularyEntry


SPECIAL_SAMPLE_SEQUENCES = (48, 147, 583, 616, 804, 3756)


def select_pronunciation_samples(
    entries: list[VocabularyEntry], count: int = 30
) -> list[VocabularyEntry]:
    """Select deterministic, spread-out samples plus known edge cases."""
    if count <= 0 or not entries:
        return []
    by_sequence = {entry.sequence: entry for entry in entries}
    selected: list[VocabularyEntry] = []
    seen: set[int] = set()

    def add(entry: VocabularyEntry | None) -> None:
        if entry and entry.sequence not in seen and len(selected) < count:
            selected.append(entry)
            seen.add(entry.sequence)

    for sequence in SPECIAL_SAMPLE_SEQUENCES:
        add(by_sequence.get(sequence))
    for entry in entries:
        if entry.has_issue:
            add(entry)
    if len(selected) < count:
        remaining = count - len(selected)
        step = max(1, len(entries) // remaining)
        for index in range(0, len(entries), step):
            add(entries[index])
    for entry in sorted(entries, key=lambda item: len(item.word), reverse=True):
        add(entry)
    return sorted(selected[:count], key=lambda item: item.sequence)

