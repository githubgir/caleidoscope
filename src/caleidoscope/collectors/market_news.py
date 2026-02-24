"""Market news aggregator from multiple RSS feeds."""

import logging
from datetime import datetime
from typing import Optional

import feedparser
import httpx
from bs4 import BeautifulSoup

from caleidoscope.collectors.base import BaseCollector, RawItem

logger = logging.getLogger(__name__)


class MarketNewsCollector(BaseCollector):
    """Collector for general market news from multiple RSS feeds."""

    name = "market_news"
    entity = None

    # RSS feeds to aggregate
    RSS_FEEDS = [
        {
            "url": "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best",
            "source_name": "Reuters",
        },
        {
            "url": "https://feeds.finance.yahoo.com/rss/2.0/headline",
            "source_name": "Yahoo Finance",
        },
        {
            "url": "https://www.morningstar.com/rss/news.xml",
            "source_name": "Morningstar",
        },
        {
            "url": "https://www.marketwatch.com/rss/",
            "source_name": "MarketWatch",
        },
        {
            "url": "https://www.bloomberg.com/feed/news.rss",
            "source_name": "Bloomberg",
        },
    ]

    async def collect(self) -> list[RawItem]:
        """Fetch and parse market news from multiple RSS feeds.

        Returns:
            List of RawItem objects from market news sources.
        """
        items = []
        seen_urls = set()  # For deduplication

        for feed_info in self.RSS_FEEDS:
            feed_url = feed_info["url"]
            source_name = feed_info["source_name"]

            try:
                feed_items = await self._collect_feed(feed_url, source_name)

                # Deduplicate
                for item in feed_items:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        items.append(item)

                logger.info(f"Collected {len(feed_items)} items from {source_name}")
            except Exception as e:
                logger.error(f"Failed to collect from {source_name}: {e}")

        logger.info(f"Total unique market news items: {len(items)}")
        return items

    async def _collect_feed(self, feed_url: str, source_name: str) -> list[RawItem]:
        """Fetch and parse a single RSS feed.

        Args:
            feed_url: URL of the RSS feed
            source_name: Human-readable name of the source

        Returns:
            List of RawItem objects from this feed.
        """
        items = []

        try:
            response = await self.client.get(feed_url, timeout=30.0, follow_redirects=True)
            response.raise_for_status()

            # Parse RSS feed
            feed = feedparser.parse(response.text)

            if not feed.entries:
                logger.debug(f"No entries found for {source_name}")
                return items

            for entry in feed.entries[:15]:  # Limit to 15 per feed
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
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    try:
                        published_at = datetime(*entry.updated_parsed[:6])
                    except Exception:
                        pass

                # Get summary/description
                body = entry.get('summary', '') or entry.get('description', '') or entry.get('content', [{}])[0].get('value', '')
                if body:
                    # Clean HTML from summary
                    soup = BeautifulSoup(body, 'html.parser')
                    body = soup.get_text(strip=True)

                # Try to extract entity from title or content
                entity = self._extract_entity(title, body)

                # Extract tags from categories if available
                tags = []
                if hasattr(entry, 'tags'):
                    tags = [tag.get('term', '') for tag in entry.tags if tag.get('term')]

                item = RawItem(
                    title=title,
                    url=link,
                    published_at=published_at,
                    source=self.name,
                    entity=entity,
                    category="market_commentary",
                    body=body,
                    tags=tags if tags else None
                )
                items.append(item)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching {source_name} feed: {e}")
        except Exception as e:
            logger.error(f"Error parsing {source_name} feed: {e}")

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
        elif "s&p dow jones" in text or "s&p dji" in text or "s&p 500" in text:
            return "S&P DJI"
        elif "ftse russell" in text or "ftse 100" in text:
            return "FTSE Russell"
        elif "stoxx" in text:
            return "STOXX"
        elif "blackrock" in text or "ishares" in text:
            return "BlackRock"
        elif "vanguard" in text:
            return "Vanguard"
        elif "state street" in text or "spdr" in text:
            return "State Street"
        elif "invesco" in text:
            return "Invesco"

        return None
