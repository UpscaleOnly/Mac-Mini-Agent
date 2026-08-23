# ADR fragment hunt — August 22, 2026

Archived source material from the ADR-042 fragment search conducted the evening
of August 22, 2026. Originals were saved to `~/Downloads` by Sheldon during the
session (browser page-saves and Claude.ai project file downloads) and copied
here for durability — Downloads is not a stable location.

## Contents

- `ADRs.html` / `ADRs_extracted_text.txt` — saved capture of a Claude.ai
  Project page (sidebar read "Projects / Mac Mini" — **still unconfirmed**
  whether this is the project Sheldon calls "AI Build"). Captured ~17:13.
  Contains the project's custom instructions, Memory panel, and a 9-file
  filtered view of its knowledge base.
- `Claude.html` / `Claude_extracted_text.txt` — a second, fuller capture of
  the same project (~19:09), same instructions/memory content plus the
  **full 47-file knowledge-base listing** (no filter) and the complete
  rendered text of `ADR_031.docx` as it exists in that project's knowledge
  base.
- `Mac_Mini_NIST_800_53_Compliance.docx` — NIST 800-53 Rev 5 Moderate
  baseline compliance mapping, dated March 28, 2026. Explicitly states it
  maps controls "against the architecture decisions recorded in **ADR
  v2.6**." Strongly suspected to be **ADR-032** (ADR-036's own reference
  list cites "ADR-032 (NIST)"), but this document does not self-identify
  with that number anywhere in its own text — treat the ADR-032 identity as
  probable, not confirmed.

## What this search resolved

- **ADR-014**: no original document exists anywhere checked. Reconstructed
  from fragments as `~/openclaw/ADR_014.docx` (committed `7558894`) — see
  that document's Section 6 for full provenance. If a real original ever
  surfaces, it supersedes the reconstruction.
- **ADR-036 is not actually an orphan.** It's a real, DECIDED policy (GPU
  VRAM Allocation Policy, April 4, 2026) — it was just never cross-referenced
  by the exact string "ADR-036" in code/changelog/state docs, which is what
  the original ADR-042 inventory grepped for. Note separately: the physical
  `~/openclaw/ADR_036.docx` file is **not actually a valid .docx** — it's
  plain markdown text saved with a `.docx` extension (a leftover from the
  old ".txt renamed in Finder" delivery convention, done incorrectly this
  one time). It reads fine as plain text but will fail in any tool expecting
  real OOXML (`unzip`, `pandoc`, python-docx, etc.) until it's properly
  converted. Worth fixing opportunistically.
- **ADR-032**: probable identity found (see above), not confirmed.

## Real titles/fragments recovered (via cross-references inside ADR-031 and
## ADR-036's own "ADR References" fields — NOT full original documents)

| ADR | Title (as cited) | Substance recovered |
|---|---|---|
| ADR-002 | Hardware | Title only |
| ADR-003 | Model Selection | Title only |
| ADR-005 | Model Strings | Title only |
| ADR-019 | Backup (Strategy/Configuration) | Nightly pg_dump, 30-day retention, real-time failure alert |
| ADR-020 | Account Structure | Title only |
| ADR-021 | "LayerModel" (model tier routing) | Confidence thresholds: 0.85 Tier1→2, 0.90 Tier2→3 |
| ADR-023 | Encryption Posture | Title only |
| ADR-024 | Little Snitch (egress control) | New permitted domain requires a changelog entry before activation |
| ADR-027 | (Middleware) Interceptor | Pattern scanner, flag-and-continue on suspicious input, post-call hook for real-time security alerts |
| ADR-028 | Operator Approval | Tier 4 usage routes through a Telegram Y/N gate; quiet hours 7pm–7am |
| ADR-029 | Audit Table | `agent_actions` table; 90-day retention, monthly partition, DROP PARTITION after 90 days |
| ADR-030 | (Persona) Network Policy | YAML-based, one file per persona |

None of these have been built into stub `.docx` files yet — that was
deliberately deferred pending the search below, and should be revisited
against whatever `Mac_Mini_ADR_v2_6.docx` / `Mac_Mini_ADR_v1_3.docx` (see
below) actually turn out to contain, so effort isn't spent on a partial
reconstruction that a fuller source immediately obsoletes.

## Still completely unrecovered

**ADR-017 and ADR-022** — zero fragments found anywhere: not in `~/openclaw`,
not in OneDrive, not in iCloud, not in either Claude.ai capture above, and
not in a direct in-project search Sheldon ran for both numbers at the end of
this session. If they exist, they're somewhere not yet checked.

## Dead end — do not re-chase

`Mac_Mini_ADR_v2_6.docx` and `Mac_Mini_ADR_v1_3.docx`
(`~/Library/CloudStorage/OneDrive-Personal/Documents/`) were the leading
hypothesis for a consolidated master ADR document, based on their
version-numbered naming and the NIST doc's explicit "ADR v2.6" citation.
Sheldon got `Mac_Mini_ADR_v2_6.docx` open and saved a copy
(`~/Downloads/Mac_Mini_ADR_031.docx`) — **its content turned out to be just
another copy of the pre-amendment ADR-031 draft**, not a multi-ADR master
document. The "v2.6" versioning most likely refers to a personal revision
count for ADR-031 alone, not a corpus-wide document. `Mac_Mini_ADR_v1_3.docx`
was never successfully opened/read — technically still unconfirmed, but the
v2.6 result makes it a low-priority lead now, not the high-priority one it
was treated as mid-session.

## Recommended next step, whenever this becomes active

Per ADR-042, this reconciliation work is deferred to a dedicated future
session — nothing here should be acted on opportunistically. When that
session happens:

1. Re-run the "AI Build" vs. "Mac Mini" project name question — get a
   definitive answer before doing anything else, since every finding above
   is qualified by that being unconfirmed.
2. Decide whether to build the partial stubs listed in the table above
   (clearly marked as cross-reference-only, not original documents) or hold
   out for fuller source material.
3. `Mac_Mini_ADR_v1_3.docx` remains genuinely unopened — worth one more try
   before writing it off entirely.
4. Fix `~/openclaw/ADR_036.docx`'s file-format problem (plain text with a
   `.docx` extension) independent of the rest of this — it's a quick,
   low-risk fix and doesn't need the full reconciliation project to happen
   first.
