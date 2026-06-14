"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "retry_note": None,          # set if search was retried with looser constraints
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.
    """
    session = _new_session(query, wardrobe)

    # Step 2: parse the query with regex
    text = query.lower()

    size_match = re.search(
        r'\b(xxs|xs|s/m|m/l|l/xl|s|m|l|xl|xxl|w\d{2}(?:\s*l\d{2})?|one\s*size)\b',
        text,
    )
    price_match = re.search(r'under\s*\$?([\d.]+)', text)

    raw_description = query
    # Strip trailing "under $X" and "size Y" clauses to isolate the item description
    raw_description = re.sub(r'\bunder\s*\$?[\d.]+', '', raw_description, flags=re.IGNORECASE)
    raw_description = re.sub(
        r'\bsize\s*(xxs|xs|s/m|m/l|l/xl|s|m|l|xl|xxl|w\d{2}(?:\s*l\d{2})?|one\s*size)\b',
        '', raw_description, flags=re.IGNORECASE,
    )
    description = raw_description.strip().strip(',').strip()

    session["parsed"] = {
        "description": description,
        "size": size_match.group(0).strip() if size_match else None,
        "max_price": float(price_match.group(1)) if price_match else None,
    }

    # Step 3: call search_listings with retry-with-fallback
    desc = session["parsed"]["description"]
    size = session["parsed"]["size"]
    max_price = session["parsed"]["max_price"]
    retry_note = None

    session["search_results"] = search_listings(desc, size, max_price)

    # Retry 1: drop size filter
    if not session["search_results"] and size is not None:
        session["search_results"] = search_listings(desc, None, max_price)
        if session["search_results"]:
            retry_note = f"No results for size {size}, so I searched all sizes instead."
            size = None

    # Retry 2: drop price filter
    if not session["search_results"] and max_price is not None:
        session["search_results"] = search_listings(desc, size, None)
        if session["search_results"]:
            note = f"price limit removed (was ${max_price:.2f})"
            retry_note = (retry_note + f" Also {note}." if retry_note else f"No results under ${max_price:.2f}, so I {note}.")

    session["retry_note"] = retry_note

    if not session["search_results"]:
        session["error"] = (
            f"No listings found matching '{desc}' even after broadening the search. "
            f"Try different keywords."
        )
        return session

    # Step 4: select the top result
    session["selected_item"] = session["search_results"][0]

    # Step 5: suggest an outfit
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
    )

    # Step 6: create the fit card
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"],
        session["selected_item"],
    )

    # Step 7: return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
