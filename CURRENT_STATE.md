# OpenClaw — CURRENT STATE

*Read this first, every session. This is the snapshot of where things stand right now.*
*Standing rules and how-to-assist live in the project instructions. Full session-by-session history lives in `changelog.md`.*

**Last updated:** August 23, 2026 (Entry #024 — ADR corpus reconciliation; nightly-scrape misfire fix)
**Project status:** **Active, production-first.** The federal_policy_brief pipeline generates *and delivers* briefs end to end. Governance and housekeeping are opportunistic and do not block shipping.

---

## Source of truth (the core rule)

**Disk (`~/openclaw`) + Git are canonical.** Project knowledge is a **one-way mirror** — files flow disk → project knowledge, never the reverse — and is **lagging; a clean rebuild is still pending**. Memory is never authoritative. If any two sources disagree, **disk wins**.

Confirm sync yourself rather than trusting a hash written here:

```
git log -1 --oneline && git status -sb
```

**Check your working directory before anything else.** `~/openclaw` is now the **only** clone on this machine — the stale second clone at `~/projects/mac-mini` was deleted August 23, 2026 (it had derailed two sessions; verified to hold nothing unique first). Keep running the check anyway, as cheap insurance against a stray clone reappearing:

```
pwd && git remote -v
```

Must show `~/openclaw` and `git@github.com:UpscaleOnly/Mac-Mini-Agent.git` (SSH).

## Schema

Live PostgreSQL schema is **version 7** (`migration_006.sql` — `brief_runs` table; ADR-039 H4 send-wiring). `openclaw_fastapi` was rebuilt August 23 and now logs `Schema version OK — live database is at version 7 (required 7)`; the long-standing version-6 startup warning is gone. *(The v2.0 instructions still say "version 4" — stale, corrected in the pending v3.0 refresh.)*

## What's running / operational

- **Docker:** four containers — `openclaw_fastapi` (port 8080), `openclaw_postgres` (PostgreSQL 16), `openclaw_chromadb`, `openclaw_telegram`.
- **Ollama:** native on the host (`host.docker.internal`), model **`gemma4:e4b`** (`llama3.2` is the lightweight fallback).
- **Backup automation** (live since May 17): nightly `pg_dump` at 04:00 ET via launchd; 30-day retention; Telegram failure alerts; `pmset` repeating wake at 03:55 ET (AC only).
- **Federal Register scraper:** APScheduler cron nominally **01:00 ET**, running **inside `openclaw_fastapi`**. As of August 23 its `misfire_grace_time` is **11100s (3h05m)** with `coalesce=True`, so a run missed because the Mac was asleep at 01:00 now **fires on the 03:55 ET wake instead of being discarded**. See the scraper-reliability item below for why. **Empirical confirmation is still pending** — the fix has not yet survived a real overnight cycle.

## Content state (`scraped_content`)

- Coverage **April 24 → August 21, 2026**, all `project = 'federal_policy_brief'`. **283 rows total: 259 `is_new = TRUE`, 24 consumed** by the August 22 send.
- **Every query MUST filter `WHERE project = 'federal_policy_brief'`** — the table is project-scoped.
- `content_type` distribution: **`notice` 231, `final_rule` 28, `proposed_rule` 24.**
- `raw_content` is **title + abstract only** (~569 chars avg). Brief depth is abstract-level by design of the current scraper.
- ⚠️ **Unbackfilled historical gap: August 4–16, 2026.** Only Aug 3 (23 docs) and Aug 17 (21 docs) exist in that span — roughly **nine missing weekdays**. This is *larger* than the "Aug 9–16" previously recorded here; corrected August 23 against the live table. It predates the Entry #020 catch-up logic, so it was never self-healed and **will not heal on its own** — the catch-up window computes from the last successful run, which has since moved well past it. Recoverable only by an explicit backfill.
- The Aug 18–21 gap **is closed** (8/13/18/8 docs on those dates) — catch-up logic worked as designed.
- No content is expected for Saturdays or Sundays; the Federal Register does not publish weekends. A "stale" latest-date of Friday on a Sunday is correct, not a fault.
- **An empty 7-day window means the scraper has not run — it does not mean the generator is broken.** Fix the scraper; never raise `WINDOW_DAYS` to compensate.

## federal_policy_brief — where the generator stands

`~/openclaw/generate_brief_review.py` is at **v5**. Rollbacks preserved: `.bak.v4`, `.bak.v3`, `.bak.v2`, `.bak.v0`.

**Default mode (no flags) remains review-only and side-effect-free** — sends nothing, marks nothing processed, writes no `brief_runs` row, safe to re-run indefinitely. Verified byte-identical to v4 on that path.

**`--send` (new in v5)** additionally emails the brief, flips `is_new = FALSE` on consumed rows, and writes one `brief_runs` audit row:

- Self-send SMTP via `smtp.mail.me.com:587`, STARTTLS, credentials from macOS Keychain at send time — never through a chat session. No ESP, no purchased sender domain (ADR-039 H4 sub-decision: unnecessary at an audience of one).
- **Gated on `verify_claims()` returning zero warnings.** An unverified claim blocks the email entirely — independent of the `HARD_FAIL_ON_UNVERIFIED` switch, which governs only review-mode print-vs-abort.
- `is_new` flips **only after a successful send**, so a failed send leaves rows eligible for retry rather than silently dropping them.

`HARD_FAIL_ON_UNVERIFIED` is still **`False`** (line ~195) — flip to `True` once a few more clean `--send` runs build confidence.

**Live-verified end to end (Aug 22):** 24 documents emailed to `sheldon.wheeler@icloud.com`, verification `clean`, one clean `brief_runs` row. That remains the only send to date.

## Active task (in order)

1. **[Next]** Confirm the scrape misfire fix actually fired overnight — check `scraper_runs` for a run dated the 24th, then `docker logs openclaw_fastapi | grep -i misfire`.
2. **[Then]** Backfill the August 4–16 content gap (explicit `days_back`, or a targeted Federal Register API pull).
3. **[Then]** Flip `HARD_FAIL_ON_UNVERIFIED` to `True` after a few more clean `--send` runs.
4. **[Then]** Output polish: ISO dates in reader-facing prose; executive summary running long; ORR-under-TANF routing (a scope decision, not a bug).
5. **[Opportunistic]** Rebuild project knowledge as a clean one-way mirror of disk. *(v3.0 instructions refresh — DONE Aug 23.)*

## Top open items

- **Scraper reliability — MEDIUM (was HIGH; two fixes now in place, neither fully proven).** Root cause of the recurring gaps was finally isolated August 23: the 01:00 ET job carried a **10-minute** misfire grace, the Mac sleeps overnight, and the only repeating `pmset` wake is 03:55 ET — so on any night the machine slept, the run was **silently skipped, not delayed**. Confirmed against `scraper_runs` history and `pmset -g log` (DarkWake from Deep Idle through 01:00). macOS permits exactly **one** repeating power-on event, so a second wake at 00:55 is unavailable without sacrificing the backup's 03:55 wake — the grace window was widened to 3h05m instead. Entry #020's catch-up logic and this fix are complementary: catch-up backfills content once a run fires, this ensures a run actually fires. **Neither has yet been proven across a real overnight cycle.**
- **PostgreSQL credential reconciliation — open since Aug 20.** The live `openclaw` role password is **NOT** the `changeme` placeholder. The real value lives in `~/openclaw/.env`; container env and Keychain both still hold the stale placeholder. *Read it without echoing it:* `export POSTGRES_PASSWORD=$(grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)` — needed in every new Terminal window for host-run scripts. Verify with a length check, not by printing. Anything routed through `docker exec openclaw_postgres psql ...` needs no host-side password at all.
- **Dual-clone — RESOLVED August 23, 2026.** `~/projects/mac-mini` deleted after verification that it held nothing unique (clean tree, no stashes, no local-only branches, no unpushed commits, no files deleted upstream since its `fa80ac8` HEAD). Its one irreplaceable item — an accumulated 91-rule Claude Code permission allowlist — was migrated to `~/openclaw/.claude/settings.local.json` first (six dead rules pointing at the old path were dropped; that file is covered by the global gitignore, so it is **not** in version control and will not survive a fresh machine setup). The now-empty `~/projects` directory was left in place.
- **ADR corpus — materially improved Aug 23, not finished.** 25 ADR `.docx` files now on disk, up from 12. Five files that were plain text mis-saved with a `.docx` extension (033–037) are now real OOXML; ADR-032 was identified and promoted; twelve partial-recovery ADRs now have explicit **stub** documents (clearly marked as stubs, with per-claim sourcing). **Still unrecovered: ADR-017 and ADR-022** (both cited in live code, zero content found anywhere). No evidence at all for ADR-001, 004, 006–013, 015, 016. Full picture: `adr_fragments_2026-08-22/reconciliation_2026-08-23/`.
- **ADR-042 (ADR corpus reconciliation) — OPEN, still deferred.** Amended Aug 23 to correct a factual error: it had attributed the missing ADRs to a Claude.ai project called "AI Build." That project was captured directly and proved unrelated (dormant pre-prototype SaaS concept, no ADR-NNN documents). The real counterpart is the **"Mac Mini"** project. Full reconciliation remains a dedicated future project — do not start it casually.
- **Two Claude.ai projects share the "OpenClaw" working name** — "Mac Mini" (this system) and "AI Build" (an unrelated pre-prototype SaaS concept). This collision has already caused one documented misattribution. Consider renaming one.
- **ORR routes to TANF** — the Burke Law Group withdrawal is an Office of Refugee Resettlement notice, routed to TANF because both sit under the Children and Families Administration. Fixing it means deciding where ORR content belongs. Scope decision, not a defect.
- **ADR-041** (third-party memory injection) — trigger was "Anthropic response to ticket 215474340039847 **or** May 31, 2026, whichever first." The date has long passed and the operator has confirmed the ticket was never resolved and is **not worth chasing**. ADR-041 remains formally OPEN; closing it as "not needed" is a one-line decision whenever convenient.
- **Instructions — v3.0 DEPLOYED August 23, 2026.** Replaces v2.0 (May 18). Source of record on disk: `~/openclaw/instructions_v3.0.md` — keep that file and the live claude.ai panel in step; if they diverge, the disk copy is canonical. Most important change: v2.0's blanket "no shell/bash from any agent path" rule is replaced with the surface-dependent ADR-014 boundary (Claude Code Manual mode may run shell/edit/commit scoped to `~/openclaw`; Auto and Cowork prohibited; Desktop chat unchanged). Also corrected schema 4 → 7, three containers → four, "39+ ADRs" → 001–042, "governance precedes features" → "governance serves shipping", session-start pointer → this file, and retired the weekly-reupload mandate as load-bearing. **Two items deliberately left open inside v3.0:** the target production machine is recorded inconsistently across sources (v2.0 said "Mac Studio M5", project memory said "M4 Mac Mini 32GB / possibly the M5 Mini") and needs settling once; and v3.0 runs ~65% longer than v2.0 (2,478 vs 1,502 words), a standing token cost on every conversation — trim if it starts to bite.
- **Project-knowledge rebuild** — clean one-way mirror of disk, including this file. Now further out of date: Aug 23 added 13 ADR documents, fixed 5, amended 1.
- **The context ceiling — RESOLVED, but remember why.** Ollama defaulted `gemma4:e4b` to **4096 tokens for prompt and response combined**. A 19-document section overran it: earliest documents fell out unseen, response truncated mid-sentence. Entry #018 recorded these symptoms as "oversized section degradation" and proposed significance-ranking. That diagnosis was wrong — it was a config default. `NUM_CTX = 8192` now. Ranking may still be wanted editorially, but do not build it as a fix for truncation. Watch `NUM_CTX` if `WINDOW_DAYS` ever rises.
- **Ctrl+C does not interrupt in Terminal** — dead for months. Low urgency.
- **Disk cleanup** (Bucket 4) — `.bak` files (now including `.bak.plaintext-format`, `.bak.pre-amendment-2026-08-23`, `.bak.pre-misfire-fix`, `.bak.aug20`) and `old_skeleton/`. `old_skeleton/` is untracked dead code that still carries the only references to ADR-011, 012, and 016 — read before deleting.

## Hard rules (safety quick-reference — full versions in instructions)

⚠️ **ADR-014 changed on August 22 — the old "no shell, ever" rule is no longer accurate for Claude Code.**

- **Claude Code in Manual permission mode MAY** run shell commands, edit files directly, and commit to Git — **scoped to `~/openclaw`**, with per-action operator approval. **Auto mode is never used. Cowork is never used.** (ADR-014, RESOLVED; reconstructed document at `~/openclaw/ADR_014.docx`, provenance in its Section 6.)
- **A plain Claude Desktop chat session still follows the pre-ADR-014 rules:** MCP filesystem read-only, no shell, `.py` files delivered as `.txt` for manual copy, operator runs all git commands.
- **A code block in chat means "run this"** (Claude Code) or "here is what ran" (Desktop chat, retrospectively). Don't mix the two conventions mid-session.
- **Never** use `nano`, `vim`, or any interactive terminal editor (freezes the terminal).
- **Back up before replacing a working file** — `cp file.py file.py.bak.vN`. Kept even though Claude Code can now write directly; the backup is cheap insurance, not a workaround.
- **`git commit` always with `-m` inline** — never a bare `git commit`.
- **`git push` is gated** by the Claude Code permission classifier and will be refused even when explicitly requested. Either the operator runs it, or a `Bash(git push:*)` allow rule is added to settings.
- **Token conservation**; **approve before building**.
- **Verify live state** (schema, files, config) before generating code or migrations. **Prefer an authoritative source over a clever inference** — this has paid off repeatedly: the dual clone was caught by `git remote -v` rather than assumption; the scrape misfire was proven from `pmset -g log` rather than inferred from correlation; the Aug 4–16 gap turned out larger than the doc claimed once queried directly.

## Recent history (most recent first)

- **Entry #024 (Aug 23):** ADR corpus reconciliation Phase 0 plus operator-directed execution. Captured the "AI Build" project and proved it distinct from "Mac Mini," correcting ADR-042's misattribution via a dated amendment. Fixed five ADR files that were plain text mis-saved as `.docx` (033–037). Promoted the NIST document to `ADR_032.docx`. Built twelve explicitly-marked stub ADRs. Found real substance for ADR-018 (0–100 `irreversibility_score` scale) and a fragment for ADR-022. Separately: isolated and fixed the silently-skipped nightly scrape (misfire grace 600s → 11100s) and rebuilt `fastapi` to schema v7. Commits `918b70e`, `7d3e863`, `5e8fafc`.
- **Entry #023 (Aug 22):** ADR-042 filed — ADR corpus fragmentation documented, status OPEN, reconciliation explicitly deferred. Commit `b27beb4`.
- **Entry #022 (Aug 22):** Generator v5 — `--send` flag, iCloud self-send SMTP, verification gating, `brief_runs` audit table (`migration_006.sql`, schema 6 → 7). **ADR-039 H4 CLOSED.** Live-verified: 24 documents emailed, clean audit row. Also the dual-clone discovery and cleanup. Commit `a6b16f7`.
- **Entry #021 (Aug 22):** `verify_claims()` extended beyond currency to dates, Federal Register citations, and counts. `HARD_FAIL_ON_UNVERIFIED` switch added (still `False`). Foreign content dropped on marker alone. Cross-Program limited to high-signal instruments (57 → 17 docs), resolving a recurring context-window overrun. **ADR-014 OPEN → RESOLVED.** Commits `b0000ce`, `fa80ac8`.
- **Entry #020 (Aug 21):** Scraper catch-up logic — `days_back` computed from `scraper_runs` history with a one-day safety buffer and 30-day cap, instead of assumed. Closed the Aug 18–21 gap.
- **Entry #019 (Aug 20):** Scraper `TYPE_MAP` fixed; 15 rows relabeled `proposed_rule`. `WINDOW_DAYS` → 7. Found the Ollama 4096-token context ceiling. Caught a **fabricated $105M total**. Generator v3.
- **Entry #018 and earlier:** see `changelog.md`.

---

*Sheldon Wheeler — OpenClaw Personal Stack — CURRENT_STATE.md — maintained at each session close.*
