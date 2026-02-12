# Market Intelligence Aggregator — Product Requirements Document

## 1. Problem Statement

The Head of Index Research & Design at FTSE Russell needs a single system that continuously monitors competitors (MSCI, S&P Dow Jones, STOXX), clients (Vanguard, Invesco, Amundi, BlackRock, Franklin Templeton), and the broader index/ETF ecosystem for:

- **New index launches** (filings, announcements, methodology changes)
- **ETF flows and AUM** (which products are gathering/losing assets)
- **Research publications** (white papers, methodology papers, consultation papers)
- **Regulatory and news** (FT articles, industry press, SEC/FCA filings)
- **Product actions** (fund launches, closures, fee changes, rebalances)

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
4. **Daily digest** — an AI-summarised morning briefing delivered via email (and optionally viewable in a web UI).
5. **Low maintenance** — once configured, should run unattended; alert on failures.

## 4. Source Inventory

### 4.1 Competitor websites (scrape / RSS)

| Entity | What to monitor | Likely method |
|--------|----------------|---------------|
| **MSCI** | Index announcements, methodology docs, consultations, blog | RSS (`msci.com/our-solutions/indexes`), scrape announcements page |
| **S&P Dow Jones Indices** | Index launches, methodology changes, research, press releases | RSS feed, scrape press room, EDGAR for rule filings |
| **STOXX** | New indices, rulebook updates, announcements | Scrape `stoxx.com/index-medialist`, RSS |
| **Solactive** | Index launches (rising competitor) | Scrape press page |
| **Morningstar Indexes** | Methodology, announcements | RSS / scrape |

### 4.2 Client / asset manager websites (scrape / RSS)

| Entity | What to monitor | Likely method |
|--------|----------------|---------------|
| **BlackRock / iShares** | ETF launches, closures, fee changes, blog | RSS, scrape product page, iShares ETF screener |
| **Vanguard** | Fund launches, index changes, research | Scrape press room |
| **Invesco** | ETF launches, index switches, research | RSS, scrape |
| **Amundi** | ETF launches (EU focus), research | Scrape |
| **Franklin Templeton** | ETF/index fund launches | Scrape press releases |

### 4.3 Data feeds (API)

| Source | Data | Method |
|--------|------|--------|
| **LSEG Data Library** (Refinitiv) | ETF AUM, flows, index returns, new listings | Python SDK (`lseg.data`) with user credentials |
| **SEC EDGAR** | ETF registration statements (N-1A), index-related 19b-4 filings | EDGAR FULL-TEXT search API (free) |
| **FCA / ESMA** | EU regulatory filings | Scrape / RSS |

### 4.4 News & research (API / scrape)

| Source | Data | Method |
|--------|------|--------|
| **Financial Times** | Articles mentioning indices, ETFs, named entities | FT API or scrape with subscription cookies |
| **ETF.com / ETF Stream** | ETF news, flow data, new launches | RSS / scrape |
| **IndexUniverse / ETF Trends** | Industry commentary | RSS |
| **Google News** | Catch-all for entity mentions | Google News RSS with query parameters |
| **Google Scholar / SSRN** | Academic & practitioner research on indexing | Scholar RSS alerts / SSRN API |

## 5. Functional Requirements

### FR-1: Data Ingestion Pipeline

- Each source has a dedicated **collector** (a Python module) that:
  - Connects to the source (HTTP scrape, RSS parse, API call)
  - Extracts structured items: `{title, url, date, source, entity, body_text, category, raw_html}`
  - Handles pagination, rate limiting, retries, and error logging
- A **scheduler** (cron or Celery Beat) triggers collectors at configurable intervals (default: daily 05:00 UTC)
- A **deduplication** layer prevents storing the same item twice (hash on URL + title)
- Failures are logged and an alert email is sent if >N collectors fail

### FR-2: Storage

- Items stored in a **PostgreSQL** database (structured metadata) + body text
- Full-text search index via **PostgreSQL tsvector** or an **Elasticsearch** sidecar
- Optional: raw HTML/PDF archived to **S3-compatible object storage** for compliance/reference
- Tagging: each item auto-tagged with:
  - Entity (MSCI, BlackRock, etc.)
  - Category (index launch, ETF flow, research, regulatory, news)
  - Detected tickers / index names (via NER or keyword matching)

