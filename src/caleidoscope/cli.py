"""Command-line interface for Caleidoscope."""

import asyncio
from datetime import datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from caleidoscope.config import load_config
from caleidoscope.db.models import Item
from caleidoscope.db.session import get_session, init_db

app = typer.Typer(
    name="caleidoscope",
    help="Market Intelligence Aggregator for Index & ETF Ecosystem",
    no_args_is_help=True,
)
console = Console()


@app.command()
def init_db_cmd(
    db_path: str = typer.Option(
        None, "--db-path", help="Path to SQLite database (overrides config)"
    ),
):
    """Initialize the database with tables and FTS5 indexes."""
    config = load_config()
    db = db_path or config.db_path

    init_db(db)
    console.print(f"[green]✓[/green] Database initialized at {db}")


@app.command()
def collect(
    all: bool = typer.Option(False, "--all", help="Run all enabled collectors"),
    source: str = typer.Option(
        None, "--source", help="Comma-separated list of collector names to run"
    ),
    db_path: str = typer.Option(None, "--db-path", help="Path to SQLite database"),
):
    """Collect items from configured sources."""
    config = load_config()
    db = db_path or config.db_path

    # Import collector registry
    from caleidoscope.collectors import ALL_COLLECTORS

    if not ALL_COLLECTORS:
        console.print(
            "[yellow]Warning:[/yellow] No collectors found. "
            "Agent 2 needs to implement the collector modules."
        )
        return

    # Determine which collectors to run
    collectors_to_run = []

    if all:
        # Run all enabled collectors from config
        for source_config in config.sources:
            if source_config.enabled and source_config.name in ALL_COLLECTORS:
                collectors_to_run.append(source_config.name)
    elif source:
        # Run specific collectors
        collectors_to_run = [s.strip() for s in source.split(",")]
    else:
        console.print("[red]Error:[/red] Must specify --all or --source")
        raise typer.Exit(1)

    if not collectors_to_run:
        console.print("[yellow]No collectors to run[/yellow]")
        return

    # Run collectors
    console.print(f"[blue]Running {len(collectors_to_run)} collector(s)...[/blue]")

    async def run_all_collectors():
        results = []
        for collector_name in collectors_to_run:
            if collector_name not in ALL_COLLECTORS:
                console.print(f"[red]✗[/red] Unknown collector: {collector_name}")
                continue

            console.print(f"\n[cyan]→[/cyan] Running {collector_name}...")

            # Get source config
            source_config = next(
                (s for s in config.sources if s.name == collector_name), None
            )

            # Instantiate collector
            collector_class = ALL_COLLECTORS[collector_name]

            # Check if it needs special initialization (like RSSCollector)
            if hasattr(collector_class, "__init__"):
                try:
                    # Try to instantiate with source config if available
                    if source_config:
                        collector = collector_class(
                            name=source_config.name,
                            feed_urls=source_config.urls,
                            entity=source_config.entity,
                            category_default=source_config.category_default,
                        )
                    else:
                        collector = collector_class()
                except TypeError:
                    # Fallback to no-args instantiation
                    collector = collector_class()
            else:
                collector = collector_class()

            # Run collector
            result = await collector.run(db_path=db, rate_limit=config.rate_limit_seconds)
            results.append(result)

            # Print result
            status = "[green]✓[/green]" if not result.errors else "[yellow]⚠[/yellow]"
            console.print(
                f"{status} {collector_name}: "
                f"{result.items_new} new, {result.items_duplicate} duplicates, "
                f"{len(result.errors)} errors"
            )

            if result.errors:
                for error in result.errors[:3]:  # Show first 3 errors
                    console.print(f"  [red]•[/red] {error}")

        return results

    # Run async collectors
    results = asyncio.run(run_all_collectors())

    # Summary
    total_new = sum(r.items_new for r in results)
    total_dup = sum(r.items_duplicate for r in results)
    console.print(
        f"\n[green]✓[/green] Collection complete: {total_new} new items, {total_dup} duplicates"
    )


