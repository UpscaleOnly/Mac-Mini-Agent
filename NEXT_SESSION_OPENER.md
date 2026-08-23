# Next-session opener — paste this as your first message

*(Written August 22-23, 2026 at the close of Entry #023, revised late the same evening after an ADR-042 fragment-hunt session. Everything below is stated inline so the session does not depend on memory or on project knowledge.)*

---

Starting a new OpenClaw session. Read this first — it carries current state
inline and supersedes memory. Project knowledge is still a lagging mirror
(rebuild pending), so trust this message and disk/Git over it. Memory is never
authoritative.

WORKING MODE HAS CHANGED SINCE AUG 20 — READ THIS BEFORE ANYTHING ELSE.
ADR-014 (Entry #021, Aug 22) moved from OPEN to RESOLVED with a narrow
exception: **Claude Code in Manual permission mode may now run shell commands,
edit files directly, and commit to Git — scoped to `~/openclaw`, per-action
operator approval, Auto mode never used, Cowork never used.** The old rules
below (".py delivered as .txt", "no shell on the Mac", "git commit -m only" =
operator does it) describe the PRE-ADR-014 world and are only accurate for a
plain Claude Desktop chat session (MCP filesystem, read-only), not for Claude
Code. If you are in Claude Code: verify you are actually in `~/openclaw`
first (see the dual-clone warning below), then work directly — edit files,
run migrations, commit — with per-action approval as normal. If you are in
Claude Desktop chat: the old rules still apply there.

⚠️ DUAL-CLONE WARNING (new, Aug 22): a second local clone of this exact repo
exists at `~/projects/mac-mini`. It was where an entire session's worth of
work happened before anyone noticed — same GitHub remote, same commit
history, no `.env`, so it silently fails DB/SMTP operations instead of
loudly refusing. **Before doing anything, confirm:**
    pwd && git remote -v
should show `~/openclaw` and `UpscaleOnly/Mac-Mini-Agent`. If Claude Code
opened somewhere else, stop and relocate before writing anything. See
changelog Entry #022 for the full incident and ADR-014 for the scoping rule
this violated. `~/projects/mac-mini`'s working tree was reverted clean; its
disposition (keep vs. remove) is still an open item.

⚠️ GOVERNANCE IS FRAGMENTED — READ ADR-042 (filed OPEN Aug 22, full
reconciliation still explicitly DEFERRED to a future project — but a
fragment-hunt session happened the same evening and moved several things).
Read `~/openclaw/adr_fragments_2026-08-22/README.md` for the full writeup
before touching this area again. Summary:
- **ADR-014 has been reconstructed** (not an original — clearly flagged as
  such) at `~/openclaw/ADR_014.docx`, committed `7558894`. Built from two
  independently-maintained sources that agree word-for-word. Use this
  instead of changelog Entry #021 now; Section 6 of the document itself
  carries the full provenance trail.
- **ADR-036 is not an orphan.** It's real, DECIDED policy (GPU VRAM
  Allocation, April 4, 2026) — just never cross-referenced by the exact
  string "ADR-036" locally, which is what the original grep checked for.
  Separately: `~/openclaw/ADR_036.docx` is NOT a valid .docx file — it's
  plain markdown text saved with a `.docx` extension (an old
  ".txt-renamed-in-Finder" mistake). Reads fine as plain text; breaks
  `unzip`/pandoc/python-docx until fixed. Quick opportunistic fix, does not
  need to wait for the full reconciliation.
- **ADR-032's likely identity found**, not confirmed: probably
  `Mac_Mini_NIST_800_53_Compliance.docx` (archived in the fragments folder
  above), based on ADR-036 citing "ADR-032 (NIST)" in its own reference
  list. The document itself never self-identifies as ADR-032.
- **Real titles + partial substance recovered** (via cross-references
  inside ADR-031 and ADR-036, NOT full original documents) for ADR-002,
  003, 005, 019, 020, 021, 023, 024, 027, 028, 029, 030. Full table in the
  fragments README. None built into stub documents yet — deliberately held
  back pending a fuller source, see next point.
- **`Mac_Mini_ADR_v2_6.docx` ruled out** as a hoped-for master multi-ADR
  document — opened and checked; it's just another copy of the ADR-031
  draft. Don't re-chase this specific file. `Mac_Mini_ADR_v1_3.docx` was
  never actually opened — technically still unconfirmed, low priority now.
- **ADR-017 and ADR-022 remain completely unrecovered** — zero fragments
  anywhere, including a direct in-project search for both numbers. If they
  exist, they're somewhere not yet checked.
- The Claude.ai project the fragments came from has sidebar text reading
  "Projects / Mac Mini" — **still unconfirmed** whether this is the project
  Sheldon calls "AI Build," or a different one. Get this confirmed before
  trusting anything above as complete.

PRIORITY THIS SESSION: no fixed priority carried forward — Aug 22 closed out
both the standing production priority (send-to-inbox, ADR-039 H4) and filed
the governance gap (ADR-042) as a deferred future project. Check IMMEDIATE
TASKS below for what's actually open.

SOURCE OF TRUTH: Disk (`~/openclaw`) + Git are canonical. **GitHub is NOT in
sync** — local `main` is 2 commits ahead of `origin/main` as of the close of
this session (the ADR-014 reconstruction and the fragments archive were
committed after the last push). Confirm current state and push status
yourself, do not trust this number:
    git log -1 --oneline && git status -sb
Live PostgreSQL schema is version 7 (migration_006.sql, `brief_runs` table).
`~/openclaw/CURRENT_STATE.md` was NOT updated on Aug 22 — it's still dated
Aug 20 and does not reflect send-to-inbox or ADR-042. Treat this document and
the Aug 21–23 changelog entries (#020–#023) as more current than
CURRENT_STATE.md until someone refreshes it.

DO THIS FIRST, BEFORE ANY WORK:
  1. Confirm you're in `~/openclaw`, not `~/projects/mac-mini` (see dual-clone
     warning above).
  2. `docker ps` — all four containers up. If the daemon is down, launch
     Docker Desktop and wait for the whale to stop animating.
  3. `openclaw_fastapi` is still running PRE-Aug-22 code (`REQUIRED_SCHEMA_VERSION
     = 6`) against a live DB now at version 7. It logs a harmless warning, not
     a failure — but rebuild when convenient:
       docker compose build fastapi && docker compose up -d fastapi
  4. Export the real Postgres password (Keychain and the container's own env
     var both still hold the stale "changeme" placeholder — unresolved, see
     below):
       export POSTGRES_PASSWORD=$(grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
     Verify with a length check, not by echoing the value.
  5. CHECK COVERAGE BEFORE RUNNING THE GENERATOR:
       docker exec openclaw_postgres psql -U openclaw -d openclaw -c "SELECT max(publication_date), count(*) FROM scraped_content WHERE project = 'federal_policy_brief' AND is_new = TRUE AND publication_date >= CURRENT_DATE - 7;"
     As of the Aug 22 --send run: 44 documents remain is_new = TRUE in the
     7-day window (68 minus the 24 consumed by that send). Newest content was
     Aug 21.

SHIPPED AUG 22 (Entries #020-#023):
- Entry #020: scraper catch-up logic — days_back computed from scraper_runs
  history instead of assumed. Aug 18-21 gap closed, self-healing on future
  outages.
- Entry #021: verify_claims() extended to dates, FR citations, and counts
  (beyond currency). HARD_FAIL_ON_UNVERIFIED switch added (still False).
  Foreign content dropped silently (marker alone, no funding requirement).
  Cross-Program limited to high-signal instruments (proposed/final rules,
  Privacy Act notices, presidential documents) — routine paperwork dropped
  with review-output visibility. ADR-014 OPEN -> RESOLVED (Claude Code Manual
  mode permitted, scoped to ~/openclaw).
- Entry #022: generate_brief_review.py v5. New `--send` flag: self-send SMTP
  via iCloud (smtp.mail.me.com:587, STARTTLS, credentials from Keychain),
  gated on verify_claims() returning zero warnings, flips is_new only after a
  successful send, writes one brief_runs audit row per --send invocation.
  migration_006.sql added the brief_runs table (schema_version 6->7).
  ADR-039 H4 CLOSED — no ESP or purchased sender domain needed; self-send to
  the operator's own inbox is sufficient at this audience size.
  Live-verified end to end: emailed sheldon.wheeler@icloud.com, 24 documents
  marked processed, clean brief_runs row. Also: the dual-clone discovery and
  cleanup (see warning above).
- Entry #023: ADR-042 filed — documents the ADR corpus fragmentation between
  ~/openclaw's local .docx store and the "AI Build" Claude.ai Project.
  Status OPEN, reconciliation explicitly deferred to a future project per
  operator direction.
- Late Aug 22 (no changelog entry — a search session, not a durable system
  change per ADR-031's changelog discipline): ADR-042 fragment hunt across
  Downloads, OneDrive, iCloud Drive, and a Claude.ai project. Produced the
  ADR-014 reconstruction (commit `7558894`), the archived fragments folder
  (commit `aff928a`, see `~/openclaw/adr_fragments_2026-08-22/README.md`),
  and everything summarized in the GOVERNANCE IS FRAGMENTED section above.
  No ADR-042 reconciliation decision was made — this was search, not
  reconciliation.

LIVE-STATE FACTS TO CARRY (do not re-discover these):
- scraped_content is project-scoped: every query MUST filter
  WHERE project = 'federal_policy_brief'.
- brief_runs table exists (migration_006, schema v7). One row so far: Aug 22
  20:39 UTC, 24 docs, verification_status='clean', send_status='sent'.
- is_new=TRUE count in the 7-day window: 44 as of the close of Aug 22 (see
  DO THIS FIRST #5 for the live query).
- raw_content is title + abstract only (~569 chars avg), by design.
- Generator model: gemma4:e4b (llama3.2 is the lightweight fallback).
- generate_brief_review.py is at v5. Default (no flag) is still fully
  review-only and side-effect-free — verified byte-identical to v4 on that
  path. `--send` is new; see Entry #022 above for exactly what it gates on.
- DB PASSWORD: the live openclaw role password is NOT "changeme". Container
  env and Keychain both still hold that stale placeholder — this was known
  on Aug 20 and is STILL not reconciled on Aug 22. The real value is in
  ~/openclaw/.env. Host-run scripts need it exported in EVERY new terminal
  window (see DO THIS FIRST #4). This will keep costing a few minutes of
  confusion at the start of every session until someone actually rotates
  Keychain/container env to match .env, or rotates the DB password itself
  and updates .env — either resolves it, closing this note for good.
- SCRAPER RELIABILITY: nightly scrape is APScheduler inside openclaw_fastapi.
  Catch-up logic (Entry #020) now self-heals gaps regardless of cause
  (Docker down, Mac unplugged, etc.) — this class of problem should no
  longer need manual backfill. Still worth an early `docker ps` check.

IMMEDIATE TASKS (nothing here is production-blocking; send-to-inbox is live):
1. Reconcile stale POSTGRES_PASSWORD in Keychain/container env with the real
   .env value — low urgency (workaround in DO THIS FIRST #4 works fine), but
   it's been sitting open since Aug 20.
2. Rebuild openclaw_fastapi to pick up REQUIRED_SCHEMA_VERSION=7 cleanly (see
   DO THIS FIRST #3) — cosmetic warning only, no rush.
3. Decide the fate of ~/projects/mac-mini (keep for a specific purpose, or
   remove it) — see dual-clone warning above.
4. Flip HARD_FAIL_ON_UNVERIFIED to True once a few more clean --send runs
   build confidence. One switch, one place, top of generate_brief_review.py.
5. Output polish (small, do when convenient, carried over from Aug 20):
   ISO dates in reader-facing prose ("published 2026-08-17" reads as machine
   output); executive summary running long; ORR-under-TANF is a scope
   decision, not a bug.
6. Push to origin — local main is 2 commits ahead as of the close of Aug 22
   (see SOURCE OF TRUTH above). Confirm with the operator before pushing.
7. Fix ~/openclaw/ADR_036.docx — it's plain text with a .docx extension, not
   a real OOXML file (see GOVERNANCE IS FRAGMENTED above). Quick, low-risk,
   independent of the ADR-042 reconciliation project.

HOUSEKEEPING (opportunistic — never ahead of the above):
- ADR-042 reconciliation — explicitly a SEPARATE, DEFERRED future project,
  not opportunistic housekeeping to slot in casually. Needs its own session
  with "AI Build" export/read-access arranged first. Do not start this
  without the operator explicitly scheduling it.
- CURRENT_STATE.md needs refreshing — still dated Aug 20 (see SOURCE OF TRUTH
  above).
- v3.0 instructions refresh (carried over from Aug 20, still not done):
  schema 4->7 (was ->6); "read changelog first"->"read CURRENT_STATE.md
  first" (only once CURRENT_STATE.md is actually refreshed); retire the
  weekly-reupload mandate as load-bearing; ADR-014 OPEN->RESOLVED; note the
  Claude Code Manual-mode exception; note the dual-clone gotcha.
- Rebuild project knowledge as a clean one-way mirror of disk.
- Close ADR-041 as "not needed" if that still holds (unconfirmed — no
  activity on it since May 17).
- Fix Ctrl+C not interrupting in Terminal. Low urgency.

ROLLBACKS AVAILABLE:
- generate_brief_review.py.bak.v4 — the working v4 (pre-v5, review-only,
  no --send, no SMTP, no brief_runs).
- generate_brief_review.py.bak.v3, .bak.v2, .bak.v0 — earlier states, see
  each file's own header comment for what it lacks relative to current.
- changelog.md.bak.session21, changelog.md.bak.pre-entry020.
The scraper has no .bak; recover it from Git if needed
(`git show <commit>:app/scheduling/scrapers/federal_register.py`).
migration_006.sql has already been applied live — do not re-run it; a second
run is a no-op (CREATE TABLE IF NOT EXISTS, ON CONFLICT DO NOTHING) but
confirm schema_version first if in doubt.

WORKING RULES:
- See "WORKING MODE HAS CHANGED" at the top — Claude Code in Manual mode
  works directly (shell, file edits, commits) scoped to ~/openclaw with
  per-action approval. Auto mode and Cowork remain prohibited everywhere.
- A plain Claude Desktop chat session (no Claude Code) still follows the
  pre-ADR-014 rules: MCP filesystem read-only, no shell, files delivered as
  .txt for manual copy, operator does all git commands.
- Token conservation still applies regardless of mode.

PRACTICAL NOTES:
- A code block in chat means "run this" (Claude Code) or "here is what ran"
  (Desktop chat, retrospectively) — don't confuse the two modes' conventions
  mid-session.
- Back up a working file before replacing it: cp file.py file.py.bak.vN.
  Established pattern, kept even though Claude Code can now write files
  directly — the backup is cheap insurance, not a workaround for a
  restriction.
- Prefer an authoritative source over a clever inference. The Aug 22 dual-
  clone discovery was found by diffing and checking `git log`/`git remote
  -v` directly rather than assuming; the ADR-042 inventory was built by
  grepping actual ADR-NNN references rather than guessing which ADRs exist.
  Same principle both times: verify from disk/Git, not from what seems
  likely.
- Every DB-touching command in this document assumes POSTGRES_PASSWORD is
  exported in the current shell (DO THIS FIRST #4) OR routes through
  `docker exec openclaw_postgres psql ...`, which needs no host-side
  password at all.
