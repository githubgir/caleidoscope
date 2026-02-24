"""
Digest renderer using Jinja2 templates.
"""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


def _get_templates_dir() -> Path:
    """Get the path to the templates directory."""
    return Path(__file__).parent / "templates"


def _format_item_for_template(item):
    """Format an Item object for template rendering."""
    # Format the date nicely
    date_str = "Unknown"
    if item.published_at:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(item.published_at.replace('Z', '+00:00'))
            date_str = dt.strftime("%b %d, %Y")
        except:
            date_str = item.published_at

    return {
        "title": item.title,
        "source": item.source,
        "entity": item.entity,
        "category": item.category,
        "url": item.url,
        "date": date_str,
        "published_at": item.published_at,
        "body": item.body,
        "summary": item.summary
    }


def render_digest(
    cadence: str,
    date_str: dict,
    sections_data: list,
    summaries: dict,
    item_count: int,
    error_count: int = 0,
    entity_activity: dict | None = None
) -> str:
    """
    Render digest to markdown using Jinja2 templates.

    Args:
        cadence: "daily", "weekly", or "monthly"
        date_str: Dict with date formatting info (date, week_number, year, etc.)
        sections_data: List of dicts with "key", "title", "items" (Item objects)
        summaries: Dict with "executive_summary" and "sections" (key -> summary)
        item_count: Total number of items in digest
        error_count: Number of collector errors
        entity_activity: Optional dict of entity -> category -> count

    Returns:
        Rendered markdown string
    """
    # Set up Jinja2 environment
    templates_dir = _get_templates_dir()
    env = Environment(loader=FileSystemLoader(str(templates_dir)))

    # Select template based on cadence
    template_name = f"{cadence}.md.j2"
    template = env.get_template(template_name)

    # Format sections for template
    formatted_sections = []
    for section in sections_data:
        formatted_items = [_format_item_for_template(item) for item in section["items"]]

        section_summary = None
        if summaries and summaries.get("sections"):
            section_summary = summaries["sections"].get(section["key"])

        formatted_sections.append({
            "title": section["title"],
            "items": formatted_items,
            "summary": section_summary
        })

    # Prepare context for template
    context = {
        "item_count": item_count,
        "error_count": error_count,
        "executive_summary": summaries.get("executive_summary") if summaries else None,
        "sections": formatted_sections,
        **date_str  # Unpack date formatting info
    }

    # Add entity activity for weekly/monthly
    if entity_activity:
        # Format entity activity as list for easier template rendering
        entity_activity_list = []
        all_categories = set()

        # Collect all categories
        for entity_data in entity_activity.values():
            all_categories.update(entity_data.keys())

        all_categories = sorted(all_categories)

        # Build rows
        for entity, categories in sorted(entity_activity.items()):
            row = {"entity": entity}
            for category in all_categories:
                row[category] = categories.get(category, 0)
            row["total"] = sum(categories.values())
            entity_activity_list.append(row)

        context["entity_activity"] = entity_activity_list
        context["entity_activity_categories"] = all_categories

    # Render template
    markdown = template.render(**context)

    return markdown
