# OpenClaw — CURRENT STATE

*Read this first, every session. This is the snapshot of where things stand right now.*
*Standing rules and how-to-assist live in the project instructions. Full session-by-session history lives in `changelog.md`.*

**Last updated:** September 30, 2026 (Entry #050 — **generator v9.9**: every section every week + Appendices A (sources) / B (earlier docs, days 8–30) / C (IT Governance reference); v9.8: IT Governance section (ADR-048 Part A — routing + weekly reference block); v9.7: USDA (FNS/FNA/SNAP only) and IRS (HHS-adjacent) scope filters, clickable links (HTML email + per-section Sources), `--test-email`; **ADR-048 IT Governance section drafted (PROPOSED)**; fourth §2 breach disclosed (scratchpad); **ADR-047 step 7 done** (ADR-021/033/043/046 marked; ADR-046 F3, F9, F10 closed, F2 scoped); F9 residue fixed; post-reboot: Ollama login race PASSED, Docker needed a password (**F17**); Entry #049 — **briefs back to `gemma4:e4b`** (qwen3:8b broke SYSTEM_PROMPT); generator **v9.5** — FR links in the source list; **ADR-047 step 6 live** — F10 partition maintenance, April–June 2026 dropped; finding F16; Entry #048 — **ADR-047 DECIDED and steps 1–5 built**: guards, lock, Ollama settings, Docker 3 GB, bake-off; briefs → qwen3:8b, chat → gemma4, thinking off; findings F11–F15; Docker reset + restore; Entry #047 — ADR-029/046 amended; F10; Entry #046 — AU-5 spool; ADR-034 deferred; 16 GB inference architecture queued as the next conversation; Entry #045 — F7 fixed, schema 8; ADR-046 amended; Entry #044 — F7 audit-log partition outage found; findings rule revised; Entry #043 — Aug 4–16 gap backfilled; scraper pagination fixed; Entry #042 — §8.3 traversal hook built, live test pending; Entry #041 — ADR-014 §7 auto-mode amendment; ADR-045 §8.2 home-wide `Read` grant removed)
**Project status:** **Active, production-first.** The federal_policy_brief pipeline generates *and delivers* briefs end to end. Governance and housekeeping are opportunistic and do not block shipping.

> **Note on cadence:** the project sat dormant from August 23 to September 20, 2026. It survived that unattended — the scraper ran itself throughout. Dormancy is not a failure state for this system.

---

## Source of truth (the core rule)

**Disk (`~/openclaw`) + Git are canonical.** Project knowledge is a **one-way mirror** — files flow disk → project knowledge, never the reverse — and is **lagging; a clean rebuild is still pending**. Memory is never authoritative. If any two sources disagree, **disk wins**.

Confirm sync yourself rather than trusting a hash written here:

```
git log -1 --oneline && git status -sb
```

**Check your working directory before anything else.** `~/openclaw` is the **only** repository directory for this project on this machine. Two others were found and removed on August 23, 2026: `~/projects/mac-mini` (Entry #027) and `~/mac-mini-agent` (Entry #029, the original March–April prototype, whose unique history is preserved as tag `prototype-2026-04`). Both had derailed sessions. Keep running the check anyway, as cheap insurance:

```
pwd && git remote -v
```

Must show `~/openclaw` and `git@github.com:UpscaleOnly/Mac-Mini-Agent.git` (SSH). Note the second clone's remote differed only in **letter case** — a case difference is exactly what a reader confirms at a glance and gets wrong.

## Start here — session startup commands

0. **Next session (Entry #050 carry-forward):** (a) confirm the Entry #050 commit reached origin — `git log -1 --oneline && git status -sb` must show `main...origin/main` with nothing ahead; the auto-mode classifier blocked Claude's commit/push, so the operator ran it. (b) First scheduled `db_maintenance` run — the audit-row query under Schema. (c) **F17** — only if the Mac has rebooted: did Docker Desktop ask for a password? See Active task 1.

1. **Working directory** — the check above.
2. **Containers** — `docker ps`; expect four up. If the daemon is down, launch Docker Desktop and wait for the whale to stop animating.
3. **Git state** — `git log -1 --oneline && git status -sb`. Confirm rather than trusting any hash written in a document.
4. **Postgres password** (only for host-run scripts; anything via `docker exec openclaw_postgres psql ...` needs no password):
   ```
   export POSTGRES_PASSWORD=$(grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
   ```
   Verify by length, never by echoing.
5. **Coverage check before running the generator:**
   ```
   docker exec openclaw_postgres psql -U openclaw -d openclaw -c "SELECT max(publication_date), count(*) FROM scraped_content WHERE project = 'federal_policy_brief' AND is_new = TRUE AND publication_date >= CURRENT_DATE - 7;"
   ```
   A Friday `max(publication_date)` seen on a weekend is **correct** — the Federal Register does not publish Saturdays or Sundays, nor federal holidays.

⚠️ **Before any command that touches the filesystem outside `~/openclaw`, read `DATA_BOUNDARIES.md` §2.** It has been breached three times. See "Filesystem boundary" under Top open items.

## Rollbacks available

- `generate_brief_review.py.bak.v7` — v7 (pre-modifier-word counts, no `request` unit, no enumeration rule).
- `generate_brief_review.py.bak.v4` — working v4 (pre-v5: review-only, no `--send`, no SMTP, no `brief_runs`). Also `.bak.v3`, `.bak.v2`, `.bak.v0`; each file's header comment says what it lacks.
- `app/scheduling/scheduler.py.bak.pre-misfire-fix` — pre-August-23 scheduler (10-minute misfire grace).
- `app/scheduling/scrapers/federal_register.py.bak.pre-pagination` — first-page-only `fetch()`, no date bounds, no backfill class. Rebuild `fastapi` after restoring.
- `ADR_033.docx.bak.plaintext-format` … `ADR_037.docx.bak.plaintext-format` — the original plain-text-as-`.docx` files, pre-conversion.
- `ADR_042.docx.bak.pre-amendment-2026-08-23` — pre-"Mac Mini" correction.
- `ADR_014.docx.bak.pre-amendment-2026-09-29` — before the §7 auto-mode amendment.
- `.claude/settings.local.json.bak.pre-adr045-8.2` — before removal of the home-wide `Read` grant.
- `ADR_036.docx.bak.pre-supersede-2026-09-20` — before the SUPERSEDED marking.
- `ADR_040.docx.bak.pre-amendment-2026-09-20` — before the ADR-045 amendment annotation.
- `DATA_BOUNDARIES.md.bak.pre-adr045` — v1, before the v2.0 rewrite. `DATA_BOUNDARIES.md.bak.pre-adr047` — v2.0, before v2.1. `ADR_040.docx.bak.pre-adr047`.
- `scripts/backup.sh.bak.pre-adr046-f1` — the working interim version (writes to `~/Documents`). Restores a functioning backup if the TCC grant proves impractical.
- `CURRENT_STATE.md.bak.pre-entry030` (this file's previous version), `CURRENT_STATE.md.bak.aug20`.
- `changelog.md.bak.pre-entry030`, `changelog.md.bak.session21`, `changelog.md.bak.pre-entry020`.
- **All `.bak*` files are gitignored** — they exist on disk only. Anything tracked is recoverable from Git instead: `git show <commit>:path/to/file`.
- **`migration_007.sql` (Sep 29) and `migration_006.sql` have already been applied live — do not re-run them** (both are idempotent; confirm `schema_version` first if in doubt). Pre-007 copies: `schema.sql.bak.pre-migration007`, `app/db.py.bak.pre-migration007`. Rolling back 007 means detaching/dropping the new partitions and deleting `schema_version` row 8 — only if they are empty.
- `ADR_029.docx.bak.pre-amendment-2026-09-29` — pre-§5 stub. `ADR_034.docx.bak.pre-deferral-2026-09-29` — pre-deferral.
- `ADR_046.docx.bak.pre-amendment-2026-09-29` — pre-§13 version (the post-§13, pre-§14 version is in Git at `34eb442`). **Its XML is malformed** (raw `&` in the status cell since Sep 20); do not restore it as-is.
- *(historical)* **`migration_006.sql`:** A second run is a no-op (`CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`), but confirm `schema_version` first if in doubt.

## Schema

Live PostgreSQL schema is **version 8** (`migration_007.sql` — `agent_actions` partitions 2026-08..2027-12 plus a DEFAULT partition; ADR-046 F7). `openclaw_fastapi` rebuilt September 29 and logs `Schema version OK — live database is at version 8 (required 8)`. **Health checks — both should be 0:** `SELECT count(*) FROM agent_actions_default;` and `wc -l < spool/audit_spool.jsonl 2>/dev/null || echo 0` (AU-5 spool — records waiting to replay; growth means audit writes are failing). Partitions are now maintained by the nightly **`db_maintenance`** job (01:30 ET, ADR-047 F10, Entry #049): current month + 3 created, months wholly older than 90 days dropped (19 partitions after the Sep 30 run: 2026-07 … 2027-12 + DEFAULT). Its own audit rows: `SELECT created_at, validation_verdict, error_message FROM agent_actions WHERE action_type='db_maintenance' ORDER BY created_at DESC LIMIT 3;` — `error_message` should be empty.

## What's running / operational

- **Docker:** Desktop VM capped at **3 GB memory, 5 CPUs, 160 GB disk image** (ADR-047 step 4; disk cap is the operator's change — applying it wiped Docker and the stack was rebuilt Sep 29, Entry #048; all data is in bind mounts and survived). ⚠️ **Lowering the disk-image limit again is a destructive reset** — take a fresh backup first. Four containers — `openclaw_fastapi` (port 8080), `openclaw_postgres` (PostgreSQL 16), `openclaw_chromadb`, `openclaw_telegram`.
- **Ollama:** native on the host (`host.docker.internal`), server **0.34.0**, **`gemma4:e4b`** (9.6 GB) serves **both** workloads (ADR-047 §14 + Sep 30 note): briefs thinking off; chat (`/agent`) thinking off, a message starting **`think:`** turns it on for that reply. **`qwen3:8b`** (5.2 GB) stays installed until gemma4 completes a clean `--send`, then may be removed (operator approval). One resident at a time. `llama3.2` is not installed; `qwen3.5:9b` was tested and removed (Entry #048). `NUM_CTX = 8192`. **Server settings (ADR-047 step 3):** `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`, applied at login by `~/Library/LaunchAgents/com.openclaw.ollama-env.plist` (runs `scripts/ollama_env.sh`, restarts Ollama.app). Verify: `grep 'server config' ~/.ollama/logs/server.log | tail -1`. **Login race not yet verified — check after the next reboot.** Real cost at 8K ≈ **7 GB** (not the 3.2 GB `ollama ps` shows).
- **Host platform:** MacBook Air, Apple M1, **16 GB** unified memory, fanless, ~68 GB/s memory bandwidth. This is the production host by decision, not by default — see **ADR-043**.
- **Backup automation** (live since May 17): nightly `pg_dump` at 04:00 ET via launchd; 30-day retention; Telegram failure alerts; `pmset` repeating wake at 03:55 ET (AC only).
- **Federal Register scraper:** APScheduler cron nominally **01:00 ET**, inside `openclaw_fastapi`, `misfire_grace_time` **11100s (3h05m)**, `coalesce=True`. **Proven in production** — see below.

## Scraper reliability — RESOLVED (proven September 20, 2026)

Both fixes have now survived four weeks of unattended operation. This was the longest-running open item in the project and it can be closed.

- **Misfire grace (Entry #024)** — `scraper_runs` shows runs firing with start times spread across 05:00–07:22 UTC (01:00–03:22 ET). The late fires are the widened grace catching runs on the 03:55 ET wake rather than discarding them, exactly as designed.
- **Catch-up logic (Entry #020)** — the machine was down September 7–12; the September 13 run fetched 100 documents and inserted 65, backfilling the entire outage with no intervention.
- **Coverage since August 24 has exactly one missing weekday: 2026-09-07, Labor Day.** The Federal Register does not publish federal holidays. Zero genuine gaps.

Do not re-open this without new evidence. An empty 7-day window still means the scraper has not run — never raise `WINDOW_DAYS` to compensate.

## Content state (`scraped_content`)

- Coverage **April 24 → September 28, 2026**, all `project = 'federal_policy_brief'`. **680 rows total: 638 `is_new = TRUE`, 42 consumed** by the August 22 and September 27 sends (as of September 29).
- **69 rows `is_new = TRUE` in the trailing 7-day window** as of September 20.
- **Every query MUST filter `WHERE project = 'federal_policy_brief'`** — the table is project-scoped.
- `raw_content` is **title + abstract only** (~569 chars avg). Brief depth is abstract-level by design of the current scraper.
- ✅ **August 4–16 gap BACKFILLED September 29 (Entry #043)** — 94 documents inserted; every weekday Aug 4–14 now has 6–22 documents, in line with the adjacent weeks. Rows came from the `federal_register_backfill` run and carry `is_new = TRUE`, but their publication dates sit far outside the generator's 7-day window, so they never reach a brief.
- ✅ **Silent catch-up truncation FIXED (Entry #043).** `fetch()` read only the first page — newest 100 per agency — and the parent HHS query runs ~33/week, so any catch-up over ~3 weeks (the cap is 30 days) silently lost its oldest documents. `fetch()` now follows `next_page_url`, capped at 20 pages per agency; hitting the cap marks the run `partial` and logs `older documents NOT fetched`. **Tests:** `python3 test_fr_pagination.py` (14; also runs in the container).
- **Future backfills:** `FederalRegisterBackfill(date_from, date_to).run()` inside `openclaw_fastapi` — records under its own scraper name so it never resets the nightly catch-up clock. Not registered with the scheduler.
- No content is expected Saturdays, Sundays, or federal holidays.

## federal_policy_brief — where the generator stands

`~/openclaw/generate_brief_review.py` is at **v9.9** (Entry #050 — layout: every section every week, Appendices A/B/C; v9.8 — IT Governance section, ADR-048 Part A; v9.7 — IRS scope filter, per-section Sources, HTML email part, `--test-email`; v9.6 — USDA scope filter; Entry #049 — FR link under each source-list entry; v9.4 — model back to `gemma4:e4b`, thinking off; v9.3 — qwen3:8b; `--think`; F13 ICR unit fix; v9 — ADR-047 guards: truncation, lock, memory gate, unload, `--model`). Rollbacks preserved: `.bak.v9.8`, `.bak.v9.7`, `.bak.v9.5`, `.bak.v9.4`, `.bak.v9.3`, `.bak.v9.2`, `.bak.v9.1`, `.bak.v9`, `.bak.v8`, `.bak.v7`, `.bak.v6`, `.bak.v5`, `.bak.v4`, `.bak.v3`, `.bak.v2`, `.bak.v0`.

**Default mode (no flags) remains review-only and side-effect-free** — sends nothing, marks nothing processed, writes no `brief_runs` row, safe to re-run indefinitely. Verified byte-identical to v4 on that path.

**`--send` (new in v5)** additionally emails the brief, flips `is_new = FALSE` on consumed rows, and writes one `brief_runs` audit row:

- Self-send SMTP via `smtp.mail.me.com:587`, STARTTLS, credentials from macOS Keychain at send time — never through a chat session. No ESP, no purchased sender domain (ADR-039 H4 sub-decision: unnecessary at an audience of one).
- **Gated on `verify_claims()` returning zero warnings.** An unverified claim blocks the email entirely — independent of the `HARD_FAIL_ON_UNVERIFIED` switch, which governs only review-mode print-vs-abort.
- `is_new` flips **only after a successful send**, so a failed send leaves rows eligible for retry rather than silently dropping them.

`HARD_FAIL_ON_UNVERIFIED` is still **`False`** (line ~195). 🔴 **DO NOT flip it to `True` until the count defect below is fixed** — it would convert a false positive into a hard abort.

✅ **Counts verified against ground truth — send path UNGATED (v7, Entry #038).** `ground_truth_counts()` recomputes documents, notices, rules, agencies and distinct US states from the rows the model was given; `verify_counts()` verifies a match, warns with the real figure on a mismatch, or warns as unverifiable where no ground truth exists (durations land there). **The Sept 20 run verified clean — the first since Aug 22.**
  **Scope subtlety, learned the hard way:** the executive summary makes section-scoped claims in a global context ("CMS issued three notices" — true of CMS, false of the window). `acceptable_counts()` therefore accepts any single section's count or the whole for the summary only; per-section checks stay exact. v7's first run failed on precisely this and the unit tests had passed, because they tested the wrong shape.
  ⛔ **Do not re-attempt tolerance-based approaches.** Treating counts ≤ the document count as non-blocking was tried and reverted the same hour after it demoted a real "15 states" fabrication (sources said 18) to a note. Two runs, identical input, 18 (right) and 15 (wrong) — **the model does fabricate counts, and no magnitude heuristic separates them.**
  ✅ **v8 (Entry #040): counts with modifier words are now examined.** The v7 audit's diagnosis ("add `request` to `_UNIT_PAIRS`") was wrong — the regex required the number to touch the unit, so "two information collection requests", "3 new SNAP rules" and "15 participating states" were all invisible. Up to two modifier words are now allowed; `request` is a unit with ground truth. **Enumeration rule:** "one <unit>" is accepted only when the same text states a correct total >1 for that unit — structural, not a tolerance. **Tests:** `python3 test_count_verification.py` (22, tracked, no DB needed) — run after any verifier edit.

✅ **The pipeline has delivered two briefs** — August 22 and **September 27** (`brief_runs` #3, clean, 0 warnings, 18 docs). The first Sept 27 attempt (#2) failed on SMTP 535 — a revoked app-specific password — and the gate held: no email, no `is_new` flip. Password replaced; stored **without dashes**, which iCloud accepts.
  🔁 **Recurring failure — every Apple ID password change revokes the SMTP password.** Symptom: `--send` fails with `535 authentication failed`, gate holds, rows stay eligible. Fix (operator): account.apple.com → App-Specific Passwords → revoke `OpenClaw SMTP`, generate a new one, then run `security add-generic-password -U -a openclaw -s ICLOUD_SMTP_PASSWORD -w` and **type** it at the prompt (Control+V does not paste in Terminal). Verify shape without revealing it (16 letters, or 19 with dashes), then test the SMTP login alone before a full `--send`. **Keep `HARD_FAIL_ON_UNVERIFIED` at `False` until one more clean send on a new week's content.**

**Run evidence is version-controlled.** `federal_policy_brief_review_*.txt` files are tracked deliberately, each committed alongside the generator version that produced it (`20d4951` v0, `b0000ce` v4, and now the v5 run). Do **not** gitignore them — they are the behavioural record.

## Active task (in order)

1. **[Next session, first] Startup checks (Entry #049/#050 carry-forward):**
   - **Ollama login race:** `grep 'server config' ~/.ollama/logs/server.log | tail -1` must be timed after the login and show `OLLAMA_MAX_LOADED_MODELS:1`, `OLLAMA_NUM_PARALLEL:1`.
   - ✅ **Ollama login race PASSED (Sep 30, post-reboot):** boot 07:47:37, `server config` line 07:49:00 with `MAX_LOADED_MODELS:1`, `NUM_PARALLEL:1`.
   - ⚠️ **Unattended restart FAILED (Sep 30) — F17:** Docker Desktop asked for the operator's password before it would start. After that, all four containers came up and 4 jobs registered, including `db_maintenance`. Likely a one-time privileged-helper re-grant after the Sep 29 reset; **re-test at the next reboot**. If it prompts again, the fix is a Docker Desktop setting (operator change).
   - **First scheduled maintenance run** (after the next 01:30 / 03:55 wake): the `db_maintenance` audit-row query under Schema — expect `created=none dropped=none`, empty `error_message`.
2. **[~Oct 3–4] Weekly `--send`** — **first production brief from `gemma4:e4b` thinking off** (generator **v9.9**: USDA/IRS scope filters, HTML email with clickable links, IT Governance section, every section every week, Appendices A–C). Optionally rehearse first with `--test-email` (no side effects). Read the executive summary against the sections before trusting it (**F16**); watch the F13 subset-count shape. The Sep 30 review-only run was clean (0 warnings, 3 docs). Revert = `MODEL` constant / `.bak.v9.3`.
2b. **[Next session, after startup checks] Sub-regulatory guidance gap — operator question Sep 30 (Entry #050).** The brief sees only the Federal Register. CMS State Medicaid Director / State Health Official letters and CMCS Informational Bulletins (Medicaid.gov), FNA SNAP policy memos, and ACF TANF program instructions / information memoranda are **not captured**: 0 of 691 rows; every row's link is federalregister.gov. Plan: a retrieval pass on the three agencies' guidance listing pages (confirm URLs, structure and whether automated access is allowed), then draft **ADR-049**. Pair its outbound-host approval with ADR-048 Part B in one ADR-014 §7 amendment. OBBB implementation guidance is expected in these memos.
2a. **[Operator testing today/tomorrow] ADR-048 IT Governance** — §9 decisions recorded; **Part A BUILT (v9.8)** — test with `--test-email`. Register current: **TSSR v12.1 (Apr 28, 2026), ARC-AMPE Vol. I v1.0.4 (May 7, 2026)**, both operator-supplied (the public pages lag). Operator to revisit the four uncited regulations and the three Social Security Act sections that TSSR v12.1 no longer cites, after reviewing the output. Part B (automated change monitoring) not approved yet. Part B (source-change monitor) needs an ADR-014 §7 amendment for irs.gov, cms.gov, ecfr.gov and uscode.house.gov, plus migration 008. Register: `agents/prototype/projects/federal_policy_brief/it_governance_sources.json`. Also: update `federal_policy_brief_DECISIONS.md` (links now allowed; new section).
3. **[ADR-047 — remaining step, approved separately]** Steps 1–7 DONE (step 7, the in-place marks, Entry #050). Remaining: **8** — ADR-032 full Moderate-baseline NIST re-assessment (F2, Option B).
3a. **[After the first clean gemma4 `--send` — deferred so a send problem can be traced to one change]** Anything that changes what the model reads or writes, or what the verifier checks: F16 (summary items must map one-to-one to documents — a verifier check or a deterministic summary); links inside the prose (citation markers + verifier); F13 CMS shape; FR date fields for F15 (schema); full-text archive decision (chatbot ADR); output polish (task 6); removing `qwen3:8b`.
4. **[Discussion — operator raised Sep 29]** Reuse the design for more scrape-and-summarise projects and a chatbot. Agreed direction: extract shared code (inference guards, verifiers, send gate) **when the second scraping project starts**, not before. Chatbot needs its own ADR: conversation memory (`/agent` is single-turn today), grounding in sources with citations, 8K context budget, `think:` override. **F15:** question-answering over a brief confused publication dates with deadlines — so first consider storing Federal Register date fields (comment close, effective date — field names to be verified against the FR API docs) in the scraper (schema change).
5. **[Then]** Build `--send` confidence toward flipping `HARD_FAIL_ON_UNVERIFIED` to `True`.
6. **[Opportunistic]** Output polish: ISO dates in reader-facing prose; executive summary running long; ORR-under-TANF routing (a scope decision, not a bug).
7. **[Operator]** Project-knowledge refresh — see Top open items.

## Top open items

- **F13 (Entry #048) — verifier false positives. TANF shape FIXED (v9.1:** "information collection request" is one unit). **CMS shape KNOWN LIMITATION:** "A notice … Two notices …" is correct but states no total; accepting sub-total counts is the ruled-out tolerance, so it still warns and **still blocks `--send`** — if the Oct 3–4 send is held on it, read the section, then decide. Pinned by test. ADR-047 §8 level 2 → YELLOW done.

- **F11 (Entry #048, MEDIUM) — cloud path broken:** `call_openrouter()` posts `json=headers` not `json=payload`; dormant (no key, routing always local). **F12 (LOW)** — `.env` `OPENROUTER_DEFAULT_MODEL` is ignored (config reads `OPENROUTER_MODEL`); default model ID stale. Remediation in ADR-047 §6/§10.

- **F16 (Entry #049, MEDIUM; recurred 3 times Entry #050) — executive summary can misstate the document set undetected.** Sep 30 run: one CMS correction notice appeared twice in the summary, first as a substantive IPPS final rule. The verifier has no one-to-one check between summary items and documents. Deferred to task 3a.

- **F17 (Sep 30, MEDIUM) — Docker Desktop needed the operator's password at the post-reboot launch.** Any unattended reboot (power loss, OS update) would leave the scraper, `db_maintenance` and the whole stack down until someone signs in. Losses are bounded: the scraper's 30-day catch-up backfills the gap. However, `scripts/backup.sh` skips the nightly backup and sends a `postgres_down` Telegram alert for as long as Postgres is down (line 167). The prompt was a macOS system authorization dialog, not a Docker window. Re-test at the next reboot before deciding on a fix.

- ✅ **F10 REMEDIATED Sep 30 (Entry #049)** — nightly `db_maintenance` job live; April–June 2026 partitions (26 rows) dropped. ADR-046 §15 marks it closed (Entry #050). *Original finding:* **(Entry #047, LOW) — 90-day audit retention never enforced.** ADR-029 sets 90 days; ADR-035 §9.4 assigns the partition DROP to a "monthly cron under dev account" — never built, account nonexistent. April–May 2026 rows remain. **Also confirms F7's root cause:** ADR-035 §9 says partitions "are created monthly by the nightly maintenance job" — the same missing job. F7 was F5 producing a live outage. Fix pending approval (task 5).

- ✅ **AU-5 decided and implemented (Entry #046).** Operator decision: **an audit-write failure must not fail the request, and failures must not need manual review.** `app/audit.py` `write_action()` never raises: a failed insert goes to `~/openclaw/spool/audit_spool.jsonl` (host-mounted — survives rebuilds; gitignored) and logs one ERROR; the next successful write replays the spool automatically; `ON CONFLICT (action_id, created_at) DO NOTHING` makes duplicates impossible. Only a spool-write failure loses a record (logged CRITICAL). **Tests:** `docker exec openclaw_fastapi python test_audit_spool.py` (9). ADR-029 amended (§5.1, Entry #047).

- ✅ **F7 RESOLVED September 29 (Entry #045) — `agent_actions` audit log could not accept records dated on or after August 1, 2026.** No partition existed past July 2026 and `write_action()` is unguarded, so every `/agent` request since Aug 1 failed after its LLM call. **Fixed by `migration_007.sql`** (schema 7 → 8): partitions through Dec 2027 plus a DEFAULT partition. Verified: the failing insert now succeeds (rolled back), 22 partitions, fresh-install `schema.sql` tested in a scratch DB. **`/agent` verified end to end September 29 (Entry #048)** — HTTP 200, audit row written. **The May 17 silence is explained:** the operator has not used Telegram in months (Sunday digests are automated and would have failed from Aug 2 — inferred, logs lost). Open decision: should `/agent` keep failing closed when an audit write fails (NIST AU-5)?
- **ADR-046 audit extended to code, scripts and launchd config (Entry #044); ADR-046 amended with §13 (Entry #045)** — F7 (resolved), F8, F9 below.
  - ✅ **F8 RESOLVED by deferral (Entry #046)** — ADR-034 hardware telemetry was never deployed; **ADR-034 now marked DEFERRED — WAITING ON HARDWARE** (operator decision). Not deployed here because sudoers + a root LaunchDaemon are real privilege grants. `hardware_metrics` / `hardware_alerts` stay empty; ADR-032's SI-4/SI-4(5) claims via ADR-034 do not hold on this host (part of F2).
  - ✅ **F9 CLOSED Sep 30 (Entry #050, ADR-046 §15)** — residue below corrected. *Original:* **F9 — LOW — stale host references in code and docs:** model-tier labels 7B/14B/32B (`app/models.py`, `schema.sql`) and "14B" in `federal_policy_brief_DECISIONS.md` vs the actual `gemma4:e4b`; `federal_policy_brief_CODE_REFERENCE.md` lists `scraped_content` and `brief_runs` as "OPEN — setup day" though both exist; "setup day" in `app/db.py` and `app/persona_router.py`; the backup plist template plans a "Mac Studio setup day" removal and an ADR-020 `dev`-account move.
  - **Clean:** `scripts/backup.sh` (F1/F6 fixes hold).
  - **Scope limit:** live `~/Library/LaunchAgents`, `/Library/LaunchDaemons` and `/etc` are §2-prohibited; launchd state was checked via `launchctl list` / `launchctl print system` instead.

- ✅ **BACKUP PATH — RESOLVED September 20 (ADR-046 F1, Option C).** Backups now write to `~/openclaw/backups`, already sanctioned by ADR-040 §1 — no boundary crossing, no TCC grant, no policy amendment. **Verified by live run:** 148 KB dump, `gunzip -t` clean, 39 table/data statements, invisible to git.
  **Option A (grant TCC) was chosen first and reversed.** TCC attributes access to the *executing binary*, so for a shell script the grant target is `/bin/bash` — which would give every bash script on the machine full read/write access to `~/Documents`, `~/Desktop` and the FTI-bearing iCloud root. Broader exposure than the violation it fixed. TCC also cannot be automated: `tccutil` only resets, the databases are SIP-protected, and PPPC profiles need MDM (this host is not enrolled).
  **Two follow-ups remain:**
  1. ✅ **Off-device backup CONFIRMED September 27 (Entry #040)** — seven scheduled runs logged `OFFSITE_OK`; all eight dumps visible on the operator's iPhone under `offsite/`. Upload state is checked by the operator on a second device, not from a session: §1 grants `offsite/` write only. *History below.* **Restored (Entry #039).** `scripts/backup.sh` now copies each dump to the ADR-040 §1 sanctioned path `~/Library/Mobile Documents/com~apple~CloudDocs/Mac-Mini-Backups/offsite/`. Size-verified, 30-day retention, **non-fatal** — a failure logs `OFFSITE_COPY_FAILED` and alerts but never takes down a local backup that succeeded. Live-tested: 151,242 B local and remote, `gunzip -t` clean.
     **Entry #013's TCC claim was tested and is false here** — a `launchctl submit` probe wrote to the iCloud path successfully, so no Full Disk Access grant was needed (ADR-046's Option A stays rejected: FDA on `/bin/bash` would expose every §2 path to every shell script). **Caveat: a submitted job may inherit the submitter's TCC, so the definitive test is the real 04:00 run — check the log for `OFFSITE_OK`.**
     **Second caveat, in the script:** iCloud uploads asynchronously via `bird(8)`. `OFFSITE_OK` means written into the synced folder, *not* uploaded. Until `bird` finishes, that copy is still on the same disk.
  2. **Old dumps still in `~/Documents/Mac-Mini-Backups-Interim`** — operator action, §2-prohibited so not touchable from a session. §2 is closed for new writes only.
  **Rollback:** `scripts/backup.sh.bak.pre-adr046-f1`.

- **ADR-032 NIST mapping asserts controls against the absent architecture (ADR-046 F2, HIGH).** AC-11 dismissed as "not meaningful for headless daemon operation" on a laptop with a screen; AC-18 assessed expecting WiFi disabled; SA-2 MET citing 32 GB against 16 GB; AC-6 MET citing an `openclaw` account that does not exist. **AC-11 and AC-18 err toward understating obligation.** Decide whether to re-assess the four named controls or the full Moderate baseline — they were found by targeted search, not review, so others are likely.

- ✅ **F3 CLOSED (ADR-046 §15, Entry #050)** — thresholds replaced by ADR-047 §8 in the generator; ADR-033 marked. *Original:* **ADR-033 memory alerts can never fire (ADR-046 F3, MEDIUM).** Thresholds are 28 GB yellow / 30 GB red against "Total 32GB". On 16 GB they report healthy under every condition including genuine exhaustion. Silently dead control; also references a 32B model that is not deployed.

- **Dedicated-host audit — 11 documents affected, 4 failure modes (ADR-046, OPEN).** ADR-036 was not a one-off. Beyond F1–F3: "Mac Studio setup day" is a live scheduling target in ADR-031/038/039/041 (work stalled, nothing marks it unreachable — including ADR-039's Keychain item, which is the same item as F1); and the openclaw/admin/dev account model assumed by ADR-020/033/034/035/038 does not exist. **The audit covered ADR documents only — F1 was found in a script, so the class size is still unknown.** Extending it to code, scripts and launchd config is an open item.

- **Filesystem boundary — decided September 20 (ADR-045), implementation pending.** DATA_BOUNDARIES.md §2 has been breached three times (Session 16, Entry #029, Entry #030). ADR-045 amends ADR-040 with an enforcement model and — more importantly — corrects the control classification: **AC-3 was overstated as IMPROVED and is NOT MET** until a technical control ships. PL-4 and AU-6 are accurate; the real compensating control is **disclosure**, since all three breaches were self-reported rather than detected. `DATA_BOUNDARIES.md` is now **v2.0** with §2.1 (binds all execution surfaces), §2.2 (listing and traversal prohibited, not just reading), §6 (enforcement posture) and §7 (governed artifacts).
  **Structural finding:** Claude Code matches Bash rules against *command strings*, not the paths they reach — `Bash(du:*)` permits `du` anywhere. **Shell is unbounded by construction**, so every path-scoped `Read(...)` rule is irrelevant when the same data is reachable through a shell command.
  **Still to implement:** ADR-045 §8.2 and §8.3 below.

- **ADR-045 §8.3 — traversal-verb hook BUILT (Entry #042), live verification FAILED ONCE (Entry #048):** in the first test the command ran with **no operator prompt** (mode likely auto) — either the hook is not loading or auto mode swallows its `ask`. **Corrected same day: the hook IS loading** — its new run log (`scripts/hooks/traversal_guard.log`, gitignored) recorded `mode=acceptEdits verb=ls ask` at 12:43:21 for the retest, yet the command executed. **Resolved: it did** — a Deny / Allow-once prompt (reason text not visibly shown); operator allowed once. §8.3 LIVE-VERIFIED. Also: the app reports mode `acceptEdits`, not `default`, when the operator believed it was Manual — ADR-014 §7 should name which setting counts. `scripts/hooks/traversal_guard.py`, registered in the **tracked** `.claude/settings.json`. Prompts (`ask`) when a listing/traversal verb or any wildcard reaches outside `~/openclaw`; follows `cd` within a command, so `cd ~ && du -sh */` is caught. `ls` is gated even without `-R` — the Entry #029 breach was a plain `ls -d` glob, which the original design would have missed. **Tests:** `python3 scripts/hooks/test_traversal_guard.py` (52, all three recorded breaches verbatim) — run after any guard edit. Did not fire live in the session that created it (hooks load at session start). **Speed bump, not a boundary:** interpreters, obfuscation and non-Claude-Code execution pass; AC-3 stays NOT MET.

- ✅ **ADR-045 §8.2 DONE September 29 (Entry #041)** — `Read(//Users/sheldonwheeler/**)` removed from `.claude/settings.local.json`; only `Read(//Users/sheldonwheeler/openclaw/**)` remains. Backup: `.claude/settings.local.json.bak.pre-adr045-8.2`. The file is a **governed artifact** under DATA_BOUNDARIES §7 but gitignored, so changes never appear in a diff — inspect manually at each review. **Stale-rule prune also DONE (Entry #041 addendum):** 18 rules naming OneDrive, the iCloud root, `~/Downloads` or `~/Library/Application Support` removed, including the wildcard `Bash(brctl download *)`. The broad inline-Python rules `Bash(python3 -)` and `Bash(python3 -c ' *)` were also removed — inline Python now prompts every time — as was `Bash(npm install *)` (supply-chain exposure). `Bash(docker exec *)`, `Bash(cp .claude/settings.local.json *)` and `Bash(sudo -n true)` removed too — **every `docker exec` (including the startup coverage query) now prompts**, by operator decision. `docker system *`, `docker image *` and `ollama rm *` also removed (data-destroying); `docker compose *` kept for the closing ritual. Backup: `.claude/settings.local.json.bak.pre-stale-prune`.
  ⚠️ **Gotcha — choosing "always allow" on a prompt makes the app rewrite this file from its cached rule list**, silently reverting any edit made to it on disk during that session. It happened here once. When editing this file, approve surrounding commands with **"Yes" (once)**, then re-read the file to confirm the edit held.

- **`~/Documents/Mac-Mini-Backups-Interim`** — carried from Entry #029, unexamined, inside a §2-prohibited path. Either it predates ADR-040 and needs migrating, or it is an undocumented second backup destination.

- **PostgreSQL credential reconciliation — open since Aug 20.** The live `openclaw` role password is **NOT** the `changeme` placeholder. The real value lives in `~/openclaw/.env`; container env and Keychain both still hold the stale placeholder. *Read it without echoing it:* `export POSTGRES_PASSWORD=$(grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)` — needed in every new Terminal window for host-run scripts. Anything via `docker exec openclaw_postgres psql ...` needs no host-side password at all.

- **ADR corpus — materially improved Aug 23, not finished.** 29 ADR `.docx` files now on disk (ADR-043, 044, 045, 046 added September 20). **Still unrecovered: ADR-017 and ADR-022** (both cited in live code, zero content found anywhere). No evidence at all for ADR-001, 004, 006–013, 015, 016. Full picture: `adr_fragments_2026-08-22/reconciliation_2026-08-23/`.

- **ADR-042 (ADR corpus reconciliation) — OPEN, still deferred.** The counterpart Claude.ai project is **"Mac Mini"**, not "AI Build" (corrected by dated amendment Aug 23). Full reconciliation remains a dedicated future project — do not start it casually.

- **Two Claude.ai projects share the "OpenClaw" working name** — "Mac Mini" (this system) and "AI Build" (an unrelated pre-prototype SaaS concept). This collision has already caused one documented misattribution. Consider renaming one.

- **Git identity was placeholder text until September 20.** `~/.gitconfig` held literal `YourGitHubUsername` / `YOUR-NOREPLY-ADDRESS@users.noreply.github.com`, so **the entire commit history before Entry #030 is attributed to a stub**. Now set to `Sheldon Wheeler` / `UpscaleOnly@users.noreply.github.com`. If commits do not link to the GitHub account, the `<ID>+UpscaleOnly@users.noreply.github.com` form is required — ID at github.com/settings/emails. Historical commits not rewritten.

- **Instructions — content is at v3.3 (Sep 30: closing step 8, CURRENT_STATE + changelog upload every close); the file is still named `instructions_v3.0.md`. Paste v3.3 into the Mac Mini Instructions panel.** *(Was v3.2.)* Source of record on disk: `~/openclaw/instructions_v3.0.md` (amended through v3.2 in place). Keep that file and the live claude.ai panel in step; if they diverge, the disk copy is canonical. **The filename/version mismatch is itself a small drift hazard** — rename or add an explicit version header when convenient. Most important content change: v2.0's blanket "no shell/bash from any agent path" rule is replaced with the surface-dependent ADR-014 boundary. Still open inside v3.2: it runs ~65% longer than v2.0 (2,478 vs 1,502 words), a standing token cost on every conversation.

- **ORR routes to TANF** — the Burke Law Group withdrawal is an Office of Refugee Resettlement notice, routed to TANF because both sit under the Children and Families Administration. Fixing it means deciding where ORR content belongs. Scope decision, not a defect.

- **ADR-041** (third-party memory injection) — trigger long passed, ticket confirmed never resolved and not worth chasing. Remains formally OPEN; closing it as "not needed" is a one-line decision whenever convenient.

- **Project-knowledge rebuild** — clean one-way mirror of disk, including this file.
  **Refresh owed after September 30 (Entry #050)** adds: `ADR_021.docx`, `ADR_033.docx`, `ADR_043.docx`, `ADR_046.docx`, `ADR_048.docx` (new), `generate_brief_review.py` (v9.9), `federal_policy_brief_DECISIONS.md`, `it_governance_sources.json` (new), `schema.sql`, `app/db.py`. **After September 29 (Entries #041–#048)** — Entry #048 adds: `ADR_047.docx` (new), `ADR_040.docx`, `ADR_045.docx`, `DATA_BOUNDARIES.md` (now v2.1 — changed), `generate_brief_review.py`, `app/llm.py`, `app/config.py`, `app/models.py`, `schema.sql`. Earlier list: — in the "Mac Mini" claude.ai project, **remove the old copy, then upload the current one** for each of: `instructions_v3.0.md` (or paste into the instructions panel), `CURRENT_STATE.md`, `changelog.md`, `DATA_BOUNDARIES.md` *(unchanged — upload only if absent)*, `ADR_014.docx`, `ADR_029.docx`, `ADR_034.docx`, `ADR_046.docx`. Code in the ADR-039 §5.6.4 canonical set that changed: `app/audit.py`, `app/db.py`, `app/main.py`, `app/scheduling/scrapers/federal_register.py`, `schema.sql`, `migration_007.sql`, `docker-compose.yml`, `.gitignore`. New and optional: `scripts/hooks/traversal_guard.py`, `.claude/settings.json`. Removal is operator-only — Claude does not hard-delete account data.

- **The context ceiling — RESOLVED, but remember why.** Ollama defaulted `gemma4:e4b` to 4096 tokens for prompt and response combined. A 19-document section overran it. Entry #018 recorded this as "oversized section degradation" and proposed significance-ranking; that diagnosis was wrong — it was a config default. `NUM_CTX = 8192` now. **Available memory, not the chip, is what caps this** — the pipeline's four containers share the same 16 GB. Ranking may still be wanted editorially, but do not build it as a fix for truncation. Watch `NUM_CTX` if `WINDOW_DAYS` ever rises.

- **Ctrl+C does not interrupt in Terminal** — dead for months. Low urgency.

- **Disk cleanup — largely done September 20.** Reclaimed 37 GB (93% → 76% full; 15 GiB → 52 GiB free): Docker images 29.58 GB → 2.055 GB, and `.git` 11 GB → 1.1 MB after `git gc --prune=now` cleared two abandoned temp pack files. Remaining minor: `docker builder prune` (~197 MB), ~~one unreferenced Docker volume (~49 MB)~~ destroyed unexamined by the Sep 29 disk-image reset (Entry #048), and `old_skeleton/` (untracked dead code that still carries the only references to ADR-011, 012, and 016 — read before deleting).

## Hard rules (safety quick-reference — full versions in instructions)

⚠️ **ADR-014 changed on August 22 — the old "no shell, ever" rule is no longer accurate for Claude Code.**

- **Claude Code in Manual permission mode MAY** run shell commands, edit files directly, and commit to Git — **scoped to `~/openclaw`**, with per-action operator approval. **Cowork is never used.** (ADR-014, RESOLVED; reconstructed document at `~/openclaw/ADR_014.docx`, provenance in its Section 6.)
- **Auto mode is permitted under ADR-014 §7 (amended September 29, Entry #041):** operator-initiated and present only; same scope; approve-before-building still applies; outbound limited to the generator's SMTP and the Federal Register API; changelog records the mode. **Edits to Claude Code's own permissions are made in Manual mode** — the auto-mode classifier refused the §7 amendment itself, correctly.
- **Read `DATA_BOUNDARIES.md` §2 before any command touching paths outside `~/openclaw`.** A glob is a directory read. A `du` is a directory read. The policy binds interactive shell commands, not only application code. Three breaches to date.
- **A plain Claude Desktop chat session still follows the pre-ADR-014 rules:** MCP filesystem read-only, no shell, `.py` files delivered as `.txt` for manual copy, operator runs all git commands.
- **A code block in chat means "run this"** (Claude Code) or "here is what ran" (Desktop chat, retrospectively). Don't mix the two conventions mid-session.
- **Never** use `nano`, `vim`, or any interactive terminal editor (freezes the terminal).
- **Back up before replacing a working file** — `cp file.py file.py.bak.vN`. The backup is cheap insurance, not a workaround.
- **`git commit` always with `-m` inline** — never a bare `git commit`.
- **`git push` is NOT gated — corrected September 20, 2026.** This file previously stated that push "will be refused even when explicitly requested." It was tested directly on that date and succeeded (`28d7edf..eb99ebd`). The claim may have been true when written; it is not true now. Every earlier push this session was run by the operator on the strength of the stale note, which is exactly how a false claim survives. Test before repeating a documented restriction.
- **Token conservation**; **approve before building** — for code, schema, config, permissions and ADRs. **Verified findings are recorded in the changelog and this file without prior approval** (revised September 29, Entry #044).
- **Verify live state** (schema, files, config) before generating code or migrations. **Prefer an authoritative source over a clever inference** — this keeps paying off: the dual clone was caught by `git remote -v`; the scrape misfire was proven from `pmset -g log`; the 11 GB in `.git` turned out to be garbage rather than history only because `git count-objects -vH` was run instead of assuming; and `Docker.raw` reports 228 GB apparent against 3.0 GB actual, so `ls -lh` on it misleads by two orders of magnitude.

## Recent history (most recent first)

- **Entry #050 (Sep 30):** Post-reboot checks — Ollama login race **PASSED**; Docker Desktop needed the operator's password (**F17**, re-test at next reboot). **ADR-047 step 7** — ADR-021, 033, 043, 046 marked in place; ADR-046 §15 closes F3, F9, F10 and scopes F2. F9 comment residue fixed in 5 files.
- **Entry #049 (Sep 30):** Paginated scraper's first nightly passed. **Briefs back to `gemma4:e4b`** — qwen3:8b's bake-off brief broke SYSTEM_PROMPT (advice, editorialising, input tallies, a wrong TANF attribution) in ways the verifier cannot see; ADR-047 §14 note. Generator **v9.5** — FR links in the source list. **ADR-047 step 6** — `db_maintenance` job (22 tests + scratch-DB run), live run dropped April–June 2026. **F16** — summary double-counted a correction notice; verifier passed it.
- **Entry #047 (Sep 29):** **ADR-029 amended** (§5: AU-5, partitions, retention finding) and **ADR-046 §14** (F8 resolved; F7 root cause confirmed as F5 from ADR-035 §9; **F10** retention not enforced). Global `~/.claude/CLAUDE.md` Update 003 (automation over review queues) — operator-approved write outside `~/openclaw`.
- **Entry #046 (Sep 29):** **AU-5** — audit-write failures no longer fail `/agent`; host-mounted spool with automatic replay (9 tests). **ADR-034 DEFERRED — waiting on hardware** (F8). **Operator decision: the M1 Air 16 GB is the LLM host — new workstream for the next conversation.** Session close-out.
- **Entry #045 (Sep 29):** **F7 fixed** — `migration_007.sql`, schema **7 → 8**, audit log writable again. ADR-046 amended (§13: F7–F9). Found `ADR_046.docx` had been malformed XML since Sep 20 (raw `&`); fixed; all 29 ADRs now parse.
- **Entry #044 (Sep 29):** Dedicated-host audit extended to code/scripts/launchd. **Found F7 (HIGH): `agent_actions` has no partition after July 2026 — every `/agent` request since Aug 1 fails**; verified by rolled-back insert. ADR-034 telemetry never deployed. Rule revised: **findings are recorded without prior approval; remediation still needs it.**
- **Entry #043 (Sep 29):** **Aug 4–16 gap backfilled** (94 docs). Found and fixed a silent truncation: `fetch()` read only the first 100 docs per agency, so wide catch-ups lost their oldest documents. Pagination + date bounds + a separate `FederalRegisterBackfill` class; 14 tests; `fastapi` rebuilt, schema 7.
- **Entry #042 (Sep 29):** ADR-045 §8.3 traversal hook **built** — 52 tests pass, including the three recorded breaches verbatim; tests caught a design gap (plain `ls` globs) before shipping. Registered in tracked `.claude/settings.json`. **Live test pending** — hooks load at session start.
- **Entry #041 (Sep 29):** **ADR-014 amended (§7)** — auto mode permitted under conditions, closing the Entry #040 contradiction. **ADR-045 §8.2 done** — home-wide `Read` grant removed. The auto-mode classifier refused the amendment as self-expanding permissions; the session switched to Manual mode to finish, and that is now a §7 condition.

- **Entry #040 (Sep 27):** **Second brief ever delivered** (`brief_runs` #3). Generator **v8** — the Sept 20 ICR diagnosis was wrong (eighth documented-but-false claim): counts with modifier words were never examined. Enumeration rule added; 22 tracked tests. First send failed safely on a revoked SMTP password. **Off-device backup confirmed** on a second device. Auto mode used by operator decision; ADR-014 amendment pending. Future-dated FR rows observed (scheduled next-issue documents — not a defect).
- **Entry #038 (Sep 20):** Generator **v7** — counts verified against ground truth recomputed from source rows. **First clean verification since Aug 22; `--send` ungated.** v7's first run failed on a scope bug (a correct CMS-scoped "three notices" measured against the window's 21) that the unit tests missed by testing the wrong shape; `acceptable_counts()` fixes it. Audit of the clean run found `request` is not a tracked unit, so ICR counts are unchecked.
- **Entry #037 (Sep 20):** Generator **v6** — `SYSTEM_PROMPT` forbids tallying inputs. SNAP now names all 18 states instead of counting them; count warnings 3 → 1; `--send` still gated by one correct-but-forbidden tally. **A tolerance-based fix was implemented and reverted the same hour** after it demoted a real "15 states" fabrication (sources said 18) to a non-blocking note. Verifier untouched.
- **Entry #036 (Sep 20):** First review-only run in four weeks (exit 0, no truncation at `NUM_CTX=8192` with an 18-doc section, no fabrication). **Found `verify_claims()` flags correct arithmetic as unverified** — all three warnings were right; aggregate counts are derived, not quoted, so the check cannot validate them. This is why only one brief has ever sent. Fix proposed, not built. Also corrected a wrong call of mine: review `.txt` files are tracked deliberately, not a gitignore gap.
- **Entry #035 (Sep 20):** **Correction.** Entry #034 called the loss of off-device backup a regression from Option C. It was not — "Desktop & Documents" sync is off, so `~/Documents` was never an iCloud destination and **no off-device backup has existed since May 17**. `backup.sh` line 33 was false from the day it was written. Third instance today of *documented, plausible, and wrong*.
- **Entry #034 (Sep 20):** ADR-046 **F1 RESOLVED — Option C**: backups moved to `~/openclaw/backups`, sanctioned by ADR-040 §1, no TCC grant needed. **Reverses Entry #033's Option A** — granting FDA to `/bin/bash` would have exposed every §2-prohibited path to every shell script. Caught that `.gitignore` had no backup pattern before dumps could reach GitHub. Verified by live run. Accepted weakness: no off-device copy.
- **Entry #033 (Sep 20):** ADR-046 **F1 decided — Option A**. Backup destination reverted from `~/Documents` to the ADR-040 §1 sanctioned iCloud path; F6 resolved with it. Two other ADR-019 deviations confirmed permanent. **TCC grant and old-dump migration are outstanding operator actions.**
- **Entry #032 (Sep 20):** Dedicated-host assumption audit (**ADR-046**, OPEN). ADR-036 was not a one-off — **11 documents affected across 4 failure modes**. Found a live breach: `scripts/backup.sh` has written to `~/Documents`, a §2-prohibited path, nightly since May 17, with its own header comments still describing the compliant path. Also: ADR-032's NIST mapping asserts controls against the absent architecture, and ADR-033's memory alerts cannot fire on 16 GB. No remediation performed — F1 and F2 need operator decisions.
- **Entry #031 (Sep 20):** Governance. **ADR-036 SUPERSEDED by ADR-044** — VRAM policy for hardware never acquired; `sysctl iogpu.wired_limit_mb` verified 0, so it was never implemented and no remediation was needed. **ADR-040 AMENDED by ADR-045** — enforcement model, scope language, and a control reclassification: AC-3 downgraded from IMPROVED to NOT MET, with disclosure named as the real compensating control. `DATA_BOUNDARIES.md` → v2.0. Both source ADRs marked in place.
- **Entry #030 (Sep 20):** Four-week re-entry. Both scraper fixes proven across four weeks of unattended operation — reliability closed. 37 GB reclaimed (Docker images; 11 GB of abandoned git temp packs). **ADR-043 created** — production host platform decided: retain the MacBook Air, no hardware purchase, split the workloads instead. Found **ADR-036 unimplementable**. Git identity corrected from placeholder. **Third DATA_BOUNDARIES §2 breach disclosed.** Commit `7200b8e`.
- **Entry #029 (Aug 23):** Third repository directory `~/mac-mini-agent` found and removed; its unique 5-commit prototype history preserved as pushed tag `prototype-2026-04` first. Identified the Claude Code allowlist as an undocumented parallel permission surface ADR-040 does not reach. Commit `ef80e2c`.
- **Entry #028 (Aug 23):** `NEXT_SESSION_OPENER.md` retired and deleted; handoff consolidated into this file. Instructions v3.1 → v3.2. Commit `672bcc1`.
- **Entry #027 (Aug 23):** Stale `~/projects/mac-mini` clone deleted; 91-rule permission allowlist migrated first. Commit `05553b3`.
- **Entry #026 (Aug 23):** Instructions v3.0 deployed, superseding v2.0 (May 18). Commit `66414c7`.
- **Entry #025 (Aug 23):** This file refreshed after running 4 entries stale. Commit `0024b29`.
- **Entry #024 (Aug 23):** ADR corpus reconciliation Phase 0. Five ADR files fixed from plain-text-as-`.docx` (033–037); NIST document promoted to `ADR_032.docx`; twelve stub ADRs built; ADR-042 amended to correct the "AI Build" misattribution. Separately, isolated and fixed the silently-skipped nightly scrape (misfire grace 600s → 11100s) and rebuilt `fastapi` to schema v7. Commits `918b70e`, `7d3e863`, `5e8fafc`.
- **Entry #023 (Aug 22):** ADR-042 filed — ADR corpus fragmentation documented, status OPEN. Commit `b27beb4`.
- **Entry #022 (Aug 22):** Generator v5 — `--send`, iCloud self-send SMTP, verification gating, `brief_runs` audit table (schema 6 → 7). **ADR-039 H4 CLOSED.** Commit `a6b16f7`.
- **Entry #021 (Aug 22):** `verify_claims()` extended to dates, FR citations, counts. **ADR-014 OPEN → RESOLVED.** Commits `b0000ce`, `fa80ac8`.
- **Entry #020 and earlier:** see `changelog.md`.

---

## Handoff practice (changed August 23, 2026)

**This file is the single session-handoff document.** `NEXT_SESSION_OPENER.md` was retired and deleted on August 23, 2026 — recoverable from Git history (last version at commit `861f4d9`) if ever needed.

*Why:* the opener existed as a workaround for this file being unreliable, and it did carry that load. But once this file was brought current and the instructions designated it as *the* startup entry point, the opener became a second competing source of truth — two documents to keep accurate and two chances to drift. They had already drifted, in five separate places within a single day.

**Every session close ends with the operator uploading this file and `changelog.md` to the "Mac Mini" claude.ai project** (instructions v3.3, closing ritual step 8, operator decision September 30, 2026). This had not been happening, so the project's copies went stale. Method: remove the old copy, drag and drop from Finder (`~/openclaw`; the upload dialog offered stale copies), then check the "Last updated" entry number in the preview. Claude prompts for this after the push and does not call the session closed until it's confirmed. **Last upload: September 30, 2026, Entry #050** (both files). The project also holds operator-uploaded copies of the SSA TSSR v12.1 and CMS ARC-AMPE Vol. I v1.0.4 PDFs; they are not mirrored from disk (originals are in the operator's "SSA" and "IT Privacy and Security" projects).

**Do not recreate a separate opener document.** If session-start guidance needs to change, change it here. The corresponding discipline is step 7 of the session-closing ritual: update this file whenever state actually changes. A single accurate document beats two documents that disagree.

*A note for the next session, learned September 20:* this file went four weeks without an update and was wrong in three material places on re-entry — row counts, coverage dates, and a reliability status that had in fact been proven. **A stale handoff document is most dangerous precisely when the project has been dormant**, because that is when it is trusted most and checked least. Verify against the live system before trusting any number written here.

---

*Sheldon Wheeler — OpenClaw Personal Stack — CURRENT_STATE.md — the single handoff document, maintained at each session close.*
