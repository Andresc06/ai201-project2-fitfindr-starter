"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Returns up to 5 listing dicts sorted by relevance score (highest first).
    Returns [] if nothing matches — does not raise an exception.
    """
    listings = load_listings()

    # Price filter
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    # Size filter — case-insensitive substring match
    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    # Keyword scoring: count how many words from description appear in the
    # combined searchable text (title + description + style_tags joined)
    keywords = set(re.findall(r'\w+', description.lower()))

    scored = []
    for listing in listings:
        searchable = " ".join([
            listing["title"],
            listing["description"],
            " ".join(listing["style_tags"]),
        ]).lower()
        score = sum(1 for kw in keywords if kw in searchable)
        if score > 0:
            scored.append((score, listing))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [listing for _, listing in scored[:5]]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Returns a non-empty string. Falls back to a hardcoded message if the LLM
    call fails.
    """
    client = _get_groq_client()

    item_summary = (
        f"Title: {new_item['title']}\n"
        f"Category: {new_item['category']}\n"
        f"Style tags: {', '.join(new_item['style_tags'])}\n"
        f"Colors: {', '.join(new_item['colors'])}\n"
        f"Condition: {new_item['condition']}\n"
        f"Price: ${new_item['price']:.2f}"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = (
            f"You are a personal stylist helping someone style a thrifted piece.\n\n"
            f"New item:\n{item_summary}\n\n"
            f"The user hasn't told you what's in their wardrobe yet. "
            f"Suggest 1–2 generic outfit archetypes that would pair well with this item. "
            f"Describe the vibe, what kinds of bottoms/tops/shoes work, and why. "
            f"Keep it to 3–5 sentences total."
        )
    else:
        wardrobe_text = "\n".join(
            f"- {w['name']} ({w['category']}, {', '.join(w['colors'])}, "
            f"tags: {', '.join(w['style_tags'])})"
            + (f" — {w['notes']}" if w.get("notes") else "")
            for w in wardrobe_items
        )
        prompt = (
            f"You are a personal stylist helping someone style a thrifted piece.\n\n"
            f"New item:\n{item_summary}\n\n"
            f"User's wardrobe:\n{wardrobe_text}\n\n"
            f"Suggest 1–2 complete outfit combinations using the new item and specific "
            f"named pieces from the wardrobe above. For each outfit, explain why the "
            f"pieces work together. Keep it to 3–5 sentences total. "
            f"Refer to wardrobe pieces by their exact names."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        tags = ", ".join(new_item.get("style_tags", []))
        category = new_item.get("category", "piece")
        complements = {
            "tops": "bottoms in neutral tones",
            "bottoms": "a simple top in a neutral color",
            "outerwear": "a basic tee and jeans underneath",
            "shoes": "a monochrome outfit to let them stand out",
            "accessories": "a minimal outfit so the accessory reads",
        }
        complement = complements.get(category, "complementary basics")
        return (
            f"Could not generate outfit suggestions right now. "
            f"The item is a {category} in {tags} style — "
            f"try pairing it with {complement}."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Returns a 2–4 sentence string. Guards against empty outfit input.
    Falls back to a hardcoded message if the LLM call fails.
    """
    if not outfit or not outfit.strip():
        return (
            "Outfit details are missing — cannot generate a fit card. "
            "Check that suggest_outfit ran successfully."
        )

    client = _get_groq_client()

    title = new_item.get("title", "thrifted find")
    price = new_item.get("price", 0)
    platform = new_item.get("platform", "a thrift platform")
    tags = ", ".join(new_item.get("style_tags", []))

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok caption for this thrifted OOTD post.\n\n"
        f"Thrifted item: {title}, found on {platform} for ${price:.2f}.\n"
        f"Style vibe: {tags}.\n"
        f"Outfit: {outfit}\n\n"
        f"Rules:\n"
        f"- Write in first-person casual voice, like a real OOTD post\n"
        f"- Mention the item name, price, and platform exactly once each\n"
        f"- Capture the outfit vibe using specific aesthetic words\n"
        f"- Do NOT sound like a product description or ad\n"
        f"- 2–4 sentences only"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=150,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        preview = outfit[:200].strip()
        return (
            f"Could not generate a fit card right now. "
            f"Here's the look: {preview}."
        )
