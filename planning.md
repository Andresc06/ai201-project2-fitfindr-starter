# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Loads all listings from `data/listings.json` using `load_listings()`, filters them by size and the maximum price if provided, scores each remaining listing by keyword overlap between the user's description and the listing's title, description, and style_tags, and returns up to 5 best-matching listings sorted by descending score.

**Input parameters:**
- `description` (string): keywords describing what the user wants. Used to compute a keyword relevance score against each listing's title, description, and style_tags.
- `size` (string or None): Size to filter by, or None to skip size filtering. Matching is case-insensitive.
- `max_price` (float or None): Maximum price or None to skip price filtering. Compared against the listing's `price` field.

**What it returns:**
A list of listing dicts (possibly empty). Each dict has these fields:
- `id` (string): unique listing ID, e.g. `"lst_001"`
- `title` (string): short listing name, e.g. `"Y2K Baby Tee"`
- `description` (string): longer text description of the item
- `category` (string): one of `tops`, `bottoms`, `outerwear`, `shoes`, `accessories`
- `style_tags` (list[string]): descriptors like `["vintage", "graphic tee", "y2k"]`
- `size` (string): size string as listed, e.g. `"S/M"`
- `condition` (string): one of `excellent`, `good`, or `fair`
- `price` (float): asking price in USD
- `colors` (list[string]): color names
- `brand` (string or None): brand name or null
- `platform` (string): one of `depop`, `thredUp`, or `poshmark`

The list is sorted by relevance score (highest first).

