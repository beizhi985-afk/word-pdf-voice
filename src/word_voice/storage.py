from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True, slots=True)
class ImportedProject:
    workspace: ProjectWorkspace
    source_path: Path
    source_hash: str
    page_count: int
    entry_count: int
    flagged_count: int
    audio_ready_count: int
    modified_at: float

    @property
    def display_name(self) -> str:
        return self.source_path.name or self.workspace.root.name


@dataclass(frozen=True, slots=True)
class DatabaseBackup:
    workspace: ProjectWorkspace
    path: Path
    created_at: float
    reason: str

    @property
    def display_time(self) -> str:
        return datetime.fromtimestamp(self.created_at).strftime("%Y-%m-%d %H:%M:%S")


DATA_VERSION = "0.4.0"
LEARNING_STATUSES = ("unrated", "known", "unsure", "unknown")


def _local_data_base() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    return Path(local_app_data) if local_app_data else Path.home() / ".word-pdf-voice"


def _safe_project_name(pdf_path: str | Path) -> str:
    source = Path(pdf_path)
    safe_stem = "".join(ch if ch.isalnum() else "-" for ch in source.stem).strip("-")
    return safe_stem[:80]


def default_workspace_root(pdf_path: str | Path) -> Path:
    return imported_projects_root() / _safe_project_name(pdf_path)


def imported_projects_root() -> Path:
    return _local_data_base() / "WordPdfVoice" / "v0.2" / "projects"


def custom_stickers_root() -> Path:
    return _local_data_base() / "WordPdfVoice" / "v0.2" / "custom-stickers"


def _backup_reason(path: Path) -> str:
    match = re.match(r"\d{8}-\d{6}-(.+)\.sqlite3$", path.name)
    return match.group(1).replace("-", " ") if match else "历史备份"


def _database_is_valid(path: Path) -> bool:
    try:
        with closing(sqlite3.connect(path)) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
        return bool(result and result[0] == "ok")
    except (OSError, sqlite3.Error):
        return False


def create_database_backup(
    database_path: str | Path,
    reason: str = "manual",
    *,
    once_per_day: bool = False,
    keep: int = 12,
) -> Path | None:
    source_path = Path(database_path).expanduser().resolve()
    if not source_path.is_file() or not _database_is_valid(source_path):
        return None
    backup_dir = source_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_reason = re.sub(r"[^a-z0-9-]+", "-", reason.casefold()).strip("-") or "manual"
    date_prefix = datetime.now().strftime("%Y%m%d")
    existing = sorted(backup_dir.glob(f"{date_prefix}-*-{safe_reason}.sqlite3"))
    if once_per_day and existing:
        return existing[-1]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination_path = backup_dir / f"{timestamp}-{safe_reason}.sqlite3"
    suffix = 1
    while destination_path.exists():
        destination_path = backup_dir / f"{timestamp}-{safe_reason}-{suffix}.sqlite3"
        suffix += 1
    with closing(sqlite3.connect(source_path)) as source, closing(
        sqlite3.connect(destination_path)
    ) as destination:
        source.backup(destination)
        destination.commit()
    if not _database_is_valid(destination_path):
        destination_path.unlink(missing_ok=True)
        raise sqlite3.DatabaseError("数据库备份完整性检查失败")
    backups = sorted(backup_dir.glob("*.sqlite3"), key=lambda path: path.stat().st_mtime)
    for expired in backups[:-max(keep, 1)]:
        expired.unlink(missing_ok=True)
    return destination_path


def list_database_backups(
    workspace: ProjectWorkspace | None = None,
    projects_root: str | Path | None = None,
) -> list[DatabaseBackup]:
    if workspace is not None:
        workspace_roots = [workspace.root]
    else:
        root = Path(projects_root).expanduser().resolve() if projects_root else imported_projects_root()
        workspace_roots = [path for path in root.glob("*") if path.is_dir()]
    backups: list[DatabaseBackup] = []
    for workspace_root in workspace_roots:
        project_workspace = ProjectWorkspace.create(workspace_root)
        for path in (workspace_root / "backups").glob("*.sqlite3"):
            if _database_is_valid(path):
                backups.append(
                    DatabaseBackup(
                        workspace=project_workspace,
                        path=path,
                        created_at=path.stat().st_mtime,
                        reason=_backup_reason(path),
                    )
                )
    return sorted(backups, key=lambda item: item.created_at, reverse=True)


def restore_database_backup(backup: DatabaseBackup) -> Path:
    if not _database_is_valid(backup.path):
        raise sqlite3.DatabaseError("所选备份已经损坏，不能恢复")
    target = backup.workspace.database_path
    if target.is_file() and _database_is_valid(target):
        create_database_backup(target, "before-restore")
    temporary = target.with_name("project.restore.sqlite3")
    temporary.unlink(missing_ok=True)
    with closing(sqlite3.connect(backup.path)) as source, closing(
        sqlite3.connect(temporary)
    ) as destination:
        source.backup(destination)
        destination.commit()
    if not _database_is_valid(temporary):
        temporary.unlink(missing_ok=True)
        raise sqlite3.DatabaseError("恢复后的数据库完整性检查失败")
    os.replace(temporary, target)
    return target


def legacy_workspace_root(pdf_path: str | Path) -> Path:
    return _local_data_base() / "WordPdfVoice" / "projects" / _safe_project_name(pdf_path)


