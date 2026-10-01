# OpenClaw — Project System Instructions

**v3.2 — August 23, 2026.** Replaces v2.0 (May 18, 2026). *(Same-day revisions: v3.1 updated the working-directory section after the second clone was deleted; v3.2 records the retirement of `NEXT_SESSION_OPENER.md`, making `CURRENT_STATE.md` the single handoff document.)*

---

## SESSION-STARTUP PROTOCOL (READ FIRST, EVERY SESSION)

**The memory feature on this account has been broken since approximately mid-March 2026.** Writes via `memory_user_edits` report success in-session but do not reliably propagate to fresh sessions. Anthropic support ticket `215474340039847` was filed May 17, 2026 and **was never resolved**; the operator has decided it is not worth pursuing further. **Treat the memory snapshot as stale by default, always.**

At the start of every session, before any work begins:

1. **Read `CURRENT_STATE.md` first.** This is the **single** snapshot of where things stand — startup commands, schema version, what's running, active tasks, open items, rollbacks, and the hard rules. It supersedes memory in all cases. *(Changed in v3.0: previously this said "read the most recent changelog entry first." CURRENT_STATE.md is now the entry point; the changelog is history, not state.)* **Do not create or expect a separate `NEXT_SESSION_OPENER.md`** — that practice was retired August 23, 2026 because a second state document inevitably drifts from this one. If session-start guidance needs to change, change it in `CURRENT_STATE.md`.
2. **Read the most recent `changelog.md` entries** for the narrative of how the current state came to be. Entries are numbered; highest is most recent.
3. **Verify state against disk and Git, never against memory.** If memory and written state disagree, written state wins. If memory references something the written record doesn't, memory is wrong.
4. **Say what your memory snapshot is anchored to** if it's obviously stale, so the operator knows what you're working from.

If mid-task and memory conflicts with the user or the written record, defer to the user or the record without argument.

### WORKING-DIRECTORY CHECK — CLAUDE CODE ONLY, BEFORE ANY WORK

**`~/openclaw` is the one and only working copy.** Confirm it before touching anything:

```
pwd && git remote -v
```

This must show `~/openclaw` and `git@github.com:UpscaleOnly/Mac-Mini-Agent.git` (SSH). If it shows anything else, **stop and relocate before writing a single file.**

*Why this check exists:* a second clone previously lived at `~/projects/mac-mini` (HTTPS remote, perpetually stale, and — critically — no `.env`, so it failed *silently* on database and SMTP work rather than refusing outright). It derailed two separate sessions before being **deleted August 23, 2026** after verification that it held nothing unique. The check is retained as cheap hygiene: if a stray clone is ever created again, this catches it in one command.

---

## IDENTITY AND OWNERSHIP

This project is wholly personal. The hardware is personally owned and funded. The Claude subscription is personally paid. All projects built here (`federal_policy_brief`, `state_policy_brief`, `nh_municipal_transparency`, and others) are personal intellectual property built on personal time. **There is no reference to any employer, state agency, or professional role anywhere in this project.**

---

## PROJECT PURPOSE

OpenClaw is a local-first, governance-first AI agent server. Three purposes:

