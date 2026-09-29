#!/usr/bin/env python3
"""
generate_brief_review.py - federal_policy_brief, v9.3

Reads recent Federal Register items from the scraped_content table, groups
them by program area, uses local Gemma (via Ollama) to synthesize a plain-text
executive brief, appends a deterministic Source Attribution Addendum, then
prints the result and saves it to a file for operator review.

DEFAULT MODE IS STILL REVIEW-ONLY. Run with no flags and this script:
  - does NOT send any email
  - does NOT mark rows processed (the is_new flag is left untouched)
  - does NOT write a brief_runs row
It is therefore safe to run as many times as you like.

--SEND MODE (new in v5). Pass --send and, if verification is clean, the
script additionally:
  - emails the finished brief via authenticated SMTP (self-send to the
    operator's own iCloud inbox -- ADR-039 H4 sub-decision, August 22, 2026)
  - marks every consumed scraped_content row is_new = FALSE
  - writes one brief_runs row recording the outcome (sent/failed/skipped_unverified)
If verification is NOT clean, --send skips the email and the is_new flip,
still writes the review file and a brief_runs row (send_status =
'skipped_unverified'), and exits non-zero. --send never emails an unverified
brief, independent of the HARD_FAIL_ON_UNVERIFIED switch below, which still
controls only the review-mode print-vs-abort behavior.

No shell or bash is invoked (v9 runs sysctl and memory_pressure directly,
without a shell, for the pre-flight memory gate). It reaches PostgreSQL (localhost:5432),
Ollama (localhost:11434), and -- in --send mode only -- smtp.mail.me.com:587
over the network. It must run on the host, not inside Docker: Keychain
(used for SMTP credentials) is unavailable inside a container.

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

CHANGES FROM v3 (2026-08-22, Entry #021)
  9. Fabrication verification extended beyond currency. verify_claims() now
     checks four claim types against source text:
       (a) Currency amounts (unchanged from v3)
       (b) Dates -- ISO and written forms normalized to datetime.date
       (c) Federal Register citations -- "91 FR 12345" patterns
       (d) Counts with unit words -- "15 states", "three agencies"
     A fabricated date or FR citation is as damaging as a fabricated dollar
     amount; nothing previously caught one.
 10. Hard-fail mode added. HARD_FAIL_ON_UNVERIFIED controls whether an
     unverified claim is a printed warning (False, current review mode) or
     aborts the run (True, required before send-to-inbox wiring). The switch
     is in one place at the top of the file.
 11. Foreign content dropped silently. The v2/v3 scope filter required both a
     funding marker and a foreign marker; in practice, every foreign notice
     has zero relevance to state HHS leadership. Foreign content is now
     dropped on any foreign marker alone (no funding requirement), and
     "codex alimentarius" is added as a standalone international-content
     marker. Dropped foreign documents are no longer printed in the review
     output -- they are silently excluded.
 12. Cross-Program limited to high-signal instruments. The catch-all
     Cross-Program section routinely collected 50+ documents, overrunning
     Gemma's context window and producing outlines instead of prose (the
     Entry #018 / #021 failure mode). Cross-Program now keeps only proposed
     rules, final rules, Privacy Act matching program notices, Privacy Act
     system of records notices, and presidential documents. Routine
     paperwork (information collection requests, advisory committee meeting
     notices, drug/device determinations, generic notices) is dropped from
     Cross-Program and printed in the review output as "DROPPED (routine,
     Cross-Program)" so the operator can spot a bad call. CMS, SNAP, and
     TANF sections are unaffected and keep all instruments.

CHANGES FROM v4 (2026-08-22, Entry #022)
 13. Send-to-inbox wiring added (ADR-039 H4 closure). New --send flag. No
     ESP or purchased sender domain: the only recipient is the operator's
     own inbox, so authenticated SMTP against an existing mailbox the
     operator already controls (iCloud, smtp.mail.me.com:587, STARTTLS) is
     sufficient and adds no new third-party dependency. Credentials
     (ICLOUD_SMTP_USER, ICLOUD_SMTP_PASSWORD) are read from macOS Keychain
     via the same account=openclaw / service=SECRET_NAME convention as
     app/config.py's _keychain_get(), duplicated here rather than imported
     because this script is intentionally standalone (no app.* imports,
     direct psycopg2 connection).
 14. Send gated on clean verification. --send checks the SAME claim_warnings
     list verify_claims() already produces -- no second detection pass. Any
     warning blocks the email and the is_new flip; the review file and a
     brief_runs audit row are still written either way. This is deliberately
     stricter than the module-level HARD_FAIL_ON_UNVERIFIED switch, which
     stays False (review mode prints warnings but does not abort) -- that
     switch is reserved for a later, separate flip per the v3/Entry #021
     plan, not bundled into this change.
 15. brief_runs audit trail (migration_006.sql). One row per --send
     invocation only; review-only runs remain fully side-effect-free, same
     guarantee v0-v4 always made. Records doc count, verification status,
     send status, recipient, and any SMTP error.
 16. is_new flip on successful send only. Consumed scraped_content rows are
     marked is_new = FALSE after the SMTP send succeeds, not before -- a
     failed send leaves the rows eligible for the next run instead of
     silently losing them.

UPSTREAM DEFECT RESOLVED (2026-08-20)
  The scraper TYPE_MAP defect that stored every proposed rule as 'other' is
  fixed in app/scheduling/scrapers/federal_register.py, and the 15 banked rows
  were relabeled. The "document" entry in HIGH_SIGNAL that worked around it
  has been removed.

CHANGES FROM v5 (2026-09-20, Entry #037)
 17. Derived counts are now forbidden in the system prompt, not tolerated in
     the verifier. This closes a defect that had silently gated --send shut
     since v5, and it records a rejected fix because the reasoning matters.

     The defect: verify_claims() validates a number by finding it in source
     text. That works for currency, dates and FR citations, which are QUOTED.
     Aggregate counts are DERIVED from the document set and appear in no
     single source, so they always flag. v4 knew and chose to flag them --
     correct when a warning cost a glance. v5 then hard-gated --send on zero
     warnings, turning known noise into a blocker. The Sept 20 run produced
     three count warnings, all three arithmetically correct, and a live send
     would have been refused. Only one brief has ever been sent; this is why.

     THE FIX THAT WAS TRIED AND REVERTED: treat a count at or below the
     section's document count as a non-blocking note, on the theory that the
     model cannot count more items than it was handed. It was implemented,
     run, and reverted the same hour. On its first run the model wrote "SNAP
     demonstration projects in 15 states" where the sources named 18 -- and
     the new rule demoted that fabrication from a blocking warning to an
     informational note, because 15 was below the document count. It also
     still warned on "within the last seven days", a duration rather than an
     entity count. Net: it passed a real error and still blocked on a
     non-error. Strictly worse than v5.

     What that proved is the useful part: the model DOES fabricate counts.
     Two runs over identical input produced 18 (right) and 15 (wrong). The
     strict check was catching a live failure mode, not just noise, and no
     magnitude heuristic can separate 15 from 18 -- only ground truth can,
     and the verifier has none.

     THE FIX APPLIED: remove the counts at the source. SYSTEM_PROMPT now
     forbids tallying inputs at all -- name the items or describe them with
     no number -- and forbids restating the coverage window as a duration.
     verify_counts() is left strict and untouched. This is the same
     enforce-twice pattern as to_plain_text() and verify_figures(): prompt
     against it, and detect it if it happens anyway.

     Honest expectation: this reduces how often counts appear; it does not
     guarantee they never will. If the model tallies anyway, --send stays
     gated -- and that is the correct outcome, not a bug to engineer around.
     A count in the output is a fabrication risk, as 15-vs-18 demonstrated.


CHANGES FROM v7 (2026-09-27, Entry #040)
 19. Counts with modifier words are now examined. The v7 audit recorded that
     "two information collection requests" went unchecked and proposed adding
     "request" to _UNIT_PAIRS. That diagnosis was wrong: the count regexes
     required the number to touch the unit, so the phrase was invisible with
     or without the unit. The same gap hid "3 new SNAP rules" and "15
     participating states" -- the exact shape of the 15-vs-18 fabrication.
     Now up to two modifier words may sit between number and unit (function
     words, units and number words excluded; lazy, so the nearest unit wins;
     date and currency tails excluded). "request" is a unit, with ground truth
     from both request instruments.
     First live run then flagged "One information collection request,
     titled ..." -- correct text enumerating a correctly stated "two". v8
     accepts "one <unit>" only when the same text states a total above one
     for that unit that matches ground truth. Structural, not a tolerance:
     a standalone "one notice" against 18 is still caught.
     Tests: test_count_verification.py.

CHANGES FROM v6 (2026-09-20, Entry #038)
 18. Counts are now verified against GROUND TRUTH recomputed from the source
     rows, which is the deterministic backstop v6's prompt change could not
     provide. This is the third approach tried in one day; the first two are
     recorded above and below because the reasoning is the durable part.

     Why a backstop was still needed: v6 forbade tallying in SYSTEM_PROMPT
     and that worked partially -- SNAP began naming all eighteen states
     instead of counting them, which is better output, and warnings fell from
     three to one. But the model still wrote "issued three notices" despite a
     near-verbatim prohibition. Prompting has now failed three times in this
     file (markdown v1, arithmetic v2, tallying v6) and the answer every time
     was a deterministic check, not a firmer instruction.

     How it works: ground_truth_counts() recomputes, from the rows the model
     was actually given, what the section contains -- documents, notices,
     rules, agencies, and distinct US states named in titles and abstracts.
     verify_counts() then has three outcomes per count:
       (a) ground truth exists and matches   -> VERIFIED, cleared silently.
           This is the only legitimate way a derived count can pass.
       (b) ground truth exists and disagrees -> WARNING naming the real
           figure ("'15 state(s)' is WRONG -- the sources contain 18").
       (c) no ground truth for that unit     -> WARNING, unverifiable, as
           before. Durations ("7 days") land here and stay surfaced.

     Nothing is loosened. Pass no truth mapping and every count warns exactly
     as in v4-v6. A unit whose true count is zero is dropped from the mapping
     rather than reported as "wrong, 0", so a section that simply has no
     states says "unverifiable" instead of accusing the model.

     State matching is longest-first with word boundaries, so "West Virginia"
     does not also match "Virginia" and "Arkansas" does not contain "Kansas".
     Both cases are unit-tested; both occur in real SNAP titles.

     This is the only approach of the three that catches the 15-vs-18 error,
     because catching it requires knowing the answer is 18. Tolerance
     heuristics cannot, and prompts do not reliably prevent it.

CHANGES FROM v8 (2026-09-29, Entry #048, ADR-047 §4-§6 and §8)
 19. --model NAME runs the brief with another local model, for the ADR-047
     bake-off. Evaluation only: it cannot be combined with --send, and its
     review file is named <date>_<model>_<time>.txt so a bake-off never
     overwrites the tracked review file for the day.
 20. Truncation guard (fail-closed). Ollama truncates silently -- the Entry
     #018 misdiagnosis. After every call, if prompt + output tokens reach
     NUM_CTX - 256, or the output stopped at the length limit, the call is
     reported as a TRUNCATION warning. It joins claim_warnings, so it blocks
     --send exactly as an unverified claim does.
 21. One inference job at a time (ADR-047 §6): a PostgreSQL session advisory
     lock (key 470047, shared with app/llm.py's /agent path). Waits up to 15
     minutes, then exits 4. The lock is held on its own autocommit
     connection that runs no transaction and touches no table -- a narrow,
     deliberate exception to "synthesis holds no DB connection" below.
 22. Pre-flight memory gate: kernel memory pressure must be normal (1) and
     free memory >= 40% before the model loads; retries for up to 15
     minutes, then exits 3. Memory is reported before and after, flagged
     YELLOW/RED per ADR-047 §8 (the replacement for ADR-033's dead 28/30 GB
     thresholds).
 23. The model is unloaded when the run ends (keep_alive 0), success or
     failure, returning ~7 GB to the operator immediately instead of after
     Ollama's five-minute default.
     Tests: test_inference_guards.py.
 24. F13 (Entry #048): "information collection request(s)" is now one unit.
     As three words it used up the two-word modifier budget, so "Two recent
     information collection requests" was never read and the following "One
     request" was flagged -- a false positive on correct text. Subset counts
     with no stated total (CMS: "A notice ... Two notices ...") remain
     flagged by design: accepting a count below the true total is the
     tolerance approach ruled out after 15-vs-18. The WRONG message now says
     a subset may be correct, so the operator knows what to check.
 25. --think on|off (v9.2, Entry #048). The bake-off found gemma4:e4b
     reasoning by default -- 275 tokens and 21 s for a one-sentence answer --
     so every brief has spent time and context on hidden reasoning. The flag
     sends Ollama's "think" setting; omitted, the request is unchanged.
     Evaluation only, like --model.
 26. v9.3 (Entry #048, ADR-047 §14): production defaults set per workload --
     MODEL qwen3:8b, THINK False (was gemma4:e4b with its default reasoning).
     Bake-off: zero fabrications for both; thinking off 2.8x faster; qwen3:8b
     lightest in memory. Revert = these two constants.

"""

