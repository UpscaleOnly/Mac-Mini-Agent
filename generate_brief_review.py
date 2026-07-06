#!/usr/bin/env python3
"""
generate_brief_review.py - federal_policy_brief, review-only v0

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
"""

import os
import sys
import datetime as dt

import psycopg2
import httpx

# ----------------------------- CONFIG -----------------------------
WINDOW_DAYS = 7                       # first run: last 7 days of published docs
PROJECT = "federal_policy_brief"      # scoping tag in scraped_content.project
MODEL = "gemma4:e4b"                  # local Ollama model to summarize with
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TIMEOUT = 300                  # seconds; local inference can be slow
TEMPERATURE = 0.2                     # low = factual, consistent

DB = dict(
    host="localhost",
    port=5432,
    dbname="openclaw",
    user="openclaw",
    password=os.environ.get("POSTGRES_PASSWORD", "changeme"),
)

# Agency-name substring -> program area. First match wins, so order matters.
# publishing_agency holds human-readable agency names and may list several.
PROGRAM_AREA_RULES = [
    ("Medicaid/CHIP", ["Medicaid", "Medicare"]),              # CMS
    ("SNAP",          ["Agriculture", "Food and Nutrition"]),  # USDA / FNS
    ("TANF",          ["Children and Families"]),              # ACF
]
DEFAULT_AREA = "Cross-Program"        # IRS, SSA, generic HHS, anything else

# Fixed section ordering in the finished brief.
AREA_ORDER = ["Medicaid/CHIP", "SNAP", "TANF", "Cross-Program"]

SYSTEM_PROMPT = (
    "You are a federal policy analyst preparing an executive briefing for "
    "state health and human services agency leadership. Write in plain, "
    "executive-level language suitable for a commissioner reading on a phone. "
    "Summarize only what the source documents state. Do not editorialize, "
    "advocate, predict outcomes, or recommend action. Do not invent policy "
    "developments that are not present in the sources. Be concise."
)


def fetch_rows(conn):
    """Pull the unprocessed documents published within the window."""
    cutoff = dt.date.today() - dt.timedelta(days=WINDOW_DAYS)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, publishing_agency, document_title,
                   publication_date, raw_content
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


def area_for(agency):
    """Map a publishing_agency string to a program area."""
    agency = (agency or "").lower()
    for area, needles in PROGRAM_AREA_RULES:
        if any(n.lower() in agency for n in needles):
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
        "options": {"temperature": TEMPERATURE},
    }
    r = httpx.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def docs_block(rows):
    """Format a group of documents as a numbered title+abstract list."""
    lines = []
    for i, d in enumerate(rows, 1):
        title = (d["document_title"] or "").strip()
        body = (d["raw_content"] or "").strip()
        lines.append(f"[{i}] {title}\n{body}")
    return "\n\n".join(lines)


def synthesize_section(area, rows):
    prompt = (
        f"Program area: {area}.\n\n"
        f"The following Federal Register documents were published in the last "
        f"{WINDOW_DAYS} days. Write a short briefing section (2-4 short "
        f"paragraphs) that synthesizes what they contain and why they matter "
        f"for state {area} programs. Do not list them mechanically; weave "
        f"them into prose. Documents:\n\n{docs_block(rows)}"
    )
    return ollama_chat(prompt)


def synthesize_exec_summary(date_range, section_texts):
    combined = "\n\n".join(f"{a}:\n{t}" for a, t in section_texts)
    prompt = (
        f"Write a 3-4 sentence executive summary for the top of a federal "
        f"policy brief covering {date_range}. Base it only on these section "
        f"summaries. Plain language, no editorializing:\n\n{combined}"
    )
    return ollama_chat(prompt)


def attribution(rows_by_area):
    """Deterministic source list built straight from metadata."""
    out = ["SOURCE ATTRIBUTION ADDENDUM", "=" * 27, ""]
    for area in AREA_ORDER:
        rows = rows_by_area.get(area)
        if not rows:
            continue
        out.append(area)
        out.append("-" * len(area))
        for d in rows:
            agency = (d["publishing_agency"] or "Unknown agency").strip()
            title = (d["document_title"] or "Untitled").strip()
            out.append(f"  - {agency} - {title} ({d['publication_date']})")
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

    # ---- input set (printed for review) ----
    print("=" * 64)
    print(f"INPUT SET  project={PROJECT}  window={WINDOW_DAYS}d "
          f"({date_range})  is_new only")
    print("=" * 64)
    if not rows:
        print("No unprocessed documents in the window. Nothing to brief.")
        print("Tip: raise WINDOW_DAYS at the top of the script to reach "
              "older banked content.")
        return
    print(f"{len(rows)} document(s):")
    for d in rows:
        agency = (d["publishing_agency"] or "?")[:38]
        title = (d["document_title"] or "")[:58]
        print(f"  [{d['publication_date']}] {agency:38}  {title}")
    print()

    # ---- group by program area ----
    rows_by_area = {}
    for d in rows:
        rows_by_area.setdefault(area_for(d["publishing_agency"]), []).append(d)

    # ---- synthesize each populated area ----
    section_texts = []
    for area in AREA_ORDER:
        area_rows = rows_by_area.get(area)
        if not area_rows:
            continue
        print(f"... synthesizing {area} ({len(area_rows)} doc(s)) via {MODEL}",
              file=sys.stderr)
        section_texts.append((area, synthesize_section(area, area_rows)))

    # ---- executive summary ----
    print(f"... synthesizing executive summary via {MODEL}", file=sys.stderr)
    exec_summary = synthesize_exec_summary(date_range, section_texts)

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
        parts.append(area.upper())
        parts.append("-" * len(area))
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
