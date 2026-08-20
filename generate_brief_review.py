#!/usr/bin/env python3
"""
generate_brief_review.py - federal_policy_brief, review-only v3

Reads recent Federal Register items from the scraped_content table, groups
them by program area, uses local Gemma (via Ollama) to synthesize a plain-text
executive brief, appends a deterministic Source Attribution Addendum, then
prints the result and saves it to a file for operator review.

REVIEW-ONLY. This script:
  - does NOT send any email
  - does NOT mark rows processed (the is_new flag is left untouched)
  - does NOT write a brief_runs row
It is therefore safe to run as many times as you like.

No shell or bash is invoked. It reaches PostgreSQL (localhost:5432) and
Ollama (localhost:11434) over the network only.

CHANGES FROM v0
  1. Instrument-type fidelity. Each document now carries an explicit
     instrument label (proposed rule / Privacy Act matching program notice /
     information collection request / ...) derived from the stored
     scraped_content.content_type -- which is the Federal Register API's own
     "type" field -- refined for notices by title keyword. The label is shown
     to the model, and the executive summary is now built from a deterministic
     inventory of those labels in addition to the section prose, so a specific
     CMS-VA matching notice can no longer be softened into a vague
     "eligibility verification update."
  2. Program-area mapping now matches on SUB-AGENCY only, never on the parent
     department. v0 matched the substring "Agriculture", which swept every
     USDA sub-agency (Forest Service, APHIS, Farm Service Agency) into SNAP.
     Only Food and Nutrition Service/Administration routes to SNAP now; the
     rest of USDA falls through to Cross-Program.
  3. CMS section renamed "CMS (Medicaid/CHIP/Medicare)". All CMS content still
     lands in one bucket, but the heading no longer implies that Medicare
     authorities (the CY2027 HH PPS rule, DMEPOS) are Medicaid rules.

CHANGES FROM v1 (regression repair after the 2026-08-16 review run)
  4. Plain-text output is now enforced twice. The system prompt forbids
     markdown, and to_plain_text() deterministically strips headings, bullets,
     bold markers, tables, horizontal rules and emoji from every model
     response. v1's larger prompts pushed Gemma into document-formatting mode
     and it emitted "###" headings, "**bold**", emoji and a pipe table. This
     is an email product; prompting alone is not a strong enough guarantee.
  5. The executive summary now receives a COMPRESSED inventory -- per-area
     counts by instrument plus only the non-routine items -- rather than one
     line per document. v1 handed it 108 lines and asked for 4-6 sentences;
     it treated the inventory as a work order and rewrote the whole brief as
     a 50-line structured document. Smaller input, harder length instruction.

CHANGES FROM v2 (2026-08-20, Entry #019)
  6. num_ctx is now set explicitly. Ollama defaulted to 4096 tokens for both
     prompt AND response. A 19-document Cross-Program prompt overran it: the
     earliest documents fell out of the window unseen and the response was
     truncated mid-sentence. This -- not model capability -- is the likely
     cause of the Entry #018 "oversized section" symptoms (outlines instead of
     prose, self-contradiction, covering a third of the inputs).
  7. Foreign-recipient funding notices are suppressed. The audience is state
     HHS leadership; a CDC cooperative agreement funding a foreign health
     ministry has no bearing on their work. Suppression requires BOTH a
     funding-instrument marker AND a foreign-recipient marker, so a domestic
     rule that merely cites another country is not swept up. Every suppressed
     document is printed above the brief for audit -- this filter is never
     silent.
  8. Fabricated figures are now detected. On the 2026-08-20 review run Gemma
     reported three CDC awards ($15M + $30M + $30M = $75M) as "totaling
     approximately $105 million" -- a total that appears in no source and is
     wrong by 40%. The system prompt now forbids arithmetic outright, and
     verify_figures() checks every currency amount in the generated prose
     against that section's source text. Same enforce-twice pattern as
     to_plain_text(): prompting alone has now failed twice.
     NOTE: while this script is review-only, an unverified figure is FLAGGED.
     Before send-to-inbox wiring, an unverified figure must HARD-FAIL the run.

UPSTREAM DEFECT RESOLVED (2026-08-20)
  The scraper TYPE_MAP defect that stored every proposed rule as 'other' is
  fixed in app/scheduling/scrapers/federal_register.py, and the 15 banked rows
  were relabeled. The "document" entry in HIGH_SIGNAL that worked around it
  has been removed.
"""