import argparse
import logging
import os
import re
import smtplib
import subprocess
import sys
import time
import datetime as dt
from email.message import EmailMessage

import psycopg2
import httpx

log = logging.getLogger(__name__)

# ----------------------------- CONFIG -----------------------------
WINDOW_DAYS = 7                       # production value
PROJECT = "federal_policy_brief"      # scoping tag in scraped_content.project
MODEL = "qwen3:8b"                    # ADR-047 §14: the BRIEF workload's model (was gemma4:e4b)
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_TIMEOUT = 300                  # seconds; local inference can be slow
TEMPERATURE = 0.2                     # low = factual, consistent
NUM_CTX = 8192                        # prompt+response budget; Ollama default 4096 truncated Cross-Program
THINK = False                         # ADR-047 §14: thinking off for briefs (v9.3); --think on/off overrides for evaluation
OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"   # used only to unload the model

# ----------------------- INFERENCE GUARDS (v9, ADR-047) -----------------------
TRUNCATION_MARGIN = 256               # tokens; prompt+output this close to NUM_CTX = truncated
INFERENCE_LOCK_KEY = 470047           # ADR-047 §6 -- same key as app/llm.py
LOCK_WAIT_SECONDS = 900               # wait up to 15 min for another inference job
LOCK_POLL_SECONDS = 30
GATE_MIN_FREE_PCT = 40                # pre-flight: free memory needed before loading
GATE_WAIT_SECONDS = 900               # retry the gate for up to 15 min
GATE_POLL_SECONDS = 60
YELLOW_FREE_PCT = 25                  # ADR-047 §8
YELLOW_SWAP_GROWTH_MB = 1024
RED_PRESSURE_LEVEL = 4                # kern.memorystatus_vm_pressure_level: 1 normal, 2 warn, 4 critical

