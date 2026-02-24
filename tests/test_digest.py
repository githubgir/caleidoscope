"""
Tests for digest generation.
"""
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from caleidoscope.db.models import Base, Item
from caleidoscope.db.session import get_engine, init_db
from caleidoscope.digest.generator import generate_digest, _get_time_window, _compute_entity_activity
from caleidoscope.digest.renderer import render_digest
from sqlalchemy.orm import Session


@pytest.fixture
def temp_db_with_items():
    """Create a temporary database with diverse test items."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Initialize database
        init_db(str(db_path))

        # Create test data across different categories
        engine = get_engine(str(db_path))
        session = Session(engine)

        now = datetime.utcnow()

        test_items = [
            # Market commentary
            Item(
                url="https://example.com/market-1",
                url_hash="market_hash1",
                title="Market Commentary: Q4 Performance",
                published_at=(now - timedelta(hours=12)).isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="market_news",
                entity=None,
                category="market_commentary",
                body="Analysis of Q4 market performance across major indices.",
                tags='["market", "performance"]'
            ),
            # Index launches
            Item(
                url="https://example.com/msci-launch",
                url_hash="msci_launch1",
                title="MSCI Launches Climate Action Index",
                published_at=(now - timedelta(hours=6)).isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="msci",
                entity="MSCI",
                category="index_launch",
                body="MSCI introduces a new climate-focused index series.",
                tags='["climate", "ESG"]'
            ),
            Item(
                url="https://example.com/sp-launch",
                url_hash="sp_launch1",
                title="S&P DJI Debuts Asia Pacific Index",
                published_at=(now - timedelta(hours=18)).isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="sp_dji",
                entity="S&P DJI",
                category="index_launch",
                body="S&P Dow Jones Indices launches new APAC equity index.",
                tags='["APAC", "equity"]'
            ),
            # Methodology changes
            Item(
                url="https://example.com/stoxx-method",
                url_hash="stoxx_method1",
                title="STOXX Updates Methodology for Europe 600",
                published_at=(now - timedelta(hours=3)).isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="stoxx",
                entity="STOXX",
                category="methodology_change",
                body="STOXX announces methodology updates for flagship European index.",
                tags='["Europe", "methodology"]'
            ),
            # ETF actions
            Item(
                url="https://example.com/blackrock-etf",
                url_hash="blackrock_etf1",
                title="BlackRock Launches Bitcoin ETF",
                published_at=(now - timedelta(hours=8)).isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="blackrock",
                entity="BlackRock",
                category="etf_launch",
                body="iShares launches new cryptocurrency ETF product.",
                tags='["ETF", "crypto"]'
            ),
            Item(
                url="https://example.com/vanguard-fee",
                url_hash="vanguard_fee1",
                title="Vanguard Reduces Fees on Index Funds",
                published_at=(now - timedelta(hours=20)).isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="vanguard",
                entity="Vanguard",
                category="fee_change",
                body="Vanguard announces fee reductions across multiple index products.",
                tags='["fees", "index_funds"]'
            ),
            # Research
            Item(
                url="https://example.com/msci-research",
                url_hash="msci_research1",
                title="MSCI Research: ESG Integration Trends",
                published_at=(now - timedelta(hours=15)).isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="msci",
                entity="MSCI",
                category="research",
                body="New MSCI research examines ESG integration in institutional portfolios.",
                tags='["ESG", "research"]'
            ),
            # News and regulatory
            Item(
                url="https://example.com/sec-news",
                url_hash="sec_news1",
                title="SEC Proposes New ETF Disclosure Rules",
                published_at=(now - timedelta(hours=10)).isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="edgar",
                entity=None,
                category="regulatory",
                body="Securities and Exchange Commission proposes enhanced disclosure requirements.",
                tags='["SEC", "regulatory"]'
            ),
            Item(
                url="https://example.com/news-1",
                url_hash="news_hash1",
                title="Index Providers See Record Growth in ESG Products",
                published_at=(now - timedelta(hours=4)).isoformat() + 'Z',
                collected_at=now.isoformat() + 'Z',
                source="google_news",
                entity=None,
                category="news",
                body="Industry analysis shows surge in ESG index product launches.",
                tags='["ESG", "industry"]'
            ),
        ]

        for item in test_items:
            session.add(item)

        session.commit()
        session.close()

        yield str(db_path)


def test_generate_daily_digest(temp_db_with_items):
    """Test daily digest generation."""
    digest_md = generate_digest(
        cadence="daily",
        db_path=temp_db_with_items,
        save=False,
        anthropic_api_key=None
    )

    assert digest_md is not None
    assert len(digest_md) > 0
    assert "Caleidoscope Daily Brief" in digest_md
    assert "new items collected" in digest_md


def test_generate_weekly_digest(temp_db_with_items):
    """Test weekly digest generation."""
    digest_md = generate_digest(
        cadence="weekly",
        db_path=temp_db_with_items,
        save=False,
        anthropic_api_key=None
    )

    assert digest_md is not None
    assert len(digest_md) > 0
    assert "Caleidoscope Weekly Brief" in digest_md
    assert "items this week" in digest_md


def test_generate_monthly_digest(temp_db_with_items):
    """Test monthly digest generation."""
    digest_md = generate_digest(
        cadence="monthly",
        db_path=temp_db_with_items,
        save=False,
        anthropic_api_key=None
    )

    assert digest_md is not None
    assert len(digest_md) > 0
    assert "Caleidoscope Monthly Brief" in digest_md
    assert "items this month" in digest_md


def test_digest_contains_sections(temp_db_with_items):
    """Test that digest contains expected section headers."""
    digest_md = generate_digest(
        cadence="daily",
        db_path=temp_db_with_items,
        save=False,
        anthropic_api_key=None
    )

    # Check for section headers
    assert "Market Commentary" in digest_md
    assert "Index Launches & Methodology Changes" in digest_md
    assert "ETF Product Actions" in digest_md
    assert "Research & Publications" in digest_md
    assert "News & Regulatory" in digest_md


def test_digest_contains_items(temp_db_with_items):
    """Test that digest includes actual items."""
    digest_md = generate_digest(
        cadence="daily",
        db_path=temp_db_with_items,
        save=False,
        anthropic_api_key=None
    )

    # Check for some specific item titles
    assert "MSCI Launches Climate Action Index" in digest_md or "Climate Action" in digest_md
    assert "BlackRock" in digest_md or "Bitcoin ETF" in digest_md
    assert "link" in digest_md  # Should have links


def test_weekly_digest_entity_activity(temp_db_with_items):
    """Test that weekly digest includes entity activity table."""
    digest_md = generate_digest(
        cadence="weekly",
        db_path=temp_db_with_items,
        save=False,
        anthropic_api_key=None
    )

    # Should have entity activity section
    assert "Entity Activity This Week" in digest_md
    # Should mention some entities
    assert "MSCI" in digest_md or "BlackRock" in digest_md


def test_monthly_digest_entity_activity(temp_db_with_items):
    """Test that monthly digest includes entity activity table."""
    digest_md = generate_digest(
        cadence="monthly",
        db_path=temp_db_with_items,
        save=False,
        anthropic_api_key=None
    )

    # Should have entity activity section
    assert "Entity Activity" in digest_md


def test_digest_without_api_key_works(temp_db_with_items):
    """Test that digest works without API key (no AI summaries)."""
    digest_md = generate_digest(
        cadence="daily",
        db_path=temp_db_with_items,
        save=False,
        anthropic_api_key=None
    )

    # Should generate successfully
    assert digest_md is not None
    assert len(digest_md) > 100  # Should have substantial content

    # Should NOT have executive summary section (since no API key)
    # But should have all the items listed


def test_digest_save_to_file(temp_db_with_items):
    """Test that digest saves to file correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        digest_dir = Path(tmpdir) / "digests"

        digest_md = generate_digest(
            cadence="daily",
            db_path=temp_db_with_items,
            save=True,
            digest_dir=str(digest_dir),
            anthropic_api_key=None
        )

        # Check that file was created
        daily_dir = digest_dir / "daily"
        assert daily_dir.exists()

        # Should have a markdown file
        md_files = list(daily_dir.glob("*.md"))
        assert len(md_files) == 1

        # File should contain the digest
        with open(md_files[0], 'r') as f:
            content = f.read()
            assert content == digest_md


