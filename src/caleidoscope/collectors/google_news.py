"""Google News RSS collector for index and ETF topics."""

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import feedparser
import httpx
from bs4 import BeautifulSoup

from caleidoscope.collectors.base import BaseCollector, RawItem

logger = logging.getLogger(__name__)


class GoogleNewsCollector(BaseCollector):
    """Collector for Google News RSS feeds on index and ETF topics."""

    name = "google_news"
    entity = None

    # Search queries to fetch
    SEARCH_QUERIES = [
        "MSCI index",
        "S&P Dow Jones index",
        "FTSE Russell",
        "ETF launch",
        "index methodology",
        "ESG index",
        "index rebalance",
        "new ETF",
    ]

    async def collect(self) -> list[RawItem]:
        """Fetch and parse Google News RSS feeds for multiple search queries.

        Returns:
            List of RawItem objects from Google News.
        """
        items = []
        seen_urls = set()  # For deduplication

        for query in self.SEARCH_QUERIES:
            try:
                query_items = await self._collect_query(query)

                # Deduplicate
                for item in query_items:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        items.append(item)

                logger.info(f"Collected {len(query_items)} items from Google News for query '{query}'")
            except Exception as e:
                logger.error(f"Failed to collect Google News for query '{query}': {e}")

        logger.info(f"Total unique items from Google News: {len(items)}")
        return items

    async def _collect_query(self, query: str) -> list[RawItem]:
        """Fetch Google News RSS feed for a specific query.

        Args:
            query: Search query string

        Returns:
            List of RawItem objects from this query.
        """
        items = []

        # Build Google News RSS URL
        encoded_query = quote_plus(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

        try:
            response = await self.client.get(url, timeout=30.0)
            response.raise_for_status()

            # Parse RSS feed
            feed = feedparser.parse(response.text)

            if not feed.entries:
                logger.debug(f"No entries found for query '{query}'")
                return items

            for entry in feed.entries[:10]:  # Limit to 10 per query
                title = entry.get('title', '').strip()
                link = entry.get('link', '').strip()

                if not title or not link:
                    continue

                # Parse published date
                published_at = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_at = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass

                # Get summary/description
                body = entry.get('summary', '') or entry.get('description', '')
                if body:
                    # Clean HTML from summary
                    soup = BeautifulSoup(body, 'html.parser')
                    body = soup.get_text(strip=True)

                # Extract source from entry if available
                source_name = entry.get('source', {}).get('title', '') if hasattr(entry.get('source', {}), 'get') else ''

                # Try to extract entity from title or content
                entity = self._extract_entity(title, body)

                item = RawItem(
                    title=title,
                    url=link,
                    published_at=published_at,
                    source=self.name,
                    entity=entity,
                    category="news",
                    body=body,
                    tags=[query] if query else None
                )
                items.append(item)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching Google News for query '{query}': {e}")
        except Exception as e:
            logger.error(f"Error parsing Google News for query '{query}': {e}")

        return items

    def _extract_entity(self, title: str, body: Optional[str] = None) -> Optional[str]:
        """Try to extract entity name from title or body.

        Args:
            title: Article title
            body: Article summary/body

        Returns:
            Entity name if detected, None otherwise.
        """
        text = (title + " " + (body or "")).lower()

        # Check for known entities
        if "msci" in text:
            return "MSCI"
        elif "s&p dow jones" in text or "s&p dji" in text:
            return "S&P DJI"
        elif "ftse russell" in text or "ftse" in text:
            return "FTSE Russell"
        elif "stoxx" in text:
            return "STOXX"
        elif "blackrock" in text or "ishares" in text:
            return "BlackRock"
        elif "vanguard" in text:
            return "Vanguard"
        elif "state street" in text or "spdr" in text:
            return "State Street"

        return None