@app.command()
def search_cmd(
    query: str = typer.Argument(..., help="Search query"),
    source: str = typer.Option(None, "--source", help="Filter by source"),
    entity: str = typer.Option(None, "--entity", help="Filter by entity"),
    category: str = typer.Option(None, "--category", help="Filter by category"),
    since: str = typer.Option(None, "--since", help="Filter by date (e.g., 7d, 30d)"),
    limit: int = typer.Option(20, "--limit", help="Maximum number of results"),
    db_path: str = typer.Option(None, "--db-path", help="Path to SQLite database"),
):
    """Search collected items using full-text search."""
    try:
        from caleidoscope.search.engine import search
    except ImportError:
        console.print(
            "[red]Error:[/red] Search module not available. "
            "Agent 3 needs to implement search/engine.py"
        )
        raise typer.Exit(1)

    config = load_config()
    db = db_path or config.db_path

    # Perform search
    results = search(
        query=query,
        db_path=db,
        source=source,
        entity=entity,
        category=category,
        since=since,
        limit=limit,
    )

    # Display results
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    console.print(f"\n[blue]Found {len(results)} result(s)[/blue]\n")

    for i, result in enumerate(results, 1):
        console.print(f"[cyan]{i}.[/cyan] [bold]{result.title}[/bold]")
        console.print(f"   Source: {result.source}", end="")
        if result.entity:
            console.print(f" | Entity: {result.entity}", end="")
        if result.category:
            console.print(f" | Category: {result.category}", end="")
        if result.published_at:
            console.print(f" | Published: {result.published_at}")
        else:
            console.print()
        console.print(f"   URL: {result.url}")
        if result.snippet:
            console.print(f"   {result.snippet}")
        console.print()


@app.command()
def digest(
    daily: bool = typer.Option(True, "--daily", help="Generate daily digest"),
    weekly: bool = typer.Option(False, "--weekly", help="Generate weekly digest"),
    monthly: bool = typer.Option(False, "--monthly", help="Generate monthly digest"),
    preview: bool = typer.Option(False, "--preview", help="Print only, don't save"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to file"),
    db_path: str = typer.Option(None, "--db-path", help="Path to SQLite database"),
):
    """Generate a digest (daily, weekly, or monthly)."""
    try:
        from caleidoscope.digest.generator import generate_digest
    except ImportError:
        console.print(
            "[red]Error:[/red] Digest module not available. "
            "Agent 3 needs to implement digest/generator.py"
        )
        raise typer.Exit(1)

    config = load_config()
    db = db_path or config.db_path

    # Determine cadence
    if weekly:
        cadence = "weekly"
    elif monthly:
        cadence = "monthly"
    else:
        cadence = "daily"

    # Generate digest
    console.print(f"[blue]Generating {cadence} digest...[/blue]")

    digest_md = generate_digest(
        cadence=cadence,
        db_path=db,
        save=(save and not preview),
        digest_dir=config.digest_dir,
        anthropic_api_key=config.anthropic_api_key,
    )

    # Display
    console.print("\n" + digest_md)

    if save and not preview:
        console.print(f"\n[green]✓[/green] Digest saved to {config.digest_dir}/")


@app.command()
def run_all(
    db_path: str = typer.Option(None, "--db-path", help="Path to SQLite database"),
):
    """Run all collectors then generate daily digest."""
    console.print("[blue]Running full collection pipeline...[/blue]\n")

    # Run collect --all
    config = load_config()
    db = db_path or config.db_path

    # Collect
    collect(all=True, db_path=db)

    # Digest
    console.print("\n[blue]Generating digest...[/blue]")
    digest(daily=True, db_path=db)

    console.print("\n[green]✓[/green] Pipeline complete")


@app.command()
def status(
    db_path: str = typer.Option(None, "--db-path", help="Path to SQLite database"),
):
    """Show database statistics."""
    config = load_config()
    db = db_path or config.db_path

    session = get_session(db)

    try:
        # Total item count
        total_items = session.execute(select(func.count(Item.id))).scalar()

        # Items per source
        items_by_source = (
            session.execute(
                select(Item.source, func.count(Item.id))
                .group_by(Item.source)
                .order_by(func.count(Item.id).desc())
            )
            .fetchall()
        )

        # Last collected date
        last_collected = session.execute(
            select(func.max(Item.collected_at))
        ).scalar()

        # Display status
        console.print(f"\n[bold]Caleidoscope Status[/bold]")
        console.print(f"Database: {db}")
        console.print(f"Total items: [cyan]{total_items}[/cyan]")

        if last_collected:
            console.print(f"Last collected: [cyan]{last_collected}[/cyan]")

        if items_by_source:
            console.print("\n[bold]Items by Source:[/bold]")
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Source", style="cyan")
            table.add_column("Count", justify="right", style="green")

            for source, count in items_by_source:
                table.add_row(source, str(count))

            console.print(table)

    finally:
        session.close()


if __name__ == "__main__":
    app()
