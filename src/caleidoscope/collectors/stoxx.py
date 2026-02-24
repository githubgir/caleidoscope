"""STOXX index announcements collector."""

import logging
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from caleidoscope.collectors.base import BaseCollector, RawItem

logger = logging.getLogger(__name__)


class STOXXCollector(BaseCollector):
    """Collector for STOXX announcements and press releases."""

    name = "stoxx"
    entity = "STOXX"

    async def collect(self) -> list[RawItem]:
        """Fetch and parse STOXX announcements.

        Returns:
            List of RawItem objects from STOXX sources.
        """
        items = []

        # Collect from press releases
        try:
            press_items = await self._collect_press_releases()
            items.extend(press_items)
            logger.info(f"Collected {len(press_items)} items from STOXX press releases")
        except Exception as e:
            logger.error(f"Failed to collect STOXX press releases: {e}")

        # Collect from announcements/news
        try:
            news_items = await self._collect_announcements()
            items.extend(news_items)
            logger.info(f"Collected {len(news_items)} items from STOXX announcements")
        except Exception as e:
            logger.error(f"Failed to collect STOXX announcements: {e}")

        return items

    async def _collect_press_releases(self) -> list[RawItem]:
        """Scrape STOXX press releases page."""
        url = "https://www.stoxx.com/news-media/press-releases"
        items = []

        try:
            response = await self.client.get(url, timeout=30.0)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for press release listings
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('press' in x.lower() or 'release' in x.lower() or 'news-item' in x.lower() or 'article' in x.lower()))

            # If no specific articles, look for links in main content
            if not articles:
                main_content = soup.find('main') or soup.find('div', class_=lambda x: x and 'content' in x.lower())
                if main_content:
                    # Look for structured lists
                    article_list = main_content.find_all(['li', 'div'], class_=lambda x: x and ('item' in x.lower() or 'news' in x.lower()))
                    if article_list:
                        articles = article_list

            for article in articles[:20]:  # Limit to recent 20
                # Find title
                title_elem = article.find(['h1', 'h2', 'h3', 'h4', 'a'])
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)

                if not title or len(title) < 10:
                    continue

                # Find link
                link_elem = article.find('a', href=True)
                if not link_elem:
                    continue

                href = link_elem['href']

                # Make URL absolute
                if href.startswith('/'):
                    href = f"https://www.stoxx.com{href}"
                elif not href.startswith('http'):
                    continue

                # Extract date
                published_at = self._extract_date_from_element(article)

                # Extract body/summary
                body_elem = article.find(['p', 'div'], class_=lambda x: x and ('description' in x.lower() or 'summary' in x.lower() or 'excerpt' in x.lower() or 'text' in x.lower()))
                body = body_elem.get_text(strip=True) if body_elem else None

                # Categorize
                category = self._categorize_content(title, body)

                item = RawItem(
                    title=title,
                    url=href,
                    published_at=published_at,
                    source=self.name,
                    entity=self.entity,
                    category=category,
                    body=body,
                    tags=None
                )
                items.append(item)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching STOXX press releases: {e}")
        except Exception as e:
            logger.error(f"Error parsing STOXX press releases: {e}")

        return items

    async def _collect_announcements(self) -> list[RawItem]:
        """Scrape STOXX announcements/news page."""
        # Try multiple possible URLs
        urls = [
            "https://www.stoxx.com/news-media",
            "https://www.stoxx.com/index-announcements",
            "https://www.stoxx.com/announcements",
        ]

        items = []

        for url in urls:
            try:
                response = await self.client.get(url, timeout=30.0)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')

                # Look for announcements
                articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('announcement' in x.lower() or 'news' in x.lower() or 'article' in x.lower()))

                if not articles:
                    continue

                for article in articles[:15]:  # Limit to recent 15
                    # Find title
                    title_elem = article.find(['h1', 'h2', 'h3', 'h4', 'a'])
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)

                    if not title or len(title) < 10:
                        continue

                    # Find link
                    link_elem = article.find('a', href=True)
                    if not link_elem:
                        continue

                    href = link_elem['href']

                    # Make URL absolute
                    if href.startswith('/'):
                        href = f"https://www.stoxx.com{href}"
                    elif not href.startswith('http'):
                        continue

                    # Extract date
                    published_at = self._extract_date_from_element(article)

                    # Extract body
                    body_elem = article.find(['p', 'div'], class_=lambda x: x and ('description' in x.lower() or 'summary' in x.lower()))
                    body = body_elem.get_text(strip=True) if body_elem else None

                    # Categorize
                    category = self._categorize_content(title, body)

                    item = RawItem(
                        title=title,
                        url=href,
                        published_at=published_at,
                        source=self.name,
                        entity=self.entity,
                        category=category,
                        body=body,
                        tags=None
                    )
                    items.append(item)

                # If we got items, return them
                if items:
                    break

            except httpx.HTTPError as e:
                logger.debug(f"HTTP error fetching {url}: {e}")
                continue
            except Exception as e:
                logger.debug(f"Error parsing {url}: {e}")
                continue

        return items

    def _extract_date_from_element(self, element) -> Optional[datetime]:
        """Try to extract a date from an element or its children."""
        if not element:
            return None

        # Look for time tags
        time_elem = element.find('time')
        if time_elem:
            datetime_attr = time_elem.get('datetime')
            if datetime_attr:
                try:
                    return datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                except Exception:
                    pass

        # Look for date-like text
        date_elem = element.find(class_=lambda x: x and 'date' in x.lower())
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            try:
                # Try common date formats
                for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%d.%m.%Y", "%m/%d/%Y"]:
                    try:
                        return datetime.strptime(date_text, fmt)
                    except ValueError:
                        continue
            except Exception:
                pass

        return None

    def _categorize_content(self, title: str, body: Optional[str] = None) -> Optional[str]:
        """Categorize content based on keywords in title and body."""
        text = (title + " " + (body or "")).lower()

        # Index launch keywords
        if any(kw in text for kw in ['launch', 'new index', 'introduces index', 'unveils index', 'announces index', 'adds index']):
            return "index_launch"

        # Methodology change keywords
        if any(kw in text for kw in ['methodology', 'consultation', 'review', 'changes to', 'updates to', 'index maintenance', 'rebalance', 'rulebook']):
            return "methodology_change"

        return None