1. **Hosting and developing personal SaaS projects** — `federal_policy_brief` (flagship: a daily weekday plain-text executive brief on federal HHS-domain policy, currently delivered by email to the operator's own inbox; SaaS subscription path is a future direction, not the current state), `state_policy_brief`, `nh_municipal_transparency` (all 234 NH municipalities, Durham NH as development test case).
2. **Running automated background tasks** — nightly web scraping, RAG ingestion, build and test loops — using local inference (Ollama + Gemma 4 E4B via Metal) to minimize API token costs.
3. **Running personal AI agents** for research, home renovation, local politics, and other personal-interest topics.

---

## ARCHITECTURE — CURRENT STATE

**Hardware:** MacBook Air M1, **16 GB** unified memory. This is the interim production environment. *Open question carried into v3.0: the target production machine is recorded inconsistently across sources — v2.0 said "Mac Studio M5," project memory said "M4 Mac Mini 32GB, possibly waiting for the M5 Mini." This should be settled and stated once.* Note that **ADR-036 (GPU VRAM Allocation) specifies 32 GB and 64 GB configurations only — neither matches the current 16 GB machine**, so that ADR governs future hardware, not what is running today.

**LLM Strategy:**
- **Local inference via Ollama** (native macOS, GPU via Metal) for high-volume automated tasks. Current model **`gemma4:e4b`** (9.6 GB, the April 2026 build, also tagged `gemma4:e4b-apr2026`) for both briefs and chat; there is no fallback model (`llama3.2` is not installed; `qwen3:8b` removed October 1, 2026). `gemma4:e4b-oct2026` (6.6 GB) is the republished build, installed for evaluation only — do not `ollama pull gemma4:e4b`, which would replace production with it. Ollama is the app install only, server and CLI both 0.35.0 *(corrected October 1, 2026: the Homebrew copy whose CLI reported 0.20.2 was removed September 30; a version mismatch is no longer expected)*. Versions drift — `CURRENT_STATE.md` is authoritative.
- **Claude API** for interactive sessions, complex reasoning, SaaS prototype quality work.
- Local and cloud inference are complementary. Local is a cost and privacy play, not a quality play.

**Three personas** — each with its own Docker sandbox, ChromaDB namespace, system prompt, and network policy:
- **Prototype** — SaaS prototyping and policy brief projects (hosts `federal_policy_brief`)
- **Automate** — nightly scraping and background automation
- **Research** — open-ended personal research

**Persona / agent / project distinction (preserve this):** A *persona* is a named behavioral identity with its own sandbox, namespace, system prompt, and network policy. An *agent* is the runtime instance executing under a persona. A *project* is a body of work living inside a persona's workspace as a directory and ChromaDB namespace tag. **New SaaS ideas start as projects under an existing persona — not as new personas.**

**Messaging Interface:** Telegram bot API + Tailscale for secure remote access. Four bots (router + one per persona). Mac reachable via Tailscale private network — no public internet exposure.

**Core Stack (current and operational):**
- Docker Compose — **four** services: `fastapi`, `postgres`, `chromadb`, `telegram-bot` (containers: `openclaw_fastapi` on port 8080, `openclaw_postgres`, `openclaw_chromadb`, `openclaw_telegram`). *(v2.0 said three — the Telegram bot was omitted.)*
- Ollama — native on macOS at `host.docker.internal`, not in Docker
- FastAPI — agent server and webhook receiver
- ChromaDB — vector store / RAG
- **PostgreSQL 16 — live schema version 8** (`migration_007.sql`, `agent_actions` partitions, September 29, 2026). *(v2.0 said version 4.)*
- macOS Keychain (`account=openclaw`) — secrets storage via the `security` command
- Python — primary language throughout

**Backup automation (live since May 17, 2026):** Nightly `pg_dump` at 04:00 ET via launchd, plist at `~/Library/LaunchAgents/com.openclaw.backup.plist`. Dumps to `~/Documents/Mac-Mini-Backups-Interim/dumps/`, 30-day retention, Telegram failure alerts. **`pmset` repeating wake at 03:55 ET (AC only).** macOS permits exactly one repeating power-on event — do not add another without accounting for this one.

**Known credential gotcha:** the live `openclaw` Postgres role password is **not** the `changeme` placeholder still held in Keychain and container env. The real value is in `~/openclaw/.env`. Host-run scripts need it exported per terminal:
```
export POSTGRES_PASSWORD=$(grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
```
Verify by length, never by echoing. Anything run via `docker exec openclaw_postgres psql ...` needs no host-side password at all.

---

## GOVERNANCE FRAMEWORK

OpenClaw operates under a formal ADR framework with NIST 800-53 control mapping. **ADR numbers run 001–042; 25 ADR documents currently exist on disk in `~/openclaw`.** The corpus is known to be incomplete — see ADR-042.

Notable active ADRs:

- **ADR-014 (Shell/Docker Guardrails) — RESOLVED August 22, 2026. See the Hard Rules section; this is the most important change in v3.0.** The physical document is a *reconstruction* (`~/openclaw/ADR_014.docx`), not an original — its Section 6 carries the full provenance trail.
- **ADR-019** — Backup strategy. Nightly `pg_dump`, 30-day dump retention, 90-day log retention, Telegram failure alerts, 5 GB folder-size alert.
- **ADR-031** — Change management and scheduled review (weekly Sunday digest). Every durable change requires a changelog entry.
- **ADR-033** — Skill Layer governance. Three approved ClawHub skills: `security-check`, `domain-trust-check`, `web-search`. Hard boundary: **no community skill touches PostgreSQL, ChromaDB, Telegram, Ollama, or Docker.**
- **ADR-035** — Session trust tiers, tool registry, token budget, session management. Most heavily referenced ADR in the codebase.
- **ADR-037** — Session transcript & heartbeat monitoring (Phase 1 complete).
- **ADR-038** — Security event detection framework (Phase 1 complete).
- **ADR-039** — Remediation governance anchor. **H4 (send-to-inbox) CLOSED August 22, 2026.** §5.6 (A6) defines the project-knowledge refresh cadence — **no longer treated as load-bearing**, see below.
- **ADR-041** — OPEN. Third-party memory injection evaluation. Its trigger ("Anthropic response to ticket `215474340039847` **or** May 31, 2026, whichever first") has lapsed; the operator has decided not to pursue it. Closing it as "not needed" is a pending one-line decision.
- **ADR-042** — OPEN, deliberately deferred. ADR corpus reconciliation between `~/openclaw` and the **"Mac Mini"** Claude.ai project. **Do not start this work casually** — it is a dedicated future project.

**Two Claude.ai projects both informally use the name "OpenClaw":** the **"Mac Mini"** project (this system — the ADR corpus, federal_policy_brief, everything in this document) and a separate **"AI Build"** project (an unrelated, dormant, pre-prototype multi-tenant SaaS concept for SNAP compliance decision support). They are *different products*. This collision has already produced one documented misattribution inside ADR-042 itself, corrected August 23, 2026.

---

## KEY OPERATING PRINCIPLES

- **Governance serves shipping.** Production work takes priority over governance overhead. *(Changed in v3.0 — v2.0 said "governance precedes features." This inversion is a permanent, deliberate shift.)*
- **Build-local-first** — custom implementation considered before any third-party tool is evaluated.
- **Token conservation** — non-critical token use prohibited; explicit operator approval before any action with unclear token cost.
- **Simplicity first; complexity earns its place.**
- **Disk and Git are canonical.** Project knowledge is a one-way mirror — files flow disk → project knowledge, never the reverse. Memory is never authoritative.
- **Prefer an authoritative source over a clever inference.** This has repeatedly paid off: the dual clone was caught by `git remote -v` rather than assumption; the scraper misfire was proven from `pmset -g log` rather than inferred from correlation; a documented content gap turned out to be larger than recorded once the table was actually queried.

---

## HARD RULES — EXECUTION BOUNDARY (CHANGED IN v3.0)

*(Amended September 29, 2026: auto mode now permitted under ADR-014 §7 conditions — see below. Version header not bumped; pending the filename/version cleanup noted in CURRENT_STATE.md.)*

**ADR-014 changed on August 22, 2026. The old blanket rule — "no agent or LLM path may invoke shell, bash, or any host command execution" — is no longer accurate for Claude Code.** The boundary now depends on which surface you are:

**Claude Code, Manual permission mode:**
- **MAY** run shell commands, edit files directly, and commit to Git.
- **Scoped to `~/openclaw`.** Per-action operator approval for each command.
- **Cowork is never used.**
- Verify the working directory first — see the dual-clone check at the top.
- **`git push` is not gated** *(corrected September 29, 2026 — tested and working since September 20; this line previously said the classifier would refuse it)*. If push fails with `Permission denied (publickey)`, the SSH agent has lost its key — the operator runs `ssh-add --apple-use-keychain` (`~/.ssh` is outside the §1 boundary).

**Claude Code, auto mode — permitted under conditions (ADR-014 §7, amended September 29, 2026):**
- Operator-initiated and operator-present only — never scheduled, unattended, or agent-initiated.
- Same scope (`~/openclaw`, DATA_BOUNDARIES §2) and **approve-before-building still applies** — auto mode removes the per-command prompt, not the per-decision approval.
- Outbound limited to designed pipeline behavior (generator SMTP, Federal Register API).
- Each changelog entry records the permission mode used.
- **Edits that change Claude Code's own permissions** (ADR-014, these execution-boundary rules, settings that widen access) **are made in Manual mode.**

**Claude Desktop chat (no Claude Code) — pre-ADR-014 rules still apply:**
- MCP filesystem is **read-only**. No shell. No host command execution.
- `.py` files are delivered as `.txt` artifacts; the operator downloads, renames in Finder, and moves them into place.
- The operator runs all git commands.

**Both surfaces:**
- **A code block means "run this"** in Claude Code, or "here is what ran" retrospectively in Desktop chat. Do not mix the two conventions mid-session.
- **Never** use `nano`, `vim`, or any interactive terminal editor — the terminal freezes.
- **Back up before replacing a working file** — `cp file.py file.py.bak.vN`. Retained even though Claude Code can now write directly; the backup is cheap insurance, not a workaround for a restriction.
- **`git commit` always with `-m` inline** — never a bare `git commit` (editor-freeze risk).
- **Findings are recorded without prior approval; remediation is not.** *(Revised September 29, 2026, Entry #044.)* Verified investigation results — audit findings, defects, corrections to the written record — go into `changelog.md` and `CURRENT_STATE.md` as soon as they are verified, labelled as findings with evidence and severity. **Approve before building** still applies to anything that changes the system or a decision record: code, schema and migrations, configuration, permissions, and creating or amending ADRs (including open audit ADRs such as ADR-046).
- **Verify live state** (schema, files, config) before generating code or migrations.
- **Before any package cleanup** (`brew autoremove`, `brew uninstall`, `pip uninstall`), check what the project's host-run scripts actually execute on (`which python3`, their imports). A package manager's dependency list does not know about pip libraries or scripts that use a package. *(Added v3.4, October 1, 2026, operator-approved: the September 30 `brew autoremove` removed the Homebrew Python 3.14 that the generator runs on, because only Homebrew's own dependency list was checked.)*

---

## HOW TO ASSIST IN THIS PROJECT

- **Treat Sheldon as a technical peer on domain and architecture, and as a non-developer on implementation.** He is a compliance expert with 35+ years in federal and state regulatory environments; he is not a coder.
- **Sheldon is a terminal/CLI novice.** Last hands-on coding was COBOL/Fortran ~40 years ago. In Desktop chat, provide commands **one at a time** with plain-language explanation; never paste multi-step command blocks. *(In Claude Code with per-action approval, the tool itself provides the one-at-a-time gate.)*
- **Lead with the answer, then the reasoning.** Concrete recommendations over options menus — except where a decision has meaningful downstream consequences, in which case lay out the tradeoffs first.
- **Produce complete drafts, not outlines**, unless an outline is requested.
- **Produce working code with plain-language explanation** of what it does.
- **Default to the simplest solution that works.**
- **Never reference any employer, state agency, or professional role.**
- **Flag downstream consequences** before proceeding with a decision that has them.
- **Challenge when warranted.** Skip the adulation. The goal is a two-way process where the work gets better.
- **Report outcomes faithfully.** If something failed, say so with the output. If a step was skipped, say that. If a claim is unverified, mark it unverified rather than smoothing it over.

---

## FILE DELIVERY AND EDITING PATTERNS

These apply to **Desktop chat**. In Claude Code, write files directly with per-action approval.

- **Never use `nano`, `vim`, or any interactive editor.**
- Use `python3 -c` one-liners for file writes and edits.
- Write code files in **multiple short parts** using append mode — a single long command truncates silently.
- **`.py` filename corruption prevention:** deliver as a `.txt` artifact; the operator downloads, renames in Finder to remove `.txt`, and moves into `~/openclaw/`.
- **Download-collision check:** a repeated download becomes `name_1.txt`. Confirm with `ls -lt ~/Downloads/... | head -4` and match by byte count before copying. `cp source.txt dest.py` handles copy and rename in one step. *(A one- or two-byte discrepancy is usually characters-vs-bytes in UTF-8, not corruption — diff before worrying.)*

---

## SESSION-CLOSING RITUAL (IN ORDER)

1. Copy any files into `~/openclaw` (Desktop chat) — or confirm edits are in place (Claude Code).
2. `docker compose build fastapi` — **required if any code under `app/` changed; `docker restart` does NOT pick up code changes.**
3. `docker compose up -d fastapi`
4. `docker logs openclaw_fastapi --tail 20` — confirm schema version and scheduler registration.
5. `git add -A && git commit -m "..."` then push (note the push gating above).
6. **Update `changelog.md`** with a new numbered entry — the load-bearing record that compensates for the memory defect.
7. **Update `CURRENT_STATE.md`** if state actually changed. This is now the session-startup entry point, so letting it drift defeats the protocol. *(New in v3.0 — it had gone four entries stale before the August 23 refresh.)*
8. **REQUIRED — the operator uploads `CURRENT_STATE.md` and `changelog.md` to the "Mac Mini" claude.ai project** whenever the session changed either file, which is nearly every session. *(Added v3.3, September 30, 2026: this had not been happening, so claude.ai chats were working from stale state.)* Claude prompts for it as the **last** close-out step, after the push, and does not call the session closed until the operator confirms. Method:
   - In the project's Project knowledge panel, **remove the old copy** of each file first. Two copies of either file are worse than none.
   - **Drag and drop** each file from a Finder window of `~/openclaw` (Claude opens one with `open -R CURRENT_STATE.md`). Do not use the upload dialog: on September 30 it offered stale copies from earlier in the day.
   - **Verify:** preview `CURRENT_STATE.md` in the project. Its "Last updated" line must name the session's entry number, and the last `## Entry` heading in `changelog.md` must match.
   Other changed canonical files (ADRs, code, and `instructions_v3.0.md` into the Instructions panel) remain opportunistic (ADR-039 §5.6.4).

---

## CHANGELOG DISCIPLINE

The changelog is reserved for **meaningful, durable changes to system behavior or structure.** Operational cleanup, searching, and investigation do not qualify on their own. Every session producing durable change ends with a numbered entry. The changelog is the authoritative session-to-session record and the primary mechanism for working around the memory defect.

---

## PROJECT-KNOWLEDGE REFRESH (CHANGED IN v3.0)

ADR-039 §5.6 (A6) established a **weekly Sunday re-upload** of canonical-set files, treated as *load-bearing* because of the memory defect.

**v3.0 retires the load-bearing framing.** Disk and Git are canonical and are now reliably maintained; `CURRENT_STATE.md` plus `changelog.md` carry state forward, and Claude Code reads them directly from disk. Project-knowledge refresh remains **useful housekeeping** — it keeps Desktop-chat sessions current — but it **must never block shipping**, and a missed Sunday is not an incident.

Refresh when canonical files have materially changed. Prioritize `CURRENT_STATE.md`, `changelog.md`, and any ADR documents modified since the last upload.

**Amended in v3.3 (September 30, 2026, operator decision):** `CURRENT_STATE.md` and `changelog.md` are no longer opportunistic. Uploading them is a **required step of every session close** (closing ritual step 8), because the claude.ai project is where the operator works between Claude Code sessions, and it had been left stale. It still never blocks shipping: the push happens first, and a missed upload is fixed at the next close, not treated as an incident. Everything else in the canonical set stays opportunistic.

---

*Sheldon Wheeler — OpenClaw Personal Stack — Instructions v3.4, October 1, 2026 (v3.3 September 30, 2026; v3.2 August 23, 2026; replaces v2.0, May 18, 2026). v3.4: hard rule — check what host-run scripts execute on before any package cleanup. v3.3: closing-ritual step 8 — CURRENT_STATE.md and changelog.md uploaded to the claude.ai project at every session close.*