# ----------------------- SEND-TO-INBOX (v5, ADR-039 H4) -----------------------
# Self-send only: the sole recipient is the operator's own inbox, so an
# existing mailbox the operator already controls is used directly -- no ESP,
# no purchased sender domain. Credentials come from Keychain, never from
# this file or the environment.
SMTP_HOST = "smtp.mail.me.com"
SMTP_PORT = 587
SMTP_USER_SERVICE = "ICLOUD_SMTP_USER"
SMTP_PASSWORD_SERVICE = "ICLOUD_SMTP_PASSWORD"
SMTP_TIMEOUT = 30                     # seconds

# Controls REVIEW-MODE behavior only: whether an unverified claim aborts a
# review-only run (True) or just prints a warning (False, current). --send
# mode does NOT read this switch -- it always blocks the email (see
# maybe_send() below) on any claim_warnings, regardless of this value. Flip
# this to True separately, later, once send mode has enough clean live runs
# behind it (v3/Entry #021 plan) -- do not bundle that flip into this change.
HARD_FAIL_ON_UNVERIFIED = False

DB = dict(
    host="localhost",
    port=5432,
    dbname="openclaw",
    user="openclaw",
    password=os.environ.get("POSTGRES_PASSWORD", "changeme"),
)


def _keychain_get(service, fallback=""):
    """Read a secret from macOS Keychain (account=openclaw, service=SERVICE).

    Mirrors app/config.py's _keychain_get(). Duplicated rather than imported:
    this script is intentionally standalone (no app.* imports, direct
    psycopg2 connection, runs on the host via cron/manually -- not inside
    the Docker network the app package targets).
    """
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", "openclaw", "-s", service, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            if value and value != "empty":
                return value
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        log.warning("Keychain lookup failed for %s: %s", service, e)

    return fallback


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

# --------------------- SCOPE FILTER: FOREIGN CONTENT ---------------------
# Audience is state HHS leadership. Foreign content has zero relevance.
# Any foreign marker drops the document silently -- no funding requirement,
# no review output. A domestic rule that merely cites a foreign country in
# passing is an accepted false-positive risk; in practice the word-boundary
# matching on country names and the "ministry" marker make this rare.