def list_imported_projects(projects_root: str | Path | None = None) -> list[ImportedProject]:
    root = Path(projects_root).expanduser().resolve() if projects_root else imported_projects_root()
    if not root.is_dir():
        return []

    projects: list[ImportedProject] = []
    for database_path in root.glob("*/project.sqlite3"):
        try:
            with closing(sqlite3.connect(database_path)) as connection:
                metadata = dict(connection.execute("SELECT key, value FROM metadata").fetchall())
                counts = connection.execute(
                    """
                    SELECT
                        COUNT(*),
                        SUM(CASE WHEN flags_json <> '[]' THEN 1 ELSE 0 END),
                        SUM(CASE WHEN audio_status = 'ready' THEN 1 ELSE 0 END),
                        COALESCE(MAX(page), 0)
                    FROM entries
                    """
                ).fetchone()
            entry_count = int(counts[0] or 0)
            if entry_count == 0:
                continue
            workspace = ProjectWorkspace.create(database_path.parent)
            source_value = metadata.get("source_path", "")
            source_path = Path(source_value) if source_value else Path(workspace.root.name)
            projects.append(
                ImportedProject(
                    workspace=workspace,
                    source_path=source_path,
                    source_hash=metadata.get("source_hash", ""),
                    page_count=int(metadata.get("page_count", "0") or counts[3] or 0),
                    entry_count=entry_count,
                    flagged_count=int(counts[1] or 0),
                    audio_ready_count=int(counts[2] or 0),
                    modified_at=database_path.stat().st_mtime,
                )
            )
        except (OSError, sqlite3.Error, ValueError):
            continue
    return sorted(projects, key=lambda project: (-project.modified_at, project.display_name.lower()))


def open_imported_project(
    project: ImportedProject,
) -> tuple[ExtractedDocument, ProjectWorkspace, "VocabularyStore"]:
    workspace = ProjectWorkspace.create(project.workspace.root)
    store = VocabularyStore(workspace.database_path)
    document = ExtractedDocument(
        source_path=project.source_path,
        source_hash=project.source_hash,
        page_count=project.page_count,
        entries=store.list_entries(),
        issues=[],
    )
    return document, workspace, store


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
        if self.database_path.is_file() and self._needs_v040_migration():
            create_database_backup(
                self.database_path,
                "before-v040-migration",
                once_per_day=True,
            )
        self._initialize()
        if self.entry_count():
            create_database_backup(
                self.database_path,
                "automatic",
                once_per_day=True,
            )

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
                    audio_error TEXT NOT NULL DEFAULT '',
                    audio_profile TEXT NOT NULL DEFAULT '',
                    learning_status TEXT NOT NULL DEFAULT 'unrated'
                );
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(entries)").fetchall()
            }
            if "audio_profile" not in columns:
                connection.execute(
                    "ALTER TABLE entries ADD COLUMN audio_profile TEXT NOT NULL DEFAULT ''"
                )
            if "learning_status" not in columns:
                connection.execute(
                    "ALTER TABLE entries ADD COLUMN learning_status TEXT NOT NULL DEFAULT 'unrated'"
                )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('data_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (DATA_VERSION,),
            )

    def _needs_v040_migration(self) -> bool:
        try:
            with closing(sqlite3.connect(self.database_path)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                if "entries" not in tables:
                    return False
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(entries)").fetchall()
                }
            return "learning_status" not in columns
        except sqlite3.Error:
            return False

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
        if self.entry_count():
            create_database_backup(
                self.database_path,
                "before-reimport",
                once_per_day=True,
            )
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
        learning_filter: str = "all",
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
        if learning_filter == "focus":
            clauses.append("learning_status IN ('unsure', 'unknown')")
        elif learning_filter in LEARNING_STATUSES:
            clauses.append("learning_status = ?")
            parameters.append(learning_filter)
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
                    manually_edited=1, audio_status='missing', audio_path='', audio_error='',
                    audio_profile=''
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
                    pronunciation_override='', manually_edited=0, audio_status='missing',
                    audio_path='', audio_error='', audio_profile=''
                WHERE sequence=?
                """,
                (sequence,),
            )

    def mark_audio_ready(
        self,
        sequence: int,
        audio_path: str | Path,
        audio_profile: str = "",
    ) -> None:
        with self.session() as connection:
            connection.execute(
                "UPDATE entries SET audio_status='ready', audio_path=?, audio_error='', "
                "audio_profile=? WHERE sequence=?",
                (str(Path(audio_path).resolve()), audio_profile, sequence),
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
                "UPDATE entries SET audio_status='missing', audio_path='', audio_error='', "
                "audio_profile='' "
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

    def audio_profile(self, sequence: int) -> str:
        with self.session() as connection:
            row = connection.execute(
                "SELECT audio_profile FROM entries WHERE sequence=?", (sequence,)
            ).fetchone()
        return row["audio_profile"] if row else ""

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

    def set_learning_status(self, sequence: int, status: str) -> None:
        if status not in LEARNING_STATUSES:
            raise ValueError(f"不支持的学习状态：{status}")
        with self.session() as connection:
            connection.execute(
                "UPDATE entries SET learning_status=? WHERE sequence=?",
                (status, sequence),
            )

    def learning_status(self, sequence: int) -> str:
        with self.session() as connection:
            row = connection.execute(
                "SELECT learning_status FROM entries WHERE sequence=?", (sequence,)
            ).fetchone()
        return str(row["learning_status"]) if row else "unrated"

    def learning_status_map(self) -> dict[int, str]:
        with self.session() as connection:
            rows = connection.execute("SELECT sequence, learning_status FROM entries").fetchall()
        return {int(row["sequence"]): str(row["learning_status"]) for row in rows}

    def learning_counts(self) -> dict[str, int]:
        result = {status: 0 for status in LEARNING_STATUSES}
        with self.session() as connection:
            rows = connection.execute(
                "SELECT learning_status, COUNT(*) AS count FROM entries GROUP BY learning_status"
            ).fetchall()
        for row in rows:
            result[str(row["learning_status"])] = int(row["count"])
        return result

    def entry_count(self) -> int:
        with self.session() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM entries").fetchone()
        return int(row["count"])