import os
import re
import sys
import datetime as dt

import psycopg2
import httpx

# ----------------------------- CONFIG -----------------------------
WINDOW_DAYS = 7                       # production value
PROJECT = "federal_policy_brief"      # scoping tag in scraped_content.project
MODEL = "gemma4:e4b"                  # local Ollama model to summarize with
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TIMEOUT = 300                  # seconds; local inference can be slow
TEMPERATURE = 0.2                     # low = factual, consistent
NUM_CTX = 8192                        # prompt+response budget; Ollama default 4096 truncated Cross-Program

DB = dict(
    host="localhost",
    port=5432,
    dbname="openclaw",
    user="openclaw",
    password=os.environ.get("POSTGRES_PASSWORD", "changeme"),
)

# --------------------- PROGRAM AREA MAPPING ---------------------
# publishing_agency is stored as "Parent Department, Sub-agency[, Sub-agency]".
# We route on the SUB-AGENCY positions ONLY. Matching the parent department was
# the v0 bug: "Agriculture" matched every USDA document before the sub-agency
# was ever consulted, so Forest Service notices were briefed as SNAP.
SUB_AGENCY_RULES = [
    ("CMS", [
        "centers for medicare & medicaid services",
        "centers for medicare and medicaid services",
    ]),
    ("SNAP", [
        # live data uses "Administration"; the API has also used "Service"
        "food and nutrition service",
        "food and nutrition administration",
    ]),
    ("TANF", [
        "administration for children and families",
        "children and families administration",
        "children and families",
    ]),
]
DEFAULT_AREA = "Cross-Program"   # rest of USDA, FDA, CDC, NIH, IRS, SSA, ...

# Fixed section ordering in the finished brief.
AREA_ORDER = ["CMS", "SNAP", "TANF", "Cross-Program"]

# Printed section headings.
AREA_HEADING = {
    "CMS": "CMS (Medicaid/CHIP/Medicare)",
    "SNAP": "SNAP",
    "TANF": "TANF",
    "Cross-Program": "Cross-Program",
}

# How each section is described to the model when asking for relevance.
AREA_AUDIENCE = {
    "CMS": ("state Medicaid and CHIP agencies. Note that this group mixes "
            "Medicaid/CHIP authorities with Medicare authorities -- always "
            "make clear which program a given document governs"),
    "SNAP": "state SNAP agencies",
    "TANF": "state TANF agencies",
    "Cross-Program": ("state health and human services agencies generally, "
                      "across program lines"),
}

# --------------------- SCOPE FILTER ---------------------
# Audience is state health and human services leadership. Federal money going
# to a foreign government or foreign institution does not reach them, so those
# notices are suppressed before synthesis.
#
# Suppression requires BOTH markers below. Requiring both is deliberate: a
# domestic Medicaid rule that happens to cite another country keeps only the
# foreign marker and is therefore kept. Every suppressed document is listed in
# the review output -- a false positive must be visible, never silent.
FUNDING_MARKERS = (
    "notice of award",
    "cooperative agreement",
    "to fund",
    "grant to",
)

# A US federal agency is never a "ministry"; that word alone is a reliable
# foreign-government marker.
FOREIGN_MARKERS = (
    "ministry of health",
    "ministry of",
)

