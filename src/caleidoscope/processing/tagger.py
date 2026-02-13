"""Auto-tags items with entity and category based on keywords."""

from caleidoscope.collectors.base import RawItem

# Entity keyword mapping - lowercase keywords to entity names
ENTITY_KEYWORDS = {
    "msci": "MSCI",
    "msci inc": "MSCI",
    "s&p dow jones": "S&P DJI",
    "s&p global": "S&P DJI",
    "spglobal": "S&P DJI",
    "dow jones": "S&P DJI",
    "stoxx": "STOXX",
    "blackrock": "BlackRock",
    "ishares": "BlackRock",
    "vanguard": "Vanguard",
    "invesco": "Invesco",
    "amundi": "Amundi",
    "franklin templeton": "Franklin Templeton",
    "ftse russell": "FTSE Russell",
    "ftse": "FTSE Russell",
    "russell": "FTSE Russell",
    "morningstar": "Morningstar",
    "solactive": "Solactive",
}

# Category keyword mapping - lowercase keywords to categories
CATEGORY_KEYWORDS = {
    "index launch": "index_launch",
    "new index": "index_launch",
    "launching index": "index_launch",
    "index series": "index_launch",
    "methodology change": "methodology_change",
    "methodology update": "methodology_change",
    "rulebook": "methodology_change",
    "consultation": "methodology_change",
    "rebalance": "methodology_change",
    "etf launch": "etf_launch",
    "new etf": "etf_launch",
    "launching etf": "etf_launch",
    "fund launch": "etf_launch",
    "etf closure": "etf_closure",
    "etf close": "etf_closure",
    "fund closure": "etf_closure",
    "delisting": "etf_closure",
    "fee change": "fee_change",
    "expense ratio": "fee_change",
    "fee reduction": "fee_change",
    "research": "research",
    "white paper": "research",
    "research paper": "research",
    "study": "research",
    "analysis": "research",
    "regulatory": "regulatory",
    "sec filing": "regulatory",
    "n-1a": "regulatory",
    "19b-4": "regulatory",
    "edgar": "regulatory",
    "market commentary": "market_commentary",
    "market update": "market_commentary",
    "market view": "market_commentary",
    "outlook": "market_commentary",
}


def tag_item(item: RawItem) -> RawItem:
    """Auto-detect entity and category from title and body using keywords.

    Only overwrites entity/category if not already set by the collector.

    Args:
        item: Raw item to tag

    Returns:
        Tagged RawItem with detected entity and category
    """
    # Create a copy to avoid modifying the original
    tagged = item.model_copy(deep=True)

    # Combine title and body for keyword matching
    search_text = (tagged.title + " " + (tagged.body or "")).lower()

    # Detect entity if not already set
    if not tagged.entity:
        for keyword, entity in ENTITY_KEYWORDS.items():
            if keyword in search_text:
                tagged.entity = entity
                break

    # Detect category if not already set
    if not tagged.category:
        for keyword, category in CATEGORY_KEYWORDS.items():
            if keyword in search_text:
                tagged.category = category
                break

    return tagged
