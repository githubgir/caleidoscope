"""Tests for database models and session management."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from caleidoscope.db.models import DigestLog, Item
from caleidoscope.db.session import get_session, init_db


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        init_db(db_path)
        yield db_path


def test_init_db_creates_tables(test_db):
    """Test that init_db creates all required tables."""
    session = get_session(test_db)

    try:
        # Check that we can query tables
        items = session.execute(select(Item)).fetchall()
        assert items == []

        digests = session.execute(select(DigestLog)).fetchall()
        assert digests == []

    finally:
        session.close()


def test_insert_and_query_item(test_db):
    """Test inserting and querying an Item."""
    session = get_session(test_db)

    try:
        # Create an item
        item = Item(
            url="https://example.com/article",
            url_hash="abc123",
            title="Test Article",
            published_at=datetime(2024, 1, 1).isoformat(),
            collected_at=datetime.utcnow().isoformat(),
            source="test_source",
            entity="Test Entity",
            category="news",
            body="This is a test article body.",
            tags='["test", "example"]',
        )

        session.add(item)
        session.commit()

        # Query it back
        retrieved = session.execute(select(Item).where(Item.url_hash == "abc123")).scalar_one()

        assert retrieved.title == "Test Article"
        assert retrieved.source == "test_source"
        assert retrieved.entity == "Test Entity"
        assert retrieved.category == "news"
        assert retrieved.body == "This is a test article body."

    finally:
        session.close()


def test_url_hash_unique_constraint(test_db):
    """Test that url_hash has a unique constraint."""
    session = get_session(test_db)

    try:
        # Create first item
        item1 = Item(
            url="https://example.com/article",
            url_hash="duplicate_hash",
            title="First Article",
            collected_at=datetime.utcnow().isoformat(),
            source="test",
        )
        session.add(item1)
        session.commit()

        # Try to create second item with same hash
        item2 = Item(
            url="https://example.com/article2",
            url_hash="duplicate_hash",
            title="Second Article",
            collected_at=datetime.utcnow().isoformat(),
            source="test",
        )
        session.add(item2)

        # Should raise an IntegrityError
        with pytest.raises(Exception):  # SQLAlchemy will wrap this
            session.commit()

    finally:
        session.close()


def test_digest_log_creation(test_db):
    """Test creating a DigestLog entry."""
    session = get_session(test_db)

    try:
        digest = DigestLog(
            generated_at=datetime.utcnow().isoformat(),
            cadence="daily",
            item_count=42,
            digest_md="# Test Digest\n\nContent here.",
        )

        session.add(digest)
        session.commit()

        # Query it back
        retrieved = session.execute(select(DigestLog)).scalar_one()

        assert retrieved.cadence == "daily"
        assert retrieved.item_count == 42
        assert "# Test Digest" in retrieved.digest_md

    finally:
        session.close()


def test_item_nullable_fields(test_db):
    """Test that nullable fields can be None."""
    session = get_session(test_db)

    try:
        # Create minimal item
        item = Item(
            url="https://example.com/minimal",
            url_hash="minimal123",
            title="Minimal Article",
            collected_at=datetime.utcnow().isoformat(),
            source="test",
            # All optional fields left as None
        )

        session.add(item)
        session.commit()

        # Query it back
        retrieved = session.execute(
            select(Item).where(Item.url_hash == "minimal123")
        ).scalar_one()

        assert retrieved.published_at is None
        assert retrieved.entity is None
        assert retrieved.category is None
        assert retrieved.body is None
        assert retrieved.summary is None
        assert retrieved.tags is None

    finally:
        session.close()
