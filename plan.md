# Implementation Plan — Caleidoscope Market Intelligence Aggregator

## Overview

This plan covers the Phase 1 MVP: **free sources only, SQLite, no credentials required**. Each step produces a working, testable increment. LLM summarisation is optional (works if you set `ANTHROPIC_API_KEY`, gracefully skipped otherwise).

---

## Step 0: Project Scaffolding

**What**: Set up the Python project structure, dependencies, and configuration.

**Actions**:
1. Create project layout:
   ```
   caleidoscope/
   ├── pyproject.toml              # Project metadata, dependencies
   ├── config.yaml                 # Source definitions, schedule config
   ├── .env.example                # Template for optional env vars
   ├── src/
   │   └── caleidoscope/
   │       ├── __init__.py
   │       ├── __main__.py         # CLI entry point
   │       ├── config.py           # Load YAML + env vars
   │       ├── db/
   │       │   ├── __init__.py
   │       │   ├── models.py       # SQLAlchemy models (SQLite)
   │       │   └── session.py      # DB session/engine factory
   │       ├── collectors/
   │       │   ├── __init__.py
   │       │   ├── base.py         # Abstract collector class
   │       │   ├── rss.py          # Generic RSS collector
   │       │   ├── msci.py
   │       │   ├── sp_dji.py
   │       │   ├── stoxx.py
   │       │   ├── blackrock.py
   │       │   ├── edgar.py
   │       │   └── google_news.py
   │       ├── processing/
   │       │   ├── __init__.py
   │       │   ├── normaliser.py   # Clean, normalise, deduplicate
   │       │   └── tagger.py       # Auto-categorise and tag
   │       ├── search/
   │       │   ├── __init__.py
   │       │   └── engine.py       # FTS5 search queries
   │       ├── digest/
   │       │   ├── __init__.py
   │       │   ├── generator.py    # Compile digest from DB
   │       │   ├── summariser.py   # LLM summarisation (optional)
   │       │   └── renderer.py     # Markdown templates
   │       └── cli.py              # Typer CLI commands
   └── tests/
       ├── conftest.py
       ├── test_collectors/
       ├── test_processing/
       ├── test_search/
       └── test_digest/
   ```

2. Dependencies in `pyproject.toml`:
   - Core: `httpx`, `beautifulsoup4`, `feedparser`, `sqlalchemy`, `pyyaml`, `pydantic`, `typer[all]`
   - Optional: `anthropic` (for LLM summaries — not required)
   - Dev: `pytest`, `ruff`
   - No Playwright initially (add only if a specific site needs JS rendering)

3. Create `.env.example`:
   ```
   # All optional for Phase 1
   ANTHROPIC_API_KEY=         # Optional: enables AI summaries in digest
   CALEIDOSCOPE_DB=data/caleidoscope.db  # Default DB location
   ```

4. Create `config.yaml` with source definitions and category keywords.

**Deliverable**: `pip install -e .` installs the package; `caleidoscope --help` shows CLI; no external services needed.

---

## Step 1: Database Setup (SQLite + FTS5)

**What**: Create the SQLite database with FTS5 full-text search.

**Actions**:
1. `db/models.py` — SQLAlchemy models:
   - `Item` model: id (UUID text), url, url_hash, title, published_at, collected_at, source, entity, category, body, summary, tags (JSON text), raw_html_path
   - `DigestLog` model: id, generated_at, item_count, digest_md

2. `db/session.py`:
   - `get_engine()` — creates SQLite engine pointing to `data/caleidoscope.db`
   - `init_db()` — creates tables + FTS5 virtual table + triggers (see PRD Section 10)
   - `get_session()` — returns a session

3. CLI command: `caleidoscope init-db` — creates the database file and schema.

4. Test: init-db creates file; can insert and query an item; FTS5 search works.

**Deliverable**: `caleidoscope init-db` creates a working SQLite database with full-text search.

---

## Step 2: Base Collector Framework

**What**: Build the abstract collector class and normalisation/dedup pipeline.

**Actions**:
1. `collectors/base.py` — abstract base class:
   ```python
   class BaseCollector(ABC):
       name: str
       entity: str | None

       @abstractmethod
       async def collect(self) -> list[RawItem]: ...

       async def run(self, session) -> CollectorResult:
           """Collect, normalise, deduplicate, store."""
   ```
   - `RawItem`: pydantic model with `title, url, date, source, entity, body, category`
   - Built-in retry logic (3 attempts, exponential backoff)
   - Respects rate limiting (configurable delay between requests, default 2s per domain)
   - Logs stats: items found, new items stored, duplicates skipped, errors

