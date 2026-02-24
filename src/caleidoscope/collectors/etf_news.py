"""ETF-specific news aggregator from multiple RSS feeds."""

import logging
from datetime import datetime
from typing import Optional

import feedparser
import httpx
from bs4 import BeautifulSoup

from caleidoscope.collectors.base import BaseCollector, RawItem

logger = logging.getLogger(__name__)


class ETFNewsCollector(BaseCollector):
    """Collector for ETF-specific news from multiple RSS feeds."""

    name = "etf_news"
    entity = None

    # RSS feeds to aggregate
    RSS_FEEDS = [
        {
            "url": "https://www.etfstream.com/feed",
            "source_name": "ETF Stream",
        },
        {
            "url": "https://www.etf.com/sections/feeds/news.xml",
            "source_name": "ETF.com",
        },
        {
            "url": "https://www.etftrends.com/feed/",
            "source_name": "ETF Trends",
        },
        {
            "url": "https://www.etfdailynews.com/feed/",
            "source_name": "ETF Daily News",
        },
    ]

    async def collect(self) -> list[RawItem]:
        """Fetch and parse ETF news from multiple RSS feeds.

        Returns:
            List of RawItem objects from ETF news sources.
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

        logger.info(f"Total unique ETF news items: {len(items)}")
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

                # Categorize content
                category = self._categorize_content(title, body)

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
                    category=category,
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
        elif "invesco" in text:
            return "Invesco"
        elif "schwab" in text:
            return "Charles Schwab"
        elif "wisdomtree" in text:
            return "WisdomTree"

        return None

    def _categorize_content(self, title: str, body: Optional[str] = None) -> Optional[str]:
        """Categorize content based on keywords in title and body.

        Args:
            title: Article title
            body: Article summary/body

        Returns:
            Category string if detected, defaults to 'news'.
        """
        text = (title + " " + (body or "")).lower()

        # ETF launch keywords
        if any(kw in text for kw in ['launch', 'new etf', 'introduces etf', 'unveils etf', 'announces etf', 'debuts', 'lists etf']):
            return "etf_launch"

        # ETF closure keywords
        if any(kw in text for kw in ['close', 'closure', 'closing', 'delisting', 'liquidation', 'liquidate', 'terminate']):
            return "etf_closure"

        # Fee change keywords
        if any(kw in text for kw in ['fee', 'expense ratio', 'waiver', 'reduces cost', 'lowers fee', 'fee reduction', 'cuts fee']):
            return "fee_change"

        # Default to news
        return "news"
