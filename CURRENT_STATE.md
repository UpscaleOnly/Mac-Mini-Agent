# OpenClaw — CURRENT STATE

*Read this first, every session. This is the snapshot of where things stand right now.*
*Standing rules and how-to-assist live in the project instructions. Full session-by-session history lives in `changelog.md`.*

**Last updated:** August 16, 2026 (Entry #018 — brief-generator v2: instrument fidelity, sub-agency mapping, plain-text enforcement)
**Project status:** **Active, production-first.** The federal_policy_brief generator produces readable output against live data. Governance and housekeeping are opportunistic and do not block shipping.

---

## Source of truth (the core rule)

**Disk (`~/openclaw`) + Git are canonical.** GitHub (`UpscaleOnly/Mac-Mini-Agent`) is in sync as of commit **`8aa21ed`** (August 16, 2026). Project knowledge is a **one-way mirror** — files flow disk → project knowledge, never the reverse — and is currently **lagging; a clean rebuild is still pending**. Memory is never authoritative. If any two sources disagree, **disk wins**.

## Schema

Live PostgreSQL schema is **version 6** (Migration 005 — `scraper_runs` table; ADR-039 H4). Confirmed against the live database July 5, 2026. *(The v2.0 instructions still say "version 4" — stale, corrected in the pending v3.0 refresh.)*

## What's running / operational

- **Docker:** four containers — `openclaw_fastapi` (port 8080), `openclaw_postgres` (PostgreSQL 16), `openclaw_chromadb`, `openclaw_telegram`.
- **Ollama:** native on the host (`host.docker.internal`), model **`gemma4:e4b`** (`llama3.2` is the lightweight fallback).
- **Backup automation** (live since May 17): nightly `pg_dump` at 04:00 ET via launchd; 30-day retention; Telegram failure alerts; `pmset` wake at 03:55 ET (AC only).
- **Federal Register scraper:** APScheduler cron at 01:00 ET, running **inside `openclaw_fastapi`**. ⚠️ **This means Docker Desktop must be running or the nightly scrape silently does not happen.** That is exactly what the August 9–16 gap was — host downtime, not scraper failure.

## Content state (`scraped_content`)

- Continuous coverage **April 24 → August 3, 2026**, all `project = 'federal_policy_brief'`.
- **Every query MUST filter `WHERE project = 'federal_policy_brief'`** — the table is project-scoped.
- All banked rows remain `is_new = TRUE`; nothing has been consumed. A 48-day window returns 108 documents; a 20-day window returns 61.
- `raw_content` is **title + abstract only** (~569 chars avg). Brief depth is abstract-level by design of the current scraper — right for a "what published" briefing, not deep analysis.
- ⚠️ **`content_type` is unreliable for proposed rules** — see the `TYPE_MAP` defect under open items. No row anywhere is labeled `proposed_rule`.

## federal_policy_brief — where the generator stands

`~/openclaw/generate_brief_review.py` is at **v2**, review-only: sends nothing, marks nothing processed, writes no `brief_runs` row, safe to re-run. v0 is preserved at `generate_brief_review.py.bak.v0`.

Working as of Entry #018:

- Program areas route on **sub-agency only** (FNS → SNAP; ACF → TANF; CMS → "CMS (Medicaid/CHIP/Medicare)"; everything else → Cross-Program). The parent department never routes.
- Instrument type comes from `scraped_content.content_type`, refined for notices by title keyword.
- Plain-text output enforced twice: system-prompt mandate plus `to_plain_text()`, a deterministic scrubber for markdown, tables and emoji.
- Executive summary receives a compressed inventory (per-area counts + high-signal items only), producing a single 4–6 sentence paragraph.

⚠️ **`WINDOW_DAYS` is currently `20`** — a temporary value for validation. **Return it to `7` before send wiring.**

## Active task (in order)

1. **[Next]** Fix scraper `TYPE_MAP`; backfill mislabeled `content_type` rows.
2. **[Then]** Cap or rank documents per section; stop `docs_block` index numbers leaking into prose.
3. **[Then]** Return `WINDOW_DAYS` to 7; confirm a clean small-window run.
4. **[Then]** Wire send-to-inbox — delivery mechanism + `brief_runs` logging + `is_new` flip.
5. **[Opportunistic]** v3.0 instructions refresh; rebuild project knowledge as a clean one-way mirror of disk.

## Top open items

- **Scraper `TYPE_MAP` defect — HIGH.** In `app/scheduling/scrapers/federal_register.py`, `TYPE_MAP` is keyed on the Federal Register API's *query-filter* codes (`PRORULE`, `PRESDOCU`) but applied to its *returned display strings* (`"Proposed Rule"`, `"Presidential Document"`). `"RULE"` and `"NOTICE"` match by coincidence; the other two fall through to `'other'`. **Every proposed rule in the database is stored as `'other'`** and briefs as "a document." Fix accepts both forms; pair with a one-time backfill `UPDATE`.
- **Oversized sections degrade output — MEDIUM.** Cross-Program at 51+ documents abandons prose for outlines and tables, covers a fraction of its inputs, and leaks internal `[n]` index references into reader-facing text. Unlikely at `WINDOW_DAYS = 7`, but unfixed.
- **`federal_policy_brief` delivery is BLOCKED** on two ADR-039 decisions: **email provider** (SES vs Postmark vs Mailgun) and **sender domain** purchase. This is the gate to shipping the flagship.
- **PostgreSQL credential reconciliation** — the live `openclaw` role password is **NOT** the `changeme` placeholder (corrected in Entry #017). The real value lives in `~/openclaw/.env`; the container env and Keychain both still hold the stale placeholder. Host-run scripts need `export POSTGRES_PASSWORD='<value>'` in **every new Terminal window**. Rotation still open. *(The value appeared in an assistant chat transcript on Aug 16 — no new exposure, Postgres is localhost behind Tailscale, but it reinforces the rotation item.)*
- **ADR-041** (third-party memory injection) — decision deadline was May 31; unresolved. With disk+Git working, memory is no longer load-bearing, so this is likely closable as "not needed."
- **ADR-014** (shell/Docker guardrails) — operative rule in force; formal ADR closure still pending.
- **v3.0 instructions refresh** — schema 4 → 6; "read changelog first" → "read CURRENT_STATE.md first"; "governance precedes features" → "governance serves shipping"; retire the weekly-reupload mandate as load-bearing; 39+ → 41+ ADRs; ADR-014 OPEN → operative.
- **Project-knowledge rebuild** — clean one-way mirror of disk, including this file.
- **Ctrl+C does not interrupt in Terminal** — dead for months. Materially felt on Aug 16: a 20-minute Gemma run with no abort short of closing the window.
- **Disk cleanup** (Bucket 4) — `.bak` files and `old_skeleton/`; housekeeping only.

## Hard rules (safety quick-reference — full versions in instructions)

- **No shell/bash/host commands** from any agent or LLM path on the Mac (ADR-014). Operator runs all host commands manually.
- **One command at a time**, with a plain-English explanation. Never multi-step command blocks.
- **Never** use `nano`, `vim`, or any interactive terminal editor (freezes the terminal).
- **`.py` files delivered through chat come as `.txt`**, renamed on disk. *(Watch for browser download collisions — a repeat download becomes `name_1.txt`; verify the filename before `cp`. `cp source.txt dest.py` renames in one step, so no Finder rename is needed.)*
- **`git commit` always with `-m` inline** — never a bare `git commit` (it opens an editor). Multiple `-m` flags are safe for trailers.
- **Token conservation**; **approve before building**.
- **Verify live state** (schema, files, config) before generating code or migrations.
- **Folder-bridge access pattern (new, Aug 16):** the Claude desktop app can be granted read access to `~/openclaw` for file inspection and verification. This is file transfer, not host command execution — ADR-014 is untouched. Write access has been declined; all disk writes are performed by operator-run commands.

## Recent history (most recent first)

- **Entry #018 (Aug 16):** Brief generator v0 → v2. Fixed both Entry #017 flaws — sub-agency program mapping (SNAP 10 → 4 documents; TANF populated for the first time) and instrument-type fidelity (reads `content_type`; the CMS–VA matching notice now briefs correctly). CMS section renamed to acknowledge it holds Medicare authorities. Repaired two regressions v1 introduced: a 50-line emoji-headed executive summary and markdown contamination. Discovered the scraper `TYPE_MAP` defect and the Docker-downtime scraper gap. Committed `8aa21ed`.
- **Entry #017 (Jul 6):** First working end-to-end brief pipeline (`generate_brief_review.py` v0, review-only). Dormancy question closed — scraper had run autonomously. Live-state corrections: `project` scoping, `scraper_run_id`, abstract-only `raw_content`, real Postgres password ≠ placeholder. Two output flaws identified. Committed `20d4951`.
- **Entry #016 (Jul 5):** Found bidirectional disk↔project-knowledge drift; rescued 15 sole-copy files to disk + Git (`f91e931`). Established disk+Git as single source of truth. Confirmed schema v6.
- **Entry #015 (May 18):** v2.0 instructions rewrite; memory-defect session-startup protocol.
- **Entry #014 and earlier:** see `changelog.md`.

---

*Sheldon Wheeler — OpenClaw Personal Stack — CURRENT_STATE.md — maintained at each session close.*