# A US federal agency is never a "ministry"; that word alone is a reliable
# foreign-government marker.
FOREIGN_MARKERS = (
    "ministry of health",
    "ministry of",
    "codex alimentarius",
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


def is_foreign(d):
    """Return True if the document matches any foreign-content marker."""
    text = f"{d.get('document_title') or ''}\n{d.get('raw_content') or ''}".lower()

    if any(m in text for m in FOREIGN_MARKERS):
        return True

    if _COUNTRY_RE.search(text):
        return True

    return False


# --------------------- CROSS-PROGRAM INSTRUMENT FILTER ---------------------
# Cross-Program routinely collects 50+ documents, overrunning Gemma's context
# window and producing outlines instead of prose. Only high-signal instruments
# are kept; routine paperwork is dropped. CMS, SNAP, and TANF are unaffected.
#
# Dropped documents are printed in the review output so the operator can spot
# a wrongly-dropped item. Foreign drops are silent; instrument drops are not.
CROSS_PROGRAM_KEEP = {
    "proposed rule",
    "final rule",
    "Privacy Act matching program notice",
    "Privacy Act system of records notice",
    "presidential document",
}


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
    "NEVER TALLY THE INPUTS. Counting the documents you were given is "
    "arithmetic, and you get it wrong. Do not write how many states, notices, "
    "rules, agencies, programs or documents a section contains -- not as a "
    "digit and not as a word. Do not write 'in 15 states', 'three notices "
    "were published', or 'several dozen items'. Name the items, or describe "
    "them with no number at all: 'notices for North Dakota, Virginia and "
    "Nevada, among others' is correct; 'notices for 18 states' is not. This "
    "is not hypothetical -- on one production run you reported 15 states "
    "where the sources named 18. If a source document itself states a count, "
    "you may report that count exactly as that document states it. Do not "
    "restate the brief's coverage period as a duration either ('within the "
    "last seven days'); the coverage dates are printed above your text.\n\n"
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


# =====================================================================
# CLAIM VERIFICATION
# =====================================================================
# Deterministic backstop for fabricated claims. The system prompt forbids
# arithmetic and demands source fidelity; this proves it. Prompting alone
# has now failed twice (markdown in v1, arithmetic in v2), so every
# verifiable claim type gets the enforce-twice treatment.
#
# Four extractors, each following the same pattern:
#   1. Extract claims from generated prose, normalize to comparable form
#   2. Extract the same claim type from source text, normalize identically
#   3. Flag anything in generated that is absent from source
#
# False positives are possible (see per-extractor notes). In review mode
# (HARD_FAIL_ON_UNVERIFIED = False), these print as warnings for operator
# review. In send mode, any warning aborts the run.
# =====================================================================

# ----- (a) Currency amounts (unchanged from v3) -----
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

    Returns a list of warning strings.
    """
    source = _money_values(source_text)
    warnings = []
    for value in sorted(_money_values(generated) - source):
        warnings.append(
            f"[currency] {label}: ${value:,.0f} appears in the generated "
            f"text but in no source document for this section"
        )
    return warnings


# ----- (b) Dates -----
# Normalized to datetime.date so "August 17, 2026" matches "2026-08-17".
# Only specific dates (month + day + year) are checked. Month-only
# references ("in August 2026") are too vague to be a fabrication risk
# and are not extracted.

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}

# ISO dates: 2026-08-17
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Written dates: August 17, 2026 / Aug. 17, 2026 / Aug 17, 2026
# The comma after the day is optional to catch informal usage.
_WRITTEN_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\.?\s+(\d{1,2}),?\s+(\d{4})\b",
    re.I,
)


def _extract_dates(text):
    """Every specific date in text, normalized to datetime.date objects."""
    dates = set()
    for y, m, d in _ISO_DATE_RE.findall(text or ""):
        try:
            dates.add(dt.date(int(y), int(m), int(d)))
        except ValueError:
            continue
    for month_str, day_str, year_str in _WRITTEN_DATE_RE.findall(text or ""):
        month_num = _MONTH_NAMES.get(month_str.lower().rstrip("."))
        if month_num:
            try:
                dates.add(dt.date(int(year_str), month_num, int(day_str)))
            except ValueError:
                continue
    return dates


def verify_dates(label, generated, source_text):
    """Flag dates in generated prose absent from the source.

    Returns a list of warning strings. False positives are unlikely here:
    a date either appears in a source document or it does not.
    """
    source_dates = _extract_dates(source_text)
    warnings = []
    for d in sorted(_extract_dates(generated) - source_dates):
        warnings.append(
            f"[date] {label}: {d.strftime('%B %d, %Y')} appears in the "
            f"generated text but in no source document for this section"
        )
    return warnings


# ----- (c) Federal Register citations -----
# Pattern: "91 FR 12345" (volume, page). A fabricated citation number sends
# a commissioner looking for a document that does not exist.

_FR_CITE_RE = re.compile(r"\b(\d{1,3})\s+FR\s+(\d{3,6})\b", re.I)


def _extract_fr_citations(text):
    """Every Federal Register citation as (volume, page) integer tuples."""
    cites = set()
    for vol, page in _FR_CITE_RE.findall(text or ""):
        cites.add((int(vol), int(page)))
    return cites


def verify_fr_citations(label, generated, source_text):
    """Flag FR citations in generated prose absent from the source.

    Returns a list of warning strings. False positives are very unlikely:
    FR volume/page numbers are specific enough that an invented one is
    almost certainly wrong.
    """
    source_cites = _extract_fr_citations(source_text)
    warnings = []
    for vol, page in sorted(_extract_fr_citations(generated) - source_cites):
        warnings.append(
            f"[FR citation] {label}: {vol} FR {page} appears in the "
            f"generated text but in no source document for this section"
        )
    return warnings


# ----- (d) Counts with unit words -----
# Catches "15 states", "three agencies", "$30M to 47 organizations" etc.
# Requires a recognized unit word after the number so that bare numbers,
# section numbers ("Section 3"), and citation numbers ("91 FR") are not
# swept up.
#
# FALSE POSITIVE NOTE: the model legitimately counts its inputs ("the
# three proposed rules in this section"). That count does not appear in any
# single source document, so it will be flagged. These are expected and
# are easy to spot in review. Suppressing them automatically would require
# knowing how many documents the model was given, which is fragile; better
# to flag and let the operator clear them.

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100,
}

# Unit words relevant to this domain. Both singular and plural forms map
# to a canonical singular. Only words likely to appear in federal policy
# prose are included; adding a word here is cheap and safe.
_UNIT_NORMALIZE = {}
_UNIT_PAIRS = [
    ("state", "states"),
    ("agency", "agencies"),
    ("document", "documents"),
    ("program", "programs"),
    ("notice", "notices"),
    ("rule", "rules"),
    ("award", "awards"),
    ("grant", "grants"),
    ("agreement", "agreements"),
    ("organization", "organizations"),
    ("entity", "entities"),
    ("beneficiary", "beneficiaries"),
    ("recipient", "recipients"),
    ("application", "applications"),
    ("comment", "comments"),
    ("provision", "provisions"),
    ("requirement", "requirements"),
    ("condition", "conditions"),
    ("section", "sections"),
    ("category", "categories"),
    ("item", "items"),
    ("change", "changes"),
    ("amendment", "amendments"),
    ("waiver", "waivers"),
    ("indicator", "indicators"),
    ("measure", "measures"),
    ("facility", "facilities"),
    ("jurisdiction", "jurisdictions"),
    ("territory", "territories"),
    ("county", "counties"),
    ("tribe", "tribes"),
    ("provider", "providers"),
    ("hospital", "hospitals"),
    ("plan", "plans"),
    ("option", "options"),
    ("request", "requests"),
    # The instrument's full name, as one unit (F13, Entry #048). As three
    # words it consumed the whole two-word modifier budget, so "Two recent
    # information collection requests" went unread -- and the "One request"
    # that followed was then flagged for lack of a stated total.
    ("information collection request", "information collection requests"),
    ("criterion", "criteria"),
    ("year", "years"),
    ("day", "days"),
    ("month", "months"),
]
for _sing, _plur in _UNIT_PAIRS:
    _UNIT_NORMALIZE[_sing] = _sing
    _UNIT_NORMALIZE[_plur] = _sing
# Compound units count toward their head noun, which is what ground truth tracks.
_UNIT_NORMALIZE["information collection request"] = "request"
_UNIT_NORMALIZE["information collection requests"] = "request"

# All unit words for regex alternation (longest first to avoid prefix issues).
_ALL_UNITS = sorted(_UNIT_NORMALIZE.keys(), key=len, reverse=True)
_UNIT_PATTERN = "|".join(re.escape(u) for u in _ALL_UNITS)

# All word-form numbers for regex alternation.
_WORD_NUM_PATTERN = "|".join(
    sorted(_WORD_NUMBERS.keys(), key=len, reverse=True)
)

# Up to two modifier words may sit between the number and the unit (v8,
# Entry #040). Before v8 the number had to touch the unit, so "two information
# collection requests" and "3 new SNAP rules" were never examined at all -- they
# passed by not being seen. A gap word may not be a function word (which ends
# the noun phrase: "7 days of comments" is not a count of comments), a unit
# (so "3 notices issued rules" stays a count of notices), or a number word.
# The gap is lazy, so the nearest unit wins.
_GAP_STOPWORDS = (
    "the|a|an|of|and|or|for|to|in|on|by|from|with|at|as|is|are|was|were|"
    "that|which|this|these|those|its|their|each|other"
)
_GAP_WORD = (
    rf"(?:(?!(?:{_GAP_STOPWORDS}|{_UNIT_PATTERN}|{_WORD_NUM_PATTERN})\b)"
    rf"[a-z][a-z'\-]*\s+)"
)

# "15 states", "3 new SNAP rules" -- digit, optional modifiers, unit word.
# The lookbehind keeps the tail of a date or figure ("2026-09-17 the proposed
# rules", "$1,250 grants") from being read as a count.
_DIGIT_COUNT_RE = re.compile(
    rf"(?<![\d\-/.,$])\b(\d{{1,6}})\s+{_GAP_WORD}{{0,2}}?({_UNIT_PATTERN})\b",
    re.I,
)

# "three agencies", "two information collection requests".
_WORD_COUNT_RE = re.compile(
    rf"\b({_WORD_NUM_PATTERN})\s+{_GAP_WORD}{{0,2}}?({_UNIT_PATTERN})\b", re.I
)


def _extract_counts(text):
    """Counts with unit words, normalized to (int, singular_unit) tuples."""
    counts = set()
    for num_str, unit in _DIGIT_COUNT_RE.findall(text or ""):
        canonical = _UNIT_NORMALIZE.get(unit.lower())
        if canonical:
            counts.add((int(num_str), canonical))
    for word, unit in _WORD_COUNT_RE.findall(text or ""):
        num = _WORD_NUMBERS.get(word.lower())
        canonical = _UNIT_NORMALIZE.get(unit.lower())
        if num and canonical:
            counts.add((num, canonical))
    return counts


# ----- Ground truth for counts (v7, Entry #038) -----
#
# Longest-first so "West Virginia" wins over "Virginia". Word boundaries in
# the regex keep "Kansas" from matching inside "Arkansas".
_US_STATES = (
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "District of Columbia", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
    "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina",
    "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
    "Puerto Rico", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virgin Islands", "Virginia",
    "Washington", "West Virginia", "Wisconsin", "Wyoming",
)
_STATE_RE = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in
                      sorted(_US_STATES, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

_STATE_CANON = {s.lower(): s for s in _US_STATES}


def _states_in(text):
    """Distinct US state / territory names appearing in text."""
    return {_STATE_CANON[m.group(1).lower()]
            for m in _STATE_RE.finditer(text or "")}


def ground_truth_counts(rows):
    """Compute what the source documents ACTUALLY contain, per unit.

    This is the deterministic backstop for counts. Unlike currency or dates,
    an aggregate count cannot be verified by looking it up -- it is derived,
    so it appears in no single source. It CAN be recomputed from the rows the
    model was given, which is what this does.

    Returns {unit: actual_count} for units we can establish with confidence.
    A unit absent from the dict has no ground truth and stays unverifiable.
    """
    instruments = [r.get("_instrument") or "" for r in rows]
    titles = " \n".join(
        f"{r.get('document_title') or ''} {r.get('raw_content') or ''}"
        for r in rows
    )
    truth = {
        "document": len(rows),
        "item": len(rows),
        # Instrument labels are assigned by instrument_type(); every notice
        # subtype ends in "notice", every rule in "rule".
        "notice": sum(1 for i in instruments if i.endswith("notice")),
        "rule": sum(1 for i in instruments if i.endswith("rule")),
        # Both request instruments: "information collection request" and
        # "request for information" (v8).
        "request": sum(1 for i in instruments if "request" in i),
        "agency": len({(r.get("publishing_agency") or "").strip()
                       for r in rows if (r.get("publishing_agency") or "").strip()}),
        "state": len(_states_in(titles)),
    }
    # A zero here means "the sources mention none", which is a real finding if
    # the model claims some -- but for units that simply do not apply to this
    # section, drop them so we report "unverifiable" rather than "wrong, 0".
    for unit in ("state", "notice", "rule", "request"):
        if truth[unit] == 0:
            del truth[unit]
    return truth


def acceptable_counts(rows_by_area, all_rows):
    """Ground truth for the EXECUTIVE SUMMARY, which is scope-ambiguous.

    The summary legitimately makes section-scoped claims -- "CMS issued three
    notices" is correct even though the window holds 21 notices in total.
    Checking it against the global aggregate alone produces exactly that false
    positive, observed on the first v7 run. So a count is acceptable here if
    it is true of the whole window OR of any single section.

    This is wider than a per-section check and deliberately so: the summary
    cannot be attributed to one section without parsing it. A number matching
    no section and not the total is still caught, which is the case that
    matters.
    """
    acc = {}
    for unit, n in ground_truth_counts(all_rows).items():
        acc.setdefault(unit, set()).add(n)
    for rows in rows_by_area.values():
        for unit, n in ground_truth_counts(rows).items():
            acc.setdefault(unit, set()).add(n)
    return acc


def verify_counts(label, generated, source_text, truth=None):
    """Flag counted quantities in generated prose against ground truth.

    Returns a list of warning strings.

    Three outcomes per count, in order of preference:
      1. truth has the unit and the number matches -> VERIFIED, no warning.
         This is the only way a derived count can legitimately clear.
      2. truth has the unit and the number does NOT match -> WARNING naming
         the correct figure. This is the case that matters: on 2026-09-20 the
         model wrote "15 states" where the sources named 18, and no
         lookup-based or magnitude-based check could catch it (see the
         FALSE POSITIVE NOTE above for the approach that failed).
      3. truth has no entry for the unit -> WARNING as before, unverifiable.
         Durations ("7 days") land here; they are not entity counts and have
         no ground truth, so they are still surfaced for the operator.
    """
    truth = truth or {}
    source_counts = _extract_counts(source_text)
    generated_counts = _extract_counts(generated)

    def _ok(unit):
        # A truth value may be a single int (one section) or a set of
        # acceptable ints (the executive summary, which legitimately makes
        # section-scoped claims -- see acceptable_counts()).
        actual = truth.get(unit)
        if actual is None:
            return None
        return {actual} if isinstance(actual, int) else set(actual)

    # Enumeration (v8, Entry #040). "Two information collection requests ...
    # One information collection request, titled X ... The second ..." -- the
    # "one" there names a member of a set whose total the text has already
    # stated correctly; it is not a tally. Accept "one <unit>" ONLY when this
    # same text states a total above one for that unit that matches ground
    # truth. A standalone "SNAP issued one notice" against 18 real notices is
    # still caught. This is a structural test, not a magnitude tolerance --
    # see the FALSE POSITIVE NOTE for why tolerances are ruled out.
    enumerated = {u for n, u in generated_counts
                  if n > 1 and n in (_ok(u) or set())}

    warnings = []
    for num, unit in sorted(generated_counts - source_counts):
        actual = truth.get(unit)
        if actual is not None:
            ok = _ok(unit)
            if num in ok:
                continue  # verified against the documents themselves
            if num == 1 and unit in enumerated:
                continue  # a member of a correctly stated total
            expected = (str(actual) if isinstance(actual, int)
                        else " or ".join(str(v) for v in sorted(ok)))
            warnings.append(
                f"[count] {label}: '{num} {unit}(s)' is WRONG -- the source "
                f"documents contain {expected} (if the text describes a subset "
                f"without stating the total, it may be correct -- check by hand)"
            )
        else:
            warnings.append(
                f"[count] {label}: '{num} {unit}(s)' appears in the generated "
                f"text but in no source document for this section, and there "
                f"is no ground truth for '{unit}' -- check it by hand"
            )
    return warnings


# ----- Unified verification entry point -----

def verify_claims(label, generated, source_text, truth=None):
    """Run all four claim verifiers and return collected warnings.

    Each warning is a string prefixed with its type ([currency], [date],
    [FR citation], [count]) for easy filtering in review output.

    truth is the ground_truth_counts() mapping for the rows this text was
    generated from. Omit it and counts revert to unverifiable-and-warned,
    exactly as v4 through v6 behaved -- the check never silently weakens.
    """
    warnings = []
    warnings.extend(verify_figures(label, generated, source_text))
    warnings.extend(verify_dates(label, generated, source_text))
    warnings.extend(verify_fr_citations(label, generated, source_text))
    warnings.extend(verify_counts(label, generated, source_text, truth))
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


_TRUNCATIONS = []   # filled by ollama_chat(); folded into claim_warnings by main()


def truncation_reason(label, data, num_ctx=None):
    """Return a warning if an Ollama response shows truncation, else None.

    Ollama drops the start of an over-long prompt without an error, so the
    only evidence is the token accounting: prompt + output reaching the
    context size, or the output stopping at the length limit.
    """
    num_ctx = num_ctx or NUM_CTX
    used = (data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0)
    if data.get("done_reason") == "length":
        return (f"TRUNCATION -- {label}: output stopped at the length limit "
                f"({used} of {num_ctx} context tokens used)")
    if used >= num_ctx - TRUNCATION_MARGIN:
        return (f"TRUNCATION -- {label}: {used} of {num_ctx} context tokens "
                f"used; input may have been silently cut")
    return None


def build_payload(user_prompt):
    """The /api/chat request body. 'think' is sent only when --think was given,
    so a default run sends exactly what v9.1 sent."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"temperature": TEMPERATURE, "num_ctx": NUM_CTX},
    }
    if THINK is not None:
        payload["think"] = THINK
    return payload


