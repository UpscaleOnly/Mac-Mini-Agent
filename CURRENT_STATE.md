# OpenClaw — CURRENT STATE

*Read this first, every session. This is the snapshot of where things stand right now.*
*Standing rules and how-to-assist live in the project instructions. Full session-by-session history lives in `changelog.md`.*

**Last updated:** July 5, 2026 (Entry #016 — source-of-truth reconciliation + Bucket 1 rescue)
**Project status:** Paused since mid-May 2026. Last active development was Entry #015 (May 18). The system is dormant but intact. Work is resuming with a cleanup-then-rebalance-toward-production plan.

---

## Source of truth (the core rule)

**Disk (`~/openclaw`) + Git are canonical.** GitHub (`UpscaleOnly/Mac-Mini-Agent`) is in sync as of commit **`f91e931`** (July 5, 2026). Project knowledge is a **one-way mirror** — files flow disk → project knowledge, never the reverse. Memory is never authoritative. If any two sources disagree, **disk wins**.

## Schema

Live PostgreSQL schema is **version 6** (Migration 005 — `scraper_runs` table; ADR-039 H4). Confirmed against the live database July 5, 2026. *(Note: the v2.0 instructions still say "version 4" — that is stale and is corrected in the pending v3.0 refresh.)*

## What's running / operational

- **Docker:** `openclaw_fastapi` (port 8080), `openclaw_postgres` (PostgreSQL 16), `openclaw_chromadb`.
- **Ollama:** native on the host (`host.docker.internal`), model Gemma 4 E4B.
- **Backup automation** (live since May 17): nightly `pg_dump` at 04:00 ET via launchd; 30-day retention; Telegram failure alerts; `pmset` wake at 03:55 ET (AC only).
- **H4 Federal Register scraper:** deployed, APScheduler cron at 01:00 ET. *Overnight-run success (`scraper_runs` table) was never verified before the pause — verify on return.*

## Active task (in order)

1. **[Done July 3]** Bucket 1 rescue — 15 orphaned files recovered to disk + Git.
2. **[Done July 3]** Two-file model — consolidated `changelog.md` + this `CURRENT_STATE.md`.
3. **[Next]** Rebuild project knowledge as a clean one-way mirror of disk (retire orphans/duplicates).
4. **[Then]** Rebalance governance vs. production — lean toward shipping `federal_policy_brief`.

## Top open items

- **`federal_policy_brief` delivery is BLOCKED** on two ADR-039 decisions: **email provider** (SES vs Postmark vs Mailgun) and **sender domain** purchase. This is the gate to shipping the flagship.
- **PostgreSQL password rotation** — still the default placeholder.
- **ADR-041** (third-party memory injection) — decision deadline was May 31; unresolved at pause. With disk+Git+mirror now working, memory is no longer load-bearing, so this is likely closable as "not needed."
- **ADR-014** (shell/Docker guardrails) — operative rule in force; formal ADR closure still pending.
- **v3.0 instructions refresh** — correct schema 4 → 6; relax the weekly-reupload mandate; point session-start here.
- **Disk cleanup** (Bucket 4) — `.bak` files and `old_skeleton/`; housekeeping only.

## Hard rules (safety quick-reference — full versions in instructions)

- **No shell/bash/host commands** from any agent or LLM path on the Mac (ADR-014). Operator runs all host commands manually.
- **One command at a time**, with a plain-English explanation. Never multi-step command blocks.
- **Never** use `nano`, `vim`, or any interactive terminal editor (freezes the terminal).
- **`.py` files delivered through chat come as `.txt`**, renamed on disk.
- **`git commit` always with `-m` inline** — never a bare `git commit` (it opens an editor).
- **Token conservation**; **approve before building**.
- **Verify live state** (schema, files, config) before generating code or migrations.

## Recent history (most recent first)

- **Entry #016 (Jul 5):** Found bidirectional disk↔project-knowledge drift; rescued 15 sole-copy files (5 ADRs, migration_003, 6 federal_policy_brief docs, hardware trio) to disk + Git (`f91e931`). Established disk+Git as single source of truth. Confirmed schema v6.
- **Entry #015 (May 18):** v2.0 instructions rewrite; memory-defect session-startup protocol.
- **Entry #014 (May 17):** Anthropic memory ticket filed; ADR-041 created.
- **Entry #013 and earlier:** see `changelog.md`.

---

*Sheldon Wheeler — OpenClaw Personal Stack — CURRENT_STATE.md — maintained at each session close.*
