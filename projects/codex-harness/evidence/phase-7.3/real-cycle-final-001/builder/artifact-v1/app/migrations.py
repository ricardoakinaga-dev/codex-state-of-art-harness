"""Bounded, checksum-checked SQLite migrations for the pilot."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .db import Database

MAX_MIGRATIONS = 32
MAX_MIGRATION_BYTES = 64 * 1024
MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{3,9})_(?P<name>[a-z0-9][a-z0-9_-]*)\.sql$")
REQUIRED_TABLES = frozenset(
    {
        "schema_migrations",
        "actors",
        "clients",
        "patients",
        "providers",
        "appointments",
        "idempotency_keys",
    }
)
REQUIRED_TRIGGERS = frozenset(
    {
        "appointments_actor_client_match_insert",
        "appointments_actor_client_match_update",
        "appointments_patient_client_match_insert",
        "appointments_patient_client_match_update",
        "actors_client_reassignment_guard",
        "patients_client_reassignment_guard",
    }
)
REQUIRED_TRIGGER_FRAGMENTS = {
    "appointments_actor_client_match_insert": (
        "BEFORE INSERT ON APPOINTMENTS",
        "NEW.ACTOR_ID",
        "NEW.CLIENT_ID",
        "RAISE(ABORT",
    ),
    "appointments_actor_client_match_update": (
        "BEFORE UPDATE OF ACTOR_ID, CLIENT_ID ON APPOINTMENTS",
        "NEW.ACTOR_ID",
        "NEW.CLIENT_ID",
        "RAISE(ABORT",
    ),
    "appointments_patient_client_match_insert": (
        "BEFORE INSERT ON APPOINTMENTS",
        "NEW.PATIENT_ID",
        "NEW.CLIENT_ID",
        "RAISE(ABORT",
    ),
    "appointments_patient_client_match_update": (
        "BEFORE UPDATE OF PATIENT_ID, CLIENT_ID ON APPOINTMENTS",
        "NEW.PATIENT_ID",
        "NEW.CLIENT_ID",
        "RAISE(ABORT",
    ),
    "actors_client_reassignment_guard": (
        "BEFORE UPDATE OF CLIENT_ID ON ACTORS",
        "OLD.ID",
        "NEW.CLIENT_ID",
        "APPOINTMENTS",
        "RAISE(ABORT",
    ),
    "patients_client_reassignment_guard": (
        "BEFORE UPDATE OF CLIENT_ID ON PATIENTS",
        "OLD.ID",
        "NEW.CLIENT_ID",
        "APPOINTMENTS",
        "RAISE(ABORT",
    ),
}


class MigrationError(RuntimeError):
    """Raised when migration input or migration state is unsafe."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path
    contents: bytes
    checksum: str


@dataclass(frozen=True, slots=True)
class MigrationReport:
    applied_versions: tuple[int, ...]
    verified_tables: tuple[str, ...]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _iter_statements(contents: bytes) -> Iterable[str]:
    """Split the small SQL fixture without ``executescript`` transaction leaks."""

    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MigrationError("migration is not valid UTF-8") from exc
    buffer = ""
    for line in text.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement and not statement.startswith("--"):
                yield statement
    if buffer.strip():
        raise MigrationError("migration contains an incomplete SQL statement")