def ollama_chat(user_prompt, label="call"):
    """Single non-streaming chat call to the local Ollama server."""
    payload = build_payload(user_prompt)
    r = httpx.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    reason = truncation_reason(label, data)
    if reason:
        _TRUNCATIONS.append(reason)
    return to_plain_text(data["message"]["content"])


def parse_free_pct(text):
    """'System-wide memory free percentage: 59%' -> 59, or None."""
    m = re.search(r"memory free percentage:\s*(\d+)%", text or "")
    return int(m.group(1)) if m else None


def parse_swap_used_mb(text):
    """'total = 4096.00M  used = 1558.12M  free = ...' -> 1558.12, or None."""
    m = re.search(r"used = ([\d.]+)M", text or "")
    return float(m.group(1)) if m else None


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=30).stdout
    except Exception:
        return ""


def memory_snapshot():
    """Pressure level, free %, swap used (MB). Any value may be None."""
    level = _run(["/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip()
    return {
        "level": int(level) if level.isdigit() else None,
        "free_pct": parse_free_pct(_run(["/usr/bin/memory_pressure"])),
        "swap_mb": parse_swap_used_mb(_run(["/usr/sbin/sysctl", "-n", "vm.swapusage"])),
    }


def gate_ok(snap):
    return snap["level"] == 1 and (snap["free_pct"] or 0) >= GATE_MIN_FREE_PCT


def preflight_gate(snapshot=memory_snapshot, sleep=time.sleep,
                   wait=None, poll=None):
    """Wait until memory is safe to load the model; exit 3 if it never is."""
    wait = GATE_WAIT_SECONDS if wait is None else wait
    poll = GATE_POLL_SECONDS if poll is None else poll
    waited = 0
    while True:
        snap = snapshot()
        if gate_ok(snap):
            return snap
        if waited >= wait:
            print(f"Memory gate not met after {waited}s (need pressure level 1 "
                  f"and free >= {GATE_MIN_FREE_PCT}%; last: level "
                  f"{snap['level']}, free {snap['free_pct']}%). Model NOT "
                  f"loaded. Close some applications and re-run.",
                  file=sys.stderr)
            sys.exit(3)
        print(f"... memory gate: level {snap['level']}, free "
              f"{snap['free_pct']}% -- waiting {poll}s", file=sys.stderr)
        sleep(poll)
        waited += poll


def memory_state(before, after):
    """ADR-047 §8 state for the run: GREEN, YELLOW or RED, with reasons."""
    reasons = []
    if after["level"] is not None and after["level"] >= RED_PRESSURE_LEVEL:
        return "RED", ["kernel memory pressure critical"]
    if after["level"] == 2:   # warn -- added Entry #048 after a live run ended here
        reasons.append("kernel memory pressure warn (level 2)")
    if after["free_pct"] is not None and after["free_pct"] < YELLOW_FREE_PCT:
        reasons.append(f"free {after['free_pct']}% < {YELLOW_FREE_PCT}%")
    if before["swap_mb"] is not None and after["swap_mb"] is not None:
        growth = after["swap_mb"] - before["swap_mb"]
        if growth > YELLOW_SWAP_GROWTH_MB:
            reasons.append(f"swap grew {growth:.0f} MB during the run")
    return ("YELLOW" if reasons else "GREEN"), reasons


def acquire_inference_lock():
    """Hold the host-wide inference lock (ADR-047 §6); exit 4 on timeout.

    Returns the connection holding the session lock. It runs no transaction
    and touches no table; closing it releases the lock.
    """
    conn = psycopg2.connect(**DB)
    conn.autocommit = True
    waited = 0
    with conn.cursor() as cur:
        while True:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (INFERENCE_LOCK_KEY,))
            if cur.fetchone()[0]:
                return conn
            if waited >= LOCK_WAIT_SECONDS:
                conn.close()
                print(f"Another inference job held the lock for {waited}s. "
                      f"Model NOT loaded. Re-run when it finishes.",
                      file=sys.stderr)
                sys.exit(4)
            print(f"... another inference job is running -- waiting "
                  f"{LOCK_POLL_SECONDS}s", file=sys.stderr)
            time.sleep(LOCK_POLL_SECONDS)
            waited += LOCK_POLL_SECONDS


def release_model():
    """Unload the model now (keep_alive 0). Best effort -- never raises."""
    try:
        httpx.post(OLLAMA_GENERATE_URL,
                   json={"model": MODEL, "keep_alive": 0}, timeout=30)
    except Exception as e:
        print(f"(could not unload {MODEL}: {e})", file=sys.stderr)


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
    return ollama_chat(prompt, label=AREA_HEADING[area])


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
    return ollama_chat(prompt, label="EXECUTIVE SUMMARY")


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


# =====================================================================
# SEND-TO-INBOX (v5, ADR-039 H4)
# =====================================================================
# Self-send only: the operator's own inbox is both sender and recipient, so
# an existing mailbox the operator already controls is used directly. No
# ESP, no purchased sender domain -- see the v5 docstring section above for
# the full rationale. Every function here opens its own short-lived DB
# connection rather than sharing main()'s -- main() closes its connection
# immediately after fetch_rows() (unchanged from v0-v4, and correct: the
# long-running Ollama synthesis has no business holding a DB connection
# open), so these late-stage writes need their own. v9 exception: the
# inference lock (ADR-047 §6) is held on its own autocommit connection that
# runs no transaction and touches no table -- a cross-process lock needs one.
# =====================================================================

def send_email(subject, body):
    """Send `body` as a plain-text email, self-addressed via iCloud SMTP.

    Returns the sender/recipient address on success. Raises on any
    Keychain-lookup or SMTP failure -- callers must catch and record the
    failure rather than let a bad send pass silently.
    """
    user = _keychain_get(SMTP_USER_SERVICE)
    password = _keychain_get(SMTP_PASSWORD_SERVICE)
    if not user or not password:
        raise RuntimeError(
            f"SMTP credentials not found in Keychain (account='openclaw', "
            f"service={SMTP_USER_SERVICE!r} / {SMTP_PASSWORD_SERVICE!r}). "
            f"Store them with `security add-generic-password` before using --send."
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = user
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)

    return user


def mark_processed(conn, ids):
    """Flip is_new = FALSE for the given scraped_content ids."""
    if not ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE scraped_content SET is_new = FALSE WHERE id = ANY(%s)",
            (list(ids),),
        )
    conn.commit()


