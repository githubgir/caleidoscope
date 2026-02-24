"""MSCI press releases and research collector."""

import logging
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from caleidoscope.collectors.base import BaseCollector, RawItem

logger = logging.getLogger(__name__)


class MSCICollector(BaseCollector):
    """Collector for MSCI press releases and research."""

    name = "msci"
    entity = "MSCI"

    async def collect(self) -> list[RawItem]:
        """Fetch and parse MSCI press releases and research articles.

        Returns:
            List of RawItem objects from MSCI sources.
        """
        items = []

        # Collect from press releases
        try:
            press_items = await self._collect_press_releases()
            items.extend(press_items)
            logger.info(f"Collected {len(press_items)} items from MSCI press releases")
        except Exception as e:
            logger.error(f"Failed to collect MSCI press releases: {e}")

        # Collect from research/insights
        try:
            research_items = await self._collect_research()
            items.extend(research_items)
            logger.info(f"Collected {len(research_items)} items from MSCI research")
        except Exception as e:
            logger.error(f"Failed to collect MSCI research: {e}")

        return items

    async def _collect_press_releases(self) -> list[RawItem]:
        """Scrape MSCI press releases page."""
        url = "https://www.msci.com/press-releases"
        items = []

        try:
            response = await self.client.get(url, timeout=30.0)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for press release listings
            # MSCI typically uses article tags or divs with specific classes
            # We'll look for common patterns
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('press' in x.lower() or 'article' in x.lower() or 'news' in x.lower()))

            # If no specific articles found, try looking for links in the main content
            if not articles:
                # Try finding all links that look like press releases
                main_content = soup.find('main') or soup.find('div', class_=lambda x: x and 'content' in x.lower())
                if main_content:
                    links = main_content.find_all('a', href=True)
                    for link in links:
                        title = link.get_text(strip=True)
                        href = link['href']

                        # Skip empty titles or navigation links
                        if not title or len(title) < 10:
                            continue
                        if any(skip in href.lower() for skip in ['#', 'javascript:', 'mailto:']):
                            continue

                        # Make URL absolute
                        if href.startswith('/'):
                            href = f"https://www.msci.com{href}"
                        elif not href.startswith('http'):
                            continue

                        # Try to extract date from nearby text
                        published_at = self._extract_date_from_element(link.parent)

                        # Determine category from title/content
                        category = self._categorize_content(title)

                        item = RawItem(
                            title=title,
                            url=href,
                            published_at=published_at,
                            source=self.name,
                            entity=self.entity,
                            category=category,
                            body=None,
                            tags=None
                        )
                        items.append(item)
            else:
                # Process found articles
                for article in articles[:20]:  # Limit to recent 20
                    title_elem = article.find(['h1', 'h2', 'h3', 'h4', 'a'])
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)

                    # Find link
                    link_elem = article.find('a', href=True)
                    if not link_elem:
                        continue

                    href = link_elem['href']
                    if href.startswith('/'):
                        href = f"https://www.msci.com{href}"

                    # Extract date
                    published_at = self._extract_date_from_element(article)

                    # Extract snippet/body
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
            logger.error(f"HTTP error fetching MSCI press releases: {e}")
        except Exception as e:
            logger.error(f"Error parsing MSCI press releases: {e}")

        return items

    async def _collect_research(self) -> list[RawItem]:
        """Scrape MSCI research and insights page."""
        url = "https://www.msci.com/insights"
        items = []

        try:
            response = await self.client.get(url, timeout=30.0)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for research articles
            articles = soup.find_all(['article', 'div'], class_=lambda x: x and ('insight' in x.lower() or 'research' in x.lower() or 'article' in x.lower()))

            for article in articles[:15]:  # Limit to recent 15
                title_elem = article.find(['h1', 'h2', 'h3', 'h4', 'a'])
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)

                # Find link
                link_elem = article.find('a', href=True)
                if not link_elem:
                    continue

                href = link_elem['href']
                if href.startswith('/'):
                    href = f"https://www.msci.com{href}"

                # Extract date
                published_at = self._extract_date_from_element(article)

                # Extract snippet
                body_elem = article.find(['p', 'div'], class_=lambda x: x and ('description' in x.lower() or 'summary' in x.lower()))
                body = body_elem.get_text(strip=True) if body_elem else None

                item = RawItem(
                    title=title,
                    url=href,
                    published_at=published_at,
                    source=self.name,
                    entity=self.entity,
                    category="research",
                    body=body,
                    tags=None
                )
                items.append(item)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching MSCI research: {e}")
        except Exception as e:
            logger.error(f"Error parsing MSCI research: {e}")

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
                for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"]:
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
        if any(kw in text for kw in ['methodology', 'consultation', 'review', 'changes to', 'updates to', 'index maintenance']):
            return "methodology_change"

        # Research keywords
        if any(kw in text for kw in ['research', 'paper', 'insight', 'report', 'analysis', 'study']):
            return "research"

        return None
