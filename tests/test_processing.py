"""Tests for processing pipeline (normalizer and tagger)."""

from datetime import datetime

import pytest

from caleidoscope.collectors.base import RawItem
from caleidoscope.processing.normaliser import (
    generate_url_hash,
    normalise_item,
    strip_html,
)
from caleidoscope.processing.tagger import tag_item


class TestNormaliser:
    """Tests for the normaliser module."""

    def test_strip_html_removes_tags(self):
        """Test that HTML tags are removed."""
        html = "<p>This is <b>bold</b> and <i>italic</i> text.</p>"
        result = strip_html(html)
        assert result == "This is bold and italic text."
        assert "<p>" not in result
        assert "<b>" not in result

    def test_strip_html_normalizes_whitespace(self):
        """Test that multiple spaces are normalized."""
        html = "<p>Too    many     spaces</p>"
        result = strip_html(html)
        assert result == "Too many spaces"

    def test_strip_html_handles_empty_string(self):
        """Test that empty string is handled."""
        assert strip_html("") == ""

    def test_strip_html_handles_none(self):
        """Test that None input returns empty string."""
        assert strip_html(None) == ""

    def test_generate_url_hash(self):
        """Test URL hash generation."""
        url = "https://example.com/article"
        hash1 = generate_url_hash(url)

        # Hash should be consistent
        hash2 = generate_url_hash(url)
        assert hash1 == hash2

        # Hash should be different for different URLs
        hash3 = generate_url_hash("https://example.com/other")
        assert hash1 != hash3

        # Hash should be hex string of expected length (SHA-256 = 64 chars)
        assert len(hash1) == 64
        assert all(c in "0123456789abcdef" for c in hash1)

    def test_normalise_item_strips_html_from_body(self):
        """Test that normalise_item strips HTML from body."""
        raw = RawItem(
            title="Test Article",
            url="https://example.com/test",
            source="test",
            body="<p>This is <b>HTML</b> content.</p>",
        )

        normalized = normalise_item(raw)
        assert normalized.body == "This is HTML content."
        assert "<p>" not in normalized.body

    def test_normalise_item_preserves_other_fields(self):
        """Test that other fields are preserved."""
        raw = RawItem(
            title="Test Article",
            url="https://example.com/test",
            source="test_source",
            entity="Test Entity",
            category="news",
            published_at=datetime(2024, 1, 1),
            tags=["test", "example"],
        )

        normalized = normalise_item(raw)
        assert normalized.title == raw.title
        assert normalized.url == raw.url
        assert normalized.source == raw.source
        assert normalized.entity == raw.entity
        assert normalized.category == raw.category
        assert normalized.published_at == raw.published_at
        assert normalized.tags == raw.tags

    def test_normalise_item_handles_no_body(self):
        """Test that items without body are handled."""
        raw = RawItem(
            title="Test Article",
            url="https://example.com/test",
            source="test",
            body=None,
        )

        normalized = normalise_item(raw)
        assert normalized.body is None


class TestTagger:
    """Tests for the tagger module."""

    def test_tag_item_detects_entity_from_title(self):
        """Test entity detection from title."""
        raw = RawItem(
            title="MSCI Launches New ESG Index",
            url="https://example.com/test",
            source="test",
            body="Details about the index.",
        )

        tagged = tag_item(raw)
        assert tagged.entity == "MSCI"

    def test_tag_item_detects_entity_from_body(self):
        """Test entity detection from body text."""
        raw = RawItem(
            title="New Index Launch",
            url="https://example.com/test",
            source="test",
            body="BlackRock's iShares division announces new product.",
        )

        tagged = tag_item(raw)
        assert tagged.entity == "BlackRock"

    def test_tag_item_detects_category(self):
        """Test category detection from keywords."""
        raw = RawItem(
            title="Company Announces Index Launch",
            url="https://example.com/test",
            source="test",
            body="Details about the new index launch.",
        )

        tagged = tag_item(raw)
        assert tagged.category == "index_launch"

    def test_tag_item_does_not_overwrite_existing_entity(self):
        """Test that existing entity is not overwritten."""
        raw = RawItem(
            title="MSCI Article",
            url="https://example.com/test",
            source="test",
            entity="Existing Entity",
            body="Article mentions MSCI.",
        )

        tagged = tag_item(raw)
        assert tagged.entity == "Existing Entity"

    def test_tag_item_does_not_overwrite_existing_category(self):
        """Test that existing category is not overwritten."""
        raw = RawItem(
            title="Index Launch Article",
            url="https://example.com/test",
            source="test",
            category="research",
            body="Article about index launch.",
        )

        tagged = tag_item(raw)
        assert tagged.category == "research"

    def test_tag_item_handles_no_matches(self):
        """Test that items with no keyword matches are handled."""
        raw = RawItem(
            title="Generic Article",
            url="https://example.com/test",
            source="test",
            body="Generic content with no specific keywords.",
        )

        tagged = tag_item(raw)
        assert tagged.entity is None
        assert tagged.category is None

    def test_tag_item_detects_multiple_keywords(self):
        """Test detection with multiple entity keywords."""
        test_cases = [
            ("S&P Dow Jones Index", "S&P DJI"),
            ("STOXX announces new product", "STOXX"),
            ("Vanguard launches fund", "Vanguard"),
            ("Invesco ETF news", "Invesco"),
        ]

        for title, expected_entity in test_cases:
            raw = RawItem(
                title=title,
                url="https://example.com/test",
                source="test",
            )
            tagged = tag_item(raw)
            assert tagged.entity == expected_entity

    def test_tag_item_detects_category_variations(self):
        """Test detection of various category keywords."""
        test_cases = [
            ("ETF launch announcement", "etf_launch"),
            ("Fund closure notice", "etf_closure"),
            ("Fee change update", "fee_change"),
            ("New research paper", "research"),
            ("SEC filing released", "regulatory"),
            ("Market commentary today", "market_commentary"),
            ("Methodology update published", "methodology_change"),
        ]

        for title, expected_category in test_cases:
            raw = RawItem(
                title=title,
                url="https://example.com/test",
                source="test",
            )
            tagged = tag_item(raw)
            assert tagged.category == expected_category
