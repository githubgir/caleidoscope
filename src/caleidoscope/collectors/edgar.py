"""SEC EDGAR filings collector."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from caleidoscope.collectors.base import BaseCollector, RawItem

logger = logging.getLogger(__name__)


class EDGARCollector(BaseCollector):
    """Collector for SEC EDGAR filings related to ETFs and indices."""

    name = "edgar"
    entity = None  # Entity will be extracted from filer name

    # SEC requires identification in User-Agent
    USER_AGENT = "Caleidoscope/0.1 (caleidoscope@example.com)"

    # Rate limit: 2 seconds between requests (SEC requirement)
    RATE_LIMIT_SECONDS = 2.0

    async def collect(self) -> list[RawItem]:
        """Fetch and parse SEC EDGAR filings.

        Returns:
            List of RawItem objects from SEC EDGAR.
        """
        items = []

        # Search for relevant filings from the last 7 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        # Multiple search queries to cover different filing types
        search_queries = [
            ("ETF index", ["N-1A", "19b-4"]),
            ("index methodology", ["19b-4"]),
            ("new index", ["19b-4"]),
        ]

        for query, forms in search_queries:
            try:
                query_items = await self._search_edgar(query, forms, start_date, end_date)
                items.extend(query_items)
                logger.info(f"Collected {len(query_items)} items from EDGAR for query '{query}'")

                # Rate limit between queries
                await asyncio.sleep(self.RATE_LIMIT_SECONDS)
            except Exception as e:
                logger.error(f"Failed to collect from EDGAR for query '{query}': {e}")

        # Deduplicate by URL (same filing might appear in multiple searches)
        seen_urls = set()
        unique_items = []
        for item in items:
            if item.url not in seen_urls:
                seen_urls.add(item.url)
                unique_items.append(item)

        return unique_items

    async def _search_edgar(
        self,
        query: str,
        forms: list[str],
        start_date: datetime,
        end_date: datetime
    ) -> list[RawItem]:
        """Search EDGAR full-text search API.

        Args:
            query: Search query string
            forms: List of form types to search (e.g., ['N-1A', '19b-4'])
            start_date: Start date for search
            end_date: End date for search

        Returns:
            List of RawItem objects from search results.
        """
        items = []

        # Format dates for API
        start_dt = start_date.strftime("%Y-%m-%d")
        end_dt = end_date.strftime("%Y-%m-%d")

        # Build form types parameter
        forms_param = ",".join(forms)

        # Build search URL
        url = (
            f"https://efts.sec.gov/LATEST/search-index"
            f"?q={query}"
            f"&dateRange=custom"
            f"&startdt={start_dt}"
            f"&enddt={end_dt}"
            f"&forms={forms_param}"
        )

        try:
            # Set required User-Agent header
            headers = {
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
            }

            response = await self.client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()

            data = response.json()

            # Parse results
            hits = data.get("hits", {}).get("hits", [])

            for hit in hits[:50]:  # Limit to 50 results per query
                source = hit.get("_source", {})

                # Extract filing information
                file_num = source.get("file_num", "")
                form_type = source.get("form", "")
                filing_date = source.get("file_date", "")
                company_name = source.get("display_names", [""])[0] if source.get("display_names") else ""
                cik = source.get("ciks", [""])[0] if source.get("ciks") else ""
                accession_num = source.get("adsh", "")

                # Build title
                title = f"{form_type}: {company_name}" if company_name else f"{form_type} Filing"

                # Build URL to filing
                if accession_num:
                    # Format accession number for URL (remove hyphens)
                    accession_formatted = accession_num.replace("-", "")
                    filing_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_type}&dateb=&owner=exclude&count=100&search_text={accession_num}"

                    # Better URL: direct link to filing
                    if cik:
                        filing_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_type}&dateb=&owner=exclude&count=10"
                else:
                    filing_url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={company_name}&type={form_type}"

                # Parse filing date
                published_at = None
                if filing_date:
                    try:
                        published_at = datetime.strptime(filing_date, "%Y-%m-%d")
                    except ValueError:
                        pass

                # Extract snippet from highlights if available
                body = None
                highlights = hit.get("highlight", {})
                if highlights:
                    # Get first highlight snippet
                    for field, snippets in highlights.items():
                        if snippets:
                            body = " ".join(snippets[:2])  # First 2 snippets
                            break

                # Entity is the company name
                entity = company_name if company_name else None

                item = RawItem(
                    title=title,
                    url=filing_url,
                    published_at=published_at,
                    source=self.name,
                    entity=entity,
                    category="regulatory",
                    body=body,
                    tags=[form_type] if form_type else None
                )
                items.append(item)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error searching EDGAR: {e}")
        except Exception as e:
            logger.error(f"Error parsing EDGAR results: {e}")

        return items
