# OpenClaw — CURRENT STATE

*Read this first, every session. This is the snapshot of where things stand right now.*
*Standing rules and how-to-assist live in the project instructions. Full session-by-session history lives in `changelog.md`.*

**Last updated:** September 20, 2026 (Entry #038 — generator v7: ground-truth count verification; FIRST CLEAN VERIFICATION SINCE AUG 22, send path ungated)
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

- `generate_brief_review.py.bak.v4` — working v4 (pre-v5: review-only, no `--send`, no SMTP, no `brief_runs`). Also `.bak.v3`, `.bak.v2`, `.bak.v0`; each file's header comment says what it lacks.
- `app/scheduling/scheduler.py.bak.pre-misfire-fix` — pre-August-23 scheduler (10-minute misfire grace).
- `ADR_033.docx.bak.plaintext-format` … `ADR_037.docx.bak.plaintext-format` — the original plain-text-as-`.docx` files, pre-conversion.
- `ADR_042.docx.bak.pre-amendment-2026-08-23` — pre-"Mac Mini" correction.
- `ADR_036.docx.bak.pre-supersede-2026-09-20` — before the SUPERSEDED marking.
- `ADR_040.docx.bak.pre-amendment-2026-09-20` — before the ADR-045 amendment annotation.
- `DATA_BOUNDARIES.md.bak.pre-adr045` — v1, before the v2.0 rewrite.
- `scripts/backup.sh.bak.pre-adr046-f1` — the working interim version (writes to `~/Documents`). Restores a functioning backup if the TCC grant proves impractical.
- `CURRENT_STATE.md.bak.pre-entry030` (this file's previous version), `CURRENT_STATE.md.bak.aug20`.
- `changelog.md.bak.pre-entry030`, `changelog.md.bak.session21`, `changelog.md.bak.pre-entry020`.
- **All `.bak*` files are gitignored** — they exist on disk only. Anything tracked is recoverable from Git instead: `git show <commit>:path/to/file`.
- **`migration_006.sql` has already been applied live — do not re-run it.** A second run is a no-op (`CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`), but confirm `schema_version` first if in doubt.

## Schema

Live PostgreSQL schema is **version 7** (`migration_006.sql` — `brief_runs` table; ADR-039 H4 send-wiring). `openclaw_fastapi` was rebuilt August 23 and logs `Schema version OK — live database is at version 7 (required 7)`.

## What's running / operational

- **Docker:** four containers — `openclaw_fastapi` (port 8080), `openclaw_postgres` (PostgreSQL 16), `openclaw_chromadb`, `openclaw_telegram`.
- **Ollama:** native on the host (`host.docker.internal`), model **`gemma4:e4b`** (`llama3.2` is the lightweight fallback). `NUM_CTX = 8192`.
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

- Coverage **April 24 → September 18, 2026**, all `project = 'federal_policy_brief'`. **526 rows total: 502 `is_new = TRUE`, 24 consumed** by the August 22 send.
- **69 rows `is_new = TRUE` in the trailing 7-day window** as of September 20.
- **Every query MUST filter `WHERE project = 'federal_policy_brief'`** — the table is project-scoped.
- `raw_content` is **title + abstract only** (~569 chars avg). Brief depth is abstract-level by design of the current scraper.
- ⚠️ **Unbackfilled historical gap: August 4–16, 2026 — still zero documents.** Roughly nine missing weekdays. It predates the Entry #020 catch-up logic, so it was never self-healed and **will not heal on its own** — the catch-up window computes from the last successful run, which has long since moved past it. Recoverable only by an explicit backfill.
- No content is expected Saturdays, Sundays, or federal holidays.

## federal_policy_brief — where the generator stands

`~/openclaw/generate_brief_review.py` is at **v7**. Rollbacks preserved: `.bak.v6`, `.bak.v5`, `.bak.v4`, `.bak.v3`, `.bak.v2`, `.bak.v0`.

**Default mode (no flags) remains review-only and side-effect-free** — sends nothing, marks nothing processed, writes no `brief_runs` row, safe to re-run indefinitely. Verified byte-identical to v4 on that path.

**`--send` (new in v5)** additionally emails the brief, flips `is_new = FALSE` on consumed rows, and writes one `brief_runs` audit row:

- Self-send SMTP via `smtp.mail.me.com:587`, STARTTLS, credentials from macOS Keychain at send time — never through a chat session. No ESP, no purchased sender domain (ADR-039 H4 sub-decision: unnecessary at an audience of one).
- **Gated on `verify_claims()` returning zero warnings.** An unverified claim blocks the email entirely — independent of the `HARD_FAIL_ON_UNVERIFIED` switch, which governs only review-mode print-vs-abort.
- `is_new` flips **only after a successful send**, so a failed send leaves rows eligible for retry rather than silently dropping them.

`HARD_FAIL_ON_UNVERIFIED` is still **`False`** (line ~195). 🔴 **DO NOT flip it to `True` until the count defect below is fixed** — it would convert a false positive into a hard abort.

✅ **Counts verified against ground truth — send path UNGATED (v7, Entry #038).** `ground_truth_counts()` recomputes documents, notices, rules, agencies and distinct US states from the rows the model was given; `verify_counts()` verifies a match, warns with the real figure on a mismatch, or warns as unverifiable where no ground truth exists (durations land there). **The Sept 20 run verified clean — the first since Aug 22.**
  **Scope subtlety, learned the hard way:** the executive summary makes section-scoped claims in a global context ("CMS issued three notices" — true of CMS, false of the window). `acceptable_counts()` therefore accepts any single section's count or the whole for the summary only; per-section checks stay exact. v7's first run failed on precisely this and the unit tests had passed, because they tested the wrong shape.
  ⛔ **Do not re-attempt tolerance-based approaches.** Treating counts ≤ the document count as non-blocking was tried and reverted the same hour after it demoted a real "15 states" fabrication (sources said 18) to a note. Two runs, identical input, 18 (right) and 15 (wrong) — **the model does fabricate counts, and no magnitude heuristic separates them.**
  ⚠️ **Known coverage gap:** `_UNIT_PAIRS` has no `request` entry, so "two information collection requests" is **not checked at all**. It was correct in the clean run, but it passed by not being examined. Add `request` with ground truth from instrument labels.

⚠️ **The pipeline has delivered exactly one brief, ever** — the August 22 verification send. The blocker is now removed: verification runs clean as of Sept 20, so `--send` would proceed. The next live send will be only the second ever. **Keep `HARD_FAIL_ON_UNVERIFIED` at `False` until at least two further clean runs.**

**Run evidence is version-controlled.** `federal_policy_brief_review_*.txt` files are tracked deliberately, each committed alongside the generator version that produced it (`20d4951` v0, `b0000ce` v4, and now the v5 run). Do **not** gitignore them — they are the behavioural record.

## Active task (in order)

1. **[Next]** **A second `--send` run** — the path is ungated for the first time since Aug 22. Builds toward the `HARD_FAIL_ON_UNVERIFIED` flip, which still needs two more clean runs. *(Ground-truth verification is DONE — Entry #038.)*
2. **[Next]** 🔴 **Establish an off-device backup** — none has existed since May 17; this is a four-month gap, not a new one.
3. **[Then]** **Decide ADR-046 F2 scope** — re-assess four NIST controls, or the full Moderate baseline.
4. **[Then]** Implement **ADR-045 §8.2 and §8.3** — remove the home-wide `Read` grant; build the traversal-verb hook.
5. **[Then]** **Extend the dedicated-host audit to code, scripts and launchd config** — F1 was found in a script, not an ADR.
6. **[Then]** Backfill the August 4–16 content gap (explicit `days_back`, or a targeted Federal Register API pull).
7. **[Then]** Build `--send` confidence toward flipping `HARD_FAIL_ON_UNVERIFIED` to `True`.
8. **[Then]** Refresh the local model — `gemma4:e4b` is five months old; a current model in the same size class is likely the highest-value zero-cost improvement available.
9. **[Opportunistic]** Output polish: ISO dates in reader-facing prose; executive summary running long; ORR-under-TANF routing (a scope decision, not a bug).
10. **[Opportunistic]** Rebuild project knowledge as a clean one-way mirror of disk.

## Top open items

- ✅ **BACKUP PATH — RESOLVED September 20 (ADR-046 F1, Option C).** Backups now write to `~/openclaw/backups`, already sanctioned by ADR-040 §1 — no boundary crossing, no TCC grant, no policy amendment. **Verified by live run:** 148 KB dump, `gunzip -t` clean, 39 table/data statements, invisible to git.
  **Option A (grant TCC) was chosen first and reversed.** TCC attributes access to the *executing binary*, so for a shell script the grant target is `/bin/bash` — which would give every bash script on the machine full read/write access to `~/Documents`, `~/Desktop` and the FTI-bearing iCloud root. Broader exposure than the violation it fixed. TCC also cannot be automated: `tccutil` only resets, the databases are SIP-protected, and PPPC profiles need MDM (this host is not enrolled).
  **Two follow-ups remain:**
  1. 🔴 **NO OFF-DEVICE BACKUP — and there has not been one since May 17 (Entry #035 correction).** "Desktop & Documents Folders" sync is **OFF** on this host: `~/Documents` is a plain local directory, and the symlink in the CloudDocs container points *outward* at it, which iCloud does not follow. `scripts/backup.sh` line 33 claimed "same iCloud destination" and was false from the day it was written. **Every nightly dump for four months went to the same physical disk as the database.** Option C cost nothing — this gap pre-dates it. A disk failure or lost laptop takes the database and all its backups together. Data is public Federal Register content and re-scrapable, but `brief_runs` history and ~5 months of curation are not. **148 KB per dump — fix with `scp`/`rsync` to a remote host, a private repo (ADR-030 egress applies), or an external drive. Verify by checking the destination, not by reading a comment.**
  2. **Old dumps still in `~/Documents/Mac-Mini-Backups-Interim`** — operator action, §2-prohibited so not touchable from a session. §2 is closed for new writes only.
  **Rollback:** `scripts/backup.sh.bak.pre-adr046-f1`.

- **ADR-032 NIST mapping asserts controls against the absent architecture (ADR-046 F2, HIGH).** AC-11 dismissed as "not meaningful for headless daemon operation" on a laptop with a screen; AC-18 assessed expecting WiFi disabled; SA-2 MET citing 32 GB against 16 GB; AC-6 MET citing an `openclaw` account that does not exist. **AC-11 and AC-18 err toward understating obligation.** Decide whether to re-assess the four named controls or the full Moderate baseline — they were found by targeted search, not review, so others are likely.

- **ADR-033 memory alerts can never fire (ADR-046 F3, MEDIUM).** Thresholds are 28 GB yellow / 30 GB red against "Total 32GB". On 16 GB they report healthy under every condition including genuine exhaustion. Silently dead control; also references a 32B model that is not deployed.

- **Dedicated-host audit — 11 documents affected, 4 failure modes (ADR-046, OPEN).** ADR-036 was not a one-off. Beyond F1–F3: "Mac Studio setup day" is a live scheduling target in ADR-031/038/039/041 (work stalled, nothing marks it unreachable — including ADR-039's Keychain item, which is the same item as F1); and the openclaw/admin/dev account model assumed by ADR-020/033/034/035/038 does not exist. **The audit covered ADR documents only — F1 was found in a script, so the class size is still unknown.** Extending it to code, scripts and launchd config is an open item.

- **Filesystem boundary — decided September 20 (ADR-045), implementation pending.** DATA_BOUNDARIES.md §2 has been breached three times (Session 16, Entry #029, Entry #030). ADR-045 amends ADR-040 with an enforcement model and — more importantly — corrects the control classification: **AC-3 was overstated as IMPROVED and is NOT MET** until a technical control ships. PL-4 and AU-6 are accurate; the real compensating control is **disclosure**, since all three breaches were self-reported rather than detected. `DATA_BOUNDARIES.md` is now **v2.0** with §2.1 (binds all execution surfaces), §2.2 (listing and traversal prohibited, not just reading), §6 (enforcement posture) and §7 (governed artifacts).
  **Structural finding:** Claude Code matches Bash rules against *command strings*, not the paths they reach — `Bash(du:*)` permits `du` anywhere. **Shell is unbounded by construction**, so every path-scoped `Read(...)` rule is irrelevant when the same data is reachable through a shell command.
  **Still to implement:** ADR-045 §8.2 and §8.3 below.

- **ADR-045 §8.3 — traversal-verb hook, not yet built.** A PreToolUse hook gating `du`, `find`, `ls -R`, `grep -r`, `tree`, `mdfind`, `locate` when not explicitly scoped to `~/openclaw`. It must match on **commands, not path literals** — a path blacklist would not have caught `cd ~ && du -sh */`, which contains no prohibited path. Verify hook mechanics against the live settings schema before building. **It is a speed bump, not a boundary** — document it as such.

- **`Read(//Users/sheldonwheeler/**)` remains in the Claude Code allowlist** — carried from Entry #029, now formally pending removal under **ADR-045 §8.2**. It pre-authorises reads across the entire home directory including all three §2-prohibited paths; the narrow `Read(//Users/sheldonwheeler/openclaw/**)` replacement already exists alongside it. `.claude/settings.local.json` is now a **governed artifact** under DATA_BOUNDARIES §7 — but it is gitignored, so the contradiction never appears in a diff and must be inspected manually at each review.

- **`~/Documents/Mac-Mini-Backups-Interim`** — carried from Entry #029, unexamined, inside a §2-prohibited path. Either it predates ADR-040 and needs migrating, or it is an undocumented second backup destination.

- **PostgreSQL credential reconciliation — open since Aug 20.** The live `openclaw` role password is **NOT** the `changeme` placeholder. The real value lives in `~/openclaw/.env`; container env and Keychain both still hold the stale placeholder. *Read it without echoing it:* `export POSTGRES_PASSWORD=$(grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)` — needed in every new Terminal window for host-run scripts. Anything via `docker exec openclaw_postgres psql ...` needs no host-side password at all.

- **ADR corpus — materially improved Aug 23, not finished.** 29 ADR `.docx` files now on disk (ADR-043, 044, 045, 046 added September 20). **Still unrecovered: ADR-017 and ADR-022** (both cited in live code, zero content found anywhere). No evidence at all for ADR-001, 004, 006–013, 015, 016. Full picture: `adr_fragments_2026-08-22/reconciliation_2026-08-23/`.

- **ADR-042 (ADR corpus reconciliation) — OPEN, still deferred.** The counterpart Claude.ai project is **"Mac Mini"**, not "AI Build" (corrected by dated amendment Aug 23). Full reconciliation remains a dedicated future project — do not start it casually.

- **Two Claude.ai projects share the "OpenClaw" working name** — "Mac Mini" (this system) and "AI Build" (an unrelated pre-prototype SaaS concept). This collision has already caused one documented misattribution. Consider renaming one.

- **Git identity was placeholder text until September 20.** `~/.gitconfig` held literal `YourGitHubUsername` / `YOUR-NOREPLY-ADDRESS@users.noreply.github.com`, so **the entire commit history before Entry #030 is attributed to a stub**. Now set to `Sheldon Wheeler` / `UpscaleOnly@users.noreply.github.com`. If commits do not link to the GitHub account, the `<ID>+UpscaleOnly@users.noreply.github.com` form is required — ID at github.com/settings/emails. Historical commits not rewritten.

- **Instructions — content is at v3.2; the file is still named `instructions_v3.0.md`.** Source of record on disk: `~/openclaw/instructions_v3.0.md` (amended through v3.2 in place). Keep that file and the live claude.ai panel in step; if they diverge, the disk copy is canonical. **The filename/version mismatch is itself a small drift hazard** — rename or add an explicit version header when convenient. Most important content change: v2.0's blanket "no shell/bash from any agent path" rule is replaced with the surface-dependent ADR-014 boundary. Still open inside v3.2: it runs ~65% longer than v2.0 (2,478 vs 1,502 words), a standing token cost on every conversation.

- **ORR routes to TANF** — the Burke Law Group withdrawal is an Office of Refugee Resettlement notice, routed to TANF because both sit under the Children and Families Administration. Fixing it means deciding where ORR content belongs. Scope decision, not a defect.

- **ADR-041** (third-party memory injection) — trigger long passed, ticket confirmed never resolved and not worth chasing. Remains formally OPEN; closing it as "not needed" is a one-line decision whenever convenient.

- **Project-knowledge rebuild** — clean one-way mirror of disk, including this file.

- **The context ceiling — RESOLVED, but remember why.** Ollama defaulted `gemma4:e4b` to 4096 tokens for prompt and response combined. A 19-document section overran it. Entry #018 recorded this as "oversized section degradation" and proposed significance-ranking; that diagnosis was wrong — it was a config default. `NUM_CTX = 8192` now. **Available memory, not the chip, is what caps this** — the pipeline's four containers share the same 16 GB. Ranking may still be wanted editorially, but do not build it as a fix for truncation. Watch `NUM_CTX` if `WINDOW_DAYS` ever rises.

- **Ctrl+C does not interrupt in Terminal** — dead for months. Low urgency.

- **Disk cleanup — largely done September 20.** Reclaimed 37 GB (93% → 76% full; 15 GiB → 52 GiB free): Docker images 29.58 GB → 2.055 GB, and `.git` 11 GB → 1.1 MB after `git gc --prune=now` cleared two abandoned temp pack files. Remaining minor: `docker builder prune` (~197 MB), one unreferenced Docker volume (~49 MB — verify it is not an orphaned Postgres volume first), and `old_skeleton/` (untracked dead code that still carries the only references to ADR-011, 012, and 016 — read before deleting).

## Hard rules (safety quick-reference — full versions in instructions)

⚠️ **ADR-014 changed on August 22 — the old "no shell, ever" rule is no longer accurate for Claude Code.**

- **Claude Code in Manual permission mode MAY** run shell commands, edit files directly, and commit to Git — **scoped to `~/openclaw`**, with per-action operator approval. **Auto mode is never used. Cowork is never used.** (ADR-014, RESOLVED; reconstructed document at `~/openclaw/ADR_014.docx`, provenance in its Section 6.)
- **Read `DATA_BOUNDARIES.md` §2 before any command touching paths outside `~/openclaw`.** A glob is a directory read. A `du` is a directory read. The policy binds interactive shell commands, not only application code. Three breaches to date.
- **A plain Claude Desktop chat session still follows the pre-ADR-014 rules:** MCP filesystem read-only, no shell, `.py` files delivered as `.txt` for manual copy, operator runs all git commands.
- **A code block in chat means "run this"** (Claude Code) or "here is what ran" (Desktop chat, retrospectively). Don't mix the two conventions mid-session.
- **Never** use `nano`, `vim`, or any interactive terminal editor (freezes the terminal).
- **Back up before replacing a working file** — `cp file.py file.py.bak.vN`. The backup is cheap insurance, not a workaround.
- **`git commit` always with `-m` inline** — never a bare `git commit`.
- **`git push` is NOT gated — corrected September 20, 2026.** This file previously stated that push "will be refused even when explicitly requested." It was tested directly on that date and succeeded (`28d7edf..eb99ebd`). The claim may have been true when written; it is not true now. Every earlier push this session was run by the operator on the strength of the stale note, which is exactly how a false claim survives. Test before repeating a documented restriction.
- **Token conservation**; **approve before building**.
- **Verify live state** (schema, files, config) before generating code or migrations. **Prefer an authoritative source over a clever inference** — this keeps paying off: the dual clone was caught by `git remote -v`; the scrape misfire was proven from `pmset -g log`; the 11 GB in `.git` turned out to be garbage rather than history only because `git count-objects -vH` was run instead of assuming; and `Docker.raw` reports 228 GB apparent against 3.0 GB actual, so `ls -lh` on it misleads by two orders of magnitude.

## Recent history (most recent first)

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

**Do not recreate a separate opener document.** If session-start guidance needs to change, change it here. The corresponding discipline is step 7 of the session-closing ritual: update this file whenever state actually changes. A single accurate document beats two documents that disagree.

*A note for the next session, learned September 20:* this file went four weeks without an update and was wrong in three material places on re-entry — row counts, coverage dates, and a reliability status that had in fact been proven. **A stale handoff document is most dangerous precisely when the project has been dormant**, because that is when it is trusted most and checked least. Verify against the live system before trusting any number written here.

---

*Sheldon Wheeler — OpenClaw Personal Stack — CURRENT_STATE.md — the single handoff document, maintained at each session close.*
