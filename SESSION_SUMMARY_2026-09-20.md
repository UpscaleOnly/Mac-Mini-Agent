# Session Summary — September 20, 2026

*Narrative record of what happened this session and why. **This is history, not
state.** `CURRENT_STATE.md` is the single handoff document and the only
authoritative account of where things stand — if this file and that one
disagree, that one wins. Read it first; read this for the reasoning behind the
changes it describes.*

*(A dated summary is not the `NEXT_SESSION_OPENER.md` that Entry #028 retired.
The opener was a second **current-state** document that drifted out of step
with this file's predecessor within a single day. A dated snapshot of one
session cannot drift, because it never claims to be current.)*

---

## What this session was

The project came off four weeks dormant. Fourteen commits, changelog entries
#030–#039, four new ADRs (043–046), and one ADR superseded.

The work fell into five threads: a hardware decision, disk reclamation, a
governance audit, the backup path, and the brief generator's verification
gate. They looked unrelated at the start and turned out to share a single root.

---

## The through-line: seven claims that were documented, plausible, and false

This is the finding with the longest shelf life, and it is why the session ran
as long as it did. Each of these was written by someone competent, read many
times, and wrong. **Four had been in the repository for months.**

| # | Claim | Reality | Found by |
|---|---|---|---|
| 1 | ADR-036's GPU VRAM policy, DECIDED five months | Specified 32/64 GB headless hosts that were never bought | `sysctl iogpu.wired_limit_mb` returned 0 |
| 2 | ADR-033's memory alerts: 28 GB yellow, 30 GB red | Above the machine's 16 GB — could never fire | Reading it against measured RAM |
| 3 | `backup.sh` line 33: "same iCloud destination" | Desktop & Documents sync is off; never left the disk | `ls -ld ~/Documents` |
| 4 | `CURRENT_STATE.md`: "git push is gated, will be refused" | It isn't | Trying it |
| 5 | Review `.txt` files are an untracked gitignore gap *(mine)* | Tracked deliberately as version evidence | `git ls-files` |
| 6 | v7 "unit-tested" and sound *(mine)* | Tests checked the wrong shape; first run failed | Running it |
| 7 | Entry #013: launchd can't write to iCloud without TCC | It can | `launchctl submit` probe |

**The common defect:** each asserted a property of *the world* rather than of
the code, and nothing ever tested the assertion. A claim about what the
hardware has, what a folder syncs to, what the OS permits — none of these
fails a test suite, none shows up in a diff, and all of them read as
authoritative because someone competent wrote them down.

Two of the seven were mine, made during this session, one of them in a commit
message written minutes earlier. The rate is not a property of the previous
author; it is a property of the medium.

**Practical consequence for next time:** when a document states a fact about
the machine, the filesystem, or the OS, that fact is a hypothesis until
something runs. Checking usually costs ten seconds.

---

## Thread 1 — Hardware: no purchase (ADR-043)

The question was whether to buy a used ~$1,500 Mac Studio or rent cloud
capacity, for confidential local inference.

**Decided: neither.** At an anticipated 1–2 confidential sessions per month, a
$1,500 machine costs roughly $60–125 per session in year one for capability
exercised a couple of dozen times a year, on a 2022-generation machine whose
macOS support runway ends around 2029–2030.

Measured rather than assumed: MacBook Air M1, **16 GB** unified memory,
~68 GB/s bandwidth, fanless, and — the number that reframed everything — a
**10 MB** production database.

That last figure split the problem. The pipeline is 10 MB of *public* Federal
Register data needing uptime, not compute; no confidentiality constraint
governs where it runs. Only local inference for the operator's own private
material justifies hardware, and at 1–2 sessions a month the existing machine
holds.

ADR-043 closes the "target production machine recorded inconsistently" item
that instructions v3.0 left open. The resolution: **there is no target
machine, by design.**

---

## Thread 2 — Disk: 37 GB reclaimed, 93% → 76%

Neither consumer was project data. Docker held 27.6 GB of stale images. `.git`
held **11 GB of garbage** — two abandoned temporary pack files from a repack
interrupted during the August 23 tagging work, with `packs: 0` and everything
loose. The repository's actual content is 928 KB packed.

