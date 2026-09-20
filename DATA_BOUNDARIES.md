# DATA_BOUNDARIES.md
# OpenClaw Filesystem Boundary Policy
# Governing ADR: ADR-040 | Established: April 19, 2026 | Status: DECIDED
# Version 2.0 — Amended September 20, 2026 by ADR-045 (enforcement, scope, control classification)

---

## 1. What OpenClaw May Touch

| Path | Access | Purpose |
|------|--------|---------|
| `~/openclaw` | Read / Write / Execute | Primary working directory. All code, config, logs, and migration files live here. |
| `~/Library/Mobile Documents/com~apple~CloudDocs/Mac-Mini-Backups/` | Write only | Sole iCloud backup destination. PostgreSQL pg_dump output only. |
| `~/Downloads` | Read only | Staging area for files the operator intentionally moves into OpenClaw workflows. |

---

## 2. What OpenClaw May Never Touch

| Path | Why |
|------|-----|
| `~/Library/Mobile Documents/com~apple~CloudDocs/` (root) | Contains Federal Tax Information (FTI), personal financial documents, legal documents, and family records. No agent or process may read, list, or write here. |
| `~/Documents` | Personal document store. Prohibited at current phase. |
| `~/Desktop` | Personal workspace. Prohibited at current phase. |
| `~/Library` (except Mac-Mini-Backups) | System and application support files. No agent traversal permitted. |
| All other paths not listed in Section 1 | Prohibited by default. A new ADR amendment is required before any code touches them. |

**Default rule: if a path is not in Section 1, it is prohibited.**

### 2.1 What this binds *(added v2.0, ADR-045)*

This prohibition binds **every execution surface**, not only application code:

- OpenClaw application code, scrapers, and skills
- Scheduled jobs, daemons, and launchd items
- **Interactive shell commands** issued by any agent or by the operator inside an agent session

The earlier heading "What OpenClaw May Never Touch" was read by more than one session as governing the *application*. It does not. If a command runs on this machine in the course of this project, it is in scope.

### 2.2 Listing and traversal are prohibited, not just reading *(added v2.0, ADR-045)*

The prohibition covers **reading, listing, and traversing**. Opening a file is not the threshold. In particular:

- **A glob is a directory read.** `ls -d ~/Library/.../*ackup*` reads the directory to resolve the pattern.
- **A directory-size command is a directory read.** `du -sh */` recursively traverses everything it totals.
- A command that displays no filenames has still read them.

Before any command that touches a path outside `~/openclaw`, re-read Section 2. If a command's *scope* is determined by a glob, a wildcard, or the current working directory rather than by an explicit path you wrote, treat it as unscoped and assume it will reach further than intended.

---

## 3. How to Add a New Path

Before writing any code that accesses a new filesystem path:

1. **Identify** the exact path, the access type needed (read / write / execute), and the business purpose.
2. **Assess** whether the path may contain personal, sensitive, or legally protected data. If yes, document the mitigation.
3. **Amend ADR-040 Section 3.1** with the new path and access type, and create a changelog entry before the first deployment that touches it.

This procedure applies to paths outside `~/openclaw`. Subdirectories inside `~/openclaw` are already fully permitted.

---

## 4. Why This Exists

During Session 16 (April 19, 2026), a routine terminal command to locate the backup folder listed the iCloud Drive root directory. That listing included Federal Tax Information belonging to a family member, along with personal financial and legal documents. No file was opened or read — only filenames were displayed. But the event made clear that OpenClaw had no documented rule preventing any future agent, scraper, or automated task from encountering these files.

This policy closes that gap permanently. The governing principle is the same as the network egress whitelist in ADR-030: **OpenClaw processes operate within a defined, minimal scope. Expanding that scope requires an explicit decision, not just working code.**

FTI is protected data under 26 U.S.C. § 6103. Its presence on this filesystem is acknowledged. No OpenClaw process will be permitted to access paths where FTI may reside.

---

## 5. ADR Reference

| Field | Value |
|-------|-------|
| ADR | ADR-040 (amended by ADR-045) |
| Title | Filesystem Boundary and Sensitive Data Separation Policy |
| Date | April 19, 2026 — amended September 20, 2026 |
| Status | DECIDED |
| Owner | Sheldon Wheeler |

Full governance record: `ADR_040.docx`, `ADR_045.docx`

---

## 6. Enforcement Posture — read this before relying on the policy *(added v2.0, ADR-045)*

**This policy is not enforced. It directs behaviour; it does not prevent access.**

Section 4 above says the April 2026 gap was closed "permanently." That was optimistic. It has been breached three times:

| Date | Event |
|---|---|
| April 19, 2026 | Session 16 — iCloud root listed; FTI filenames displayed. Created this policy. |
| August 23, 2026 | Entry #029 — a glob resolved against the prohibited iCloud root. |
| September 20, 2026 | Entry #030 — `du` traversal of `~/Documents`, `~/Desktop`, `~/Library`. |

Each breach was committed by a party with access to this document who would have complied had they consulted it. **Three recurrences under unchanged text is evidence about the control, not about any one session.**

**Why enforcement is hard.** Claude Code permission rules match Bash invocations against *command strings*, not against the paths those commands reach. `Bash(du:*)` permits `du` anywhere on the volume; there is no expressible rule meaning "`du`, but only inside `~/openclaw`." Every path-scoped `Read(...)` rule is therefore enforced against the Read tool only, and is silently irrelevant when the same data is reachable through a shell command. **Shell access is unbounded by construction.**

**What is being done about it (ADR-045 §8):** a PreToolUse hook gating traversal verbs — `du`, `find`, `ls -R`, `grep -r`, `tree`, `mdfind`, `locate` — when not explicitly scoped to `~/openclaw`. It matches on commands rather than path literals, because a path blacklist would not have caught `cd ~ && du -sh */`, which contains no prohibited path.

**The hook is a speed bump, not a boundary.** It narrows the common failure mode. Any sufficiently novel command will pass it.

**The actual compensating control is disclosure.** All three breaches entered the record because they were self-reported, not because anything detected them. That is a detective control working correctly — and it is currently the *primary* one. Anyone operating under this policy should know that, rather than discovering it after a fourth breach.

**Control classification** (revised by ADR-045 §7, superseding ADR-040 §7): PL-4 and AU-6 are accurate and effective. **AC-3 is NOT MET** until the hook ships, and was overstated as IMPROVED in the original ADR-040.

---

## 7. Governed Artifacts *(added v2.0, ADR-045)*

**`~/openclaw/.claude/settings.local.json` is governed by this policy.**

It is a parallel permission surface capable of authorising exactly what Section 2 prohibits. It currently contains `Read(//Users/sheldonwheeler/**)`, which pre-authorises reads across the entire home directory including all three Section 2 paths. The narrow replacement — `Read(//Users/sheldonwheeler/openclaw/**)` — already exists alongside it.

Because the file is covered by the global gitignore, **it is not in version control, so a contradiction between it and this policy will never appear in a diff and cannot be caught in code review.** Its contents must be inspected manually at each review of this document.

*Status: the home-wide grant is pending removal under ADR-045 §8.2.*
