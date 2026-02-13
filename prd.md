# Market Intelligence Aggregator — Product Requirements Document

## 1. Problem Statement

The Head of Index Research & Design at FTSE Russell needs a single system that continuously monitors competitors (MSCI, S&P Dow Jones, STOXX), clients (Vanguard, Invesco, Amundi, BlackRock, Franklin Templeton), and the broader index/ETF ecosystem for:

- **New index launches** (filings, announcements, methodology changes)
- **ETF flows and AUM** (which products are gathering/losing assets)
- **Research publications** (white papers, methodology papers, consultation papers)
- **Regulatory and news** (industry press, SEC/FCA filings)
- **Product actions** (fund launches, closures, fee changes, rebalances)
- **Market commentary** (broader market news, macro context, industry trends)

This information is currently scattered across dozens of websites, data feeds, news outlets, and subscription services. There is no unified view, and manual checking is unsustainable.

## 2. Users

| User | Need |
|------|------|
| Primary: Head of Index Research & Design | Morning briefing with actionable intelligence, searchable archive |
| Secondary: Index research team members | Shared access to the same intelligence base |

## 3. Goals

1. **Automated collection** — scrape, poll, and ingest from all configured sources on a schedule (overnight / early morning).
2. **Persistent storage** — every item stored with full metadata, deduplication, and tagging.
3. **Search** — full-text search across all collected items, filterable by source, entity, date, topic.
4. **Daily digest** — a morning briefing (AI-summarised when API key available, plain listing otherwise).
5. **Low maintenance** — once configured, should run unattended; alert on failures.
6. **Zero credentials for Phase 1** — everything works with free, public sources only.

## 4. Source Inventory

### 4.1 Competitor websites — free (scrape / RSS)

| Entity | What to monitor | Likely method |
|--------|----------------|---------------|
| **MSCI** | Index announcements, methodology docs, consultations, blog | RSS (`msci.com/our-solutions/indexes`), scrape announcements page |
| **S&P Dow Jones Indices** | Index launches, methodology changes, research, press releases | RSS feed, scrape press room |
| **STOXX** | New indices, rulebook updates, announcements | Scrape `stoxx.com/index-medialist`, RSS |
| **Solactive** | Index launches (rising competitor) | Scrape press page |
| **Morningstar Indexes** | Methodology, announcements | RSS / scrape |

### 4.2 Client / asset manager websites — free (scrape / RSS)

| Entity | What to monitor | Likely method |
|--------|----------------|---------------|
| **BlackRock / iShares** | ETF launches, closures, fee changes, blog | RSS, scrape product page |
| **Vanguard** | Fund launches, index changes, research | Scrape press room |
| **Invesco** | ETF launches, index switches, research | RSS, scrape |
| **Amundi** | ETF launches (EU focus), research | Scrape |
| **Franklin Templeton** | ETF/index fund launches | Scrape press releases |

### 4.3 Data feeds — free, no auth

| Source | Data | Method |
|--------|------|--------|
| **SEC EDGAR** | ETF registration statements (N-1A), index-related 19b-4 filings | EDGAR FULL-TEXT search API (free, no auth) |

### 4.4 News, research & market commentary — free, no auth

| Source | Data | Method |
|--------|------|--------|
| **ETF.com / ETF Stream** | ETF news, flow data, new launches | RSS / scrape |
| **ETF Trends / IndexUniverse** | Industry commentary | RSS |
| **Google News** | Catch-all for entity mentions | Google News RSS with query parameters |
| **Google Scholar / SSRN** | Academic & practitioner research on indexing | Scholar RSS alerts / SSRN API (free) |
| **Reuters** | Market commentary, macro news | RSS feed (free) |
| **Bloomberg (free tier)** | Market news headlines | RSS / scrape (headline + link only) |
| **Yahoo Finance** | Market commentary, ETF coverage | RSS feed |
| **Morningstar** | Fund/ETF commentary, market analysis | RSS feed |