### FR-3: Search Interface

- **CLI search**: `python -m caleidoscope search "MSCI ESG" --since 7d --source msci,ft`
- **Web UI** (optional, Phase 2): simple search page with filters (date range, source, entity, category)
- Returns results ranked by relevance, with snippet preview

### FR-4: Daily Digest / Morning Briefing

- Runs after all collectors complete (e.g., 06:30 UTC)
- Collects all new items from the last 24 hours
- Groups by category:
  1. **Index launches & methodology changes**
  2. **ETF product actions** (launches, closures, fee changes)
  3. **AUM & flow highlights** (top gatherers, largest outflows)
  4. **Research & publications**
  5. **News & regulatory**
- Each section: 3–5 bullet summaries generated by an LLM (Claude API or OpenAI)
- Individual items listed below each section with title, source, one-line summary, link
- Output formats:
  - **Email** (HTML) — sent to configured recipients
  - **Markdown file** — archived in the repo / on disk
  - **Web page** (Phase 2) — viewable in browser

### FR-5: Alerting (Phase 2)

- User-defined keyword watches (e.g., "FTSE Russell", "Russell 2000", "ESG index methodology")
- Instant email/Slack notification when a matching item is ingested (not waiting for morning digest)

## 6. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| Reliability | Collectors must handle source downtime gracefully; retry 3x with backoff |
| Latency | Digest email delivered by 07:00 London time |
| Data retention | All items retained indefinitely; raw HTML for 1 year |
| Security | Credentials stored in environment variables or a secrets manager, never in code |
| Cost | Prefer free/low-cost infra; cloud VM or local server; LLM cost < £5/day |
| Compliance | Respect robots.txt; rate-limit scraping to 1 req/2s per domain |

## 7. Delivery Format Decision

### Recommended: **Email digest + CLI search + optional web UI**

| Option | Pros | Cons |
|--------|------|------|
| **Email digest** | Zero friction — arrives in inbox; readable on phone; shareable | Not interactive; can't search history from email |
| **Web app** | Searchable, filterable, rich UI | Requires hosting, auth, maintenance; another thing to check |
| **Slack/Teams bot** | Push notifications; conversational queries | Requires workspace integration; noisy |
| **CLI tool** | Powerful search; scriptable | Not accessible on phone; requires terminal |

**Recommendation**: Start with **email as the primary delivery channel** (everyone checks email in the morning). Add a **CLI search tool** for ad-hoc queries into the archive. A lightweight web UI can follow in Phase 2 if needed.

## 8. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        SCHEDULER (cron)                         │
│                   05:00 UTC — trigger collectors                │
└──────────┬──────────────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     COLLECTOR MODULES                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ msci.py  │ │ sp_dji.py│ │ stoxx.py │ │ edgar.py │  ...      │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       │             │            │             │                 │
│       ▼             ▼            ▼             ▼                 │
│  ┌──────────────────────────────────────────────────┐           │
│  │           NORMALISER + DEDUPLICATOR              │           │
│  └──────────────────────┬───────────────────────────┘           │
└─────────────────────────┼───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      POSTGRESQL DATABASE                        │
│  items(id, url, title, date, source, entity, category,          │
│        body, summary, tags, raw_hash, created_at)               │
│  + full-text search index (tsvector)                            │
└──────────┬──────────────────────────────────┬───────────────────┘
           │                                  │
           ▼                                  ▼
