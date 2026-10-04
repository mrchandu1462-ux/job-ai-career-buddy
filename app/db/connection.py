"""SQLite database connection management and pragmas."""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from app.config import settings
from app.db.schema import create_schema


def get_connection(
    db_path: str | Path | None = None, auto_init: bool = True
) -> sqlite3.Connection:
    """Create and configure a SQLite connection with robust pragmas and idempotent schema auto-initialization."""
    if db_path is None:
        target_path = settings.data_dir / "job_ai.db"
    elif isinstance(db_path, str) and db_path == ":memory:":
        target_path = ":memory:"
    else:
        target_path = Path(db_path)

    if isinstance(target_path, Path):
        target_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target_path))
        conn.execute("PRAGMA journal_mode = WAL;")
    else:
        conn = sqlite3.connect(":memory:")

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    if auto_init:
        create_schema(conn)
    return conn


get_db_connection = get_connection


class DatabaseConnection:
    """Database connection wrapper with auto-initialization."""

    def __init__(self, db_path: str | Path | None = None, auto_init: bool = True):
        self.db_path = db_path
        self._conn = get_connection(db_path, auto_init=auto_init)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


@contextmanager
def get_db(
    db_path: str | Path | None = None, auto_init: bool = True
) -> Generator[sqlite3.Connection, None, None]:
    """Context manager yielding an initialized database connection."""
    db = DatabaseConnection(db_path=db_path, auto_init=auto_init)
    try:
        yield db.conn
    finally:
        db.close()
