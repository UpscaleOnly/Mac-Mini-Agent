## Entry #018 — federal_policy_brief: brief-generator v1/v2 — instrument fidelity, sub-agency mapping, plain-text enforcement

**Date:** August 16, 2026
**Session focus:** Production over governance. Fix the two output flaws identified in Entry #017, validate against live data, and ship a generator whose output is fit to read.

---

### Summary

Both Entry #017 flaws are fixed and validated against live data. `generate_brief_review.py` went through two revisions this session: **v1** (instrument-type fidelity + sub-agency program mapping) and **v2** (repair of two regressions v1 introduced). The generator remains **review-only** — no email sent, `is_new` untouched, no `brief_runs` row written.

Two findings landed that were not visible from the July 6 output: the nightly scraper stopped around **August 9** when Docker Desktop went down (not a code fault), and a **latent defect in the scraper's `TYPE_MAP`** means every proposed rule in `scraped_content` is stored as `content_type = 'other'`. The second is the highest-value open item leaving this session.

---

### Narrative

1. **Environment recovery.** Postgres refused connections at session start — Docker Desktop itself was not running (last console login August 9). All four containers (`openclaw_fastapi`, `openclaw_postgres`, `openclaw_chromadb`, `openclaw_telegram`) restarted cleanly. Because APScheduler runs inside `openclaw_fastapi`, the nightly `federal_register` scrape has not run since the Mac went down. `scraped_content` is continuous through **August 3**; the ~13-day gap is host downtime, not scraper failure. The scraper resumes on its own at 01:00 ET now that Docker is up.