# Word-boundary matched so "niger" does not fire on "nigeria" and "india"
# does not fire on "indiana".
FOREIGN_COUNTRIES = [
    "angola", "armenia", "azerbaijan", "bangladesh", "belarus", "benin",
    "botswana", "brazil", "burkina faso", "burundi", "cambodia", "cameroon",
    "central african republic", "chad", "congo", "cote d'ivoire",
    "cote divoire", "dominican republic", "el salvador", "eswatini",
    "ethiopia", "gabon", "ghana", "guatemala", "guinea", "haiti", "honduras",
    "india", "indonesia", "ivory coast", "kazakhstan", "kenya", "kyrgyzstan",
    "laos", "lesotho", "liberia", "madagascar", "malawi", "malaysia", "mali",
    "moldova", "mozambique", "myanmar", "namibia", "nepal", "niger",
    "nigeria", "pakistan", "papua new guinea", "peru", "philippines",
    "rwanda", "senegal", "sierra leone", "south africa", "south sudan",
    "tajikistan", "tanzania", "thailand", "togo", "uganda", "ukraine",
    "uzbekistan", "vietnam", "zambia", "zanzibar", "zimbabwe",
]
_COUNTRY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in FOREIGN_COUNTRIES) + r")\b"
)


def out_of_scope(d):
    """Return a reason string if this document should be suppressed, else None.

    Both conditions must hold: it must look like a funding instrument AND name
    a foreign recipient.
    """
    text = f"{d.get('document_title') or ''}\n{d.get('raw_content') or ''}".lower()

    if not any(m in text for m in FUNDING_MARKERS):
        return None

    if any(m in text for m in FOREIGN_MARKERS):
        return "foreign recipient (government ministry)"

    hit = _COUNTRY_RE.search(text)
    if hit:
        return f"foreign recipient ({hit.group(1)})"

    return None


# --------------------- INSTRUMENT TYPING ---------------------
# Coarse type comes from scraped_content.content_type, which the scraper copies
# from the Federal Register API's own "type" field. This is authoritative --
# do not second-guess it from the title.
CONTENT_TYPE_LABEL = {
    "proposed_rule": "proposed rule",
    "final_rule": "final rule",
    "notice": "notice",
    "presidential_document": "presidential document",
}

# "notice" is too coarse to be useful in a brief, so refine it by title
# keyword. First match wins -- order matters. Only applied when the stored
# content_type is "notice" (or missing); rules are never re-labeled.
NOTICE_SUBTYPE_RULES = [
    ("Privacy Act matching program notice", ["matching program"]),
    ("Privacy Act system of records notice", ["system of records"]),
    ("charter renewal notice", ["charter renewal"]),
    ("advisory committee meeting notice", [
        "notice of meeting", "notice of closed meeting", "advisory committee",
    ]),
    ("information collection request", [
        "information collection", "proposed collection", "comment request",
        "data collection", "paperwork reduction", "60-day notice",
        "30-day notice", "submission for omb", "submission to omb",
    ]),
    ("drug or device determination", [
        "determination that", "withdrawal of approval",
        "determination of regulatory review period", "classification of the",
    ]),
    ("request for information", ["request for information"]),
    ("funding or cost-share notice", ["cost share", "cost-share"]),
]


def instrument_type(content_type, title):
    """Return a short, specific instrument label for one document."""
    base = CONTENT_TYPE_LABEL.get((content_type or "").strip().lower())
    if base in (None, "notice"):
        t = (title or "").lower()
        for label, needles in NOTICE_SUBTYPE_RULES:
            if any(n in t for n in needles):
                return label
    return base or "document"


