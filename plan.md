# Implementation Plan — Caleidoscope Market Intelligence Aggregator

## Overview

This plan breaks the MVP (Phase 1 from the PRD) into concrete, ordered implementation steps. Each step produces a working, testable increment.

---

## Step 0: Project Scaffolding

**What**: Set up the Python project structure, dependencies, configuration, and Docker environment.

**Actions**:
1. Initialise project layout:
   ```
   caleidoscope/
   ├── pyproject.toml              # Project metadata, dependencies
   ├── docker-compose.yml          # Postgres + app services
   ├── Dockerfile
   ├── .env.example                # Template for secrets
   ├── config.yaml                 # Source definitions, schedule, recipients
   ├── alembic.ini                 # DB migration config
   ├── alembic/
   │   └── versions/
   ├── src/
   │   └── caleidoscope/
   │       ├── __init__.py
   │       ├── __main__.py         # CLI entry point
   │       ├── config.py           # Load YAML + env vars
   │       ├── db/
   │       │   ├── __init__.py
   │       │   ├── models.py       # SQLAlchemy models
   │       │   └── session.py      # DB session factory
   │       ├── collectors/
   │       │   ├── __init__.py
   │       │   ├── base.py         # Abstract collector class
   │       │   ├── msci.py
   │       │   ├── sp_dji.py
   │       │   ├── stoxx.py
   │       │   ├── blackrock.py
   │       │   ├── ft.py
   │       │   ├── lseg_flows.py
   │       │   └── rss.py          # Generic RSS collector
   │       ├── processing/
   │       │   ├── __init__.py
   │       │   ├── normaliser.py   # Clean, normalise, deduplicate
   │       │   └── tagger.py       # Auto-categorise and tag
   │       ├── search/
   │       │   ├── __init__.py
   │       │   └── engine.py       # Full-text search queries
   │       ├── digest/
   │       │   ├── __init__.py
   │       │   ├── generator.py    # Compile digest from DB
   │       │   ├── summariser.py   # LLM summarisation
   │       │   ├── renderer.py     # Markdown + HTML templates
   │       │   └── mailer.py       # Send email via SMTP/SendGrid
   │       └── cli.py              # Click/Typer CLI commands
   └── tests/
       ├── conftest.py
       ├── test_collectors/
       ├── test_processing/
       ├── test_search/
       └── test_digest/
   ```

