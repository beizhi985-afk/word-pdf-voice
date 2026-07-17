from __future__ import annotations

import json
import os
import shutil
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import ExtractedDocument, VocabularyEntry


@dataclass(frozen=True, slots=True)
class ProjectWorkspace:
    root: Path
    database_path: Path
    audio_dir: Path
    export_dir: Path

    @classmethod
    def create(cls, root: str | Path) -> "ProjectWorkspace":
        root_path = Path(root).expanduser().resolve()
        audio_dir = root_path / "audio"
        export_dir = root_path / "exports"
        audio_dir.mkdir(parents=True, exist_ok=True)
        export_dir.mkdir(parents=True, exist_ok=True)
        return cls(root_path, root_path / "project.sqlite3", audio_dir, export_dir)


@dataclass(frozen=True, slots=True)
class WorkspaceMigration:
    performed: bool
    copied_audio: int = 0
    unavailable_audio: int = 0
    source_root: Path | None = None


def _local_data_base() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    return Path(local_app_data) if local_app_data else Path.home() / ".word-pdf-voice"


def _safe_project_name(pdf_path: str | Path) -> str:
    source = Path(pdf_path)
    safe_stem = "".join(ch if ch.isalnum() else "-" for ch in source.stem).strip("-")
    return safe_stem[:80]


def default_workspace_root(pdf_path: str | Path) -> Path:
    return _local_data_base() / "WordPdfVoice" / "v0.2" / "projects" / _safe_project_name(pdf_path)


def legacy_workspace_root(pdf_path: str | Path) -> Path:
    return _local_data_base() / "WordPdfVoice" / "projects" / _safe_project_name(pdf_path)


def prepare_default_workspace(
    pdf_path: str | Path,
) -> tuple[ProjectWorkspace, WorkspaceMigration]:
    workspace = ProjectWorkspace.create(default_workspace_root(pdf_path))
    migration = migrate_legacy_workspace(legacy_workspace_root(pdf_path), workspace)
    return workspace, migration


def migrate_legacy_workspace(
    legacy_root: str | Path,
    target: ProjectWorkspace,
) -> WorkspaceMigration:
    """Create an independent v0.2 snapshot of a v0.1 project once."""
    source_root = Path(legacy_root).expanduser().resolve()
    source_database = source_root / "project.sqlite3"
    if target.database_path.exists() or not source_database.is_file():
        return WorkspaceMigration(False, source_root=source_root)

    target.database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source_database)) as source, closing(
        sqlite3.connect(target.database_path)
    ) as destination:
        source.backup(destination)
        destination.commit()

    store = VocabularyStore(target.database_path)
    copied = 0
    unavailable = 0
    with store.session() as connection:
        rows = connection.execute(
            "SELECT sequence, audio_path FROM entries WHERE audio_status='ready'"
        ).fetchall()
    for row in rows:
        source_audio = Path(row["audio_path"]) if row["audio_path"] else None
        if not source_audio or not source_audio.is_file():
            store.mark_audio_missing(int(row["sequence"]))
            unavailable += 1
            continue
        target_audio = target.audio_dir / source_audio.name
        try:
            shutil.copy2(source_audio, target_audio)
        except OSError:
            store.mark_audio_missing(int(row["sequence"]))
            unavailable += 1
            continue
        store.mark_audio_ready(int(row["sequence"]), target_audio)
        copied += 1
    store.set_metadata("data_version", "0.2")
    store.set_metadata("migrated_from", str(source_root))
    return WorkspaceMigration(True, copied, unavailable, source_root)


class VocabularyStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS entries (
                    sequence INTEGER PRIMARY KEY,
                    source_word TEXT NOT NULL,
                    source_phonetic TEXT NOT NULL,
                    source_meaning TEXT NOT NULL,
                    word TEXT NOT NULL,
                    phonetic TEXT NOT NULL,
                    meaning TEXT NOT NULL,
                    page INTEGER NOT NULL,
                    flags_json TEXT NOT NULL DEFAULT '[]',
                    pronunciation_override TEXT NOT NULL DEFAULT '',
                    manually_edited INTEGER NOT NULL DEFAULT 0,
                    audio_status TEXT NOT NULL DEFAULT 'missing',
                    audio_path TEXT NOT NULL DEFAULT '',
                    audio_error TEXT NOT NULL DEFAULT ''
                );
                """
            )

    def set_metadata(self, key: str, value: str) -> None:
        with self.session() as connection:
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_metadata(self, key: str, default: str = "") -> str:
        with self.session() as connection:
            row = connection.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def import_document(self, document: ExtractedDocument) -> None:
        with self.session() as connection:
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('source_path', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(document.source_path),),
            )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('source_hash', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (document.source_hash,),
            )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('page_count', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(document.page_count),),
            )
            for entry in document.entries:
                connection.execute(
                    """
                    INSERT INTO entries(
                        sequence, source_word, source_phonetic, source_meaning,
                        word, phonetic, meaning, page, flags_json, pronunciation_override
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(sequence) DO UPDATE SET
                        source_word=excluded.source_word,
                        source_phonetic=excluded.source_phonetic,
                        source_meaning=excluded.source_meaning,
                        word=CASE WHEN entries.manually_edited=0 THEN excluded.word ELSE entries.word END,
                        phonetic=CASE WHEN entries.manually_edited=0 THEN excluded.phonetic ELSE entries.phonetic END,
                        meaning=CASE WHEN entries.manually_edited=0 THEN excluded.meaning ELSE entries.meaning END,
                        page=excluded.page,
                        flags_json=excluded.flags_json
                    """,
                    (
                        entry.sequence,
                        entry.word,
                        entry.phonetic,
                        entry.meaning,
                        entry.word,
                        entry.phonetic,
                        entry.meaning,
                        entry.page,
                        json.dumps(list(entry.flags), ensure_ascii=False),
                        entry.pronunciation_override,
                    ),
                )

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> VocabularyEntry:
        return VocabularyEntry(
            sequence=row["sequence"],
            word=row["word"],
            phonetic=row["phonetic"],
            meaning=row["meaning"],
            page=row["page"],
            flags=tuple(json.loads(row["flags_json"])),
            pronunciation_override=row["pronunciation_override"],
        )

    def list_entries(
        self,
        search: str = "",
        issues_only: bool = False,
        limit: int | None = None,
        audio_ready_only: bool = False,
    ) -> list[VocabularyEntry]:
        query = "SELECT * FROM entries"
        clauses: list[str] = []
        parameters: list[object] = []
        if search:
            clauses.append("(word LIKE ? OR phonetic LIKE ? OR meaning LIKE ?)")
            pattern = f"%{search}%"
            parameters.extend((pattern, pattern, pattern))
        if issues_only:
            clauses.append("flags_json <> '[]'")
        if audio_ready_only:
            clauses.append("audio_status = 'ready'")
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY sequence"
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        with self.session() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_entry(self, sequence: int) -> VocabularyEntry | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM entries WHERE sequence=?", (sequence,)
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def update_entry(
        self,
        sequence: int,
        word: str,
        phonetic: str,
        meaning: str,
        pronunciation_override: str = "",
    ) -> None:
        with self.session() as connection:
            connection.execute(
                """
                UPDATE entries
                SET word=?, phonetic=?, meaning=?, pronunciation_override=?,
                    manually_edited=1, audio_status='missing', audio_path='', audio_error=''
                WHERE sequence=?
                """,
                (word.strip(), phonetic.strip(), meaning.strip(), pronunciation_override.strip(), sequence),
            )

    def reset_entry(self, sequence: int) -> None:
        with self.session() as connection:
            connection.execute(
                """
                UPDATE entries
                SET word=source_word, phonetic=source_phonetic, meaning=source_meaning,
                    pronunciation_override='', manually_edited=0,
                    audio_status='missing', audio_path='', audio_error=''
                WHERE sequence=?
                """,
                (sequence,),
            )

    def mark_audio_ready(self, sequence: int, audio_path: str | Path) -> None:
        with self.session() as connection:
            connection.execute(
                "UPDATE entries SET audio_status='ready', audio_path=?, audio_error='' WHERE sequence=?",
                (str(Path(audio_path).resolve()), sequence),
            )

    def mark_audio_failed(self, sequence: int, error: str) -> None:
        with self.session() as connection:
            connection.execute(
                "UPDATE entries SET audio_status='failed', audio_error=? WHERE sequence=?",
                (error[:1000], sequence),
            )

    def mark_audio_missing(self, sequence: int) -> None:
        with self.session() as connection:
            connection.execute(
                "UPDATE entries SET audio_status='missing', audio_path='', audio_error='' "
                "WHERE sequence=?",
                (sequence,),
            )

    def audio_record(self, sequence: int) -> tuple[str, str, str]:
        with self.session() as connection:
            row = connection.execute(
                "SELECT audio_status, audio_path, audio_error FROM entries WHERE sequence=?",
                (sequence,),
            ).fetchone()
        if not row:
            return "missing", "", ""
        return row["audio_status"], row["audio_path"], row["audio_error"]

    def audio_counts(self) -> dict[str, int]:
        result = {"missing": 0, "ready": 0, "failed": 0}
        with self.session() as connection:
            rows = connection.execute(
                "SELECT audio_status, COUNT(*) AS count FROM entries GROUP BY audio_status"
            ).fetchall()
        for row in rows:
            result[row["audio_status"]] = row["count"]
        return result

    def audio_status_map(self) -> dict[int, str]:
        with self.session() as connection:
            rows = connection.execute("SELECT sequence, audio_status FROM entries").fetchall()
        return {int(row["sequence"]): row["audio_status"] for row in rows}

    def entry_count(self) -> int:
        with self.session() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM entries").fetchone()
        return int(row["count"])
