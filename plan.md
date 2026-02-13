# Implementation Plan — Caleidoscope

## Parallel Workstream Split

Three agents build in parallel. Each owns distinct files. They share a contract (defined below) so their code integrates cleanly.

```
Agent 1: FOUNDATION          Agent 2: COLLECTORS           Agent 3: SEARCH + DIGEST
─────────────────────        ─────────────────────         ─────────────────────
pyproject.toml               collectors/msci.py            search/__init__.py
config.yaml                  collectors/sp_dji.py          search/engine.py
.env.example                 collectors/stoxx.py           digest/__init__.py
src/caleidoscope/            collectors/blackrock.py       digest/generator.py
  __init__.py                collectors/edgar.py           digest/summariser.py
  __main__.py                collectors/google_news.py     digest/renderer.py
  config.py                  collectors/market_news.py     digest/templates/
  cli.py                     collectors/etf_news.py          daily.md.j2
  db/__init__.py             tests/                          weekly.md.j2
  db/models.py                 conftest.py                   monthly.md.j2
  db/session.py                test_collectors.py          tests/
  collectors/__init__.py                                     test_search.py
  collectors/base.py                                         test_digest.py
  collectors/rss.py
  processing/__init__.py
  processing/normaliser.py
  processing/tagger.py
  tests/
    test_db.py
    test_processing.py
```

---

## Shared Contracts

All agents MUST use these exact interfaces so the code integrates.

### Contract 1: Database Models (`db/models.py`)

Agent 1 creates these. Agents 2 and 3 import from them.

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Text, Integer
import uuid
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Item(Base):
    __tablename__ = "items"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[str | None] = mapped_column(Text, nullable=True)       # ISO 8601
    collected_at: Mapped[str] = mapped_column(Text, nullable=False)             # ISO 8601
    source: Mapped[str] = mapped_column(Text, nullable=False)                   # 'msci', 'sp_dji', etc.
    entity: Mapped[str | None] = mapped_column(Text, nullable=True)             # 'MSCI', 'BlackRock', etc.
    category: Mapped[str | None] = mapped_column(Text, nullable=True)           # 'index_launch', 'research', etc.
    body: Mapped[str | None] = mapped_column(Text, nullable=True)               # cleaned text
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)            # LLM-generated
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)               # JSON: '["ESG","ACWI"]'
    raw_html_path: Mapped[str | None] = mapped_column(Text, nullable=True)

class DigestLog(Base):
    __tablename__ = "digest_log"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    generated_at: Mapped[str] = mapped_column(Text, nullable=False)
    cadence: Mapped[str] = mapped_column(Text, nullable=False)                  # 'daily', 'weekly', 'monthly'
    item_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    digest_md: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### Contract 2: RawItem pydantic model (`collectors/base.py`)

Agent 1 creates this. Agent 2 returns lists of these from every collector.

```python
from pydantic import BaseModel
from datetime import datetime

class RawItem(BaseModel):
    title: str
    url: str
    published_at: datetime | None = None
    source: str                          # e.g. 'msci', 'sp_dji', 'edgar'
    entity: str | None = None            # e.g. 'MSCI', 'S&P DJI'
    category: str | None = None          # e.g. 'index_launch', 'research', 'news'
    body: str | None = None              # cleaned text content
    tags: list[str] | None = None        # e.g. ['ESG', 'ACWI']

class CollectorResult(BaseModel):
    collector_name: str
    items_found: int = 0
    items_new: int = 0
    items_duplicate: int = 0
    errors: list[str] = []
```

### Contract 3: BaseCollector abstract class (`collectors/base.py`)

```python
from abc import ABC, abstractmethod

class BaseCollector(ABC):
    name: str           # e.g. 'msci'
    entity: str | None  # e.g. 'MSCI' — can be None for news sources

    @abstractmethod
    async def collect(self) -> list[RawItem]:
        """Fetch and return raw items from this source."""
        ...
```

Agent 1 provides the `run()` orchestration method on BaseCollector that:
1. Calls `self.collect()` to get RawItems
2. Passes through normaliser (strip HTML, clean whitespace)
3. Passes through tagger (auto-detect entity/category from keywords)
4. Deduplicates via url_hash
5. Inserts new items into SQLite
6. Returns CollectorResult with stats

### Contract 4: DB Session (`db/session.py`)

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

def get_engine(db_path: str = "data/caleidoscope.db"):
    """Return SQLAlchemy engine for the SQLite database."""
    ...

def get_session(db_path: str | None = None) -> Session:
    """Return a new DB session."""
    ...

def init_db(db_path: str | None = None):
    """Create all tables, FTS5 virtual table, and triggers."""
    ...
```

### Contract 5: Config (`config.py`)

```python
from pydantic import BaseModel

class SourceConfig(BaseModel):
    name: str
    entity: str | None = None
    enabled: bool = True
    urls: list[str] = []
    category_default: str | None = None

class Config(BaseModel):
    db_path: str = "data/caleidoscope.db"
    sources: list[SourceConfig] = []
    digest_dir: str = "digests"
    anthropic_api_key: str | None = None
    rate_limit_seconds: float = 2.0