2. Define dependencies in `pyproject.toml`:
   - Core: `httpx`, `beautifulsoup4`, `feedparser`, `sqlalchemy[asyncio]`, `psycopg[binary]`, `alembic`, `pyyaml`, `pydantic`, `typer`
   - Scraping: `playwright` (for JS-heavy pages)
   - Data: `lseg-data` (LSEG Data Library)
   - LLM: `anthropic` (Claude API)
   - Email: `jinja2` (templates), `sendgrid` or stdlib `smtplib`
   - Dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`

3. Create `docker-compose.yml` with:
   - PostgreSQL 16 service
   - App service (Python)
   - Volume for Postgres data persistence

4. Create `.env.example` with placeholders:
   ```
   DATABASE_URL=postgresql://caleidoscope:secret@localhost:5432/caleidoscope
   LSEG_APP_KEY=
   LSEG_USERNAME=
   LSEG_PASSWORD=
   ANTHROPIC_API_KEY=
   SMTP_HOST=
   SMTP_PORT=
   SMTP_USER=
   SMTP_PASS=
   DIGEST_RECIPIENTS=you@example.com
   FT_SESSION_COOKIE=
   ```

5. Create `config.yaml` with source definitions and defaults.

**Deliverable**: `docker-compose up` starts Postgres; `pip install -e .` installs the package; `caleidoscope --help` shows CLI.

---

## Step 1: Database Models & Migrations

**What**: Define the data model and create the initial database schema.

**Actions**:
1. Implement SQLAlchemy models in `db/models.py`:
   - `Item` model (matches schema from PRD Section 10)
   - `DigestLog` model
   - Full-text search trigger to auto-update `search_vector` on insert/update

2. Configure Alembic and generate initial migration.

3. Write `db/session.py` — async session factory using `create_async_engine`.

4. Test: migration runs cleanly; can insert and query an item.

**Deliverable**: `alembic upgrade head` creates all tables with indices.

---

## Step 2: Base Collector Framework

**What**: Build the abstract collector class and the normalisation/dedup pipeline.

**Actions**:
1. `collectors/base.py` — abstract base class:
   ```python
   class BaseCollector(ABC):
       name: str
       entity: str | None

       @abstractmethod
       async def collect(self) -> list[RawItem]: ...

       async def run(self) -> CollectorResult:
           """Collect, normalise, deduplicate, store."""
   ```
   - `RawItem`: pydantic model with `title, url, date, source, entity, body, category`
   - Built-in retry logic (3 attempts, exponential backoff)
   - Respects rate limiting (configurable delay between requests)
   - Logs stats: items found, new items stored, duplicates skipped, errors

2. `collectors/rss.py` — generic RSS collector (reusable for any RSS feed):
   - Takes feed URL + entity/source config
   - Parses with feedparser
   - Returns list of RawItems

3. `processing/normaliser.py`:
   - Strip HTML tags from body text
   - Normalise whitespace, encoding
   - Generate URL hash for dedup
   - Check DB for existing hash before insert

4. `processing/tagger.py`:
   - Keyword-based category detection (configurable keyword → category mapping)
   - Entity extraction via keyword lists (index names, ticker symbols)

5. Tests with mock HTTP responses.

**Deliverable**: Can run a collector against a mock source, see items appear in DB with correct tags.

---

## Step 3: First Collectors (MSCI, S&P DJI, STOXX)

**What**: Implement the three competitor collectors.

**Actions**:
1. **MSCI collector** (`collectors/msci.py`):
   - Scrape `msci.com/index-announcements` for announcements
   - Parse MSCI RSS/media feed for press releases
   - Scrape `msci.com/research-and-insights` for research papers
   - Category mapping: announcement → `index_launch` / `methodology_change`; paper → `research`

2. **S&P DJI collector** (`collectors/sp_dji.py`):
   - Scrape `spglobal.com/spdji/en/media-center/press-releases/` for press releases
   - Parse RSS for index announcements
   - Scrape methodology change notices
   - Monitor for consultation papers

3. **STOXX collector** (`collectors/stoxx.py`):
   - Scrape `stoxx.com` announcements/media list
   - Parse any available RSS
   - Monitor rulebook updates

4. For each: write a focused test with a saved HTML fixture to verify parsing logic is correct.

**Deliverable**: `caleidoscope collect --source msci,sp_dji,stoxx` populates DB with real items.

---

## Step 4: Client Collector — BlackRock/iShares

**What**: Monitor the largest ETF issuer for product actions.

**Actions**:
1. **BlackRock collector** (`collectors/blackrock.py`):
   - Scrape iShares product announcements / press releases
   - Monitor for new ETF listings (product page changes)
   - Parse RSS feed for blog posts and insights
   - Categories: `etf_launch`, `etf_closure`, `fee_change`, `research`

2. Test with fixture.

**Deliverable**: BlackRock items flowing into DB with correct categorisation.

---

## Step 5: News Collector — Financial Times

**What**: Ingest FT articles matching relevant keywords.

**Actions**:
1. **FT collector** (`collectors/ft.py`):
   - Approach A (preferred): Use FT search/content API if available with subscription
   - Approach B (fallback): Authenticated HTTP session using subscription cookies
   - Search queries: "index launch", "ETF", "MSCI", "S&P index", "FTSE Russell", "passive investing", "ESG index"
   - Extract: headline, snippet, URL, published date
   - Respect FT terms — store headline + snippet + link, not full article body
   - Category: `news`

2. **Google News RSS collector** (instance of generic RSS collector):
   - Configure Google News RSS URLs with relevant query terms
   - Acts as catch-all for stories from other outlets

3. Test FT parser with fixture.

**Deliverable**: FT headlines and links appear in DB; Google News catches additional coverage.

---

## Step 6: LSEG Data Library — ETF Flows & AUM

**What**: Pull ETF flow and AUM data via the LSEG (Refinitiv) Data Library.

**Actions**:
1. **LSEG collector** (`collectors/lseg_flows.py`):
   - Authenticate using LSEG Data Library SDK (`lseg.data`)
   - Pull daily ETF flow data for major ETFs tracking competitor/client indices
   - Pull AUM snapshots
   - Compute: top 10 gatherers, top 10 outflows, notable AUM milestones
   - Store as items with category `etf_flow`
   - Each "item" is a structured summary (e.g., "iShares MSCI World ETF: +$450M flows, AUM $58.2B")

2. Configure a watchlist of ETF RICs/ISINs in `config.yaml` covering:
   - iShares/BlackRock products
   - Vanguard products
   - Invesco products
   - Amundi products
   - Franklin Templeton products
   - Key FTSE Russell-benchmarked ETFs (for competitive awareness)

3. Test with LSEG sandbox/mock.

**Deliverable**: Daily flow/AUM highlights stored as searchable items.

---

## Step 7: Search Engine

**What**: Implement the search interface.

**Actions**:
1. `search/engine.py`:
   - Build PostgreSQL full-text search queries using `plainto_tsquery` and `ts_rank`
   - Support filters: `source`, `entity`, `category`, `date_from`, `date_to`
   - Return results ordered by relevance (with date as tiebreaker)
   - Pagination support

2. `cli.py` — add search command:
   ```
   caleidoscope search "MSCI ESG" --since 7d --entity MSCI --category research
   caleidoscope search "fee change" --source blackrock --since 30d
   ```
   - Pretty-print results: title, source, date, snippet, URL

3. Tests against seeded DB.

**Deliverable**: Can search the full archive from the command line with filters.

---

## Step 8: Digest Generator & LLM Summarisation

**What**: Build the morning briefing pipeline.

**Actions**:
1. `digest/generator.py`:
   - Query all items from last 24 hours (or since last digest)
   - Group into sections:
     1. Index launches & methodology changes
     2. ETF product actions
     3. AUM & flow highlights
     4. Research & publications
     5. News & regulatory
   - Pass each section's items to the summariser

2. `digest/summariser.py`:
   - Use Claude API (`anthropic` SDK) to generate:
     - A 2–3 sentence section summary (what matters and why)
     - A one-line summary for each individual item
   - Prompt engineering: instruct model to be factual, concise, highlight competitive implications for FTSE Russell
   - Token budget: keep total summarisation under ~4K output tokens per digest
   - Handle empty sections gracefully (omit from digest)

3. `digest/renderer.py`:
   - Jinja2 templates for:
     - **HTML email** (clean, mobile-friendly, uses inline CSS)
     - **Markdown** (for archive and terminal viewing)
   - Template sections: header with date, executive summary, then each category section
   - Each item: title (hyperlinked), source badge, date, one-line summary

4. `digest/mailer.py`:
   - Send HTML email via SMTP or SendGrid
   - Support multiple recipients (from config)
   - Attach markdown version as .md file
   - Log to `digest_log` table

5. CLI command: `caleidoscope digest --send` (generate + email) and `caleidoscope digest --preview` (print to terminal)

6. Tests: mock LLM responses, verify template rendering, verify email assembly.

**Deliverable**: `caleidoscope digest --preview` prints a formatted morning briefing to the terminal. `--send` emails it.

---

## Step 9: Orchestration & Scheduling

**What**: Wire everything together so it runs automatically.

**Actions**:
1. `cli.py` — add `run-all` command:
   ```
   caleidoscope run-all          # collect from all sources, then generate digest
   caleidoscope collect --all    # just collection
   caleidoscope digest --send    # just digest
   ```

2. Add a `crontab` entry (or document it):
   ```cron
   # Run all collectors at 05:00 UTC (06:00 BST)
   0 5 * * 1-5  cd /opt/caleidoscope && python -m caleidoscope collect --all >> /var/log/caleidoscope/collect.log 2>&1

   # Generate and send digest at 06:30 UTC (07:30 BST)
   30 6 * * 1-5  cd /opt/caleidoscope && python -m caleidoscope digest --send >> /var/log/caleidoscope/digest.log 2>&1
   ```

3. Add health check: if >50% of collectors fail, send an alert email to admin.

4. Dockerfile: final production image with cron inside, or use host cron + container exec.

**Deliverable**: End-to-end automated: collectors run at 05:00, digest arrives in inbox by 07:00 London time on weekdays.

---

## Step 10: Documentation & Deployment

**What**: Make it deployable and maintainable.

**Actions**:
1. Write setup instructions in README (not a separate doc):
   - How to configure `.env` and `config.yaml`
   - How to add LSEG credentials
   - How to set FT authentication
   - How to add/modify collectors
   - How to add new sources to the watchlist

2. Docker deployment:
   - `docker-compose up -d` starts Postgres + app
   - `docker-compose exec app caleidoscope collect --all` for manual run
   - Verify cron schedule works inside container

3. Test end-to-end on a clean machine.

**Deliverable**: Another person can clone, configure, and deploy in under an hour.

---

## Decisions to Make Before Starting

These decisions should be made before implementation begins:

| # | Decision | Options | Recommendation |
|---|----------|---------|----------------|
| 1 | **Where to host?** | Local server / AWS EC2 / Azure VM / Raspberry Pi | Small cloud VM (AWS t3.small ~£15/mo) — always on, no VPN needed |
| 2 | **Email service** | Personal SMTP / Gmail SMTP / SendGrid free tier / AWS SES | SendGrid free tier (100 emails/day) — easiest setup, reliable |
| 3 | **LLM for summaries** | Claude (Anthropic API) / GPT-4o / Local model | Claude — best summarisation quality, ~£2-3/day at this volume |
| 4 | **FT access method** | FT API / authenticated scraping / headline-only via RSS | Start with RSS (headlines + links); add authenticated access if full text needed |
| 5 | **LSEG auth method** | Desktop session / Platform session | Platform session (server-friendly, no GUI needed) |
| 6 | **Search backend** | PostgreSQL FTS / Elasticsearch / SQLite FTS5 | PostgreSQL FTS — already have Postgres, good enough for this scale |
| 7 | **Web UI in MVP?** | Yes / No | No — add in Phase 2; email + CLI is sufficient for one user |

---

## Estimated Complexity by Step

| Step | Description | Complexity | Dependencies |
|------|-------------|------------|--------------|
| 0 | Project scaffolding | Low | None |
| 1 | Database models & migrations | Low | Step 0 |
| 2 | Base collector framework | Medium | Step 1 |
| 3 | Competitor collectors (MSCI, S&P, STOXX) | Medium-High | Step 2 |
| 4 | BlackRock collector | Medium | Step 2 |
| 5 | FT / news collectors | Medium | Step 2 |
| 6 | LSEG flows integration | Medium-High | Step 2 |
| 7 | Search engine + CLI | Medium | Step 1 |
| 8 | Digest generator + LLM + email | High | Steps 2-6, 7 |
| 9 | Orchestration & scheduling | Low | Step 8 |
| 10 | Documentation & deployment | Low | Step 9 |

Steps 3, 4, 5, and 6 can be developed in parallel once Step 2 is complete. Step 7 can also be developed in parallel with the collectors.

---

## What the Morning Email Will Look Like

```
Subject: Caleidoscope Daily Brief — Tuesday 12 February 2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXECUTIVE SUMMARY