**What happens if it fails or returns nothing:**
If the returned list is empty, `run_agent` sets `session["error"]` to `"No listings found matching '[description]' in size [size] under $[max_price]. Try a broader search."` and returns the session immediately. The agent does not call `suggest_outfit` or `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
Calls the Groq LLM (llama3-8b-8192) with the new listing item and the user's current wardrobe items to generate 1–2 specific outfit combinations. If the wardrobe is empty it generates general styling ideas for the item instead.

**Input parameters:**
- `new_item` (dict): A full listing dict as returned by `search_listings`. The relevant fields used in the prompt are `title`, `category`, `style_tags`, `colors`, `condition`, and `price`.
- `wardrobe` (dict): A wardrobe dict with a single key `"items"` containing a list of wardrobe item dicts. Each wardrobe item has: `id`, `name`, `category`, `colors`,`style_tags`, and optional `notes`.

**What it returns:**
A string describing one or two complete outfits. Each outfit names specific pieces from the wardrobe by their `name` field and explains why they work together. Example: `"Pair the flannel with your baggy straight-leg dark-wash jeans and white ribbed tank underneath for a grunge-lite look and finish with chunky sneakers."` If the wardrobe is empty, the string instead describes 1–2 generic outfit archetypes that would pair well with the item.

**What happens if it fails or returns nothing:**
The function catches it and returns the fallback string: `"Could not generate outfit suggestions right now. The item is a [category] in [style_tags] style — try pairing it with [complementary category] in neutral tones."`

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM (llama3-8b-8192) at a higher temperature (0.9) to generate a 2–4 sentence Instagram/TikTok-style caption for the outfit. The caption mentions the item name, price, and platform naturally, captures the outfit vibe in specific aesthetic terms, and feels like a real OOTD post rather than a product listing.

**Input parameters:**
- `outfit` (string): The outfit suggestion string returned by `suggest_outfit`.
- `new_item` (dict): The listing dict for the thrifted item. Fields used: `title`, `price`, `platform`, `style_tags`, and `colors`.

**What it returns:**
A 2–4 sentence string styled as a social media caption. Example: `"thrifted this flannel off thredUp for $22 and it has not left my body styled it over my white tank with baggy jeans. found this gem during my Sunday scroll and I'm obsessed. $22 well spent, honestly."` Each call produces different phrasing because the LLM temperature is set to 0.9.

**What happens if it fails or returns nothing:**
If `outfit` is an empty or whitespace-only string, the function immediately returns: `"Outfit details are missing — cannot generate a fit card. Check that suggest_outfit ran successfully."` If the LLM call raises an exception, the function catches it and returns: `"Could not generate a fit card right now. Here's the look: [first 200 characters of outfit]."` The agent stores whichever string is returned in `session["fit_card"]`.

---

### Additional Tools (if any)

None for now as the required scope is limited.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop in `run_agent()` executes linearly with conditional early exits. Here is the exact branching logic:

1. **Initialize session** — call `_new_session(query, wardrobe)` to create the session dict with all fields set to their initial values (`None`, `[]`, etc.).

2. **Parse the query** — use a regex pass to extract:
   - `description`: everything before any "size" or "under $" clause
   - `size`: match pattern `\b(XS|S|M|L|XL|XXL|[Ww]\d{2}|S\/M|one size)\b` (case-insensitive); set to `None` if not found
   - `max_price`: match pattern `under \$?([\d.]+)` or `\$?([\d.]+) or (less|under)`; set to `None` if not found
   Store `{"description": ..., "size": ..., "max_price": ...}` in `session["parsed"]`.

3. **Call search_listings** — pass `session["parsed"]["description"]`, `session["parsed"]["size"]`, `session["parsed"]["max_price"]`. Store the returned list in `session["search_results"]`.
   - **Branch A (empty results):** if `len(session["search_results"]) == 0`, set `session["error"]` to the no-results message (see Tool 1 error handling), and `return session` immediately. `suggest_outfit` and `create_fit_card` are NOT called.
   - **Branch B (results found):** set `session["selected_item"] = session["search_results"][0]` (the highest-scored item) and continue.

4. **Call suggest_outfit** — pass `session["selected_item"]` and `session["wardrobe"]`. Store the returned string in `session["outfit_suggestion"]`. This step always produces a non-empty string.

5. **Call create_fit_card** — pass `session["outfit_suggestion"]` and `session["selected_item"]`. Store the returned string in `session["fit_card"]`. This step always produces a non-empty string.

6. **Return session** — return the completed session dict. `session["error"]` is `None` on the happy path.

The agent does NOT loop back and retry automatically. It does not call all three tools unconditionally. It only reaches `suggest_outfit` if `search_results` is non-empty, and only calls `create_fit_card` after `suggest_outfit` has returned.

---

## State Management

**How does information from one tool get passed to the next?**

All state is stored in a single `session` dict created at the start of `run_agent()`. The dict is mutated in-place at each step:

| Field | Set by | Read by |
|---|---|---|
| `session["query"]` | `_new_session()` at start | Query parser (step 2) |
| `session["parsed"]` | Query parser (step 2) | `search_listings` call (step 3) |
| `session["search_results"]` | `search_listings` return (step 3) | Branch check + `selected_item` assignment (step 3) |
| `session["selected_item"]` | Step 3 (`results[0]`) | `suggest_outfit` (step 4), `create_fit_card` (step 5) |
| `session["wardrobe"]` | `_new_session()` at start | `suggest_outfit` (step 4) |
| `session["outfit_suggestion"]` | `suggest_outfit` return (step 4) | `create_fit_card` (step 5) |
| `session["fit_card"]` | `create_fit_card` return (step 5) | Returned to caller / displayed in UI |
| `session["error"]` | Set on early exit (step 3 Branch A) | Caller checks this first to detect failure |

The session dict is the return value of `run_agent()`. The Gradio UI in `app.py` reads `session["fit_card"]` for success display and `session["error"]` for error display. No global variables are used — each call to `run_agent()` starts a fresh session.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No listings match the description/size/price combination | Agent sets `session["error"]` to `"No listings found matching '[description]' in size [size] under $[max_price]. Try broadening your search — for example, remove the size filter or raise your price limit."` and returns the session immediately without calling the remaining tools. The UI displays this message in the error output box. |
| suggest_outfit | Wardrobe `items` list is empty | Tool detects `len(wardrobe["items"]) == 0` and prompts the LLM for general styling archetypes rather than named wardrobe pairings. Returns a non-empty string like `"Without knowing your wardrobe, here are two ways to style this piece: ..."`. The agent continues normally to `create_fit_card`. |
| suggest_outfit | LLM API call raises an exception | Tool catches the exception and returns a hardcoded fallback: `"Could not generate outfit suggestions right now. The item is a [category] in [style] — try pairing it with [complementary category] in neutral tones."` The agent still proceeds to `create_fit_card` with this string. |
| create_fit_card | `outfit` argument is empty or whitespace | Tool returns `"Outfit details are missing — cannot generate a fit card. Check that suggest_outfit ran successfully."` without calling the LLM. No exception is raised. |
| create_fit_card | LLM API call raises an exception | Tool catches the exception and returns `"Could not generate a fit card right now. Here's the look: [first 200 chars of outfit]."` The session stores this string in `fit_card` and the UI displays it. |

---

## Architecture

```
User query (str) + wardrobe (dict)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                        run_agent()                              │
│                      Planning Loop                              │
│                                                                 │
│  Step 1: _new_session(query, wardrobe)                          │
│          → session dict initialized                             │
│                │                                                │
│  Step 2: parse query with regex                                 │
│          → session["parsed"] = {description, size, max_price}  │
│                │                                                │
│                ▼                                                │
│  Step 3: search_listings(description, size, max_price)          │
│                │                                                │
│         results == []?                                          │
│           │         │                                           │
│          YES        NO                                          │
│           │         │                                           │
│           ▼         ▼                                           │
│  session["error"]  session["selected_item"] = results[0]        │
│  = "No listings    session["search_results"] = results          │
│    found..."            │                                       │
│           │             ▼                                       │
│      return ◄    Step 4: suggest_outfit(selected_item,          │
│      session             wardrobe)                              │
│   [ERROR PATH]          │                                       │
│                  wardrobe empty?  LLM error?                    │
│                    │        │        │                          │
│                   YES      NO      YES                          │
│                    │        │        │                          │
│                    ▼        ▼        ▼                          │
│              general    specific  fallback                      │
│              styling    pairings  string                        │
│              advice          └────────┘                        │
│                                   │                             │
│              session["outfit_suggestion"] = result              │
│                                   │                             │
│                                   ▼                             │
│              Step 5: create_fit_card(outfit_suggestion,         │
│                                      selected_item)             │
│                                   │                             │
│                           outfit empty?  LLM error?            │
│                              │               │                  │
│                             YES             YES                 │
│                              │               │                  │
│                              ▼               ▼                  │
│                        error string    fallback string          │
│                                └─────────┘                     │
│                                     │                           │
│              session["fit_card"] = result                       │
│              session["error"] = None                            │
│                                     │                           │
│                                return session                   │
└─────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────┐
                    │        app.py (Gradio UI)  │
                    │  if session["error"]:       │
                    │    display error message   │
                    │  else:                     │
                    │    display fit_card        │
                    │    display outfit          │
                    │    display selected_item   │
                    └────────────────────────────┘