def record_brief_run(conn, start, end, doc_count, warning_count,
                      verification_status, send_status,
                      recipient=None, error_message=None):
    """Insert one audit row into brief_runs. --send mode only."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO brief_runs
                (project, date_range_start, date_range_end, doc_count,
                 claim_warning_count, verification_status, send_status,
                 recipient, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (PROJECT, start, end, doc_count, warning_count,
             verification_status, send_status, recipient, error_message),
        )
    conn.commit()


def _record_run_best_effort(*args, **kwargs):
    """record_brief_run() via its own connection; DB trouble is reported, not raised.

    A failure to WRITE THE AUDIT ROW must never be confused with a failure
    to send the email -- callers report the two separately.
    """
    try:
        conn = psycopg2.connect(**DB)
    except psycopg2.OperationalError as e:
        print(f"  (could not record brief_runs row: {e})", file=sys.stderr)
        return
    try:
        record_brief_run(conn, *args, **kwargs)
    finally:
        conn.close()


def handle_send(rows, claim_warnings, brief, subject, start, today):
    """--send mode: gate on clean verification, email, flip is_new, audit.

    Returns True iff the email was actually sent. A skip (unverified) or a
    failure (SMTP or DB) both return False -- the caller uses this as the
    process exit code, so a cron job's exit status reflects "did the brief
    actually reach the inbox," not just "did the script run."
    """
    doc_count = len(rows)
    verification_status = "warnings" if claim_warnings else "clean"

    if claim_warnings:
        print(
            "--send requested but claim verification is NOT clean -- "
            "the email was NOT sent. Review the warnings above, then re-run.",
            file=sys.stderr,
        )
        _record_run_best_effort(
            start, today, doc_count, len(claim_warnings),
            verification_status, "skipped_unverified",
        )
        return False

    try:
        recipient = send_email(subject, brief)
    except Exception as e:
        print(f"SMTP send failed: {e}", file=sys.stderr)
        _record_run_best_effort(
            start, today, doc_count, 0, verification_status, "failed",
            error_message=str(e),
        )
        return False

    # Email is out. DB bookkeeping failure past this point must not read as
    # "the send failed" -- it didn't. Report it distinctly instead.
    try:
        conn = psycopg2.connect(**DB)
    except psycopg2.OperationalError as e:
        print(
            f"Sent to {recipient}, but could not connect to PostgreSQL "
            f"afterward ({e}). is_new NOT flipped, no brief_runs row -- "
            f"these {doc_count} document(s) will be re-briefed next run.",
            file=sys.stderr,
        )
        return True
    try:
        mark_processed(conn, [d["id"] for d in rows])
        record_brief_run(
            conn, start, today, doc_count, 0,
            verification_status, "sent", recipient=recipient,
        )
    finally:
        conn.close()

    print(
        f"Sent to {recipient}. {doc_count} document(s) marked processed "
        f"(is_new = FALSE). brief_runs row recorded."
    )
    return True


def synthesize_all(rows, rows_by_area, date_range):
    """All model calls for one brief. Returns (section_texts, exec_summary,
    claim_warnings); truncations are folded into claim_warnings so they block
    --send exactly as an unverified claim does (v9)."""
    _TRUNCATIONS.clear()
    # ---- synthesize each populated area ----
    section_texts = []
    claim_warnings = []
    for area in AREA_ORDER:
        area_rows = rows_by_area.get(area)
        if not area_rows:
            continue
        print(f"... synthesizing {AREA_HEADING[area]} "
              f"({len(area_rows)} doc(s)) via {MODEL}", file=sys.stderr)
        text = synthesize_section(area, area_rows)
        claim_warnings.extend(
            verify_claims(AREA_HEADING[area], text, docs_block(area_rows),
                          ground_truth_counts(area_rows))
        )
        section_texts.append((area, text))

    # ---- executive summary ----
    print(f"... synthesizing executive summary via {MODEL}", file=sys.stderr)
    exec_summary = synthesize_exec_summary(date_range, section_texts,
                                           rows_by_area)
    # The summary mixes whole-window and section-scoped claims, so its ground
    # truth is the union of both -- see acceptable_counts().
    claim_warnings.extend(
        verify_claims("EXECUTIVE SUMMARY", exec_summary,
                       docs_block(rows),
                       acceptable_counts(rows_by_area, rows))
    )

    claim_warnings.extend(_TRUNCATIONS)
    return section_texts, exec_summary, claim_warnings


def main():
    parser = argparse.ArgumentParser(
        description="Generate the federal policy brief. Review-only by "
                     "default; pass --send to email it once verification "
                     "is clean."
    )
    parser.add_argument(
        "--send", action="store_true",
        help="After generating a brief with zero claim_warnings, email it "
             "via SMTP, mark consumed rows processed (is_new = FALSE), and "
             "record a brief_runs audit row. If verification is NOT clean, "
             "the email is skipped (a brief_runs row is still recorded) "
             "and the script exits non-zero. Default: review-only, no "
             "side effects.",
    )
    parser.add_argument(
        "--model", metavar="NAME",
        help="Evaluate another local Ollama model (ADR-047 bake-off). "
             "Cannot be combined with --send. The review file is named "
             "with the model and time so the day's file is not overwritten.",
    )
    parser.add_argument(
        "--think", choices=["on", "off"],
        help="Turn the model's hidden reasoning on or off (ADR-047 bake-off). "
             "Omitted: the model's default, as before. Evaluation only -- "
             "cannot be combined with --send.",
    )
    args = parser.parse_args()
    if args.think and args.send:
        parser.error("--think is for evaluation only and cannot be combined "
                     "with --send (ADR-047 §4)")
    if args.think:
        global THINK
        THINK = (args.think == "on")
    if args.model and args.send:
        parser.error("--model is for evaluation only and cannot be combined "
                     "with --send (ADR-047 §4)")
    if args.model:
        global MODEL
        MODEL = args.model

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

    # ---- foreign content filter (silent -- no review output) ----
    rows = [d for d in rows if not is_foreign(d)]

    # ---- classify up front so review output and prompts agree ----
    for d in rows:
        d["_instrument"] = instrument_type(d["content_type"],
                                           d["document_title"])
        d["_area"] = area_for(d["publishing_agency"])

    # ---- Cross-Program instrument filter (printed for review) ----
    dropped_routine = []
    kept = []
    for d in rows:
        if d["_area"] == "Cross-Program" and d["_instrument"] not in CROSS_PROGRAM_KEEP:
            dropped_routine.append(d)
        else:
            kept.append(d)
    rows = kept

    # ---- input set (printed for review) ----
    print("=" * 78)
    print(f"INPUT SET  project={PROJECT}  window={WINDOW_DAYS}d "
          f"({date_range})  is_new only")
    print("=" * 78)
    if dropped_routine:
        print(f"DROPPED (routine, Cross-Program) -- {len(dropped_routine)} "
              f"document(s) excluded from the brief:")
        for d in dropped_routine:
            title = (d["document_title"] or "Untitled").strip()[:60]
            print(f"  [{d['publication_date']}] {d['_instrument']:38} {title}")
        print("  Review these. CMS/SNAP/TANF documents are never dropped.")
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

    # ---- synthesize: one job at a time, memory gated, model released (v9) ----
    lock_conn = acquire_inference_lock()
    before = None
    try:
        before = preflight_gate()
        section_texts, exec_summary, claim_warnings = synthesize_all(
            rows, rows_by_area, date_range)
    finally:
        release_model()
        lock_conn.close()
        if before is not None:
            after = memory_snapshot()
            state, why = memory_state(before, after)
            print(f"... memory {state}: before level {before['level']}, "
                  f"free {before['free_pct']}%, swap {before['swap_mb']} MB; "
                  f"after level {after['level']}, free {after['free_pct']}%, "
                  f"swap {after['swap_mb']} MB"
                  + (f" -- {'; '.join(why)}" if why else ""), file=sys.stderr)

    if claim_warnings:
        print()
        print("!" * 78, file=sys.stderr)
        if HARD_FAIL_ON_UNVERIFIED:
            print("UNVERIFIED CLAIMS -- aborting run (HARD_FAIL_ON_UNVERIFIED "
                  "is True):", file=sys.stderr)
        else:
            print("UNVERIFIED CLAIMS -- review before sending:",
                  file=sys.stderr)
        for w in claim_warnings:
            print(f"  ! {w}", file=sys.stderr)
        if args.send:
            print("  --send was requested: the email will be SKIPPED "
                  "because of these warnings.", file=sys.stderr)
        print("!" * 78, file=sys.stderr)
        print()

        if HARD_FAIL_ON_UNVERIFIED:
            print("Run aborted. No brief generated. Resolve the warnings "
                  "above, or if they are false positives, note them and "
                  "re-run.", file=sys.stderr)
            sys.exit(2)

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
    if args.send:
        print("GENERATED BRIEF  (--send requested: see below for outcome)")
    else:
        print("GENERATED BRIEF  (review-only: nothing sent, nothing marked "
              "processed)")
    print("=" * 64)
    print(brief)

    outname = f"federal_policy_brief_review_{today.isoformat()}.txt"
    if args.model or args.think:   # bake-off run: never overwrite the day's tracked file
        slug = re.sub(r"[^A-Za-z0-9.]+", "-", MODEL)
        if args.think:
            slug += f"_think-{args.think}"
        outname = (f"federal_policy_brief_review_{today.isoformat()}_{slug}_"
                   f"{dt.datetime.now().strftime('%H%M%S')}.txt")
    with open(outname, "w", encoding="utf-8") as f:
        f.write(brief)
    print()
    print(f"Saved to ./{outname}")

    if args.send:
        print()
        subject = f"Federal Policy Brief - {date_range}"
        sent = handle_send(rows, claim_warnings, brief, subject, start, today)
        sys.exit(0 if sent else 1)


if __name__ == "__main__":
    main()