Quiet day for index launches. MSCI published a consultation on
changes to the MSCI ACWI IMI methodology. BlackRock cut fees on
three iShares core ETFs. Significant inflows into ESG-labelled
products continue, with Vanguard ESG Global gathering $320M.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 INDEX LAUNCHES & METHODOLOGY CHANGES (2 items)

MSCI is consulting on ACWI IMI rebalancing frequency, potentially
moving from quarterly to monthly. S&P DJI announced a new S&P
500 ESG Ultra index targeting the top ESG quintile.

  • MSCI Consultation: ACWI IMI Rebalancing Frequency Review
    msci.com/... | MSCI | 11 Feb 2026

  • S&P DJI Launches S&P 500 ESG Ultra Index
    spglobal.com/... | S&P DJI | 11 Feb 2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 ETF PRODUCT ACTIONS (3 items)

BlackRock reduced expense ratios on IWDA, EIMI, and SWDA by
1-2bps, continuing the fee compression trend in core equity ETFs.

  • iShares Cuts Fees on Three Core World ETFs
    blackrock.com/... | BlackRock | 11 Feb 2026

  • Amundi Launches Euro Government Green Bond ETF
    amundi.com/... | Amundi | 11 Feb 2026

  • Franklin Templeton Files for Active Crypto ETF
    sec.gov/... | Franklin Templeton | 10 Feb 2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 AUM & FLOW HIGHLIGHTS

