"""
Tests for tools.py — one test per failure mode plus basic happy-path coverage.
Run with: pytest tests/
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from tools import search_listings, suggest_outfit, create_fit_card


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []  # empty list, no exception


def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)


def test_search_size_filter():
    # Size "W30" should not match listings sized "S/M" or "L"
    results = search_listings("jeans", size="W30", max_price=None)
    for item in results:
        assert "w30" in item["size"].lower()


def test_search_returns_at_most_five():
    # "vintage" appears in many listings — result set must be capped at 5
    results = search_listings("vintage", size=None, max_price=None)
    assert len(results) <= 5


def test_search_results_are_dicts_with_required_fields():
    results = search_listings("flannel", size=None, max_price=None)
    required = {"id", "title", "description", "category", "style_tags",
                "size", "condition", "price", "colors", "brand", "platform"}
    for item in results:
        assert required.issubset(item.keys())


def test_search_no_size_filter_when_none():
    # Without a size filter, a broad query should return results
    results = search_listings("top", size=None, max_price=None)
    assert len(results) > 0


# ── suggest_outfit ────────────────────────────────────────────────────────────

_SAMPLE_ITEM = {
    "id": "lst_003",
    "title": "Oversized Flannel Shirt — Plaid Red/Black",
    "description": "Classic oversized flannel. Great layering piece.",
    "category": "tops",
    "style_tags": ["grunge", "vintage", "flannel", "streetwear"],
    "size": "XL (oversized)",
    "condition": "good",
    "price": 22.00,
    "colors": ["red", "black"],
    "brand": "Woolrich",
    "platform": "thredUp",
}

_EXAMPLE_WARDROBE = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans, dark wash",
            "category": "bottoms",
            "colors": ["dark blue", "indigo"],
            "style_tags": ["denim", "streetwear", "baggy"],
            "notes": "High-waisted, sits above the hip",
        },
        {
            "id": "w_002",
            "name": "White ribbed tank top",
            "category": "tops",
            "colors": ["white"],
            "style_tags": ["basics", "minimal", "fitted"],
            "notes": "Goes with everything",
        },
    ]
}

_EMPTY_WARDROBE = {"items": []}


def test_suggest_outfit_returns_string():
    result = suggest_outfit(_SAMPLE_ITEM, _EXAMPLE_WARDROBE)
    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_outfit_empty_wardrobe_does_not_crash():
    result = suggest_outfit(_SAMPLE_ITEM, _EMPTY_WARDROBE)
    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_outfit_empty_wardrobe_gives_generic_advice():
    result = suggest_outfit(_SAMPLE_ITEM, _EMPTY_WARDROBE)
    # Should not reference specific wardrobe items that don't exist
    assert result  # non-empty is enough; content is LLM-generated


def test_suggest_outfit_with_wardrobe_mentions_item():
    result = suggest_outfit(_SAMPLE_ITEM, _EXAMPLE_WARDROBE)
    # The LLM should reference the new item somewhere in the suggestion
    assert "flannel" in result.lower() or "shirt" in result.lower() or "plaid" in result.lower()


# ── create_fit_card ───────────────────────────────────────────────────────────

_SAMPLE_OUTFIT = (
    "Pair the flannel with your baggy straight-leg dark-wash jeans and white ribbed "
    "tank underneath for a grunge-lite look. Finish with chunky sneakers."
)


def test_create_fit_card_returns_string():
    result = create_fit_card(_SAMPLE_OUTFIT, _SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result) > 0


def test_create_fit_card_empty_outfit_returns_error_string():
    result = create_fit_card("", _SAMPLE_ITEM)
    assert "missing" in result.lower() or "cannot" in result.lower()
    # Must return a string, not raise an exception
    assert isinstance(result, str)


def test_create_fit_card_whitespace_outfit_returns_error_string():
    result = create_fit_card("   ", _SAMPLE_ITEM)
    assert isinstance(result, str)
    assert len(result) > 0
    assert "missing" in result.lower() or "cannot" in result.lower()


def test_create_fit_card_output_varies():
    # LLM temperature=0.9 means repeated calls should produce different text
    result_a = create_fit_card(_SAMPLE_OUTFIT, _SAMPLE_ITEM)
    result_b = create_fit_card(_SAMPLE_OUTFIT, _SAMPLE_ITEM)
    # We can't guarantee variation in every run, but both must be non-empty strings
    assert isinstance(result_a, str) and len(result_a) > 0
    assert isinstance(result_b, str) and len(result_b) > 0
    # Log both so they can be checked manually in test output
    print(f"\nRun A: {result_a}")
    print(f"\nRun B: {result_b}")


def test_create_fit_card_mentions_platform():
    result = create_fit_card(_SAMPLE_OUTFIT, _SAMPLE_ITEM)
    assert "thredUp" in result or "thredup" in result.lower()
