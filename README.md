# FitFindr

An AI-powered thrift-shopping agent that searches secondhand listings, suggests outfits using your wardrobe, and generates a shareable fit card from a single natural-language query.

Built with Python, Groq (llama-3.3-70b-versatile), and Gradio.

---

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com).

Run the app:

```bash
python app.py
```

Open the URL printed in your terminal (usually `http://localhost:7860`).

Run tests:

```bash
pytest tests/
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Finds secondhand listings that match what the user is looking for.

| Parameter | Type | Meaning |
|---|---|---|
| `description` | `str` | Keywords describing the item (e.g. `"vintage graphic tee"`) |
| `size` | `str \| None` | Size to filter by; `None` skips size filtering. Case-insensitive substring match against the listing's size field. |
| `max_price` | `float \| None` | Maximum price in USD (inclusive); `None` skips price filtering. |

**Returns:** A list of up to 5 listing dicts, sorted by relevance score (highest first). Each dict contains `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, and `platform`. Returns `[]` if nothing matches — never raises an exception.

**How scoring works:** Each keyword from `description` is checked against the combined text of the listing's title, description, and style_tags. The score is the count of matching keywords. Listings with a score of zero are dropped before sorting.

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Calls the Groq LLM to suggest 1–2 complete outfit combinations using the thrifted item and the user's existing wardrobe pieces.

| Parameter | Type | Meaning |
|---|---|---|
| `new_item` | `dict` | A listing dict as returned by `search_listings` |
| `wardrobe` | `dict` | A dict with an `"items"` key containing a list of wardrobe item dicts (each has `name`, `category`, `colors`, `style_tags`, and optional `notes`) |

**Returns:** A non-empty string describing outfit suggestions. When the wardrobe has items, outfits reference specific wardrobe pieces by name. When the wardrobe is empty, the response describes generic outfit archetypes instead. Never returns an empty string.

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Calls the Groq LLM at temperature 0.9 to generate a casual, shareable 2–4 sentence Instagram/TikTok-style caption for the outfit.

| Parameter | Type | Meaning |
|---|---|---|
| `outfit` | `str` | The outfit suggestion string returned by `suggest_outfit` |
| `new_item` | `dict` | The listing dict for the thrifted item |

**Returns:** A 2–4 sentence caption that mentions the item name, price, and platform once each in a natural, first-person voice. Because temperature is set to 0.9, outputs differ across calls for the same input.

---

## Planning Loop

The planning loop in `run_agent()` is a **linear pipeline with a conditional early exit** — it does not call all three tools unconditionally.

### Step-by-step logic

**Step 1 — Initialize session.** A fresh `session` dict is created with all fields set to their zero values (`None`, `[]`). This dict is the single source of truth for the entire interaction.

**Step 2 — Parse the query.** The agent uses Python `re` to extract three values from the natural-language query:
- `description` — the item keywords, with size/price clauses stripped out
- `size` — matched by pattern `(xxs|xs|s/m|m/l|s|m|l|xl|xxl|w\d{2}...)`; `None` if not found
- `max_price` — matched by pattern `under \$?[\d.]+`; `None` if not found

These are stored in `session["parsed"]`.

**Step 3 — Call `search_listings` and branch.** The agent calls `search_listings` with the parsed values and stores the result in `session["search_results"]`.

- **If the result is empty:** `session["error"]` is set to a descriptive message and the function returns immediately. `suggest_outfit` and `create_fit_card` are **never called** in this case.
- **If results exist:** `session["selected_item"]` is set to `results[0]` (highest-scoring match) and the loop continues.

**Step 4 — Call `suggest_outfit`.** Passes `session["selected_item"]` and `session["wardrobe"]` to `suggest_outfit`. The returned string is stored in `session["outfit_suggestion"]`.

**Step 5 — Call `create_fit_card`.** Passes `session["outfit_suggestion"]` and `session["selected_item"]` to `create_fit_card`. The returned string is stored in `session["fit_card"]`.

**Step 6 — Return the session.** The full session dict is returned to the caller. `session["error"]` is `None` on a successful run.

### Why this is not a fixed sequence

The agent only reaches `suggest_outfit` if `search_listings` returned at least one result. If no listings match, the agent stops, sets a helpful error message, and returns without wasting LLM calls. The two LLM tools only run when there is a real item to work with.

### Retry logic with fallback

Before giving up on an empty result, the agent automatically retries with loosened constraints:

1. **Retry 1 — drop size filter:** If a size was specified and results are empty, retry without it. If this produces results, `session["retry_note"]` is set to `"No results for size M, so I searched all sizes instead."` The listing panel in the UI shows this note so the user knows what was adjusted.

2. **Retry 2 — drop price filter:** If results are still empty and a price ceiling was specified, retry without it. The retry note is updated to include the price limit that was removed.

3. **Final failure:** If results are still empty after both retries, `session["error"]` is set and the loop exits without calling any LLM tools.

Example: query `"vintage graphic tee size XXS under $5"` → no exact match → retry without size XXS → retry without $5 limit → finds results → `retry_note` shown in UI.

---

## State Management

All state lives in a single `session` dict created at the start of each `run_agent()` call. Values written by one step are read directly by the next — nothing is re-entered by the user between steps.