def load_config(config_path: str = "config.yaml") -> Config:
    ...
```

### Contract 6: Category Values

All agents use these exact category strings:

- `index_launch`
- `methodology_change`
- `etf_launch`
- `etf_closure`
- `fee_change`
- `research`
- `regulatory`
- `news`
- `market_commentary`

### Contract 7: Search Engine (`search/engine.py`)

Agent 3 creates this. The CLI (Agent 1) calls it.

```python
from dataclasses import dataclass

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

def search(
    query: str,
    db_path: str | None = None,
    source: str | None = None,
    entity: str | None = None,
    category: str | None = None,
    since: str | None = None,       # ISO date or relative like "7d", "30d"
    limit: int = 20,
    offset: int = 0,
) -> list[SearchResult]:
    ...
```

### Contract 8: Digest Functions (`digest/generator.py`)

Agent 3 creates this. The CLI (Agent 1) calls it.

```python
def generate_digest(
    cadence: str = "daily",         # "daily", "weekly", "monthly"
    db_path: str | None = None,
    save: bool = True,
    digest_dir: str = "digests",
    anthropic_api_key: str | None = None,
) -> str:
    """Generate digest markdown. Returns the markdown string.
    If save=True, writes to digest_dir/{cadence}/filename.md"""
    ...
```

---

## Agent 1: Foundation

**Files to create:**
- `pyproject.toml`
- `config.yaml`
- `.env.example`
- `src/caleidoscope/__init__.py`
- `src/caleidoscope/__main__.py`
- `src/caleidoscope/config.py`
- `src/caleidoscope/cli.py`
- `src/caleidoscope/db/__init__.py`
- `src/caleidoscope/db/models.py`
- `src/caleidoscope/db/session.py`
- `src/caleidoscope/collectors/__init__.py`
- `src/caleidoscope/collectors/base.py`
- `src/caleidoscope/collectors/rss.py`
- `src/caleidoscope/processing/__init__.py`
- `src/caleidoscope/processing/normaliser.py`
- `src/caleidoscope/processing/tagger.py`
- `tests/test_db.py`
- `tests/test_processing.py`

**Responsibilities:**
1. pyproject.toml with all dependencies (httpx, beautifulsoup4, feedparser, sqlalchemy, pyyaml, pydantic, typer, jinja2, anthropic as optional)
2. Config loading (YAML + env vars)
3. SQLite database: models, session factory, init_db with FTS5 + triggers
4. BaseCollector with full run() pipeline (collect → normalise → tag → dedup → store)
5. RSSCollector (generic, reusable) extending BaseCollector
6. Normaliser: strip HTML, clean whitespace, generate url_hash
7. Tagger: keyword-based category and entity detection
8. CLI with Typer — all commands (init-db, collect, search, digest, run-all, status)
   - CLI is the shell that calls into Agent 2's collectors and Agent 3's search/digest
   - For collect: dynamically discovers all collector classes registered in collectors/__init__.py
   - For search: calls `search.engine.search()`
   - For digest: calls `digest.generator.generate_digest()`
9. Tests for DB operations and processing pipeline

**The CLI commands:**
```
caleidoscope init-db                          # create SQLite DB
caleidoscope collect --all                    # run all collectors
caleidoscope collect --source msci,edgar      # run specific collectors
caleidoscope search "MSCI ESG" --since 7d    # search
caleidoscope digest                           # daily, save + print
caleidoscope digest --weekly                  # weekly
caleidoscope digest --monthly                 # monthly
caleidoscope digest --preview                 # print only
caleidoscope run-all                          # collect --all + digest
caleidoscope status                           # DB stats
```

---

## Agent 2: All Collectors

**Files to create:**
- `src/caleidoscope/collectors/msci.py`
- `src/caleidoscope/collectors/sp_dji.py`
- `src/caleidoscope/collectors/stoxx.py`
- `src/caleidoscope/collectors/blackrock.py`
- `src/caleidoscope/collectors/edgar.py`
- `src/caleidoscope/collectors/google_news.py`
- `src/caleidoscope/collectors/market_news.py`
- `src/caleidoscope/collectors/etf_news.py`
- `tests/conftest.py` (shared fixtures)
- `tests/test_collectors.py`

**Each collector extends BaseCollector and implements `async def collect() -> list[RawItem]`.**

### MSCI (`msci.py`)
- name = "msci", entity = "MSCI"
- Scrape `msci.com` press releases and announcements page
- Scrape research/insights listing
- Categories: `index_launch`, `methodology_change`, `research`

### S&P DJI (`sp_dji.py`)
- name = "sp_dji", entity = "S&P DJI"
- Scrape `spglobal.com/spdji` press releases
- Look for RSS feed; fall back to HTML scraping
- Categories: `index_launch`, `methodology_change`, `research`

### STOXX (`stoxx.py`)
- name = "stoxx", entity = "STOXX"
- Scrape `stoxx.com` announcements / media list
- Categories: `index_launch`, `methodology_change`

### BlackRock/iShares (`blackrock.py`)
- name = "blackrock", entity = "BlackRock"
- Scrape iShares press releases / product announcements
- Parse RSS if available
- Categories: `etf_launch`, `etf_closure`, `fee_change`, `research`

### SEC EDGAR (`edgar.py`)
- name = "edgar", entity = None (entity derived from filer)
- Use EDGAR full-text search API: `https://efts.sec.gov/LATEST/search-index?q=...`
- Search for form types N-1A, 19b-4 with keywords "index", "ETF"
- Set User-Agent header (SEC requirement): `Caleidoscope/0.1 (contact@example.com)`
- Category: `regulatory`
- Rate limit: 1 request per 2 seconds