2. **Fix 1a — instrument-type fidelity (Entry #017 flaw 1).** Root cause was structural, not just prompt wording: v0's executive summary read *only the section prose*, making it a summary of a summary — which is how a CMS–VA Privacy Act matching-program notice became "eligibility verification update." Three changes:
   - The generator now selects **`scraped_content.content_type`**, which the scraper copies from the Federal Register API's own `type` field. Coarse instrument type is therefore authoritative rather than guessed from title text. This column existed all along and v0 never read it.
   - `notice` is too coarse for a brief, so it is refined by title keyword into Privacy Act matching-program notice, Privacy Act system-of-records notice, information collection request, advisory committee meeting notice, charter renewal notice, drug or device determination, request for information, funding/cost-share notice. Rules are never re-labeled.
   - Every document is presented to the model with its instrument label, and the system prompt makes instrument fidelity mandatory with worked negative examples.

   **Validated.** The exact v0 failure is gone. v2 output reads: *"A Privacy Act matching program notice (July 6, 2026) establishes a new matching program between CMS and the Department of Veterans Affairs (VA) to verify eligibility for Insurance Affordability Programs under the ACA."* Sections now carry named systems (USDA/FNS-7, FNS-5 → FNA-5, SNAP-QCS, eDRS), named counterparties (OPM, VA, DHS), and hard requirements (IRF therapy start within 36 hours of admission).

3. **Fix 1b — program-area mapping (Entry #017 flaw 2).** v0 matched agency-name substrings against the whole `publishing_agency` string, which is formatted `"Parent Department, Sub-agency"`. The needle `"Agriculture"` therefore matched every USDA document before the sub-agency was ever consulted. Mapping now parses on commas and matches **sub-agency positions only** — the parent department never routes. Only Food and Nutrition Service/Administration reaches SNAP; the rest of USDA falls through to Cross-Program.

   **Validated.** In the 48-day set (108 documents) SNAP went from 10 rows to 4, all FNS. Forest Service, APHIS, Farm Service Agency, Rural Utilities Service, the USDA CFO's office and all IRS content moved to Cross-Program. **TANF populated for the first time** — v0's mapping had made it permanently empty — surfacing among others a VA-to-State-Public-Assistance-Agency matching program supplying SPAAs with veterans' compensation and pension data for benefit eligibility determinations. High-signal for the target audience and previously invisible.

4. **CMS section renamed (decision this session).** v0 routed on `"Medicare"` as well as `"Medicaid"`; since CMS's full name is "Centers for Medicare & Medicaid Services," all CMS content landed in a section headed "Medicaid/CHIP" — including pure-Medicare authorities such as the CY2027 HH PPS rule and DMEPOS provisions. Rather than split CMS on title keywords (heuristic, would strand ambiguous notices), the section is renamed **"CMS (Medicaid/CHIP/Medicare)"**. One bucket, honest heading; instrument labels carry the specificity inside the prose.

5. **v1 regressions found on first full run, fixed in v2.** Both were introduced by this session's changes, not by Gemma:
   - **Executive summary blew up.** v1 passed a one-line-per-document "authoritative inventory" to the summary step. With 108 documents the model read it as a work order and rebuilt the entire brief as a 50-line structured document with emoji headings, instead of the requested 4–6 sentences. **Fix:** the inventory is now compressed — per-area counts by instrument, plus individually named items only for high-signal instruments (rules and matching notices), capped at six per section — with hard length and format constraints.
   - **Markdown and emoji contaminated a plain-text product.** v1's larger, more directive prompts pushed Gemma into document-formatting mode: `###` headings, `**bold**`, a pipe table, emoji. v0 never did this because its prompts were small. **Fix:** two layers — an explicit plain-text mandate in the system prompt, and `to_plain_text()`, a deterministic post-processing scrubber that strips headings, bullets, numbered lists, bold/underscore markers, backticks, horizontal rules, table syntax and emoji from every model response. Prompting alone is not a sufficient guarantee for something that ships as email.

   **Validated.** v2 executive summary: one paragraph, 5 sentences, 151 words, naming the two CMS final rules, the CMS–OPM matching notice, ACF's VA/SPAA matching notice and the CACFP rate adjustment, with routine volume disposed of in a closing clause. Zero markdown headings, bold markers, tables, backticks or emoji anywhere in the generated body.

6. **NEW DEFECT — scraper `TYPE_MAP` mislabels every proposed rule.** In `app/scheduling/scrapers/federal_register.py`, `TYPE_MAP` is keyed on the Federal Register API's **query-filter codes** (`RULE`, `PRORULE`, `NOTICE`, `PRESDOCU`) but is applied to the API's **returned display strings** (`"Rule"`, `"Proposed Rule"`, `"Notice"`, `"Presidential Document"`). Uppercased, `"RULE"` and `"NOTICE"` match by coincidence; `"PROPOSED RULE"` and `"PRESIDENTIAL DOCUMENT"` match nothing and fall through to `'other'`.

   Consequence: **no proposed rule anywhere in `scraped_content` is labeled as one.** Across 108 documents there is not a single `proposed_rule`. The defect is reader-visible — the CY2027 HH PPS rule, the highest-signal item in the set, was briefed as *"a document published on July 6, 2026, proposes routine updates."* Proposed rules are precisely what a commissioner needs flagged as open for comment and not yet in effect. Interim workaround in v2: `"document"` is treated as high-signal so proposed rules are not dropped from the executive summary inventory; a removal note is attached in the file header.

7. **Remaining output defect — oversized sections.** Cross-Program carried 51 documents (20-day window) and 91 (48-day window). At that size the model abandons prose: roman-numeral outline, a summary table, self-contradiction, coverage of roughly 15 of 51 documents, and **leakage of internal document-index references** (`"Items [38], [39], and [40]..."`) from `docs_block` numbering into reader-facing text — 25 occurrences, all in Cross-Program, zero in the other three sections. At the production `WINDOW_DAYS = 7` Cross-Program would carry roughly 12–15 documents and this likely does not appear, but it is not fixed, only unlikely.

---

### Files Changed

| File | Action |
|------|--------|
| `~/openclaw/generate_brief_review.py` | Rewritten v0 → v2 — instrument typing from `content_type`, sub-agency mapping, CMS section rename, plain-text mandate + `to_plain_text()` scrubber, compressed exec-summary inventory |
| `~/openclaw/generate_brief_review.py.bak.v0` | Created — v0 backup before overwrite |
| `~/openclaw/federal_policy_brief_review_2026-08-16.txt` | Created — v2 output (20-day window, 61 documents) for operator review |
| `~/openclaw/changelog.md` | Updated — this entry |

**Not changed:** no schema change, no migration, no container image rebuild (the generator is a host-side script; `docker compose build fastapi` is not required for this session's work).

**Note:** `WINDOW_DAYS` is currently **20** on disk — a temporary value used to reach banked July 27 – August 3 content so all four sections would populate. **It must be returned to 7 before send-to-inbox wiring.** A comment marks this in the file.

---

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-014 (Shell/Docker guardrails) | Reaffirmed operative. The generator invokes no shell. All host commands run manually by the operator, one at a time. Compliant. |
| ADR-014 (note — new access pattern) | This session used the Claude desktop folder bridge to grant **read access to `~/openclaw`** for file inspection and post-run verification. This is file transfer, not host command execution, so the ADR-014 boundary is untouched — but it is a new access pattern and is recorded here deliberately. Write access was offered and **declined by the operator**; all writes to disk were performed by operator-run `cp` commands. |
| — | No new ADR created. Governance-serves-shipping rebalance honored. |

---

### NIST Controls Touched

None directly by the code. **IA-5 (Authenticator Management)** noted again: the live Postgres role password was read from `~/openclaw/.env` and, in the course of this session, appeared in the assistant chat transcript. Postgres is bound to localhost behind Tailscale with no public exposure, so no new exposure was created, but this reinforces the standing rotation item rather than relieving it.

---

### Risk Assessment

No schema change. No migration. No email sent. No rows mutated — `is_new` remains `TRUE` on all banked content. No `brief_runs` write. No egress change (Postgres and Ollama both localhost). The generator remains idempotent and safe to re-run. v0 is preserved at `generate_brief_review.py.bak.v0`. The `TYPE_MAP` defect is pre-existing and was surfaced, not introduced, by this session.

---

### Open Items Surfaced / Carried

| Item | Severity | Notes |
|------|----------|-------|
| Fix scraper `TYPE_MAP` (`PRORULE`/`PRESDOCU` vs returned display strings) | **High** | Every proposed rule stored as `'other'`. One-line fix in `federal_register.py`; accept both filter codes and display strings so it cannot break again on API shape changes. |
| Backfill `content_type` on banked rows mislabeled `'other'` | **High** | One-time `UPDATE`. Touches existing data — requires explicit approval. Pairs with the fix above. |
| Remove `"document"` from `HIGH_SIGNAL` in the generator | Low | Interim workaround; delete once the two items above are done. |
| Cap or rank documents per section | Medium | Cross-Program at 51+ documents produces outline-and-table output instead of prose. This is Entry #017's "significance ranking" item, now with evidence. |
| Stop `docs_block` index numbers leaking into prose | Low | 25 `[n]` references reached reader-facing text in the oversized section. Fix by removing the numbering or forbidding its citation. |
| Return `WINDOW_DAYS` to 7 | **Blocking for send** | Currently 20 on disk for validation purposes. |
| Wire send-to-inbox | Medium | Delivery mechanism + `brief_runs` logging + `is_new` flip. Still gated on the ADR-039 email-provider and sender-domain decisions. |
| Reconcile placeholder credential stores; complete Postgres rotation | Low-Med | Carried. Container env and Keychain still hold the stale placeholder. |
| Fix Ctrl+C not interrupting in Terminal | Low-Med | Carried. Materially felt this session — a 20-minute unstoppable Gemma run with no abort short of closing the window. |
| v3.0 instructions refresh | Medium | Carried. |
| Rebuild project knowledge as clean one-way mirror of disk | Medium | Carried. |

---

### What's Next

| Action | When |
|--------|------|
| Fix scraper `TYPE_MAP` + backfill mislabeled rows; rebuild and restart `fastapi` | Next session, first |
| Cap/rank per-section document counts; kill the `[n]` leak | Next session |
| Return `WINDOW_DAYS` to 7 and confirm a clean small-window run | Before send wiring |
| Wire send-to-inbox | After the above, and after ADR-039 email decisions |
| v3.0 instructions refresh + project-knowledge rebuild | Opportunistic |