SYSTEM_PROMPT = (
    "You are a federal policy analyst preparing an executive briefing for "
    "state health and human services agency leadership. Write in plain, "
    "executive-level language suitable for a commissioner reading on a phone. "
    "Summarize only what the source documents state. Do not editorialize, "
    "advocate, predict outcomes, or recommend action. Do not invent policy "
    "developments that are not present in the sources. Be concise.\n\n"
    "NEVER PERFORM ARITHMETIC. Do not add, total, sum, average, combine or "
    "otherwise compute figures -- not across documents, and not within one "
    "document. Do not write a total that the source does not state verbatim. "
    "If three documents each name a dollar amount, report the amounts "
    "separately or not at all; do NOT report their sum. Report every number, "
    "dollar amount, date and count exactly as a single source document states "
    "it. An invented total is a factual error even when it looks plausible.\n\n"
    "INSTRUMENT FIDELITY IS MANDATORY. Every document is given to you with an "
    "explicit instrument label in parentheses. You must characterize each "
    "document by that instrument, naming the acting agency, and never soften "
    "it into a loose topic. A 'Privacy Act matching program notice' between "
    "CMS and the VA is a matching program notice between two named agencies "
    "-- it is NOT an 'eligibility verification update.' An 'information "
    "collection request' is a request for comment on a paperwork burden -- it "
    "is NOT a policy change. A 'proposed rule' is a proposal open for comment "
    "-- it is NOT a decision that has taken effect. Preserve named programs, "
    "named agencies, named systems of records, and effective or comment dates "
    "exactly as the source states them.\n\n"
    "OUTPUT FORMAT: plain text only. This brief is delivered as plain-text "
    "email. Write flowing paragraphs separated by blank lines. Do NOT use "
    "markdown of any kind -- no # headings, no ** bold, no bullet or numbered "
    "lists, no tables, no horizontal rules, no backticks, no emoji. Do not "
    "add your own section headings; the sections are assembled for you."
)

# --------------------- PLAIN-TEXT ENFORCEMENT ---------------------
# Deterministic backstop. The system prompt asks for plain text; this
# guarantees it. v1 shipped markdown headings, bold markers, emoji and a pipe
# table straight into a product that goes out as plain-text email.
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # pictographs, emoticons, symbols
    "\U00002190-\U000021FF"   # arrows
    "\U00002300-\U000023FF"   # misc technical
    "\U00002600-\U000027BF"   # misc symbols, dingbats
    "\U00002B00-\U00002BFF"   # misc symbols and arrows
    "\U0000FE0F"              # variation selector
    "\U0000200D"              # zero-width joiner
    "]"
)


# --------------------- FIGURE VERIFICATION ---------------------
# Deterministic backstop for fabricated money. The system prompt forbids
# arithmetic; this proves it. On 2026-08-20 Gemma reported $15M + $30M + $30M
# as "approximately $105 million" -- no source states any total, and the sum
# is wrong regardless. Prompting alone has now failed twice (markdown in v1,
# arithmetic in v2), so figures get the same enforce-twice treatment.
_MONEY_RE = re.compile(
    r"\$\s?([\d,]+(?:\.\d+)?)\s*(billion|million|thousand|bn|mm?|k)?\b",
    re.I,
)

_SCALE = {
    "billion": 1_000_000_000, "bn": 1_000_000_000,
    "million": 1_000_000, "mm": 1_000_000, "m": 1_000_000,
    "thousand": 1_000, "k": 1_000,
}


def _money_values(text):
    """Every dollar amount in text, normalized to a numeric value.

    "$15,000,000", "$15 million" and "$15M" all normalize to 15000000.0, so a
    figure restated in different units still matches its source.
    """
    values = set()
    for raw, scale in _MONEY_RE.findall(text or ""):
        try:
            n = float(raw.replace(",", ""))
        except ValueError:
            continue
        values.add(n * _SCALE.get((scale or "").lower(), 1))
    return values


def verify_figures(label, generated, source_text):
    """Flag dollar amounts in generated prose absent from the source.

    Returns a list of warning strings. Review-only for now: these are
    reported, not fatal. Before send-to-inbox wiring, any warning here must
    abort the run instead.
    """
    source = _money_values(source_text)
    warnings = []
    for value in sorted(_money_values(generated) - source):
        warnings.append(
            f"{label}: ${value:,.0f} appears in the generated text but in no "
            f"source document for this section"
        )
    return warnings