| Field | Written by | Read by |
|---|---|---|
| `session["query"]` | `_new_session()` | Query parser |
| `session["parsed"]` | Query parser (regex) | `search_listings` call |
| `session["search_results"]` | `search_listings` return | Empty-check branch |
| `session["selected_item"]` | `results[0]` assignment | `suggest_outfit`, `create_fit_card` |
| `session["wardrobe"]` | `_new_session()` | `suggest_outfit` |
| `session["outfit_suggestion"]` | `suggest_outfit` return | `create_fit_card` |
| `session["fit_card"]` | `create_fit_card` return | Gradio UI output panel |
| `session["error"]` | Early-exit branch | Gradio UI error display |

Each call to `run_agent()` starts a completely fresh session — no global state, no shared mutable variables between calls.

---

## Error Handling

### `search_listings` — no results

**Failure mode:** The description/size/price combination matches zero listings.

**Agent response:** Sets `session["error"]` to:
> "No listings found matching 'designer ballgown' in size xxs under $5.00. Try broadening your search — for example, remove the size filter or raise your price limit."

Returns the session immediately. `suggest_outfit` and `create_fit_card` are not called. The Gradio UI displays the error message in the top panel.

**Tested with:** `search_listings("designer ballgown", size="XXS", max_price=5)` → `[]`

---

### `suggest_outfit` — empty wardrobe

**Failure mode:** `wardrobe["items"]` is an empty list (new user with no wardrobe data).

**Agent response:** Detects the empty list before calling the LLM and switches to a different prompt asking for general styling archetypes instead of named wardrobe pairings. Returns a non-empty string like:
> "Without knowing your wardrobe, here are two ways to style this piece: ..."

The loop continues normally to `create_fit_card`.

**Tested with:** `suggest_outfit(sample_item, {"items": []})` — confirmed non-empty response, no crash.

---

### `suggest_outfit` — LLM exception

**Failure mode:** The Groq API call raises any exception (timeout, auth error, rate limit).

**Agent response:** Catches the exception and returns a hardcoded fallback string:
> "Could not generate outfit suggestions right now. The item is a tops in grunge, vintage, flannel, streetwear style — try pairing it with bottoms in neutral tones."

The loop continues to `create_fit_card` with this fallback string.

---

### `create_fit_card` — empty outfit string

**Failure mode:** `outfit` argument is empty or whitespace-only.

**Agent response:** Detects the empty input before calling the LLM and returns immediately:
> "Outfit details are missing — cannot generate a fit card. Check that suggest_outfit ran successfully."

Never raises an exception. Stored in `session["fit_card"]` and displayed in the UI.

**Tested with:** `create_fit_card("", sample_item)` and `create_fit_card("   ", sample_item)` — both return the error string, no crash.

---

### `create_fit_card` — LLM exception

**Failure mode:** The Groq API call fails.

**Agent response:** Catches the exception and returns:
> "Could not generate a fit card right now. Here's the look: [first 200 characters of outfit]."

---

## AI Tool Usage

### Instance 1 — Implementing `search_listings`

**What I gave Claude:** The Tool 1 block from `planning.md` (input parameters, return value schema, scoring logic, failure mode) and the `load_listings()` signature from `utils/data_loader.py`. I asked it to implement the function following these exact steps: load listings, filter by max_price, filter by size using case-insensitive substring match, score by keyword overlap against title + description + style_tags, drop zero-score listings, sort descending, return top 5.

**What it produced:** A working implementation using `re.findall(r'\w+', description.lower())` for tokenization and a list comprehension to build `(score, listing)` tuples.

**What I changed:** The generated code used `any(kw in searchable for kw in keywords)` as the score (boolean), which wouldn't sort by relevance. I changed it to `sum(1 for kw in keywords if kw in searchable)` to count matches and get a real ranking. I also added the `[:5]` cap after sorting, which the generated code omitted.

---

### Instance 2 — Implementing `run_agent()` (planning loop)

**What I gave Claude:** The full ASCII architecture diagram from `planning.md` plus the Planning Loop section (all 6 numbered steps with exact branch conditions) and the State Management table. I also included the existing `_new_session()` function so it could see the exact field names.

**What it produced:** A mostly correct implementation with the regex parser, the `if not session["search_results"]` early return, and the sequential tool calls storing results into the session dict.

**What I changed:** The generated regex for size used `\b(S|M|L|XL)\b` which missed `S/M`, `M/L`, `W30 L30`, and `XXS`. I expanded the pattern to `(xxs|xs|s/m|m/l|l/xl|s|m|l|xl|xxl|w\d{2}(?:\s*l\d{2})?)` to match the actual size strings in `listings.json`. I also added the `re.IGNORECASE` flag to the description-stripping substitutions, which the generated code forgot.

---

## Spec Reflection

**What matched the spec exactly:** The three-tool pipeline, the conditional early exit on empty search results, and the session dict structure all implemented as designed in `planning.md`. The error messages in production match the exact templates written in the spec.

**What I adjusted during implementation:** The query parser originally used simple string splitting to extract the description. Once I tested with queries like `"90s track jacket in size M under $45"`, I realized the word "in" before "size" needed to be stripped too, so I added a broader regex substitution. The spec said "strip trailing clauses" but the real queries had the clauses in the middle.

**What I learned:** Scoring by keyword count rather than keyword presence made a meaningful difference "vintage graphic tee" reliably surfaces the Y2K Baby Tee and the 2003 Tour Bootleg Tee ahead of unrelated vintage items that happen to share one keyword. Without count-based scoring, a "vintage flannel" search would rank a listing with all five matching keywords the same as one with just "vintage."
