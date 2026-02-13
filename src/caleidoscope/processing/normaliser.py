"""Normalizes raw items by cleaning HTML and generating hashes."""

import hashlib
import re

from bs4 import BeautifulSoup

from caleidoscope.collectors.base import RawItem


def strip_html(text: str) -> str:
    """Remove HTML tags and clean up whitespace.

    Args:
        text: Raw HTML text

    Returns:
        Plain text with HTML tags removed
    """
    if not text:
        return ""

    # Parse HTML
    soup = BeautifulSoup(text, "html.parser")

    # Extract text
    text = soup.get_text(separator=" ", strip=True)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def generate_url_hash(url: str) -> str:
    """Generate a SHA-256 hash of the URL for deduplication.

    Args:
        url: The URL to hash

    Returns:
        Hexadecimal SHA-256 hash string
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def normalise_item(raw: RawItem) -> RawItem:
    """Normalize a raw item by cleaning HTML and generating url_hash.

    Args:
        raw: Raw item to normalize

    Returns:
        Normalized RawItem with cleaned body and url_hash
    """
    # Create a copy to avoid modifying the original
    normalized = raw.model_copy(deep=True)

    # Strip HTML from body if present
    if normalized.body:
        normalized.body = strip_html(normalized.body)

    # Note: We don't add url_hash to RawItem as it's added during DB insertion
    # The collector's run() method will use generate_url_hash() directly

    return normalized