### Google News (`google_news.py`)
- name = "google_news", entity = None
- Use Google News RSS: `https://news.google.com/rss/search?q=...`
- Query terms: "MSCI index", "S&P index launch", "FTSE Russell", "ETF launch", "ESG index", "index methodology"
- Category: `news`

### Market News (`market_news.py`)
- name = "market_news", entity = None
- Aggregate multiple RSS feeds via the generic RSSCollector:
  - Reuters business/finance RSS
  - Yahoo Finance RSS
  - Morningstar articles RSS
- Category: `market_commentary`

### ETF News (`etf_news.py`)
- name = "etf_news", entity = None
- Aggregate RSS feeds:
  - ETF Stream
  - ETF.com
  - ETF Trends
- Category: `news` (may be retagged to `etf_launch` by tagger)

### Test approach:
- `conftest.py`: shared fixtures (mock httpx client, sample RSS XML, sample HTML)
- `test_collectors.py`: for each collector, feed it saved HTML/RSS fixture, verify it returns correct RawItems
- No real network calls in tests

---

## Agent 3: Search + Digest

**Files to create:**
- `src/caleidoscope/search/__init__.py`
- `src/caleidoscope/search/engine.py`
- `src/caleidoscope/digest/__init__.py`
- `src/caleidoscope/digest/generator.py`
- `src/caleidoscope/digest/summariser.py`
- `src/caleidoscope/digest/renderer.py`
- `src/caleidoscope/digest/templates/daily.md.j2`
- `src/caleidoscope/digest/templates/weekly.md.j2`
- `src/caleidoscope/digest/templates/monthly.md.j2`
- `tests/test_search.py`
- `tests/test_digest.py`

### Search Engine (`search/engine.py`)
- FTS5 MATCH queries against items_fts virtual table
- Support filters: source, entity, category, since (date)
- Snippet extraction using FTS5 `snippet()` function
- Results ranked by FTS5 rank, date as tiebreaker
- Pagination (limit/offset)
- Function signature per Contract 7

### Digest Generator (`digest/generator.py`)
- Three cadences: daily (last 24h), weekly (last 7d), monthly (last calendar month)
- Query items for time window from SQLite
- Group into sections by category:
  1. market_commentary
  2. index_launch + methodology_change
  3. etf_launch + etf_closure + fee_change
  4. research
  5. regulatory + news
- Count items per entity (for weekly/monthly entity activity table)
- Pass to summariser, then to renderer
- Save to digests/{cadence}/filename.md
- Log to digest_log table
- Function signature per Contract 8

### Summariser (`digest/summariser.py`)
- If `ANTHROPIC_API_KEY` available:
  - Call Claude API to generate:
    - Executive summary (2-3 sentences)
    - Per-section narrative (2-3 sentences each)
    - One-line summary per item
  - Prompt: "You are a market intelligence analyst at FTSE Russell. Summarise these items factually and concisely. Highlight competitive implications."
  - Budget: ~4K tokens daily, ~6K weekly, ~8K monthly
- If no API key:
  - Return None for all summaries (renderer handles this gracefully)

### Renderer (`digest/renderer.py`)
- Load Jinja2 templates from digest/templates/
- Templates:
  - `daily.md.j2` — standard sections
  - `weekly.md.j2` — adds "Week in Review" + entity activity table
  - `monthly.md.j2` — adds "Trends & Patterns" + full entity activity table
- All templates handle missing AI summaries (just omit narrative blocks)
- Render to markdown string

### Jinja2 template structure (daily.md.j2 example):
```markdown
# Caleidoscope Daily Brief — {{ date }}

> {{ item_count }} new items collected | {{ error_count }} collector errors

{% if executive_summary %}
## Executive Summary

{{ executive_summary }}

---
{% endif %}

{% for section in sections %}
{% if section.items %}
## {{ section.title }} ({{ section.items | length }} items)

{% if section.summary %}
{{ section.summary }}

{% endif %}
{% for item in section.items %}
- **{{ item.title }}**
  {{ item.source }}{% if item.entity %} ({{ item.entity }}){% endif %} | {{ item.published_at }} | [link]({{ item.url }})
{% endfor %}

---
{% endif %}
{% endfor %}
*Generated by Caleidoscope v0.1*
```

### Tests:
- `test_search.py`: seed SQLite with test items, verify search returns correct results, test filters
- `test_digest.py`: seed DB, generate digest, verify markdown output, test all 3 cadences, test with/without API key
