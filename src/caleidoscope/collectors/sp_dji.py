"""S&P Dow Jones Indices press releases collector."""

import logging
from datetime import datetime
from typing import Optional

import feedparser
import httpx
from bs4 import BeautifulSoup

from caleidoscope.collectors.base import BaseCollector, RawItem

logger = logging.getLogger(__name__)


class SPDJICollector(BaseCollector):
    """Collector for S&P Dow Jones Indices press releases."""

    name = "sp_dji"
    entity = "S&P DJI"

    async def collect(self) -> list[RawItem]:
        """Fetch and parse S&P DJI press releases.

        Returns:
            List of RawItem objects from S&P DJI sources.
        """
        items = []

        # Try RSS feed first
        try:
            rss_items = await self._collect_from_rss()
            if rss_items:
                items.extend(rss_items)
                logger.info(f"Collected {len(rss_items)} items from S&P DJI RSS feed")
                return items  # If RSS works, use that
        except Exception as e:
            logger.warning(f"Failed to collect from S&P DJI RSS feed: {e}")

        # Fall back to HTML scraping
        try:
            html_items = await self._collect_from_html()
            items.extend(html_items)
            logger.info(f"Collected {len(html_items)} items from S&P DJI press releases page")
        except Exception as e:
            logger.error(f"Failed to collect from S&P DJI HTML: {e}")

        return items

    async def _collect_from_rss(self) -> list[RawItem]:
        """Try to collect from RSS feed if available."""
        # Common RSS feed URLs to try
        rss_urls = [
            "https://www.spglobal.com/spdji/en/rss/rss-details/?rssFeedName=all-press-releases",
            "https://www.spglobal.com/spdji/en/rss/",
        ]

        items = []

        for rss_url in rss_urls:
            try:
                response = await self.client.get(rss_url, timeout=30.0)
                response.raise_for_status()

                # Parse RSS feed
                feed = feedparser.parse(response.text)

                if not feed.entries:
                    continue

                for entry in feed.entries[:20]:  # Limit to recent 20
                    title = entry.get('title', '').strip()
                    url = entry.get('link', '').strip()

                    if not title or not url:
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

                    # Categorize
                    category = self._categorize_content(title, body)

                    item = RawItem(
                        title=title,
                        url=url,
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
                    return items

            except Exception as e:
                logger.debug(f"Failed to fetch RSS from {rss_url}: {e}")
                continue

        return items

    async def _collect_from_html(self) -> list[RawItem]:
        """Scrape S&P DJI press releases page."""
        url = "https://www.spglobal.com/spdji/en/media-center/press-releases/"
        items = []

        try:
            response = await self.client.get(url, timeout=30.0)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for press release listings
            # S&P typically uses article or div elements
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('press' in x.lower() or 'release' in x.lower() or 'article' in x.lower() or 'news-item' in x.lower()))

            # If no specific articles found, try finding links in main content
            if not articles:
                main_content = soup.find('main') or soup.find('div', class_=lambda x: x and ('content' in x.lower() or 'articles' in x.lower()))
                if main_content:
                    # Look for structured lists
                    article_list = main_content.find_all(['li', 'div'], class_=lambda x: x and ('item' in x.lower() or 'article' in x.lower()))
                    if article_list:
                        articles = article_list

            for article in articles[:20]:  # Limit to recent 20
                # Find title
                title_elem = article.find(['h1', 'h2', 'h3', 'h4', 'a'])
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)

                # Find link
                link_elem = article.find('a', href=True)
                if not link_elem:
                    continue

                href = link_elem['href']

                # Make URL absolute
                if href.startswith('/'):
                    href = f"https://www.spglobal.com{href}"
                elif not href.startswith('http'):
                    continue

                # Extract date
                published_at = self._extract_date_from_element(article)

                # Extract body/summary
                body_elem = article.find(['p', 'div'], class_=lambda x: x and ('description' in x.lower() or 'summary' in x.lower() or 'excerpt' in x.lower()))
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
            logger.error(f"HTTP error fetching S&P DJI press releases: {e}")
        except Exception as e:
            logger.error(f"Error parsing S&P DJI press releases: {e}")

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
                for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%m/%d/%Y"]:
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
        if any(kw in text for kw in ['launch', 'new index', 'introduces index', 'unveils index', 'announces index']):
            return "index_launch"

        # Methodology change keywords
        if any(kw in text for kw in ['methodology', 'consultation', 'review', 'changes to', 'updates to', 'index maintenance', 'rebalance']):
            return "methodology_change"

        # Research keywords
        if any(kw in text for kw in ['research', 'paper', 'insight', 'report', 'analysis', 'study', 'commentary']):
            return "research"

        return None
