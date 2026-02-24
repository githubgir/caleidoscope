"""
AI-powered digest summarisation using Claude.
"""
import json


def summarise_digest(
    sections,
    items_by_section,
    cadence="daily",
    anthropic_api_key=None
):
    """
    Generate AI summaries for the digest using Claude.

    Args:
        sections: List of section configs with keys and titles
        items_by_section: Dict mapping section keys to lists of items
        cadence: "daily", "weekly", or "monthly"
        anthropic_api_key: Optional Anthropic API key

    Returns:
        Dict with:
            - executive_summary: str or None
            - sections: dict mapping section key to summary string or None
    """
    # Default response with no summaries
    default_response = {
        "executive_summary": None,
        "sections": {section["key"]: None for section in sections}
    }

    if not anthropic_api_key:
        return default_response

    try:
        import anthropic
    except ImportError:
        # Anthropic library not installed - return no summaries
        return default_response

    try:
        client = anthropic.Anthropic(api_key=anthropic_api_key)

        # Build prompt with all items grouped by section
        period_text = {
            "daily": "past 24 hours",
            "weekly": "past week",
            "monthly": "past month"
        }.get(cadence, "recent period")

        # Build structured content for each section
        sections_text = []
        total_items = 0

        for section in sections:
            section_key = section["key"]
            section_title = section["title"]
            section_items = items_by_section.get(section_key, [])

            if not section_items:
                continue

            total_items += len(section_items)
            sections_text.append(f"\n### {section_title} ({len(section_items)} items)\n")

            for item in section_items[:20]:  # Limit to 20 items per section to manage token usage
                sections_text.append(
                    f"- {item.title}\n"
                    f"  Source: {item.source}"
                    f"{' (' + item.entity + ')' if item.entity else ''}\n"
                    f"  Published: {item.published_at or 'Unknown'}\n"
                )
                if item.body:
                    # Include first 200 chars of body for context
                    snippet = item.body[:200].strip()
                    if len(item.body) > 200:
                        snippet += "..."
                    sections_text.append(f"  Summary: {snippet}\n")

        if total_items == 0:
            return default_response

        content = "".join(sections_text)

        # Adjust token budget based on cadence
        max_tokens = {
            "daily": 4096,
            "weekly": 6144,
            "monthly": 8192
        }.get(cadence, 4096)

        # System prompt
        system_prompt = (
            "You are a market intelligence analyst at FTSE Russell, the global index provider. "
            f"Summarise the following items collected over the {period_text}. "
            "Be factual, concise, and highlight competitive implications for FTSE Russell. "
            "Do not make up information. Focus on themes, patterns, and notable developments."
        )

        # User prompt asking for structured output
        user_prompt = (
            f"Please analyze these {total_items} market intelligence items and provide:\n\n"
            "1. An executive summary (2-3 sentences) covering the key themes and developments.\n\n"
            "2. For each section below, provide a 2-3 sentence narrative summary highlighting the most significant items and patterns.\n\n"
            f"{content}\n\n"
            "Format your response as JSON with this structure:\n"
            "{\n"
            '  "executive_summary": "...",\n'
            '  "sections": {\n'
            '    "section_key": "summary text",\n'
            "    ...\n"
            "  }\n"
            "}\n\n"
            f"Section keys to include: {', '.join([s['key'] for s in sections])}"
        )

        # Call Claude API
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        # Parse response
        response_text = message.content[0].text

        # Try to extract JSON from response
        # Look for JSON block in the response
        try:
            # First try parsing the whole response as JSON
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find JSON block in markdown code fence
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                # Try to find raw JSON in the text
                json_match = re.search(r'\{.*"executive_summary".*\}', response_text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    # Fallback: parse manually
                    result = _parse_summaries_fallback(response_text, sections)

        # Ensure all sections have a value
        if "sections" not in result:
            result["sections"] = {}

        for section in sections:
            if section["key"] not in result["sections"]:
                result["sections"][section["key"]] = None

        return result

    except Exception as e:
        # If anything fails, return default (no summaries)
        print(f"Warning: Failed to generate AI summaries: {e}")
        return default_response


def _parse_summaries_fallback(text, sections):
    """Fallback parser if JSON extraction fails."""
    result = {
        "executive_summary": None,
        "sections": {}
    }

    # Try to extract executive summary
    import re
    exec_match = re.search(r'executive.summary[:\s]*(.+?)(?:\n\n|\n#|\nsection)', text, re.IGNORECASE | re.DOTALL)
    if exec_match:
        result["executive_summary"] = exec_match.group(1).strip()

    # Try to extract section summaries
    for section in sections:
        section_key = section["key"]
        section_title = section["title"]

        # Look for section by title or key
        pattern = rf'(?:{section_title}|{section_key})[:\s]*(.+?)(?:\n\n|\n#|$)'
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            result["sections"][section_key] = match.group(1).strip()
        else:
            result["sections"][section_key] = None

    return result