### 4.5 Credentialed sources (Phase 2 — requires login/subscription)

| Source | Data | Method | Credential needed |
|--------|------|--------|-------------------|
| **LSEG Data Library** (Refinitiv) | ETF AUM, flows, index returns, new listings | Python SDK (`lseg.data`) | LSEG app key + login |
| **Financial Times** | Articles mentioning indices, ETFs, named entities | FT API or authenticated scrape | FT subscription |
| **FCA / ESMA** | EU regulatory filings (some gated) | Scrape / RSS | May require registration |

## 5. Functional Requirements

### FR-1: Data Ingestion Pipeline

- Each source has a dedicated **collector** (a Python module) that:
  - Connects to the source (HTTP scrape, RSS parse, API call)
  - Extracts structured items: `{title, url, date, source, entity, body_text, category, raw_html}`
  - Handles pagination, rate limiting, retries, and error logging
- A **scheduler** (cron) triggers collectors at configurable intervals (default: daily 05:00 UTC)
- A **deduplication** layer prevents storing the same item twice (hash on URL + title)
- Failures are logged; collection summary printed to stdout

### FR-2: Storage

- Items stored in a **SQLite** database (single file, zero config, no server)
- Full-text search via **SQLite FTS5** virtual table
- Optional: raw HTML/PDF archived to a local `archive/` directory
- Tagging: each item auto-tagged with:
  - Entity (MSCI, BlackRock, etc.)
  - Category (index launch, ETF flow, research, regulatory, news)
  - Detected tickers / index names (via keyword matching)

### FR-3: Search Interface

- **CLI search**: `python -m caleidoscope search "MSCI ESG" --since 7d --source msci`
- **Web UI** (Phase 2): simple search page with filters
- Returns results ranked by relevance, with snippet preview

### FR-4: Digests (Daily, Weekly, Monthly)

Three digest cadences, all using the same template engine:

**Daily digest** (weekday mornings):
- Runs after all collectors complete (e.g., 06:30 UTC)
- Covers items from the last 24 hours
- Sections:
  1. **Market commentary** — broader market news, macro moves, industry trends from the past day
  2. **Index launches & methodology changes**
  3. **ETF product actions** (launches, closures, fee changes)
  4. **AUM & flow highlights** (Phase 2 — needs LSEG data)
  5. **Research & publications**
  6. **News & regulatory**

**Weekly digest** (Monday mornings):
- Covers items from the past 7 days
- Same sections as daily, but with a **week-in-review** executive summary
- Highlights: top stories of the week, most active entities, emerging themes
- Useful for catching up after time off

**Monthly digest** (1st business day of month):
- Covers items from the past calendar month
- Adds a **trends & patterns** section: what changed month-over-month
- Counts: how many index launches per competitor, how many ETF actions per client
- Useful for strategic overview and reporting

**Common to all digests**:
- **With `ANTHROPIC_API_KEY`**: each section gets AI-generated narrative summaries
- **Without API key**: items listed by category with title, source, date, link (still useful)
- Output formats:
  - **Markdown file** — saved to `digests/daily/YYYY-MM-DD.md`, `digests/weekly/YYYY-Wnn.md`, `digests/monthly/YYYY-MM.md`
  - **Terminal output** — pretty-printed via CLI
  - **Email** (Phase 2) — sent to configured recipients via SMTP/SendGrid

### FR-5: Alerting (Phase 2)

- User-defined keyword watches (e.g., "FTSE Russell", "Russell 2000", "ESG index methodology")
- Instant email/Slack notification when a matching item is ingested

## 6. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Reliability | Collectors must handle source downtime gracefully; retry 3x with backoff |
| Latency | Digest generated by 07:00 London time |
| Data retention | All items retained indefinitely |
| Security | Any future credentials stored in environment variables, never in code |
| Cost | Phase 1: free (public sources, local machine, SQLite). Phase 2+: LLM ~£2-3/day, email free tier |
| Compliance | Respect robots.txt; rate-limit scraping to 1 req/2s per domain |