Entry #029's tag is what made `git gc --prune=now` safe. That entry had warned
the prototype's five commits were "one `git gc --prune` from permanent loss";
this session ran exactly that command, and the pushed `prototype-2026-04` tag
preserved them. Verified before and after.

Also worth remembering: `Docker.raw` reports 228 GB apparent against 3.0 GB
actual. `ls -lh` on it misleads by two orders of magnitude; `du` is correct.

---

## Thread 3 — Governance: ADR-036 superseded, ADR-040 amended, corpus audited

**ADR-036 → superseded by ADR-044.** Its VRAM policy specified values for
hardware never acquired, and §4's premise (headless server, no GUI, no
interactive sessions) is false of a personal laptop independently of the
numbers. `sysctl` confirmed the LaunchDaemon was never installed, making it a
documentation correction with nothing to unwind. No replacement policy issued:
raising the wired limit on a 16 GB GUI machine would cause the swap pressure
ADR-036 §4 itself warns about.

**ADR-040 → amended by ADR-045.** The intent and prohibited-path list are
unchanged. What changed is the honesty of its claims:

- **AC-3 (Access Enforcement) went from IMPROVED to NOT MET.** A document that
  must be remembered directs behaviour; it does not enforce. The accurate
  mapping is PL-4 plus AU-6.
- **The real compensating control is disclosure.** All boundary breaches
  entered the record because they were self-reported, not detected.
- **Structural finding:** Claude Code matches Bash rules against *command
  strings*, not the paths they reach. `Bash(du:*)` permits `du` anywhere.
  Shell is unbounded by construction, so every path-scoped `Read(...)` rule is
  irrelevant when the same data is reachable through a shell command.

An overstated control mapping is worse than a missing one, because it removes
the prompt to fix the gap.

**ADR-046 — corpus audit.** ADR-036 was found by accident, so all 28 ADR
documents were searched for dedicated-host assumptions. **Eleven carry live
dependencies** across four failure modes: work deferred to a "Mac Studio setup
day" that never arrives (ADR-031, 038, 039, 041); an `openclaw`/`admin`/`dev`
account model that does not exist (ADR-020, 033, 034, 035, 038); thresholds
keyed to absent hardware (ADR-033); and ADR-032's NIST mapping asserting
control statuses against the absent architecture — with AC-11 and AC-18 both
dismissed as inapplicable to a "headless system" that is in fact an
interactive laptop.

**F2 (the NIST re-assessment scope) is still an open operator decision.**

---

## Thread 4 — Backups: a four-month gap, found and closed

The audit's most consequential finding was not in an ADR. `scripts/backup.sh`
line 34 had been writing nightly dumps into `~/Documents`, a §2-prohibited
path, since May 17 — with `mkdir -p` and a `find … -delete` retention sweep
running there too.

Three things compounded it: the script's own header comments still described
the *sanctioned* path, so the file read as compliant; the choice was
deliberate, to avoid a TCC grant; and ADR-019 recorded it as an interim
deviation "reverting on Mac Studio setup day" — which ADR-043 had just made
never.

Resolution took three attempts, and the sequence is the useful part:

1. **Option A** — revert to the sanctioned iCloud path and grant TCC. Applied,
   then reversed on investigation: TCC attributes access to the *executing
   binary*, so for a shell script the grant target is `/bin/bash`. That would
   have given every shell script on the machine read/write access to every
   §2-prohibited path — broader exposure than the violation it fixed.
2. **Option C** — write to `~/openclaw/backups`, already sanctioned, no grant
   needed. Applied. Caught in passing that `.gitignore` had no pattern for
   backup output, leaving dumps one `git add -A` from GitHub.
3. **Then the correction that mattered:** the operator asked whether iCloud
   backs up `~/Documents`. It does not — Desktop & Documents sync is off, and
   the symlink in the CloudDocs container points *outward* at `~/Documents`,
   which iCloud does not follow. **So no off-device backup had existed since
   May 17.** Option C had cost nothing; the "regression" recorded in Entry #034
   was a four-month-old pre-existing condition.