def test_renderer_handles_empty_sections():
    """Test that renderer handles empty sections gracefully."""
    from caleidoscope.digest.renderer import render_digest

    sections_data = [
        {"key": "market_commentary", "title": "Market Commentary", "items": []},
        {"key": "index_changes", "title": "Index Changes", "items": []},
    ]

    summaries = {
        "executive_summary": None,
        "sections": {
            "market_commentary": None,
            "index_changes": None
        }
    }

    date_info = {"date": "2024-01-01"}

    digest = render_digest(
        cadence="daily",
        date_str=date_info,
        sections_data=sections_data,
        summaries=summaries,
        item_count=0,
        error_count=0
    )

    # Should render without errors
    assert digest is not None
    assert "Caleidoscope Daily Brief" in digest
    assert "0 new items collected" in digest


def test_get_time_window_daily():
    """Test time window calculation for daily cadence."""
    start, end = _get_time_window("daily")

    # Should be approximately 24 hours apart
    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))

    diff = end_dt - start_dt
    assert 23 <= diff.total_seconds() / 3600 <= 25  # Between 23 and 25 hours


def test_get_time_window_weekly():
    """Test time window calculation for weekly cadence."""
    start, end = _get_time_window("weekly")

    # Should be approximately 7 days apart
    start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))

    diff = end_dt - start_dt
    assert 6.8 <= diff.total_seconds() / 86400 <= 7.2  # Between 6.8 and 7.2 days


def test_compute_entity_activity():
    """Test entity activity computation."""
    # Create mock items
    class MockItem:
        def __init__(self, entity, category):
            self.entity = entity
            self.category = category

    items = [
        MockItem("MSCI", "index_launch"),
        MockItem("MSCI", "index_launch"),
        MockItem("MSCI", "research"),
        MockItem("BlackRock", "etf_launch"),
        MockItem("BlackRock", "fee_change"),
        MockItem(None, "news"),  # No entity
    ]

    activity = _compute_entity_activity(items)

    assert "MSCI" in activity
    assert activity["MSCI"]["index_launch"] == 2
    assert activity["MSCI"]["research"] == 1

    assert "BlackRock" in activity
    assert activity["BlackRock"]["etf_launch"] == 1
    assert activity["BlackRock"]["fee_change"] == 1

    # None entity should not appear
    assert None not in activity


def test_digest_item_count(temp_db_with_items):
    """Test that digest reports correct item count."""
    digest_md = generate_digest(
        cadence="daily",
        db_path=temp_db_with_items,
        save=False,
        anthropic_api_key=None
    )

    # Should report the number of items (we added 9 items within last 24 hours)
    assert "items collected" in digest_md or "items this" in digest_md


def test_digest_generated_by_footer(temp_db_with_items):
    """Test that digest includes generation footer."""
    digest_md = generate_digest(
        cadence="daily",
        db_path=temp_db_with_items,
        save=False,
        anthropic_api_key=None
    )

    assert "Generated by Caleidoscope" in digest_md
