"""
Digest generator - creates daily, weekly, and monthly intelligence briefings.
"""
from datetime import datetime, timedelta
from pathlib import Path
import calendar

from caleidoscope.db.models import Item, DigestLog
from caleidoscope.db.session import get_session
from caleidoscope.digest.summariser import summarise_digest
from caleidoscope.digest.renderer import render_digest


# Section configuration - defines how items are grouped
SECTIONS = [
    {
        "key": "market_commentary",
        "title": "Market Commentary",
        "categories": ["market_commentary"]
    },
    {
        "key": "index_changes",
        "title": "Index Launches & Methodology Changes",
        "categories": ["index_launch", "methodology_change"]
    },
    {
        "key": "etf_actions",
        "title": "ETF Product Actions",
        "categories": ["etf_launch", "etf_closure", "fee_change"]
    },
    {
        "key": "research",
        "title": "Research & Publications",
        "categories": ["research"]
    },
    {
        "key": "news_regulatory",
        "title": "News & Regulatory",
        "categories": ["news", "regulatory"]
    },
]


def _get_time_window(cadence: str) -> tuple[str, str]:
    """
    Calculate the time window for the digest based on cadence.

    Returns:
        Tuple of (start_date, end_date) in ISO format
    """
    now = datetime.utcnow()

    if cadence == "daily":
        start = now - timedelta(days=1)
        end = now
    elif cadence == "weekly":
        start = now - timedelta(days=7)
        end = now
    elif cadence == "monthly":
        # Last calendar month: 1st to last day of previous month
        # Get first day of current month, then go back one day
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = first_of_this_month - timedelta(days=1)  # Last day of previous month
        start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)  # First day of previous month
    else:
        raise ValueError(f"Invalid cadence: {cadence}")

    return start.isoformat() + 'Z', end.isoformat() + 'Z'


def _get_filename(cadence: str) -> str:
    """Generate filename for the digest based on cadence."""
    now = datetime.utcnow()

    if cadence == "daily":
        return now.strftime("%Y-%m-%d.md")
    elif cadence == "weekly":
        # ISO week format: YYYY-Wnn
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}.md"
    elif cadence == "monthly":
        # YYYY-MM format
        prev_month = now.replace(day=1) - timedelta(days=1)
        return prev_month.strftime("%Y-%m.md")
    else:
        raise ValueError(f"Invalid cadence: {cadence}")


def _format_date_string(cadence: str) -> dict:
    """Format date information for rendering based on cadence."""
    now = datetime.utcnow()

    if cadence == "daily":
        return {
            "date": now.strftime("%Y-%m-%d"),
            "display_date": now.strftime("%B %d, %Y")
        }
    elif cadence == "weekly":
        year, week, _ = now.isocalendar()
        # Calculate the date range for the week
        start = now - timedelta(days=7)
        return {
            "date": f"Week {week}, {year}",
            "week_number": week,
            "year": year,
            "date_range": f"{start.strftime('%b %d')} - {now.strftime('%b %d, %Y')}"
        }
    elif cadence == "monthly":
        prev_month = now.replace(day=1) - timedelta(days=1)
        return {
            "date": prev_month.strftime("%B %Y"),
            "month_name": prev_month.strftime("%B"),
            "year": prev_month.year
        }
    else:
        raise ValueError(f"Invalid cadence: {cadence}")


def _compute_entity_activity(items: list[Item]) -> dict[str, dict[str, int]]:
    """
    Compute entity activity matrix: entity -> category -> count.

    Args:
        items: List of Item objects

    Returns:
        Dict like {"MSCI": {"index_launch": 3, "research": 2}, ...}
    """
    activity = {}

    for item in items:
        if not item.entity:
            continue

        if item.entity not in activity:
            activity[item.entity] = {}

        category = item.category or "uncategorized"
        activity[item.entity][category] = activity[item.entity].get(category, 0) + 1

    return activity


def generate_digest(
    cadence: str = "daily",
    db_path: str | None = None,
    save: bool = True,
    digest_dir: str = "digests",
    anthropic_api_key: str | None = None,
) -> str:
    """
    Generate a digest for the specified cadence.

    Args:
        cadence: "daily", "weekly", or "monthly"
        db_path: Path to SQLite database (uses default if None)
        save: If True, write digest to file and log to database
        digest_dir: Directory to save digests (default: "digests")
        anthropic_api_key: Optional API key for AI summaries

    Returns:
        The generated markdown digest as a string
    """
    # Get time window
    start_date, end_date = _get_time_window(cadence)

    # Query items from database
    session = get_session(db_path)
    try:
        items = session.query(Item).filter(
            Item.published_at >= start_date,
            Item.published_at <= end_date
        ).order_by(Item.published_at.desc()).all()

        # Group items by section
        sections_data = []
        items_by_section = {}

        for section_config in SECTIONS:
            section_key = section_config["key"]
            section_items = [
                item for item in items
                if item.category in section_config["categories"]
            ]

            sections_data.append({
                "key": section_key,
                "title": section_config["title"],
                "items": section_items
            })
            items_by_section[section_key] = section_items

        # Compute entity activity for weekly/monthly
        entity_activity = None
        if cadence in ["weekly", "monthly"]:
            entity_activity = _compute_entity_activity(items)

        # Generate AI summaries if API key provided
        summaries = summarise_digest(
            SECTIONS,
            items_by_section,
            cadence=cadence,
            anthropic_api_key=anthropic_api_key
        )

        # Format date information
        date_info = _format_date_string(cadence)

        # Render digest
        markdown = render_digest(
            cadence=cadence,
            date_str=date_info,
            sections_data=sections_data,
            summaries=summaries,
            item_count=len(items),
            error_count=0,  # TODO: Track errors from collectors
            entity_activity=entity_activity
        )

        # Save to file if requested
        if save:
            # Create directory structure
            output_dir = Path(digest_dir) / cadence
            output_dir.mkdir(parents=True, exist_ok=True)

            filename = _get_filename(cadence)
            output_path = output_dir / filename

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(markdown)

            # Log to database
            digest_log = DigestLog(
                generated_at=datetime.utcnow().isoformat() + 'Z',
                cadence=cadence,
                item_count=len(items),
                digest_md=markdown
            )
            session.add(digest_log)
            session.commit()

        return markdown

    finally:
        session.close()