## 7. Delivery Format Decision

### Recommended: **Markdown digest + CLI search (Phase 1), add email in Phase 2**

| Option | Pros | Cons |
|--------|------|------|
| **Markdown digest file** | Zero dependencies; readable anywhere; versioned | Must open file manually |
| **Email digest** | Zero friction — arrives in inbox; readable on phone | Requires SMTP credentials (Phase 2) |
| **Web app** | Searchable, filterable, rich UI | Requires hosting, auth, maintenance (Phase 2+) |
| **Slack/Teams bot** | Push notifications; conversational | Requires workspace integration (Phase 2+) |
| **CLI tool** | Powerful search; scriptable; no credentials needed | Not accessible on phone |

**Recommendation for Phase 1**: Generate a **markdown digest file** daily (saved to `digests/YYYY-MM-DD.md`) and provide a **CLI search tool** for the archive. No credentials required. Add **email delivery** in Phase 2.

## 8. Architecture Overview

```
SCHEDULER (cron, 05:00 UTC weekdays)
         |
         v
COLLECTOR MODULES (all free, no auth)
  msci.py | sp_dji.py | stoxx.py | blackrock.py
  edgar.py | google_news.py | etf_stream.py | ...
         |
         v
NORMALISER + DEDUPLICATOR
  - strip HTML, normalise text
  - SHA-256 URL hash for dedup
  - keyword-based category & entity tagging
         |
         v
SQLite DATABASE  (data/caleidoscope.db)
  - items table (structured metadata + body text)
  - items_fts (FTS5 virtual table for full-text search)
  - digest_log table
         |
    +----+----+
    |         |
    v         v
DIGEST        SEARCH (CLI)
GENERATOR       caleidoscope search "query"
  (06:30 UTC)   - FTS5 full-text search
  - last 24h    - filter: entity, source, date, category
  - group by category
  - LLM summarise (optional, needs ANTHROPIC_API_KEY)
  - save to digests/YYYY-MM-DD.md
  - print to terminal
```

## 9. Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | **Python 3.12+** | Best ecosystem for scraping, data, ML |
| Scraping | **httpx** + **BeautifulSoup4** | Async HTTP client + HTML parser |
| JS rendering | **Playwright** (only if needed) | For JS-heavy SPAs; most sites work without |
| RSS | **feedparser** | Standard, battle-tested |
| Database | **SQLite** (stdlib) + **FTS5** | Zero config, single file, built-in full-text search |
| ORM | **SQLAlchemy 2.0** (sync, SQLite) | Clean models, optional migration support |
| Scheduling | **cron** | Simple, reliable, no extra dependencies |
| LLM (optional) | **Claude API** (`anthropic` SDK) | Best summarisation quality; fully optional in Phase 1 |
| Config | **YAML** config file + **env vars** for secrets | Readable, secure |
| CLI | **Typer** | Clean CLI framework built on Click |
| Dev | **pytest**, **ruff** | Testing + linting |

### Phase 2 additions

| Component | Technology |
|-----------|-----------|
| Data API | **lseg-data** (LSEG Data Library SDK) |
| Email | **SMTP** via `smtplib` or **SendGrid API** |
| Web UI | **FastAPI** + **Jinja2** or **Streamlit** |
| Containerisation | **Docker + docker-compose** |

## 10. Data Model