2. `collectors/rss.py` — generic RSS collector (reusable for any RSS feed):
   - Takes feed URL + entity/source config
   - Parses with `feedparser`
   - Returns list of `RawItem`s

3. `processing/normaliser.py`:
   - Strip HTML tags from body text
   - Normalise whitespace, encoding
   - Generate URL hash (SHA-256) for dedup
   - Check DB for existing hash before insert

4. `processing/tagger.py`:
   - Keyword-based category detection (configurable keyword-to-category mapping in `config.yaml`)
   - Entity detection via keyword lists (e.g., body mentions "MSCI" → entity tag)

5. Tests with mock HTTP responses (no real network calls in tests).

**Deliverable**: Can run a collector against a mock source, see items appear in SQLite with correct tags.

---

## Step 3: Competitor Collectors (MSCI, S&P DJI, STOXX)

**What**: Implement collectors for the three main competitors. All free, no auth.

**Actions**:
1. **MSCI collector** (`collectors/msci.py`):
   - Parse MSCI press releases / media RSS feed
   - Scrape `msci.com` announcements page for index-related news
   - Scrape research/insights listing for new papers
   - Category mapping: announcement → `index_launch` / `methodology_change`; paper → `research`

2. **S&P DJI collector** (`collectors/sp_dji.py`):
   - Parse `spglobal.com/spdji` press release RSS
   - Scrape press room listing for index launches and methodology updates
   - Monitor consultation/commentary pages

3. **STOXX collector** (`collectors/stoxx.py`):
   - Scrape `stoxx.com` announcements / media list
   - Parse any available RSS feeds
   - Monitor for rulebook updates

4. For each: save an HTML fixture from the real site; write a test that parses the fixture.

**Deliverable**: `caleidoscope collect --source msci,sp_dji,stoxx` populates DB with real items.

---

## Step 4: Client Collector — BlackRock/iShares + News

**What**: Monitor BlackRock (largest ETF issuer) and add news sources.

**Actions**:
1. **BlackRock collector** (`collectors/blackrock.py`):
   - Scrape iShares press releases / product announcements
   - Parse RSS for blog posts and insights
   - Categories: `etf_launch`, `etf_closure`, `fee_change`, `research`

2. **Google News collector** (`collectors/google_news.py`):
   - Configure Google News RSS URLs with relevant query terms:
     - "index launch ETF", "MSCI index", "S&P index", "FTSE Russell",
       "ETF launch", "passive investing", "ESG index", etc.
   - Instance of generic RSS collector with custom URL builder
   - Category: `news`

3. **ETF Stream / ETF.com RSS** (instance of generic RSS collector):
   - Configure feed URLs
   - Category: `news` / `etf_launch`

4. **Market commentary collectors** (instances of generic RSS collector):
   - Reuters RSS — market/finance section
   - Yahoo Finance RSS — market commentary, ETF coverage
   - Morningstar RSS — fund/ETF analysis
   - Category: `market_commentary`
   - These provide broader market context beyond competitor/client intel

5. Tests with fixtures.

**Deliverable**: `caleidoscope collect --all` populates DB from competitors, BlackRock, and news.

---

## Step 5: SEC EDGAR Collector

**What**: Monitor SEC filings for ETF registrations and index-related rule changes.