┌─────────────────────┐           ┌───────────────────────┐
│   DIGEST GENERATOR  │           │   SEARCH ENGINE       │
│  (06:30 UTC cron)   │           │   (CLI / web API)     │
│  • query last 24h   │           │   • full-text query   │
│  • group by category│           │   • filter by entity, │
│  • LLM summarise    │           │     source, date,     │
│  • render HTML email│           │     category          │
│  • send via SMTP    │           └───────────────────────┘
└─────────────────────┘
```

## 9. Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Language | **Python 3.12+** | Best ecosystem for scraping, data, ML |
| Scraping | **httpx** + **BeautifulSoup4** / **Playwright** (JS-rendered pages) | Async HTTP; Playwright for SPAs |
| RSS | **feedparser** | Standard, battle-tested |
| Data API | **lseg-data** (LSEG Data Library SDK) | Direct access to Refinitiv data |
| Database | **PostgreSQL 16** | Robust, free, excellent full-text search |
| ORM | **SQLAlchemy 2.0** + **Alembic** | Migrations, type safety |
| Scheduling | **cron** (simple) or **Celery + Redis** (if scaling) | Start simple |
| LLM | **Claude API** (Anthropic) | Summarisation quality |
| Email | **SMTP** via Python `smtplib` or **SendGrid API** | Reliable delivery |
| Config | **YAML** config file + **env vars** for secrets | Readable, secure |
| Containerisation | **Docker + docker-compose** | Reproducible deployment |

## 10. Data Model

```sql
CREATE TABLE items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             TEXT NOT NULL,
    url_hash        TEXT NOT NULL,          -- SHA-256 of URL for dedup
    title           TEXT NOT NULL,
    published_at    TIMESTAMPTZ,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    source          TEXT NOT NULL,          -- 'msci', 'sp_dji', 'ft', etc.
    entity          TEXT,                   -- 'MSCI', 'BlackRock', etc.
    category        TEXT,                   -- 'index_launch', 'etf_flow', 'research', etc.
    body            TEXT,                   -- cleaned text content
    summary         TEXT,                   -- LLM-generated one-liner
    tags            TEXT[],                 -- extracted tickers, index names
    raw_html_ref    TEXT,                   -- S3 key for raw archive
    search_vector   TSVECTOR,              -- full-text search
    UNIQUE(url_hash)
);

CREATE INDEX idx_items_search ON items USING GIN(search_vector);
CREATE INDEX idx_items_source ON items(source);
CREATE INDEX idx_items_entity ON items(entity);
CREATE INDEX idx_items_published ON items(published_at DESC);
CREATE INDEX idx_items_category ON items(category);

CREATE TABLE digest_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    item_count      INT,
    email_sent      BOOLEAN DEFAULT FALSE,
    recipients      TEXT[],
    digest_md       TEXT                   -- archived markdown
);
```

## 11. Scope & Phasing

### Phase 1 — MVP (target: working end-to-end)

- 5 collectors: MSCI, S&P DJI, STOXX, BlackRock/iShares, FT (via RSS + basic scrape)
- PostgreSQL storage with dedup and full-text search
- CLI search tool
- Daily email digest with LLM summaries
- Docker-compose deployment (Postgres + app)
- LSEG Data Library integration for ETF AUM/flow snapshot

### Phase 2 — Expand & Enrich

- Remaining collectors (Vanguard, Invesco, Amundi, Franklin Templeton, Solactive, EDGAR)
- Keyword alerting (real-time email/Slack on match)
- Simple web UI for search + digest archive
- Entity extraction (NER) for auto-tagging index names, tickers
- Sentiment tagging on news items

### Phase 3 — Intelligence Layer

- Trend detection (e.g., "ESG index launches up 40% QoQ")
- Competitive dashboard (who launched what, market share shifts)
- Integration with internal FTSE Russell systems
- Multi-user support with role-based access

## 12. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Website structure changes break scrapers | Collection gaps | Monitor for failures; use RSS where available; keep scrapers modular for quick fixes |
| Rate limiting / IP blocking | Data loss | Respect robots.txt; use delays; rotate user-agents; consider proxy |
| LLM summarisation hallucinations | Misleading digest | Always include source link; use conservative prompts; review summaries for first 2 weeks |
| LSEG API credential expiry | Flow data gaps | Alert on auth failures; document renewal process |
| FT paywall blocks content | Missing news | Use authenticated session; fall back to headline + link if full text unavailable |
| GDPR / copyright concerns | Legal exposure | Store for internal use only; don't republish full articles; store snippets + links |

## 13. Success Metrics

- Digest delivered by 07:00 London time, 95%+ of business days
- Zero missed major index launches or ETF actions (validated weekly)
- Search returns relevant results in <2 seconds
- <30 min/week maintenance effort after initial setup