**Closed at the end of the session (Entry #039).** Each dump now copies to the
ADR-040 §1 sanctioned iCloud path. No TCC grant was needed — Entry #013's
claim proved false. The copy is **non-fatal by design**, since a
`launchctl submit` probe is strong evidence but not proof; a real 04:00 run is.

---

## Thread 5 — Generator: v5 → v7, send path ungated

The first review-only run in four weeks surfaced a defect that had silently
gated `--send` shut since v5: `verify_claims()` validates a number by finding
it in source text, which works for *quoted* values (currency, dates, FR
citations) and cannot work for *derived* aggregate counts.

Three approaches, two wrong:

| Approach | Outcome |
|---|---|
| **Tolerance** — count ≤ section document count becomes a note | **Reverted within the hour.** First run wrote "15 states" where sources named 18, and the rule demoted that fabrication to a note. Passed a real error while still blocking on "seven days", a duration. Worse than v5. |
| **Prompt prohibition** — forbid tallying in `SYSTEM_PROMPT` | **Kept.** Warnings 3 → 1, and better output: SNAP now names all eighteen states rather than counting them. Did not fully hold. |
| **Ground truth** — recompute counts from the source rows | **Current (v7).** The only approach that catches 15-vs-18, because catching it requires knowing the answer is 18. |

Two runs over identical input produced 18 (right) and 15 (wrong): **the model
genuinely fabricates counts**, and the strict check was catching a live failure
mode rather than noise. Do not re-attempt tolerance-based approaches.

v7's first cut failed on a scope bug the unit tests missed — they always
checked one section's truth, never the executive summary's ambiguity ("CMS
issued three notices" is true of CMS and false of the window).
`acceptable_counts()` fixes it.

**Result: verification runs clean — the first since August 22.** `--send` is
ungated for the first time in a month. An audit of the clean run found one
number still unchecked: "two information collection requests" is correct, but
`_UNIT_PAIRS` has no `request` entry, so nothing looked at it.

---

## Also settled

- **Scraper reliability — closed.** Four weeks of unattended evidence proved
  both the Entry #024 misfire grace and the Entry #020 catch-up logic. Coverage
  since August 24 has exactly one missing weekday: Labor Day.
- **Git identity** — was literal placeholder text (`YourGitHubUsername`);
  every commit before `9613b25` is attributed to a stub.

---

## Open for next session

1. 🟡 **Confirm the 04:00 run logged `OFFSITE_OK`** — the definitive TCC test.
   Also confirm in Finder that dumps show as *uploaded*, not merely present:
   iCloud uploads asynchronously, so `OFFSITE_OK` means written into the synced
   folder, not off-device yet.
2. **ADR-046 F2** — NIST re-assessment scope: four named controls, or the full
   Moderate baseline. Operator decision.
3. **A second `--send` run.** Only the second ever. Keep
   `HARD_FAIL_ON_UNVERIFIED` at `False` until two further clean runs.
4. **Migrate, don't delete, `~/Documents/Mac-Mini-Backups-Interim`** — those are
   the only dumps from the last ~30 days. Move into `~/openclaw/backups/dumps/`,
   then remove the folder. §2-prohibited, so operator action.
5. Add `request` to `_UNIT_PAIRS`; ADR-045 §8.2/§8.3; ADR-046 F3–F5; the
   August 4–16 content backfill.

---

## Commits

```
7200b8e  ADR-043: retain MacBook Air as production host
9613b25  Entry #030: four-week re-entry, scraper proven, 37GB reclaimed
18ddb35  Entry #031: supersede ADR-036 (ADR-044), amend ADR-040 (ADR-045)
bc23675  Entry #032: dedicated-host audit (ADR-046), live backup breach
501971b  Entry #033: ADR-046 F1 remediated in code
48b1414  Entry #034: ADR-046 F1 resolved via Option C
bd156dd  Entry #035: correction - no off-device backup since May 17
28d7edf  Entry #036: review-only run, count check blocks send path
eb99ebd  Entry #037: generator v6 - forbid derived counts at the prompt
f8a90e4  Correct CURRENT_STATE: git push is not gated
6e3f1ca  Generator v7: ground-truth count verification
39b0987  v7 fix: scope-aware ground truth for the executive summary
8e38219  Entry #038: v7 verifies clean - send path ungated
3dd92be  Entry #039: restore off-device backup to iCloud
```

---

*Sheldon Wheeler — OpenClaw Personal Stack — session narrative, September 20, 2026.*
*Current state lives in `CURRENT_STATE.md`. This file is not maintained after today.*