```sql
-- Main items table
CREATE TABLE items (
    id              TEXT PRIMARY KEY,       -- UUID as text
    url             TEXT NOT NULL,
    url_hash        TEXT NOT NULL UNIQUE,   -- SHA-256 of URL for dedup
    title           TEXT NOT NULL,
    published_at    TEXT,                   -- ISO 8601 datetime
    collected_at    TEXT NOT NULL,          -- ISO 8601 datetime
    source          TEXT NOT NULL,          -- 'msci', 'sp_dji', 'edgar', etc.
    entity          TEXT,                   -- 'MSCI', 'BlackRock', etc.
    category        TEXT,                   -- 'index_launch', 'etf_flow', 'research', etc.
    body            TEXT,                   -- cleaned text content
    summary         TEXT,                   -- LLM-generated one-liner (nullable)
    tags            TEXT,                   -- JSON array as text: '["ESG","ACWI"]'
    raw_html_path   TEXT                   -- local file path for raw archive
);

CREATE INDEX idx_items_source ON items(source);
CREATE INDEX idx_items_entity ON items(entity);
CREATE INDEX idx_items_published ON items(published_at);
CREATE INDEX idx_items_category ON items(category);

-- FTS5 virtual table for full-text search
CREATE VIRTUAL TABLE items_fts USING fts5(
    title, body, tags,
    content='items',
    content_rowid='rowid'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER items_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, title, body, tags)
    VALUES (new.rowid, new.title, new.body, new.tags);
END;

CREATE TRIGGER items_ad AFTER DELETE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, body, tags)
    VALUES ('delete', old.rowid, old.title, old.body, old.tags);
END;

-- Digest log
CREATE TABLE digest_log (
    id              TEXT PRIMARY KEY,
    generated_at    TEXT NOT NULL,
    item_count      INTEGER,
    digest_md       TEXT                   -- archived markdown content
);
```

## 11. Scope & Phasing

### Phase 1 — MVP (zero credentials, fully free)

- Collectors for free public sources:
  - Competitors: MSCI, S&P DJI, STOXX (RSS + scrape)
  - Clients: BlackRock/iShares (RSS + scrape)
  - Regulatory: SEC EDGAR (free API)
  - News: Google News RSS, ETF Stream/ETF.com RSS
- SQLite storage with FTS5 full-text search
- CLI search tool with filters
- Daily digest as markdown file + terminal output
- Optional LLM summaries if `ANTHROPIC_API_KEY` is set
- Runs on any machine with Python — no Docker required

### Phase 2 — Credentialed Sources & Delivery

- LSEG Data Library integration (ETF AUM/flows) — requires LSEG credentials
- Financial Times collector — requires FT subscription
- Email delivery via SMTP/SendGrid — requires email credentials
- Remaining client collectors (Vanguard, Invesco, Amundi, Franklin Templeton)
- Keyword alerting (real-time notifications)
- Simple web UI for search + digest archive
- Docker-compose packaging

### Phase 3 — Intelligence Layer

- Trend detection (e.g., "ESG index launches up 40% QoQ")
- Competitive dashboard (who launched what, market share shifts)
- Entity extraction (NER) for auto-tagging
- Sentiment tagging on news items
- Integration with internal FTSE Russell systems
- Multi-user support with role-based access

## 12. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Website structure changes break scrapers | Collection gaps | Monitor for failures; use RSS where available; keep scrapers modular for quick fixes |
| Rate limiting / IP blocking | Data loss | Respect robots.txt; use delays; rotate user-agents |
| Google News RSS changes/removal | Lose catch-all news source | Have fallback to direct site RSS feeds |
| SQLite concurrency limits | Unlikely at this scale | Single-writer model (one cron job); migrate to Postgres in Phase 3 if needed |
| LLM summarisation hallucinations | Misleading digest | Always include source link; use conservative prompts; review for first 2 weeks |
| GDPR / copyright concerns | Legal exposure | Store for internal use only; don't republish full articles; store snippets + links |

## 13. Success Metrics

- Digest generated by 07:00 London time, 95%+ of business days
- Zero missed major index launches or ETF actions (validated weekly)
- Search returns relevant results in <1 second (SQLite FTS5 is fast)
- <30 min/week maintenance effort after initial setup
- Phase 1 runs with zero credentials and zero cost
