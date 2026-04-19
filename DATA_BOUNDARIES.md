# DATA_BOUNDARIES.md
# OpenClaw Filesystem Boundary Policy
# Governing ADR: ADR-040 | Established: April 19, 2026 | Status: DECIDED

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
| ADR | ADR-040 |
| Title | Filesystem Boundary and Sensitive Data Separation Policy |
| Date | April 19, 2026 |
| Status | DECIDED |
| Owner | Sheldon Wheeler |

Full governance record: `ADR_040.docx`
