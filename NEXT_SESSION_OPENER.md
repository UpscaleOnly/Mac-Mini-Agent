# Next-session opener — paste this as your first message

*(Written August 16, 2026 at the close of Entry #018. Everything below is stated inline so the session does not depend on memory or on project knowledge.)*

---

Starting a new OpenClaw session. Read this first — it carries current state
inline and supersedes memory. Project knowledge is still a lagging mirror
(rebuild pending), so trust this message and disk/Git over it. Memory is never
authoritative.

PRIORITY THIS SESSION: production over governance. The federal_policy_brief
agent is the deliverable. Governance and housekeeping are opportunistic and do
not block shipping.

SOURCE OF TRUTH: Disk (~/openclaw) + Git are canonical; GitHub in sync at
commit 8aa21ed (Aug 16, 2026). Live PostgreSQL schema is version 6.
~/openclaw/CURRENT_STATE.md is current as of Aug 16 — read it.

SHIPPED LAST SESSION (Aug 16, Entry #018): generate_brief_review.py went v0 ->
v2 and both Entry #017 flaws are fixed and validated against live data.
- Program areas now route on SUB-AGENCY only, never the parent department.
  SNAP went from 10 documents to its actual 4; TANF populated for the first
  time (it had been structurally empty), surfacing a VA-to-State-Public-
  Assistance-Agency matching program.
- Instrument type now comes from scraped_content.content_type (the Federal
  Register API's own type field), refined for notices by title keyword. The
  CMS-VA notice now briefs as a matching program between two named agencies
  instead of "an eligibility verification update."
- CMS section renamed "CMS (Medicaid/CHIP/Medicare)" — one bucket, honest
  heading, since CMS content includes Medicare authorities.
- Plain text enforced twice: system-prompt mandate plus to_plain_text(), a
  deterministic scrubber for markdown, tables and emoji.
- Executive summary gets a compressed inventory and now produces one 4-6
  sentence paragraph.
Still review-only: sends nothing, marks nothing processed, safe to re-run.
v0 preserved at generate_brief_review.py.bak.v0.

LIVE-STATE FACTS TO CARRY (do not re-discover these):
- scraped_content is project-scoped: every query MUST filter
  WHERE project = 'federal_policy_brief'.
- Coverage is continuous Apr 24 -> Aug 3. All rows still is_new = TRUE.
  48-day window = 108 docs; 20-day window = 61 docs.
- raw_content is title + abstract only (~569 chars avg). Abstract-level depth
  is by design of the current scraper.
- Generator model: gemma4:e4b (llama3.2 is the lightweight fallback).
- DB PASSWORD GOTCHA: the live openclaw Postgres role password is NOT
  "changeme". Container env and Keychain both hold that stale placeholder; the
  real value is in ~/openclaw/.env. Host-run scripts fail auth until
  POSTGRES_PASSWORD is exported, and it must be set again in EVERY new
  terminal window:
    grep POSTGRES_PASSWORD .env      then      export POSTGRES_PASSWORD='<value>'
- DOCKER GOTCHA: the nightly scraper is APScheduler running INSIDE
  openclaw_fastapi. If Docker Desktop is not running, the 01:00 ET scrape
  silently does not happen. That was the Aug 9-16 gap. Check `docker ps`
  early; if the daemon is down, launch Docker Desktop from Applications and
  wait for the whale icon to stop animating.
- WINDOW_DAYS is currently 20 in generate_brief_review.py — a temporary
  validation value. It must go back to 7 before send wiring.

IMMEDIATE TASKS (production-first):

1. Fix the scraper TYPE_MAP defect — HIGH, do this first.
   In app/scheduling/scrapers/federal_register.py, TYPE_MAP is keyed on the
   Federal Register API's QUERY-FILTER codes (RULE, PRORULE, NOTICE, PRESDOCU)
   but is applied to the API's RETURNED display strings ("Rule", "Proposed
   Rule", "Notice", "Presidential Document"). Uppercased, "RULE" and "NOTICE"
   match by coincidence; "PROPOSED RULE" and "PRESIDENTIAL DOCUMENT" match
   nothing and fall through to 'other'. Consequence: no proposed rule anywhere
   in scraped_content is labeled as one — the CY2027 HH PPS rule, the highest-
   signal item in the set, briefs as "a document." Fix should accept BOTH the
   filter codes and the display strings so it cannot break again on an API
   shape change. Requires docker compose build fastapi + up -d fastapi.
   Pair with: a one-time backfill UPDATE relabeling banked rows currently
   stored as 'other'. This touches existing data — approve explicitly first.
   Then remove "document" from HIGH_SIGNAL in generate_brief_review.py (it is
   an interim workaround, marked with a removal note in the file header).

2. Fix oversized-section degradation.
   Cross-Program carried 51 documents at a 20-day window and 91 at 48 days. At
   that size Gemma abandons prose for roman-numeral outlines and summary
   tables, covers roughly a third of its inputs, contradicts itself, and leaks
   internal docs_block index references into reader-facing text ("Items [38],
   [39], and [40]...") — 25 occurrences, all in Cross-Program, zero elsewhere.
   Two parts: (a) stop the [n] numbering reaching the reader, (b) cap or rank
   documents per section. This is Entry #017's "significance ranking" item,
   now with evidence behind it.

3. Return WINDOW_DAYS to 7 and confirm a clean small-window run.
   Note: there will be a content gap between Aug 3 and whenever the scraper
   resumed, so check what the window actually returns before assuming.

4. Once the brief reads clean: wire send-to-inbox — delivery mechanism +
   brief_runs logging + flip is_new on consumed rows. Still gated on the
   ADR-039 email-provider and sender-domain decisions.

HOUSEKEEPING (opportunistic — never ahead of the above):
- v3.0 instructions refresh: schema 4->6; "read changelog first"->"read
  CURRENT_STATE.md first"; "governance precedes features"->"governance serves
  shipping"; retire the weekly-reupload mandate as load-bearing; 39+->41+
  ADRs; ADR-014 OPEN->operative.
- Rebuild project knowledge as a clean one-way mirror of disk (incl.
  CURRENT_STATE.md, which is now current).
- Reconcile the stale credential stores (container env, Keychain) with the
  live Postgres password; finish rotation.
- Close ADR-041 as "not needed" if that still holds.
- Fix Ctrl+C not interrupting in Terminal. This bit hard on Aug 16 — a
  20-minute Gemma run with no abort short of closing the window.

WORKING RULES (unchanged): one command at a time, no shell on the Mac, approve
before building, .py delivered as .txt, git commit -m only, token conservation.

TWO PRACTICAL NOTES FROM LAST SESSION:
- Browser download collisions: a second download of the same filename becomes
  name_1.txt. Check `ls -lt ~/Downloads | head -4` and match the byte count
  before copying, or you will silently reinstall the old file. `cp source.txt
  dest.py` renames in one step — no Finder rename needed.
- Granting the Claude desktop app read access to ~/openclaw made verification
  much faster (reading files back off disk to confirm what actually landed).
  That is file transfer, not shell execution, so ADR-014 is untouched. Write
  access remains declined.
