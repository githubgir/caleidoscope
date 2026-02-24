"""
Tests for the search engine.
"""
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from caleidoscope.db.models import Base, Item
from caleidoscope.db.session import get_engine, init_db
from caleidoscope.search.engine import search, SearchResult
from sqlalchemy.orm import Session


@pytest.fixture
def temp_db():
    """Create a temporary database with test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Initialize database
        init_db(str(db_path))

        # Create test data
        engine = get_engine(str(db_path))
        session = Session(engine)

        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        last_week = now - timedelta(days=7)
        last_month = now - timedelta(days=30)

        test_items = [
            Item(
                url="https://example.com/msci-esg-1",
                url_hash="hash1",
                title="MSCI Launches New ESG Index",
                published_at=now.isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="msci",
                entity="MSCI",
                category="index_launch",
                body="MSCI announced the launch of a new ESG-focused index for emerging markets.",
                tags='["ESG", "emerging_markets"]'
            ),
            Item(
                url="https://example.com/sp-climate-2",
                url_hash="hash2",
                title="S&P DJI Updates Climate Methodology",
                published_at=yesterday.isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="sp_dji",
                entity="S&P DJI",
                category="methodology_change",
                body="S&P Dow Jones Indices updated its climate index methodology to include new metrics.",
                tags='["climate", "methodology"]'
            ),
            Item(
                url="https://example.com/msci-research-3",
                url_hash="hash3",
                title="MSCI Research: ESG Performance Analysis",
                published_at=last_week.isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="msci",
                entity="MSCI",
                category="research",
                body="New MSCI research examines the correlation between ESG scores and financial performance.",
                tags='["ESG", "research"]'
            ),
            Item(
                url="https://example.com/blackrock-etf-4",
                url_hash="hash4",
                title="BlackRock Launches Low-Cost Index ETF",
                published_at=last_month.isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="blackrock",
                entity="BlackRock",
                category="etf_launch",
                body="BlackRock iShares launches a new low-cost broad market index ETF.",
                tags='["ETF", "index"]'
            ),
            Item(
                url="https://example.com/ftse-5",
                url_hash="hash5",
                title="FTSE Russell Announces Index Review",
                published_at=yesterday.isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="ftse",
                entity="FTSE Russell",
                category="methodology_change",
                body="FTSE Russell conducts annual index review with several constituent changes.",
                tags='["index", "review"]'
            ),
        ]

        for item in test_items:
            session.add(item)

        session.commit()
        session.close()

        yield str(db_path)


def test_search_basic(temp_db):
    """Test basic search functionality."""
    results = search("MSCI", db_path=temp_db)

    assert len(results) >= 2  # At least 2 MSCI items
    assert all(isinstance(r, SearchResult) for r in results)
    assert all("MSCI" in r.title or "MSCI" in (r.entity or "") for r in results)


def test_search_with_source_filter(temp_db):
    """Test search with source filter."""
    results = search("index", db_path=temp_db, source="msci")

    assert len(results) >= 1
    assert all(r.source == "msci" for r in results)


def test_search_with_entity_filter(temp_db):
    """Test search with entity filter."""
    results = search("index", db_path=temp_db, entity="BlackRock")

    assert len(results) >= 1
    assert all(r.entity == "BlackRock" for r in results)


def test_search_with_category_filter(temp_db):
    """Test search with category filter."""
    results = search("index", db_path=temp_db, category="index_launch")

    assert len(results) >= 1
    assert all(r.category == "index_launch" for r in results)


def test_search_with_since_relative(temp_db):
    """Test search with relative date filter."""
    # Search for items in last 7 days
    results = search("index", db_path=temp_db, since="7d")

    # Should exclude the month-old item
    assert all(r.title != "BlackRock Launches Low-Cost Index ETF" for r in results)


def test_search_with_since_iso(temp_db):
    """Test search with ISO date filter."""
    now = datetime.utcnow()
    two_days_ago = (now - timedelta(days=2)).isoformat() + 'Z'

    results = search("index", db_path=temp_db, since=two_days_ago)

    # Should only get recent items
    assert len(results) >= 1


def test_search_empty_query(temp_db):
    """Test that empty query returns empty results."""
    results = search("", db_path=temp_db)

    assert results == []


def test_search_no_results(temp_db):
    """Test search with no matching results."""
    results = search("nonexistent_keyword_xyz", db_path=temp_db)

    assert len(results) == 0


def test_search_pagination(temp_db):
    """Test search pagination."""
    # Get first page
    page1 = search("index", db_path=temp_db, limit=2, offset=0)

    # Get second page
    page2 = search("index", db_path=temp_db, limit=2, offset=2)

    # Pages should be different
    if len(page1) > 0 and len(page2) > 0:
        assert page1[0].id != page2[0].id


def test_search_snippet(temp_db):
    """Test that snippets are generated."""
    results = search("ESG", db_path=temp_db)

    assert len(results) >= 1
    # At least some results should have snippets
    assert any(r.snippet is not None for r in results)


def test_search_result_fields(temp_db):
    """Test that SearchResult has all required fields."""
    results = search("MSCI", db_path=temp_db, limit=1)

    assert len(results) >= 1
    result = results[0]

    assert result.id is not None
    assert result.title is not None
    assert result.url is not None
    assert result.source is not None
    # entity, category, published_at, snippet can be None but should exist
    assert hasattr(result, 'entity')
    assert hasattr(result, 'category')
    assert hasattr(result, 'published_at')
    assert hasattr(result, 'snippet')


def test_search_esg_term(temp_db):
    """Test searching for ESG specifically."""
    results = search("ESG", db_path=temp_db)

    assert len(results) >= 2  # We have 2 ESG-related items
    assert all("ESG" in r.title or "ESG" in (r.body or "") for r in results if r.snippet)
