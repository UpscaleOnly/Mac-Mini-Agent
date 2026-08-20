# OpenClaw — CURRENT STATE

*Read this first, every session. This is the snapshot of where things stand right now.*
*Standing rules and how-to-assist live in the project instructions. Full session-by-session history lives in `changelog.md`.*

**Last updated:** August 20, 2026 (Entry #019 — scraper TYPE_MAP fixed, context ceiling found, brief-generator v3)
**Project status:** **Active, production-first.** The federal_policy_brief generator produces clean, readable output against live data. Governance and housekeeping are opportunistic and do not block shipping.

---

## Source of truth (the core rule)

**Disk (`~/openclaw`) + Git are canonical.** GitHub (`UpscaleOnly/Mac-Mini-Agent`) is in sync as of commit **`cb03e58`** (August 20, 2026). Project knowledge is a **one-way mirror** — files flow disk → project knowledge, never the reverse — and is currently **lagging; a clean rebuild is still pending**. Memory is never authoritative. If any two sources disagree, **disk wins**.

## Schema

Live PostgreSQL schema is **version 6** (Migration 005 — `scraper_runs` table; ADR-039 H4). Confirmed against the live database again August 20, 2026 on container startup. *(The v2.0 instructions still say "version 4" — stale, corrected in the pending v3.0 refresh.)*

## What's running / operational

- **Docker:** four containers — `openclaw_fastapi` (port 8080), `openclaw_postgres` (PostgreSQL 16), `openclaw_chromadb`, `openclaw_telegram`.
- **Ollama:** native on the host (`host.docker.internal`), model **`gemma4:e4b`** (`llama3.2` is the lightweight fallback).
- **Backup automation** (live since May 17): nightly `pg_dump` at 04:00 ET via launchd; 30-day retention; Telegram failure alerts; `pmset` wake at 03:55 ET (AC only).
- **Federal Register scraper:** APScheduler cron at 01:00 ET, running **inside `openclaw_fastapi`**. ⚠️ **The Mac must be awake AND powered AND logged in, with Docker Desktop running, or the scrape silently does not happen.** See the scraper-reliability item below — this has now caused two data gaps.

## Content state (`scraped_content`)

- Coverage **April 24 → August 17, 2026**, all `project = 'federal_policy_brief'`.
- ⚠️ **Gap: August 18–20** — the MacBook Air was unplugged and ran the battery flat. Not backfilled.
- **Every query MUST filter `WHERE project = 'federal_policy_brief'`** — the table is project-scoped.
- All banked rows remain `is_new = TRUE`; nothing has been consumed.
- `content_type` distribution: **`notice` 195, `final_rule` 26, `proposed_rule` 15, `other` 0.**
- `raw_content` is **title + abstract only** (~569 chars avg). Brief depth is abstract-level by design of the current scraper.
- A 7-day window (as of Aug 20) returns 21 documents, all dated Aug 17.

## federal_policy_brief — where the generator stands

`~/openclaw/generate_brief_review.py` is at **v3**, review-only: sends nothing, marks nothing processed, writes no `brief_runs` row, safe to re-run. v0 preserved at `.bak.v0`, v2 at `.bak.v2`.

Working as of Entry #019:

- `WINDOW_DAYS = 7` — production value.
- `NUM_CTX = 8192` passed to Ollama. **This matters more than it looks** — see the context-ceiling note below.
- Program areas route on **sub-agency only** (FNS → SNAP; ACF → TANF; CMS → "CMS (Medicaid/CHIP/Medicare)"; everything else → Cross-Program).
- Instrument type comes from `scraped_content.content_type`, refined for notices by title keyword. Proposed rules now label correctly.
- Plain text enforced twice: system-prompt mandate plus `to_plain_text()`.
- **Arithmetic forbidden** in the system prompt, plus `verify_figures()` checking every currency amount in generated prose against source.
- **Foreign-recipient funding notices suppressed**, with an audit list printed above the brief.

Last run: 21 documents in, 3 suppressed, 18 briefed, Cross-Program 16. Clean output.

## Active task (in order)

1. **[Next]** Extend fabrication verification beyond currency — dates, FR citations, counts. **This is the gate on send-wiring.**
2. **[Then]** Scraper catch-up logic — `days_back` from the last successful `scraper_runs` row.
3. **[Then]** Output polish: ISO dates in prose; the one dropped FDA notice; ORR-to-TANF routing.
4. **[Then]** Wire send-to-inbox — delivery mechanism + `brief_runs` logging + `is_new` flip. **Also make an unverified figure hard-fail the run.**
5. **[Opportunistic]** v3.0 instructions refresh; rebuild project knowledge as a clean one-way mirror of disk.

## Top open items

- **Fabrication verification is incomplete — HIGH.** On August 20 Gemma reported three CDC awards ($15M + $30M + $30M = $75M) as *"totaling approximately $105 million"* — a total stated in no source and wrong by 40%. `verify_figures()` now catches invented currency, but **it has not yet fired on a live run** (the documents carrying dollar figures were the suppressed ones), and **it checks currency only**. A fabricated date or FR citation is equally damaging and nothing catches one. While the script is review-only an unverified figure is a warning; before send-wiring it must abort the run.
- **Scraper reliability — HIGH.** Two data gaps now (Aug 9–16, Aug 18–20). The second was a **flat battery**, i.e. a cold power-off, so no `pmset` wake schedule addresses it — `wakepoweron` fires only on AC, and a cold boot does not restore containers until someone logs in. macOS also permits only **one** repeating power event, so a 00:55 wake would displace the 03:55 backup wake. **The durable fix is catch-up logic**, not a wake schedule: compute `days_back` from the last successful `scraper_runs` entry so any outage self-heals on the next run.
- **The context ceiling — RESOLVED, but remember why.** Ollama defaulted `gemma4:e4b` to **4096 tokens for prompt and response combined**. A 19-document section overran it: earliest documents fell out unseen, response truncated mid-sentence. Entry #018 recorded these symptoms at 51 documents as "oversized section degradation" and proposed a significance-ranking system. That diagnosis was wrong — it was a config default. Ranking may still be wanted editorially, but do not build it as a fix for truncation. Watch `NUM_CTX` if `WINDOW_DAYS` ever rises.
- **`federal_policy_brief` delivery is BLOCKED** on two ADR-039 decisions: **email provider** (SES vs Postmark vs Mailgun) and **sender domain** purchase.
- **PostgreSQL credential reconciliation** — the live `openclaw` role password is **NOT** the `changeme` placeholder. The real value lives in `~/openclaw/.env`; container env and Keychain both still hold the stale placeholder. Rotation still open. *Read it without echoing it:* `export POSTGRES_PASSWORD=$(grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)` — needed in every new Terminal window for host-run scripts. Verify with `python3 -c 'import os;print(len(os.environ.get("POSTGRES_PASSWORD","")))'` rather than printing the value.
- **ORR routes to TANF** — the Burke Law Group withdrawal is an Office of Refugee Resettlement notice, routed to TANF because both sit under the Children and Families Administration. Fixing it means deciding where ORR content belongs.
- **ADR-041** (third-party memory injection) — decision deadline was May 31; unresolved. With disk+Git working, likely closable as "not needed."
- **ADR-014** (shell/Docker guardrails) — operative rule in force; formal closure still pending.
- **v3.0 instructions refresh** — schema 4 → 6; "read changelog first" → "read CURRENT_STATE.md first"; "governance precedes features" → "governance serves shipping"; retire the weekly-reupload mandate as load-bearing; 39+ → 41+ ADRs; ADR-014 OPEN → operative.
- **Project-knowledge rebuild** — clean one-way mirror of disk, including this file.
- **Ctrl+C does not interrupt in Terminal** — dead for months. Less painful now that a 7-day run takes about a minute rather than twenty.
- **Disk cleanup** (Bucket 4) — `.bak` files and `old_skeleton/`; housekeeping only.

## Hard rules (safety quick-reference — full versions in instructions)

- **No shell/bash/host commands** from any agent or LLM path on the Mac (ADR-014). Operator runs all host commands manually.
- **One command at a time**, with a plain-English explanation. Never multi-step command blocks.
- **A code block in chat means "run this."** Illustrative code, mappings and file excerpts go in prose — pasting them into zsh produces `command not found` noise.
- **Never** use `nano`, `vim`, or any interactive terminal editor (freezes the terminal).
- **`.py` files delivered through chat come as `.txt`**, renamed on disk. Verify the download before copying — a repeat download becomes `name_1.txt`. `cp source.txt dest.py` renames in one step. *(A byte-count mismatch of one or two is usually characters vs bytes in a UTF-8 file, not corruption — diff before worrying.)*
- **Back up before replacing a working file** — `cp file.py file.py.bak.vN`.
- **`git commit` always with `-m` inline** — never a bare `git commit`.
- **Token conservation**; **approve before building**.
- **Verify live state** (schema, files, config) before generating code or migrations. Prefer an authoritative source over inference — the 15-row backfill was confirmed against the Federal Register API rather than deduced from what could have gotten in.
- **Folder-bridge access pattern:** the Claude desktop app can be granted read access to `~/openclaw` for file inspection and verification. This is file transfer, not host command execution — ADR-014 is untouched. Write access has been declined; all disk writes are performed by operator-run commands. Reading a file back off disk after every install caught nothing this session, which is the point — it made each step verifiable rather than assumed.

## Recent history (most recent first)

- **Entry #019 (Aug 20):** Scraper `TYPE_MAP` fixed (accepts both API vocabularies, warns on unknown); 15 banked rows relabeled `proposed_rule` after verification against the Federal Register API. `WINDOW_DAYS` → 7. Found the Ollama 4096-token context ceiling causing truncation and dropped documents — reframes Entry #018's "oversized section" diagnosis. Found and guarded a **fabricated $105M total**. Suppressed foreign-recipient funding notices. Generator at v3. Commits `638cad7`, `cb03e58`.
- **Entry #018 (Aug 16):** Brief generator v0 → v2. Sub-agency program mapping (SNAP 10 → 4; TANF populated for the first time) and instrument-type fidelity. Repaired two v1 regressions. Discovered the scraper `TYPE_MAP` defect and the Docker-downtime scraper gap. Committed `8aa21ed`.
- **Entry #017 (Jul 6):** First working end-to-end brief pipeline (v0, review-only). Live-state corrections: `project` scoping, abstract-only `raw_content`, real Postgres password ≠ placeholder. Committed `20d4951`.
- **Entry #016 (Jul 5):** Found bidirectional disk↔project-knowledge drift; rescued 15 sole-copy files to disk + Git (`f91e931`). Established disk+Git as single source of truth. Confirmed schema v6.
- **Entry #015 (May 18):** v2.0 instructions rewrite; memory-defect session-startup protocol.
- **Entry #014 and earlier:** see `changelog.md`.

---

*Sheldon Wheeler — OpenClaw Personal Stack — CURRENT_STATE.md — maintained at each session close.*
