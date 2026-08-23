# Session Summary — August 22-23, 2026

*Companion to `NEXT_SESSION_OPENER.md`. That file is the terse operational
checklist for starting the next session; this is the narrative record of
what happened in this one and why. Read this for context, the opener for
action items.*

---

## What this session actually accomplished

Two largely separate threads: closing out the send-to-inbox production
priority (ADR-039 H4), and an evening detour into the ADR governance
fragmentation problem (ADR-042) that turned into a real fragment-recovery
effort.

### 1. Send-to-inbox is live (ADR-039 H4 closed)

The federal_policy_brief pipeline can now actually email the brief, not just
generate it for review. `generate_brief_review.py` went from v4 to v5:

- New `--send` flag. Self-send only — the operator's own iCloud inbox is
  both sender and recipient. No email service provider, no purchased
  sender domain — decided this wasn't needed at the current audience size
  (one recipient: the operator).
- SMTP via `smtp.mail.me.com:587`, STARTTLS, credentials read from macOS
  Keychain at send time — never touched the chat session.
- Send is gated on `verify_claims()` returning zero warnings. Any unverified
  claim blocks the email entirely; the review file and an audit row still
  get written either way.
- New `brief_runs` table (`migration_006.sql`, schema version 6 → 7) records
  one row per `--send` invocation: doc count, verification status, send
  status, recipient, any error. Review-only runs (no flag) still write
  nothing, exactly as v0 through v4 always guaranteed.
- `is_new` on consumed `scraped_content` rows flips to `FALSE` only after
  the send actually succeeds — a failed send leaves rows eligible for retry
  instead of silently dropping them.

Live-verified end to end, not just unit-tested: a real `--send` run emailed
`sheldon.wheeler@icloud.com`, 24 documents got marked processed, and the
`brief_runs` row came back clean.

### 2. Discovered mid-session: Claude Code was running in the wrong directory

While doing this work, it became clear this Claude Code session — and the
one before it — had been operating in `~/projects/mac-mini`, a second local
clone of the same GitHub repo, not `~/openclaw`. ADR-014 (see below)
explicitly scopes Claude Code to `~/openclaw`. Both clones were at the same
commit with identical code, so nothing had actually drifted in content —
just location — but `~/projects/mac-mini` has no `.env`, which is why the
first attempt to connect to the live database from there failed outright
rather than working with stale credentials.

Fix: every file touched this session was copied into `~/openclaw` (and
verified byte-identical before any live DB or SMTP action was taken), and
`~/projects/mac-mini`'s working tree was reverted clean. `~/openclaw` is now
confirmed as the sole working copy.

### 3. ADR-042 filed: the ADR corpus itself is fragmented

Confirming ADR-014's actual text during the cleanup above surfaced a bigger
problem: grepping every `ADR-NNN` citation in code, changelog, and state
docs against the physical `ADR_*.docx` files in `~/openclaw` found:

- 9 ADRs with both a document and live references (031, 033-035, 037-041)
- 1 orphan document never referenced anywhere (036 — later resolved, see
  below)
- 12 ADR numbers cited as active governance with **no local document at
  all** — including ADR-014, the ADR governing Claude Code's own operating
  scope
- 1 numbering gap (032) with neither document nor reference

Filed as ADR-042, status OPEN, explicitly deferred to a dedicated future
project per operator direction — Sheldon has spent months building this ADR
corpus and didn't want it rushed. This entry (`b27beb4`) just records the
problem and the inventory, no reconciliation approach selected.

### 4. The evening detour: an actual fragment-recovery session

After ADR-042 was filed, the conversation shifted into actively hunting for
the missing ADR content across every storage location on this Mac —
Google Drive, iCloud Drive, OneDrive, Downloads, and eventually a Claude.ai
Project. This was NOT the deferred ADR-042 reconciliation project (that's
still explicitly future work) — it was closer to reconnaissance: see what's
actually recoverable before that project ever starts.

**What got resolved:**

- **ADR-014 reconstructed.** No original document exists anywhere checked.
  Built from two independently-maintained sources — this repo's own
  changelog and a Claude.ai project's custom instructions/memory panel —
  that state the operative rule in matching language, which is why it's
  trustworthy. Every field with no supporting source (NIST controls, ADR
  References, original problem statement, exact decision date) is marked
  `NOT RECOVERED` rather than guessed. Saved as `~/openclaw/ADR_014.docx`
  (commit `7558894`) with a full provenance section built in.
