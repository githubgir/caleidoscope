"""
Full-text search engine using SQLite FTS5.
"""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
import re


@dataclass
class SearchResult:
    id: str
    title: str
    url: str
    source: str
    entity: str | None
    category: str | None
    published_at: str | None
    snippet: str | None


def _parse_since(since: str) -> str:
    """Parse relative date like '7d', '30d', '1y' to ISO date string."""
    pattern = r'^(\d+)([dmy])$'
    match = re.match(pattern, since)

    if match:
        value = int(match.group(1))
        unit = match.group(2)

        now = datetime.utcnow()
        if unit == 'd':
            target_date = now - timedelta(days=value)
        elif unit == 'm':
            # Approximate month as 30 days
            target_date = now - timedelta(days=value * 30)
        elif unit == 'y':
            # Approximate year as 365 days
            target_date = now - timedelta(days=value * 365)
        else:
            return since

        return target_date.isoformat() + 'Z'
    else:
        # Assume it's already an ISO date
        return since


def search(
    query: str,
    db_path: str | None = None,
    source: str | None = None,
    entity: str | None = None,
    category: str | None = None,
    since: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[SearchResult]:
    """
    Search items using FTS5 full-text search.

    Args:
        query: Search query string (FTS5 syntax)
        db_path: Path to SQLite database (default: data/caleidoscope.db)
        source: Filter by source (e.g., 'msci', 'sp_dji')
        entity: Filter by entity (e.g., 'MSCI', 'BlackRock')
        category: Filter by category (e.g., 'index_launch', 'research')
        since: Date filter - ISO date string or relative like '7d', '30d', '1y'
        limit: Maximum results to return
        offset: Pagination offset

    Returns:
        List of SearchResult objects
    """
    if not query:
        return []

    if db_path is None:
        db_path = "data/caleidoscope.db"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Build the base FTS5 query with snippet extraction
        # snippet(table, column, start_tag, end_tag, ellipsis, max_tokens)
        sql = """
            SELECT
                items.id,
                items.title,
                items.url,
                items.source,
                items.entity,
                items.category,
                items.published_at,
                snippet(items_fts, 0, '<b>', '</b>', '...', 30) as snippet
            FROM items_fts
            JOIN items ON items_fts.rowid = items.rowid
            WHERE items_fts MATCH ?
        """

        params = [query]

        # Add filters
        if source:
            sql += " AND items.source = ?"
            params.append(source)

        if entity:
            sql += " AND items.entity = ?"
            params.append(entity)

        if category:
            sql += " AND items.category = ?"
            params.append(category)

        if since:
            # Parse relative dates like '7d' to ISO
            since_iso = _parse_since(since)
            sql += " AND items.published_at >= ?"
            params.append(since_iso)

        # Order by FTS5 rank (most relevant first), then by date
        sql += " ORDER BY rank, items.published_at DESC"

        # Add pagination
        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(sql, params)

        results = []
        for row in cursor:
            results.append(SearchResult(
                id=row['id'],
                title=row['title'],
                url=row['url'],
                source=row['source'],
                entity=row['entity'],
                category=row['category'],
                published_at=row['published_at'],
                snippet=row['snippet']
            ))

        return results

    finally:
        conn.close()
