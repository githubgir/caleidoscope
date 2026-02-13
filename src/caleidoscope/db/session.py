"""Database session management and initialization."""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from caleidoscope.db.models import Base


def get_engine(db_path: str = "data/caleidoscope.db"):
    """Return SQLAlchemy engine for the SQLite database.

    Creates parent directories if they don't exist.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        SQLAlchemy Engine instance
    """
    # Ensure parent directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # Create engine with SQLite-specific settings
    engine = create_engine(
        f"sqlite:///{db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    return engine


def get_session(db_path: str | None = None) -> Session:
    """Return a new database session.

    Args:
        db_path: Path to the SQLite database file (optional)

    Returns:
        SQLAlchemy Session instance
    """
    if db_path is None:
        db_path = "data/caleidoscope.db"

    engine = get_engine(db_path)
    return Session(engine)


def init_db(db_path: str | None = None):
    """Create all tables, FTS5 virtual table, and triggers.

    Args:
        db_path: Path to the SQLite database file (optional)
    """
    if db_path is None:
        db_path = "data/caleidoscope.db"

    engine = get_engine(db_path)

    # Create all standard tables via SQLAlchemy
    Base.metadata.create_all(engine)

    # Create FTS5 virtual table and triggers via raw SQL
    with engine.connect() as conn:
        # Create FTS5 virtual table
        conn.execute(
            text(
                """
            CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
                title, body, tags,
                content='items',
                content_rowid='rowid'
            )
        """
            )
        )

        # Trigger for INSERT
        conn.execute(
            text(
                """
            CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
                INSERT INTO items_fts(rowid, title, body, tags)
                VALUES (new.rowid, new.title, new.body, new.tags);
            END
        """
            )
        )

        # Trigger for DELETE
        conn.execute(
            text(
                """
            CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
                INSERT INTO items_fts(items_fts, rowid, title, body, tags)
                VALUES ('delete', old.rowid, old.title, old.body, old.tags);
            END
        """
            )
        )

        conn.commit()

    print(f"✓ Database initialized at {db_path}")