def to_plain_text(s):
    """Strip markdown and emoji from a model response."""
    s = _EMOJI_RE.sub("", s or "")

    out = []
    for ln in s.splitlines():
        stripped = ln.strip()

        # Horizontal rules: ***, ---, ___, ===. Checked BEFORE bold markers
        # are stripped, otherwise "***" degrades to "*" and survives.
        if stripped and set(stripped) <= set("*-_="):
            continue

        ln = ln.replace("**", "").replace("__", "").replace("`", "")
        stripped = ln.strip()

        # markdown table rows -- drop separators, flatten data rows
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(set(c) <= set(":- ") for c in cells):
                continue
            ln = " - ".join(c for c in cells if c)
        else:
            ln = re.sub(r"^\s{0,3}#{1,6}\s*", "", ln)        # headings
            ln = re.sub(r"^\s*[\*\+•]\s+", "", ln)      # bullets
            ln = re.sub(r"^\s*-\s+", "", ln)                 # dash bullets
            ln = re.sub(r"^\s*\d+[\.\)]\s+", "", ln)         # numbered lists

        # collapse runs of spaces left behind by removed markers/emoji,
        # without disturbing leading indentation
        ln = re.sub(r"(?<=\S) {2,}", " ", ln)
        out.append(ln.rstrip())

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_rows(conn):
    """Pull the unprocessed documents published within the window."""
    cutoff = dt.date.today() - dt.timedelta(days=WINDOW_DAYS)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, publishing_agency, document_title,
                   publication_date, content_type, raw_content
            FROM scraped_content
            WHERE project = %s
              AND is_new = TRUE
              AND publication_date >= %s
            ORDER BY publication_date DESC, id DESC
            """,
            (PROJECT, cutoff),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def split_agency(agency):
    """Split 'Dept, Sub-agency, Sub-agency' into (department, [sub-agencies])."""
    parts = [p.strip() for p in (agency or "").split(",") if p.strip()]
    if not parts:
        return "", []
    return parts[0], parts[1:]


def area_for(agency):
    """Map a publishing_agency string to a program area on SUB-AGENCY only."""
    _dept, subs = split_agency(agency)
    hay = " | ".join(s.lower() for s in subs)
    for area, needles in SUB_AGENCY_RULES:
        if any(n in hay for n in needles):
            return area
    return DEFAULT_AREA


def ollama_chat(user_prompt):
    """Single non-streaming chat call to the local Ollama server."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": TEMPERATURE, "num_ctx": NUM_CTX},
    }
    r = httpx.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
    r.raise_for_status()
    return to_plain_text(r.json()["message"]["content"])


def abstract_of(d):
    """raw_content is 'title\\n\\nabstract'; return just the abstract part."""
    title = (d["document_title"] or "").strip()
    body = (d["raw_content"] or "").strip()
    if title and body.startswith(title):
        body = body[len(title):].strip()
    return body or "(no abstract provided in the source)"


def docs_block(rows):
    """Format a group of documents with explicit instrument labels."""
    lines = []
    for i, d in enumerate(rows, 1):
        lines.append(
            f"[{i}] ({d['_instrument']}) issued by "
            f"{(d['publishing_agency'] or 'Unknown agency').strip()}, "
            f"published {d['publication_date']}\n"
            f"    Title: {(d['document_title'] or '').strip()}\n"
            f"    Abstract: {abstract_of(d)}"
        )
    return "\n\n".join(lines)


def synthesize_section(area, rows):
    prompt = (
        f"Program area: {AREA_HEADING[area]}.\n"
        f"Audience: {AREA_AUDIENCE[area]}.\n\n"
        f"The following Federal Register documents were published in the last "
        f"{WINDOW_DAYS} days. Write a short briefing section (2-4 short "
        f"paragraphs) that synthesizes what they contain and why they matter "
        f"for this audience. Do not list them mechanically; weave them into "
        f"prose. Each document is labeled with its instrument type in "
        f"parentheses -- name that instrument when you describe it, and name "
        f"the acting agency. Documents:\n\n{docs_block(rows)}"
    )
    return ollama_chat(prompt)


# Instruments a commissioner needs named individually. Everything else
# (information collection requests, meeting notices, charter renewals) is
# routine and is conveyed to the exec summary as a count only.
HIGH_SIGNAL = {
    "final rule",
    "proposed rule",
    "Privacy Act matching program notice",
}
EXEC_NOTABLE_PER_AREA = 6      # cap on individually-named items per section