**Actions**:
1. **EDGAR collector** (`collectors/edgar.py`):
   - Use EDGAR FULL-TEXT search API (`efts.sec.gov/LATEST/search-index`)
   - Search for recent filings matching:
     - Form types: N-1A (ETF registration), 19b-4 (exchange rule filings for new indices)
     - Keywords: "index", "ETF", entity names
   - Extract: filing title, form type, filer name, date, URL to filing
   - Category: `regulatory`
   - Rate limit: SEC asks for max 10 requests/second (we'll do 1/2s to be safe)
   - Set `User-Agent` header to identify the application (SEC requirement)

2. Test with saved API response fixture.

**Deliverable**: SEC filings for ETF/index activity flowing into DB.

---

## Step 6: Search Engine (CLI)

**What**: Implement full-text search via FTS5.

**Actions**:
1. `search/engine.py`:
   - Build FTS5 `MATCH` queries from user input
   - Support filters: `source`, `entity`, `category`, `date_from`, `date_to`
   - Return results ranked by FTS5 rank, with date as tiebreaker
   - Snippet extraction using `snippet()` FTS5 function
   - Pagination (default 20 results)

2. `cli.py` — add search command:
   ```
   caleidoscope search "MSCI ESG" --since 7d --entity MSCI --category research
   caleidoscope search "fee change" --source blackrock --since 30d
   caleidoscope search "19b-4" --source edgar
   ```
   - Pretty-print results: title, source, entity, date, snippet, URL

3. Tests against seeded SQLite DB.

**Deliverable**: Full-text search of the entire archive from the command line.

---

## Step 7: Digest Generator (Daily, Weekly, Monthly)

**What**: Build the briefing pipeline with three cadences.

**Actions**:
1. `digest/generator.py`:
   - Three modes: `daily` (last 24h), `weekly` (last 7 days), `monthly` (last calendar month)
   - Query items for the relevant time window
   - Group into sections:
     1. **Market commentary** — broader market news, macro context, industry trends
     2. Index launches & methodology changes
     3. ETF product actions
     4. Research & publications
     5. News & regulatory
   - Weekly adds: **week-in-review** executive summary, most active entities
   - Monthly adds: **trends & patterns** section with counts (index launches per competitor, ETF actions per client)
   - Handle empty sections (omit from digest)

2. `digest/summariser.py`:
   - If `ANTHROPIC_API_KEY` is set:
     - Call Claude API to generate per-section summaries (2–3 sentences)
     - Generate one-line summary for each item
     - For weekly/monthly: generate a higher-level thematic summary
     - Prompt: factual, concise, highlight competitive implications for FTSE Russell
     - Budget: ~4K output tokens (daily), ~6K (weekly), ~8K (monthly)
   - If no API key:
     - Skip AI summaries
     - Digest still works — just lists items by category without narrative

3. `digest/renderer.py`:
   - Jinja2 markdown templates (one base template, conditional sections for weekly/monthly):
     - Header with date range and item count
     - Executive summary (if AI available)
     - Market commentary section (new — gives broader context)
     - Each category section: section summary + item list
     - Each item: title, source, entity, date, link
     - Monthly: entity activity table (who did what, how many items)
     - Footer with collector stats
   - Output paths:
     - Daily: `digests/daily/YYYY-MM-DD.md`
     - Weekly: `digests/weekly/YYYY-Wnn.md`
     - Monthly: `digests/monthly/YYYY-MM.md`

4. CLI commands:
   ```
   caleidoscope digest                    # daily (default), save + print
   caleidoscope digest --weekly           # last 7 days
   caleidoscope digest --monthly          # last calendar month
   caleidoscope digest --preview          # print only, don't save
   caleidoscope digest --save             # save only, don't print
   ```

5. Tests: mock LLM responses; verify template rendering for all three cadences; verify no-API-key fallback.

**Deliverable**: `caleidoscope digest` produces daily briefings; `--weekly` and `--monthly` produce longer-range summaries.

---

## Step 8: Orchestration & Scheduling

**What**: Wire everything together for automated daily runs.

**Actions**:
1. `cli.py` — add `run-all` command:
   ```
   caleidoscope run-all    # collect all sources, then generate digest
   caleidoscope collect --all
   caleidoscope digest
   ```

2. Document crontab setup:
   ```cron
   # Run all collectors at 05:00 UTC (06:00 BST) on weekdays
   0 5 * * 1-5  cd /path/to/caleidoscope && python -m caleidoscope collect --all >> logs/collect.log 2>&1

   # Generate daily digest at 06:00 UTC (07:00 BST) on weekdays
   0 6 * * 1-5  cd /path/to/caleidoscope && python -m caleidoscope digest >> logs/digest.log 2>&1

   # Generate weekly digest on Monday at 06:30 UTC
   30 6 * * 1  cd /path/to/caleidoscope && python -m caleidoscope digest --weekly >> logs/digest.log 2>&1

   # Generate monthly digest on 1st of each month at 07:00 UTC
   0 7 1 * *  cd /path/to/caleidoscope && python -m caleidoscope digest --monthly >> logs/digest.log 2>&1
   ```

3. Add `--verbose` / `--quiet` flags for logging control.

4. Collection summary: print stats at end (X items collected, Y new, Z duplicates, N errors).

**Deliverable**: End-to-end automated: collectors run overnight, digest ready by morning.

---

## Step 9: Polish & Testing

**What**: Harden, test, and document.

**Actions**:
1. Integration test: run all collectors against real sites (as a manual test, not in CI).
2. Verify FTS5 search quality with realistic queries.
3. Verify digest output reads well with real data.
4. Add `caleidoscope status` command: show DB stats, last collection time, item counts by source.
5. Write setup instructions in README:
   - Install: `pip install -e .`
   - Initialise: `caleidoscope init-db`
   - First run: `caleidoscope collect --all && caleidoscope digest`
   - Schedule: crontab instructions
   - Optional: set `ANTHROPIC_API_KEY` for AI summaries
   - Adding new sources

**Deliverable**: Solid, documented MVP that runs with zero credentials.

---

## Step Dependency Graph

```
Step 0 (scaffolding)
  |
  v
Step 1 (SQLite + FTS5)
  |
  v
Step 2 (base collector framework)
  |
  +---> Step 3 (MSCI, S&P DJI, STOXX)
  |
  +---> Step 4 (BlackRock, Google News, ETF Stream)
  |
  +---> Step 5 (SEC EDGAR)
  |
  +---> Step 6 (search engine) -- can be built in parallel with 3-5
  |
  v  (after 3, 4, 5 done)
Step 7 (digest generator)
  |
  v
Step 8 (orchestration)
  |
  v
Step 9 (polish & docs)
```

Steps 3, 4, 5, and 6 can all be developed in parallel once Step 2 is complete.

---

## What the Digests Will Look Like

### Daily digest (with AI summaries):

```markdown
# Caleidoscope Daily Brief — Wednesday 12 February 2026

> 18 new items collected | 0 collector errors

## Executive Summary

MSCI published a consultation on ACWI IMI rebalancing frequency. S&P DJI
announced a new ESG Ultra index. BlackRock cut fees on three core iShares
ETFs. Markets broadly flat; ECB minutes hinted at June rate decision.

---

## Market Commentary (4 items)

US equities closed flat ahead of CPI data. European markets edged higher
on ECB minutes suggesting a June rate pause. Oil steady at $78. The dollar
index weakened slightly against the euro.

- **US Stocks Tread Water Ahead of Inflation Data**
  Reuters | 11 Feb 2026 | [link](https://reuters.com/...)

- **ECB Minutes Signal Patience on Rate Cuts**
  Yahoo Finance | 11 Feb 2026 | [link](https://finance.yahoo.com/...)

- **European Markets Edge Higher on ECB Optimism**
  Reuters | 11 Feb 2026 | [link](https://reuters.com/...)

- **Dollar Weakens as Traders Await CPI Release**
  Morningstar | 11 Feb 2026 | [link](https://morningstar.com/...)

---

## Index Launches & Methodology Changes (2 items)

MSCI is consulting on ACWI IMI rebalancing frequency, potentially moving
from quarterly to monthly. S&P DJI announced a new S&P 500 ESG Ultra
index targeting the top ESG quintile.

- **MSCI Consultation: ACWI IMI Rebalancing Frequency Review**
  MSCI | 11 Feb 2026 | [link](https://msci.com/...)

- **S&P DJI Launches S&P 500 ESG Ultra Index**
  S&P DJI | 11 Feb 2026 | [link](https://spglobal.com/...)

---

## ETF Product Actions (3 items)

BlackRock reduced expense ratios on IWDA, EIMI, and SWDA by 1-2bps,
continuing fee compression in core equity ETFs.

- **iShares Cuts Fees on Three Core World ETFs**
  BlackRock | 11 Feb 2026 | [link](https://blackrock.com/...)

- **Amundi Launches Euro Government Green Bond ETF**
  Amundi | 11 Feb 2026 | [link](https://amundi.com/...)

---

## Research & Publications (1 item)

- **Factor Investing in a Higher-Rate Environment**
  MSCI Research | 11 Feb 2026 | [link](https://msci.com/...)

---

## News & Regulatory (4 items)

European regulators are considering stricter ESG index labelling
requirements, potentially affecting Article 8/9 fund benchmarks.

- **EU Regulators Eye Tighter ESG Index Rules**
  Google News (FT) | 11 Feb 2026 | [link](https://ft.com/...)

- **European ETF Market Hits EUR 2T Milestone**
  ETF Stream | 11 Feb 2026 | [link](https://etfstream.com/...)

---
*Generated by Caleidoscope v0.1*
```

### Daily digest (without AI — no API key, still useful):

```markdown
# Caleidoscope Daily Brief — Wednesday 12 February 2026

> 18 new items collected | 0 collector errors

---

## Market Commentary (4 items)

- **US Stocks Tread Water Ahead of Inflation Data**
  Reuters | 11 Feb 2026 | [link](https://reuters.com/...)

- **ECB Minutes Signal Patience on Rate Cuts**
  Yahoo Finance | 11 Feb 2026 | [link](https://finance.yahoo.com/...)

[...]

---

## Index Launches & Methodology Changes (2 items)

- **MSCI Consultation: ACWI IMI Rebalancing Frequency Review**
  MSCI | 11 Feb 2026 | [link](https://msci.com/...)

[...]

---
*Generated by Caleidoscope v0.1*
```

### Weekly digest (Monday morning):

```markdown
# Caleidoscope Weekly Brief — Week 7 (10–14 Feb 2026)

> 73 items this week | Sources: 8 active | 2 collector warnings

## Week in Review

Active week for index methodology. MSCI opened two consultations (ACWI IMI
rebalancing, EM index treatment of India). S&P DJI launched 3 new ESG
indices. BlackRock cut fees on core ETFs for the second time in 6 months.
SEC received 4 new N-1A filings for thematic ETFs.

Markets: S&P 500 +1.2%, STOXX 600 +0.8%. ECB signalled patience on cuts.

---

## Market Commentary Highlights (22 items)

Key themes: ECB rate path uncertainty, US CPI surprise to the downside,
continued rotation into value. Oil volatile on Middle East tensions.

- **US CPI Comes in Below Expectations at 2.1%** — Reuters | 12 Feb
- **ECB Minutes Signal Patience on Rate Cuts** — Yahoo Finance | 11 Feb
- **Value Stocks Outperform Growth for Third Straight Week** — Morningstar | 14 Feb
[...]

---

## Index Launches & Methodology Changes (5 items)
[...]

## Entity Activity This Week

| Entity | Index launches | ETF actions | Research | Total |
|--------|---------------|-------------|----------|-------|
| MSCI | 2 | 0 | 1 | 3 |
| S&P DJI | 3 | 0 | 0 | 3 |
| BlackRock | 0 | 3 | 1 | 4 |
| STOXX | 1 | 0 | 0 | 1 |

---
*Generated by Caleidoscope v0.1*
```

### Monthly digest (1st business day):

```markdown
# Caleidoscope Monthly Brief — February 2026

> 287 items this month | Sources: 8 active

## Month in Review

February saw heightened activity in ESG index methodology across all major
providers. MSCI opened 4 consultations. S&P DJI launched 7 new indices (3 ESG,
2 thematic, 2 fixed income). BlackRock and Amundi both made fee cuts. SEC
filings suggest a pipeline of 12 new thematic ETFs.

## Trends & Patterns

- ESG index launches up 40% vs January (9 vs 6)
- Fee compression continues: 3 providers cut fees on 8 ETFs
- Thematic ETF filings accelerating (12 new N-1A, up from 7 in Jan)
- MSCI most active on methodology changes (4 consultations)

## Entity Activity — February 2026

| Entity | Index | Methodology | ETF actions | Research | News | Total |
|--------|-------|-------------|-------------|----------|------|-------|
| MSCI | 3 | 4 | 0 | 2 | 12 | 21 |
| S&P DJI | 7 | 1 | 0 | 3 | 8 | 19 |
| STOXX | 2 | 1 | 0 | 0 | 3 | 6 |
| BlackRock | 0 | 0 | 5 | 2 | 15 | 22 |

[... full item listings by category ...]

---
*Generated by Caleidoscope v0.1*
```

---

## Decisions Already Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | SQLite + FTS5 | Zero config, single file, no server, built-in full-text search |
| Phase 1 credentials | None required | All sources are free/public; LSEG, FT, email move to Phase 2 |
| Digest delivery | Markdown file + terminal | No SMTP needed; email added in Phase 2 |
| LLM | Optional (Claude API) | Works without it; AI summaries are a bonus, not a requirement |
| Hosting | Any machine with Python + cron | Laptop, server, VM — no Docker required for Phase 1 |
| Web UI | Phase 2 | CLI + markdown is sufficient for a single user in Phase 1 |

## Open Decisions

| # | Decision | Options | Notes |
|---|----------|---------|-------|
| 1 | **Which sites actually have usable RSS?** | Need to probe each site | First task in Step 3; determines scrape vs RSS per source |
| 2 | **Playwright needed?** | Only if key sites are JS-rendered SPAs | Test with httpx first; add Playwright per-collector if needed |
| 3 | **Google News RSS still working?** | Test it | Google has deprecated/changed this before; need a fallback plan |

---

## Phase 2 Preview (not in scope for MVP)

When you're ready to add credentials, the following modules slot in:

| Feature | What's needed | Files to add/modify |
|---------|--------------|-------------------|
| LSEG ETF flows | `LSEG_APP_KEY`, `LSEG_USERNAME`, `LSEG_PASSWORD` | `collectors/lseg_flows.py`, config entry |
| FT articles | `FT_SESSION_COOKIE` or FT API key | `collectors/ft.py`, config entry |
| Email digest | `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `DIGEST_RECIPIENTS` | `digest/mailer.py`, CLI `--send` flag |
| Remaining clients | Nothing (free scrape) | `collectors/vanguard.py`, `invesco.py`, `amundi.py`, `franklin.py` |