- **ADR-036 isn't actually an orphan.** It's real, DECIDED policy (GPU VRAM
  Allocation, dated April 4, 2026) — it was just never cross-referenced by
  the exact string "ADR-036" in code or changelog, which is what the
  original ADR-042 grep checked for. Separately, and unrelated to the
  orphan question: the physical `ADR_036.docx` file turned out to not
  actually be a valid `.docx` at all — it's plain markdown text saved with
  a `.docx` extension, a leftover mistake from the old file-delivery
  workflow. Still readable as text, but breaks any tool expecting real
  Word XML.
- **ADR-032's likely identity found**, though not confirmed with certainty:
  probably `Mac_Mini_NIST_800_53_Compliance.docx` — ADR-036's own reference
  list cites "ADR-032 (NIST)", and this document is a NIST 800-53
  compliance mapping. The document itself never states "ADR-032" anywhere
  in its own text, so treat this as strong-but-unconfirmed.

**What got partially recovered:** real titles and, for several, real
substance — not full original documents — for ADR-002 (Hardware), ADR-003
(Model Selection), ADR-005 (Model Strings), ADR-019 (Backup), ADR-020
(Account Structure), ADR-021 (model tier routing — actual threshold values
recovered: 0.85 for Tier 1→2, 0.90 for Tier 2→3), ADR-023 (Encryption
Posture), ADR-024 (Little Snitch / egress control), ADR-027 (Interceptor),
ADR-028 (Operator Approval — Telegram Y/N gate on Tier 4 usage, quiet hours
7pm-7am), ADR-029 (Audit Table — `agent_actions`, 90-day retention), ADR-030
(persona network policy, YAML-based). None of these were built into stub
documents — deliberately held back so effort isn't wasted on a partial
reconstruction a fuller source would immediately obsolete.

**A promising lead that turned out to be a dead end:** two version-numbered
files in OneDrive, `Mac_Mini_ADR_v1_3.docx` and `Mac_Mini_ADR_v2_6.docx`,
looked like they might be a consolidated master document holding the full
ADR-001–030 range. Getting them off OneDrive (which stores files as
on-demand cloud placeholders, not always present on disk) took most of the
session's second half — brctl couldn't force it, direct reads timed out,
and it eventually took Sheldon manually opening the files in Word via
Spotlight search. `Mac_Mini_ADR_v2_6.docx` turned out to just be another
copy of the same ADR-031 draft already found elsewhere — not a master
document. `Mac_Mini_ADR_v1_3.docx` was never actually opened; still
technically unconfirmed but low priority now.

**Still completely unrecovered:** ADR-017 and ADR-022. Zero fragments found
anywhere — not in `~/openclaw`, not in any cloud storage checked, not in
either of two separate Claude.ai project page captures, and not in a direct
in-project text search Sheldon ran for both numbers at the end of the
session. If they exist, they're somewhere not yet checked.

**One open question that qualifies everything above:** the Claude.ai
project the fragments came from has sidebar text reading "Projects / Mac
Mini" — not literally "AI Build," which is what this project was originally
referred to as. Never confirmed whether these are the same project
(renamed?) or two different ones. Worth settling before treating any of
tonight's findings as complete.

Everything from the fragment hunt — both saved page captures, the NIST
document, and a detailed README — is archived at
`~/openclaw/adr_fragments_2026-08-22/` (commit `aff928a`) so it survives
independent of what happens to the Downloads folder.

---

## State at close of session

- `main` and `origin/main` are in sync — everything pushed.
- Live PostgreSQL schema version 7. `brief_runs` has one row (clean, sent).
- `openclaw_fastapi` container has NOT been rebuilt — still running
  pre-session code, logs a harmless schema-version warning.
- `~/projects/mac-mini` — reverted clean, disposition still undecided.
- No ADR-042 reconciliation decision was made. This was search and
  archival, not reconciliation — that project is still explicitly deferred.

See `NEXT_SESSION_OPENER.md` for the full prioritized task list and exact
commands to run first.
