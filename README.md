# Caleidoscope Market Intelligence Aggregator

A market intelligence aggregator for the Index & ETF ecosystem, designed for FTSE Russell's Index Research & Design team.

## Features

- **Automated Collection**: Scrapes and polls data from competitors (MSCI, S&P DJI, STOXX), clients (BlackRock), and news sources
- **Persistent Storage**: SQLite database with full-text search (FTS5)
- **Smart Tagging**: Auto-detects entities and categories using keyword matching
- **Search**: Full-text search with filters for source, entity, category, and date
- **Digests**: Daily, weekly, and monthly digests with optional AI summaries (Claude API)
- **Zero Credentials**: Phase 1 works with free, public sources only

## Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package
pip install -e .

# Optional: Install with LLM support
pip install -e ".[llm]"

# For development
pip install -e ".[dev]"
```

## Quick Start

```bash
# 1. Initialize the database
caleidoscope init-db

# 2. Run all collectors
caleidoscope collect --all

# 3. Search collected items
caleidoscope search "MSCI ESG" --since 7d

# 4. Generate a digest
caleidoscope digest

# 5. Check status
caleidoscope status
```

## Configuration

### config.yaml

The `config.yaml` file defines all data sources and settings. Each source has:
- `name`: Unique identifier
- `entity`: Company/organization name (or null for news aggregators)
- `enabled`: Whether to include in `--all` collections
- `urls`: List of RSS feeds or API endpoints
- `category_default`: Default category for items from this source

### Environment Variables

Create a `.env` file (see `.env.example`):

```bash
# Optional: Anthropic API key for AI-powered digest summaries
ANTHROPIC_API_KEY=sk-ant-your-api-key-here

# Optional: Override database path
CALEIDOSCOPE_DB=data/caleidoscope.db
```

## CLI Commands

### `caleidoscope init-db`
Initialize the database with tables and FTS5 indexes.

### `caleidoscope collect`
Collect items from configured sources.

Options:
- `--all`: Run all enabled collectors
- `--source msci,edgar`: Run specific collectors (comma-separated)
- `--db-path`: Override database path

### `caleidoscope search`
Search collected items using full-text search.

```bash
caleidoscope search "MSCI ESG" --since 7d --source msci --limit 10
```

Options:
- `--source`: Filter by source
- `--entity`: Filter by entity
- `--category`: Filter by category
- `--since`: Filter by date (e.g., 7d, 30d)
- `--limit`: Maximum results (default: 20)

### `caleidoscope digest`
Generate a digest.

Options:
- `--daily`: Daily digest (default)
- `--weekly`: Weekly digest
- `--monthly`: Monthly digest
- `--preview`: Print only, don't save
- `--no-save`: Don't save to file

### `caleidoscope run-all`
Run all collectors then generate a daily digest.

### `caleidoscope status`
Show database statistics (total items, items per source, last collection date).

## Architecture

```
COLLECTORS → NORMALIZER → TAGGER → DEDUPLICATOR → SQLite
                                                      ↓
                                                   FTS5 Index
                                                      ↓
                                        ┌─────────────┴──────────────┐
                                        ↓                            ↓
                                    SEARCH                       DIGEST
```

### Components

- **Collectors**: Fetch data from sources (RSS, HTML scraping, APIs)
- **Normalizer**: Strips HTML, cleans whitespace, generates URL hashes
- **Tagger**: Auto-detects entities and categories from keywords
- **Database**: SQLite with FTS5 for full-text search
- **Search**: Query items with filters and ranking
- **Digest**: Generates daily/weekly/monthly reports with optional AI summaries

## Development

### Running Tests

```bash
pytest
```

### Code Style

```bash
ruff check .
ruff format .
```

## Project Structure

```
caleidoscope/
├── src/caleidoscope/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py              # Typer CLI
│   ├── config.py           # Configuration management
│   ├── db/
│   │   ├── models.py       # SQLAlchemy models
│   │   └── session.py      # Database session management
│   ├── collectors/
│   │   ├── __init__.py     # Collector registry
│   │   ├── base.py         # BaseCollector abstract class
│   │   └── rss.py          # Generic RSS collector
│   ├── processing/
│   │   ├── normaliser.py   # HTML stripping, whitespace cleanup
│   │   └── tagger.py       # Keyword-based entity/category detection
│   ├── search/             # [Agent 3]
│   └── digest/             # [Agent 3]
├── tests/
│   ├── test_db.py
│   └── test_processing.py
├── config.yaml
├── pyproject.toml
└── README.md
```

## Categories

The system uses these standard categories:
- `index_launch`: New index announcements
- `methodology_change`: Index methodology updates
- `etf_launch`: New ETF launches
- `etf_closure`: ETF closures
- `fee_change`: Fee/expense ratio changes
- `research`: Research papers, white papers
- `regulatory`: SEC filings, regulatory announcements
- `news`: General news coverage
- `market_commentary`: Market analysis and commentary

## License

Internal use only - FTSE Russell Index Research & Design team.
