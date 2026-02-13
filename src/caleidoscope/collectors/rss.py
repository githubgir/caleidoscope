"""Generic RSS feed collector."""

from datetime import datetime

import feedparser

from caleidoscope.collectors.base import BaseCollector, RawItem


class RSSCollector(BaseCollector):
    """Generic collector for RSS feeds.

    This collector can be used for any source that provides RSS feeds.
    """

    def __init__(
        self,
        name: str,
        feed_urls: list[str],
        entity: str | None = None,
        category_default: str | None = None,
    ):
        """Initialize RSS collector.

        Args:
            name: Collector name (e.g., 'google_news')
            feed_urls: List of RSS feed URLs to collect from
            entity: Entity name (e.g., 'MSCI') or None
            category_default: Default category for items
        """
        self.name = name
        self.feed_urls = feed_urls
        self.entity = entity
        self.category_default = category_default

    async def collect(self) -> list[RawItem]:
        """Fetch and parse RSS feeds.

        Returns:
            List of RawItem objects from all feeds
        """
        items: list[RawItem] = []

        for feed_url in self.feed_urls:
            try:
                # Fetch feed via HTTP client
                response = await self.client.get(feed_url)
                response.raise_for_status()

                # Parse RSS/Atom feed
                feed = feedparser.parse(response.text)

                # Extract items from entries
                for entry in feed.entries:
                    # Get title
                    title = entry.get("title", "Untitled")

                    # Get URL
                    url = entry.get("link", "")
                    if not url:
                        continue

                    # Get published date
                    published_at = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            published_at = datetime(*entry.published_parsed[:6])
                        except (TypeError, ValueError):
                            pass
                    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                        try:
                            published_at = datetime(*entry.updated_parsed[:6])
                        except (TypeError, ValueError):
                            pass

                    # Get body/summary
                    body = None
                    if hasattr(entry, "summary"):
                        body = entry.summary
                    elif hasattr(entry, "description"):
                        body = entry.description
                    elif hasattr(entry, "content") and entry.content:
                        body = entry.content[0].get("value", "")

                    # Create RawItem
                    item = RawItem(
                        title=title,
                        url=url,
                        published_at=published_at,
                        source=self.name,
                        entity=self.entity,
                        category=self.category_default,
                        body=body,
                    )

                    items.append(item)

            except Exception as e:
                # Log error but continue with other feeds
                print(f"Error fetching feed {feed_url}: {e}")

        return items