Top gatherers (1d): Vanguard ESG Global (+$320M), iShares MSCI
World (+$285M), Invesco QQQ (+$210M). Largest outflow: iShares
Emerging Markets (-$180M).

  [Table of top 10 inflows / top 10 outflows]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📄 RESEARCH & PUBLICATIONS (1 item)

  • MSCI: "Factor Investing in a Higher-Rate Environment"
    msci.com/... | MSCI Research | 11 Feb 2026

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📰 NEWS & REGULATORY (4 items)

FT reports European regulators considering stricter ESG index
labelling requirements, potentially affecting Article 8/9 fund
benchmarks.

  • FT: EU Regulators Eye Tighter ESG Index Rules
    ft.com/... | Financial Times | 11 Feb 2026

  • ETF Stream: European ETF Market Hits €2T Milestone
    etfstream.com/... | ETF Stream | 11 Feb 2026

  [...]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Caleidoscope v0.1 | 12 items collected | 0 collector errors
Search archive: caleidoscope search "<query>"
```

---

## Next Steps

To start implementation, the following is needed from you:

1. **LSEG Data Library credentials** (app key, username, password) — store in `.env`
2. **FT subscription details** — how you currently log in (for cookie-based auth)
3. **Email preferences** — which email address to send to; whether you have SMTP access or prefer SendGrid
4. **Hosting preference** — cloud VM, local machine, or existing server
5. **ETF watchlist** — initial list of ETF tickers/RICs you want to track for flows
6. **Any additional sources** — beyond what's listed in the PRD