def inventory_block(rows_by_area):
    """Compressed instrument inventory fed to the executive summary.

    v0's exec summary read only the section prose -- a summary of a summary,
    which is how a CMS-VA matching notice became an "eligibility verification
    update." v1 overcorrected by passing one line per document; with 108
    documents the model treated that as a work order and rebuilt the entire
    brief. This is the middle: counts for the routine volume, individual
    naming only for the instruments that carry weight.
    """
    lines = []
    for area in AREA_ORDER:
        rows = rows_by_area.get(area) or []
        if not rows:
            continue

        counts = {}
        for d in rows:
            counts[d["_instrument"]] = counts.get(d["_instrument"], 0) + 1
        tally = "; ".join(
            f"{n} {name}" + ("s" if n > 1 and not name.endswith("s") else "")
            for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        )
        lines.append(f"{AREA_HEADING[area]} -- {len(rows)} document(s): {tally}")

        notable = [d for d in rows if d["_instrument"] in HIGH_SIGNAL]
        for d in notable[:EXEC_NOTABLE_PER_AREA]:
            title = (d["document_title"] or "Untitled").strip()
            if len(title) > 140:
                title = title[:137] + "..."
            lines.append(f"      ({d['_instrument']}) {title}")
        if len(notable) > EXEC_NOTABLE_PER_AREA:
            lines.append(
                f"      ...and {len(notable) - EXEC_NOTABLE_PER_AREA} further "
                f"rules or matching notices in this section"
            )
    return "\n".join(lines)


def synthesize_exec_summary(date_range, section_texts, rows_by_area):
    combined = "\n\n".join(
        f"{AREA_HEADING[a]}:\n{t}" for a, t in section_texts
    )
    prompt = (
        f"Write the executive summary for a federal policy brief covering "
        f"{date_range}.\n\n"
        f"HARD CONSTRAINTS -- follow these exactly:\n"
        f"  - Between 4 and 6 sentences. Not more.\n"
        f"  - One single paragraph of plain prose.\n"
        f"  - No headings, no lists, no tables, no bold, no emoji.\n"
        f"  - Never name the brief's internal sections to the reader. "
        f"'Cross-Program' is an internal filing bucket, not something the "
        f"reader knows. Describe activity by agency and subject instead.\n"
        f"  - Do NOT restate or reorganize the brief. Do NOT summarize every "
        f"document. Name only the few actions a commissioner must not miss, "
        f"and give the overall shape of the rest in a clause.\n\n"
        f"When you name an action, use its instrument type exactly as the "
        f"inventory below gives it, and name the acting agency. The inventory "
        f"lists per-section volume and the non-routine items; routine "
        f"paperwork is intentionally shown only as counts.\n\n"
        f"INVENTORY:\n{inventory_block(rows_by_area)}\n\n"
        f"DRAFTED SECTIONS (for context, do not restate):\n{combined}"
    )
    return ollama_chat(prompt)


def attribution(rows_by_area):
    """Deterministic source list built straight from metadata."""
    out = ["SOURCE ATTRIBUTION ADDENDUM", "=" * 27, ""]
    for area in AREA_ORDER:
        rows = rows_by_area.get(area)
        if not rows:
            continue
        heading = AREA_HEADING[area]
        out.append(heading)
        out.append("-" * len(heading))
        for d in rows:
            agency = (d["publishing_agency"] or "Unknown agency").strip()
            title = (d["document_title"] or "Untitled").strip()
            out.append(
                f"  - ({d['_instrument']}) {agency} - {title} "
                f"({d['publication_date']})"
            )
        out.append("")
    return "\n".join(out)