```

**Session state fields tracked throughout the loop:**

```
session = {
  "query":              string   — original user input
  "parsed":             dict  — {description, size, max_price} extracted by regex
  "search_results":     list  — all matching listing dicts from search_listings
  "selected_item":      dict  — results[0], the top-ranked listing
  "wardrobe":           dict  — {"items": [...]} passed in by the caller
  "outfit_suggestion":  string   — returned by suggest_outfit
  "fit_card":           string   — returned by create_fit_card
  "error":              string|None — set on early exit, None on success
}
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

**Tool 1 — search_listings:**
I will give Claude the Tool 1 block from this planning.md (input parameters, return value description, failure mode) along with the `load_listings()` function signature from `utils/data_loader.py`. I will ask it to implement the function in `tools.py` using these exact steps: load all listings, filter by `max_price` (skip if None), filter by `size` using case-insensitive substring match (skip if None), score each remaining listing by counting how many words from `description` appear in the combined text of `title + description + style_tags`, drop listings with score 0, sort descending by score, and return the top 5 dicts. I will verify the output by running three test queries against `listings.json`: (1) "vintage graphic tee" with size=None, max_price=None (should return at least one match from the tops category); (2) "flannel" with size=None, max_price=20.0 (should return 0 results since the flannel is $22); (3) "jeans" with size="W30", max_price=50.0 (should return the Levi's 501s).

**Tool 2 — suggest_outfit:**
I will give Claude the Tool 2 block from this planning.md (both the wardrobe-empty and wardrobe-populated branches), the wardrobe schema from `data/wardrobe_schema.json`, and the `_get_groq_client()` helper already in `tools.py`. I will ask it to implement `suggest_outfit` calling `client.chat.completions.create(model="llama3-8b-8192", messages=[...])` with a system prompt that sets the persona as a personal stylist, and a user message that lists the new item's title, colors, and style_tags then lists the wardrobe items by name, category, and colors. I will verify by calling it with the example wardrobe and the flannel listing; the response should name at least one specific wardrobe item by name.

**Tool 3 — create_fit_card:**
I will give Claude the Tool 3 block from this planning.md (caption style rules, temperature requirement, both failure modes) and a sample `suggest_outfit` output string. I will ask it to implement `create_fit_card` calling the Groq LLM with `temperature=0.9`, passing the outfit string and the item's `title`, `price`, and `platform`. The prompt should instruct the LLM to write 2–4 sentences in first-person casual style, mentioning the item name, price, and platform once each. I will verify by calling it twice with the same inputs and confirming the two outputs differ (proving the temperature variation works).

**Milestone 4 — Planning loop and state management:**

I will give Claude the full Architecture diagram from this planning.md and the Planning Loop section (both together), plus the existing `_new_session()` function skeleton in `agent.py`. I will ask it to implement `run_agent()` by: (1) calling `_new_session`, (2) using Python `re` to extract description/size/max_price from `query` using the exact patterns described in the Planning Loop section, (3) calling `search_listings` and checking if the result is empty — if yes, set `session["error"]` to the exact message template and return, (4) setting `session["selected_item"] = session["search_results"][0]`, (5) calling `suggest_outfit` and storing the result, (6) calling `create_fit_card` and storing the result, (7) returning the session. I will verify by running the two existing test cases at the bottom of `agent.py` — the happy path should print a fit card, and the no-results path should print a descriptive error message.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

FitFindr needs to search the mock listings dataset for items matching the user's description, size, and price, then combine any found item with the user's wardrobe to suggest one or more complete outfit combinations, and generate a caption for the selected outfit. The tools are triggered in sequence: `search_listings` runs on the user's find request, `suggest_outfit` runs when a listing is selected together with the user's wardrobe, and `create_fit_card` runs on the finalized outfit; if a tool fails or returns no results the agent reports this.

**Step 1:**
The agent calls `search_listings(description="vintage graphic tee", size=None, max_price=30.0)`. The regex parser extracts `description="vintage graphic tee"` from the opening clause, finds no size keyword, and extracts `max_price=30.0` from "under $30". The tool loads all 20 listings, drops the 7 that cost more than $30, then scores the remainder by keyword overlap — "vintage", "graphic", "tee" match against `title`, `description`, and `style_tags`. The Y2K Baby Tee ($18, style_tags include "vintage" and "graphic tee") scores 3 matches and ranks first. `search_listings` returns `[{"id": "lst_002", "title": "Y2K Baby Tee — Butterfly Print", "price": 18.0, "platform": "depop", ...}, ...]`. `session["search_results"]` is set to this list; since it is non-empty, `session["selected_item"]` is set to `results[0]` (the Y2K Baby Tee dict).

**Step 2:**
The agent calls `suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])`. The wardrobe has 10 items (including "Baggy straight-leg jeans, dark wash", "Chunky platform sneakers", "White ribbed tank top"). The tool builds a prompt: _"You are a personal stylist. The user just found: Y2K Baby Tee — Butterfly Print (tops, vintage/y2k/graphic tee style, white/pink/purple, $18 on depop). Their wardrobe includes: baggy straight-leg jeans (bottoms, denim/streetwear), wide-leg khaki trousers (bottoms, earth tones), white ribbed tank top (tops, basics), chunky platform sneakers (shoes, y2k/chunky), [etc.]. Suggest 1–2 complete outfits using the new item and named wardrobe pieces."_ The LLM responds: `"Outfit 1: Tuck the Y2K Baby Tee into your baggy straight-leg dark-wash jeans — the crop length works perfectly with the high waist. Finish with your chunky platform sneakers for a full Y2K revival look. Outfit 2: Layer it under your black cropped zip hoodie with the wide-leg khaki trousers for a more relaxed, streetwear take."` `session["outfit_suggestion"]` is set to this string.

**Step 3:**
The agent calls `create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])`. The tool builds a prompt with temperature=0.9: _"Write a 2–4 sentence Instagram caption for this outfit. Item: Y2K Baby Tee — Butterfly Print, $18, found on depop. Outfit: [outfit string]. Make it casual and authentic, mention the item name, price, and platform once each."_ The LLM responds: `"found this Y2K butterfly baby tee on depop for $18 and I am not okay... tucked into my baggy dark wash jeans with chunky platforms. It's giving full early-2000s main character energy. the crop + high-waist combo is doing everything. $18 and I feel like I raided a 2003 archive."` `session["fit_card"]` is set to this string. `session["error"]` remains `None`.

**Final output to user:**
The Gradio UI displays three sections:
1. **Found item:** "Y2K Baby Tee — Butterfly Print — $18.00 on depop (excellent condition, size S/M)"
2. **Outfit suggestion:** The two-outfit paragraph from suggest_outfit naming the baggy jeans, platforms, and hoodie.
3. **Fit card:** "found this Y2K butterfly baby tee on depop for $18 and I am not okay... tucked into my baggy dark wash jeans with chunky platforms. It's giving full early-2000s main character energy. the crop + high-waist combo is doing everything. $18 and I feel like I raided a 2003 archive."