class MigrationRunner:
    def __init__(self, database: Database, migrations_dir: str | Path) -> None:
        self.database = database
        self.migrations_dir = Path(migrations_dir)

    def _discover(self) -> tuple[Migration, ...]:
        if self.migrations_dir.is_symlink():
            raise MigrationError("migration directory symlinks are not allowed")
        root = self.migrations_dir.resolve()
        if not root.exists() or not root.is_dir():
            raise MigrationError("migration directory is missing")
        migrations: list[Migration] = []
        for path in sorted(root.iterdir(), key=lambda candidate: candidate.name):
            if path.is_symlink():
                raise MigrationError("migration symlinks are not allowed")
            if not path.is_file():
                continue
            match = MIGRATION_NAME.fullmatch(path.name)
            if match is None:
                if path.suffix == ".sql":
                    raise MigrationError("migration filename is not safely ordered")
                continue
            resolved = path.resolve()
            if resolved.parent != root:
                raise MigrationError("migration path escapes its directory")
            contents = path.read_bytes()
            if len(contents) > MAX_MIGRATION_BYTES:
                raise MigrationError("migration is too large")
            migrations.append(
                Migration(
                    version=int(match.group("version")),
                    name=path.stem,
                    path=path,
                    contents=contents,
                    checksum=hashlib.sha256(contents).hexdigest(),
                )
            )
        if not migrations:
            raise MigrationError("no migrations found")
        if len(migrations) > MAX_MIGRATIONS:
            raise MigrationError("too many migrations")
        migrations.sort(key=lambda migration: migration.version)
        versions = [migration.version for migration in migrations]
        if len(set(versions)) != len(versions):
            raise MigrationError("migration versions must be unique")
        return tuple(migrations)

    @staticmethod
    def _has_schema_migrations(connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("schema_migrations",),
        ).fetchone()
        return row is not None

    def _applied(self, connection: sqlite3.Connection) -> dict[int, tuple[str, str]]:
        if not self._has_schema_migrations(connection):
            return {}
        rows = connection.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
        return {int(row[0]): (str(row[1]), str(row[2])) for row in rows}

    def migrate(self, *, fail_after: int | None = None) -> MigrationReport:
        if fail_after is not None and fail_after < 0:
            raise ValueError("fail_after must be non-negative")
        migrations = self._discover()
        connection = self.database.connection()
        try:
            # Acquire SQLite's cross-process write lock before reading the
            # applied set. Without this transaction, two fresh processes can
            # both observe an absent schema_migrations table and race through
            # the first CREATE TABLE statement.
            connection.execute("BEGIN IMMEDIATE")
            applied = self._applied(connection)
            known_versions = {migration.version for migration in migrations}
            if set(applied) - known_versions:
                raise MigrationError("database contains an unknown migration version")

            pending_seen = False
            for migration in migrations:
                if migration.version in applied:
                    if pending_seen:
                        raise MigrationError("applied migrations are not an ordered prefix")
                else:
                    pending_seen = True

            applied_versions: list[int] = []
            statement_count = 0
            for migration in migrations:
                recorded = applied.get(migration.version)
                if recorded is not None:
                    if recorded != (migration.name, migration.checksum):
                        raise MigrationError(
                            f"migration checksum drift at version {migration.version}"
                        )
                    continue
                for statement in _iter_statements(migration.contents):
                    if fail_after is not None and statement_count >= fail_after:
                        raise MigrationError("injected migration failure before commit")
                    connection.execute(statement)
                    statement_count += 1
                if not self._has_schema_migrations(connection):
                    raise MigrationError("first migration did not create schema_migrations")
                if fail_after is not None and statement_count >= fail_after:
                    raise MigrationError("injected migration failure before commit")
                connection.execute(
                    "INSERT INTO schema_migrations(version, name, checksum, applied_at) "
                    "VALUES (?, ?, ?, ?)",
                    (migration.version, migration.name, migration.checksum, _utc_now()),
                )
                applied_versions.append(migration.version)

            self.verify_schema(connection)
            connection.commit()
            return MigrationReport(tuple(applied_versions), tuple(sorted(REQUIRED_TABLES)))
        except MigrationError:
            connection.rollback()
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            connection.rollback()
            raise MigrationError("migration failed and was rolled back") from exc

    @staticmethod
    def verify_schema(connection: sqlite3.Connection) -> None:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing = REQUIRED_TABLES - tables
        if missing:
            raise MigrationError("schema is missing required tables")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise MigrationError("foreign key enforcement is disabled")

        for table in REQUIRED_TABLES:
            table_sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()[0]
            if "CHECK" not in table_sql.upper():
                raise MigrationError("schema checks are missing")

        expected_foreign_keys = {
            "actors": {("client_id", "clients", "id")},
            "patients": {("client_id", "clients", "id")},
            "appointments": {
                ("actor_id", "actors", "id"),
                ("client_id", "clients", "id"),
                ("patient_id", "patients", "id"),
                ("provider_id", "providers", "id"),
            },
            "idempotency_keys": {
                ("actor_id", "actors", "id"),
                ("appointment_id", "appointments", "id"),
            },
        }
        for table, expected in expected_foreign_keys.items():
            actual = {
                (str(row[1]), str(row[0]), str(row[2]))
                for row in connection.execute(
                    'SELECT "table", "from", "to" FROM pragma_foreign_key_list(?)',
                    (table,),
                ).fetchall()
            }
            if actual != expected:
                raise MigrationError("schema foreign keys are missing")

        indexes = connection.execute("PRAGMA index_list('appointments')").fetchall()
        has_slot_index = False
        for index in indexes:
            if int(index[2]) != 1:
                continue
            columns = [
                str(row[2])
                for row in connection.execute(
                    "SELECT seqno, cid, name FROM pragma_index_info(?)",
                    (str(index[1]),),
                ).fetchall()
            ]
            if columns == ["provider_id", "starts_at"]:
                has_slot_index = True
                break
        if not has_slot_index:
            raise MigrationError("provider/start unique constraint is missing")

        idempotency_columns = {
            str(row[1]): int(row[5])
            for row in connection.execute("PRAGMA table_info('idempotency_keys')").fetchall()
        }
        if idempotency_columns.get("actor_id") != 1 or idempotency_columns.get("key") != 2:
            raise MigrationError("idempotency primary key is missing")

        trigger_sql = {
            str(row[0]): re.sub(r"\s+", " ", str(row[1]).upper()).strip()
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"
            ).fetchall()
        }
        trigger_names = set(trigger_sql)
        if not REQUIRED_TRIGGERS.issubset(trigger_names):
            raise MigrationError("appointment ownership triggers are missing")
        for name, fragments in REQUIRED_TRIGGER_FRAGMENTS.items():
            definition = trigger_sql.get(name, "")
            if any(fragment not in definition for fragment in fragments):
                raise MigrationError("appointment ownership trigger definition is unsafe")