def main():
    try:
        conn = psycopg2.connect(**DB)
    except psycopg2.OperationalError as e:
        print("Could not connect to PostgreSQL.", file=sys.stderr)
        print(f"  detail: {e}".rstrip(), file=sys.stderr)
        print("  If this is a password error, set the DB password first, e.g.:",
              file=sys.stderr)
        print("    export POSTGRES_PASSWORD='your-password'", file=sys.stderr)
        sys.exit(1)

    try:
        rows = fetch_rows(conn)
    finally:
        conn.close()

    today = dt.date.today()
    start = today - dt.timedelta(days=WINDOW_DAYS)
    date_range = f"{start.isoformat()} to {today.isoformat()}"

    # ---- scope filter (applied before anything else sees the rows) ----
    suppressed = []
    kept = []
    for d in rows:
        reason = out_of_scope(d)
        if reason:
            d["_suppressed_reason"] = reason
            suppressed.append(d)
        else:
            kept.append(d)
    rows = kept

    # ---- classify up front so review output and prompts agree ----
    for d in rows:
        d["_instrument"] = instrument_type(d["content_type"],
                                           d["document_title"])
        d["_area"] = area_for(d["publishing_agency"])

    # ---- input set (printed for review) ----
    print("=" * 78)
    print(f"INPUT SET  project={PROJECT}  window={WINDOW_DAYS}d "
          f"({date_range})  is_new only")
    print("=" * 78)
    if suppressed:
        print(f"SUPPRESSED (out of scope) -- {len(suppressed)} document(s) "
              f"withheld from the brief:")
        for d in suppressed:
            title = (d["document_title"] or "Untitled").strip()[:70]
            print(f"  [{d['publication_date']}] {d['_suppressed_reason']:42} "
                  f"{title}")
        print("  Review these. A wrongly suppressed document is a content "
              "gap the reader cannot see.")
        print()
    if not rows:
        print("No unprocessed documents in the window. Nothing to brief.")
        print("Tip: raise WINDOW_DAYS at the top of the script to reach "
              "older banked content.")
        return
    print(f"{len(rows)} document(s)  [date | area | instrument | agency | title]:")
    for d in rows:
        agency = (d["publishing_agency"] or "?")[:34]
        title = (d["document_title"] or "")[:44]
        print(f"  [{d['publication_date']}] {d['_area']:13} "
              f"{d['_instrument']:38} {agency:34}  {title}")
    print()

    # ---- group by program area ----
    rows_by_area = {}
    for d in rows:
        rows_by_area.setdefault(d["_area"], []).append(d)

    # ---- synthesize each populated area ----
    section_texts = []
    figure_warnings = []
    for area in AREA_ORDER:
        area_rows = rows_by_area.get(area)
        if not area_rows:
            continue
        print(f"... synthesizing {AREA_HEADING[area]} "
              f"({len(area_rows)} doc(s)) via {MODEL}", file=sys.stderr)
        text = synthesize_section(area, area_rows)
        figure_warnings.extend(
            verify_figures(AREA_HEADING[area], text, docs_block(area_rows))
        )
        section_texts.append((area, text))

    # ---- executive summary ----
    print(f"... synthesizing executive summary via {MODEL}", file=sys.stderr)
    exec_summary = synthesize_exec_summary(date_range, section_texts,
                                           rows_by_area)
    figure_warnings.extend(
        verify_figures("EXECUTIVE SUMMARY", exec_summary,
                       docs_block(rows))
    )

    if figure_warnings:
        print()
        print("!" * 78, file=sys.stderr)
        print("UNVERIFIED FIGURES -- do not send this brief as-is:",
              file=sys.stderr)
        for w in figure_warnings:
            print(f"  ! {w}", file=sys.stderr)
        print("!" * 78, file=sys.stderr)
        print()

    # ---- assemble brief ----
    parts = [
        "FEDERAL POLICY BRIEF",
        f"Coverage: {date_range}",
        "=" * 64,
        "",
        "EXECUTIVE SUMMARY",
        "-" * 17,
        exec_summary,
        "",
    ]
    for area, text in section_texts:
        heading = AREA_HEADING[area].upper()
        parts.append(heading)
        parts.append("-" * len(heading))
        parts.append(text)
        parts.append("")
    parts.append(attribution(rows_by_area))
    brief = "\n".join(parts)

    # ---- output: screen + file ----
    print("=" * 64)
    print("GENERATED BRIEF  (review-only: nothing sent, nothing marked "
          "processed)")
    print("=" * 64)
    print(brief)

    outname = f"federal_policy_brief_review_{today.isoformat()}.txt"
    with open(outname, "w", encoding="utf-8") as f:
        f.write(brief)
    print()
    print(f"Saved to ./{outname}")


if __name__ == "__main__":
    main()
