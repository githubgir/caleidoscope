"""Base collector class and data models."""

import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select

from caleidoscope.db.models import Item
from caleidoscope.db.session import get_session
from caleidoscope.processing.normaliser import generate_url_hash, normalise_item
from caleidoscope.processing.tagger import tag_item


class RawItem(BaseModel):
    """Represents a raw item collected from a source before processing."""

    title: str
    url: str
    published_at: datetime | None = None
    source: str  # e.g. 'msci', 'sp_dji', 'edgar'
    entity: str | None = None  # e.g. 'MSCI', 'S&P DJI'
    category: str | None = None  # e.g. 'index_launch', 'research', 'news'
    body: str | None = None  # cleaned text content
    tags: list[str] | None = None  # e.g. ['ESG', 'ACWI']


class CollectorResult(BaseModel):
    """Result of running a collector."""

    collector_name: str
    items_found: int = 0
    items_new: int = 0
    items_duplicate: int = 0
    errors: list[str] = Field(default_factory=list)


class BaseCollector(ABC):
    """Abstract base class for all collectors."""

    name: str  # e.g. 'msci'
    entity: str | None  # e.g. 'MSCI' — can be None for news sources

    @abstractmethod
    async def collect(self) -> list[RawItem]:
        """Fetch and return raw items from this source.

        This method must be implemented by each collector.

        Returns:
            List of RawItem objects
        """
        ...

    async def run(
        self, db_path: str | None = None, rate_limit: float = 2.0
    ) -> CollectorResult:
        """Run the full collection pipeline.

        This orchestrates:
        1. Calling collect() to get RawItems (with retry logic)
        2. Normalizing items (strip HTML, clean whitespace)
        3. Tagging items (auto-detect entity/category)
        4. Deduplicating via url_hash
        5. Inserting new items into SQLite
        6. Returning CollectorResult with stats

        Args:
            db_path: Path to SQLite database (optional)
            rate_limit: Seconds to wait between requests

        Returns:
            CollectorResult with statistics
        """
        result = CollectorResult(collector_name=self.name)
        session = get_session(db_path)

        # Create HTTP client for this collector run
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Caleidoscope/0.1 (Market Intelligence Aggregator)",
            },
        )

        try:
            # Collect items with retry logic
            raw_items = await self._collect_with_retry()
            result.items_found = len(raw_items)

            # Process each item
            for raw_item in raw_items:
                try:
                    # Rate limiting
                    await asyncio.sleep(rate_limit)

                    # Normalize (strip HTML, clean whitespace)
                    normalized = normalise_item(raw_item)

                    # Tag (auto-detect entity/category if not set)
                    tagged = tag_item(normalized)

                    # Generate URL hash for deduplication
                    url_hash = generate_url_hash(tagged.url)

                    # Check if already exists
                    existing = session.execute(
                        select(Item).where(Item.url_hash == url_hash)
                    ).first()

                    if existing:
                        result.items_duplicate += 1
                        continue

                    # Convert tags list to JSON string if present
                    tags_json = None
                    if tagged.tags:
                        import json

                        tags_json = json.dumps(tagged.tags)

                    # Create new Item
                    item = Item(
                        url=tagged.url,
                        url_hash=url_hash,
                        title=tagged.title,
                        published_at=(
                            tagged.published_at.isoformat() if tagged.published_at else None
                        ),
                        collected_at=datetime.utcnow().isoformat(),
                        source=tagged.source,
                        entity=tagged.entity,
                        category=tagged.category,
                        body=tagged.body,
                        tags=tags_json,
                    )

                    session.add(item)
                    result.items_new += 1

                except Exception as e:
                    result.errors.append(f"Error processing item {raw_item.url}: {str(e)}")

            # Commit all new items
            session.commit()

        except Exception as e:
            result.errors.append(f"Collection error: {str(e)}")

        finally:
            await self.client.aclose()
            session.close()

        return result

    async def _collect_with_retry(
        self, max_attempts: int = 3, backoff_base: float = 2.0
    ) -> list[RawItem]:
        """Call collect() with exponential backoff retry logic.

        Args:
            max_attempts: Maximum number of retry attempts
            backoff_base: Base for exponential backoff calculation

        Returns:
            List of RawItem objects

        Raises:
            Exception: If all retry attempts fail
        """
        last_error = None

        for attempt in range(max_attempts):
            try:
                return await self.collect()
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    wait_time = backoff_base**attempt
                    await asyncio.sleep(wait_time)

        # All attempts failed
        raise Exception(
            f"Collection failed after {max_attempts} attempts. Last error: {last_error}"
        )
