## Entry #019 — federal_policy_brief: scraper TYPE_MAP fixed, context-window ceiling found, brief-generator v3

**Date:** August 20, 2026
**Session focus:** Production over governance. Close the Entry #018 `TYPE_MAP` defect, return `WINDOW_DAYS` to 7, and get a brief that is fit to send.
**Commits:** `638cad7` (scraper fix + backfill), `cb03e58` (generator v3). GitHub in sync.

---

### Summary

The scraper `TYPE_MAP` defect identified in Entry #018 is **fixed and the banked data is corrected**. `generate_brief_review.py` advanced to **v3**. The generator remains **review-only** — no email sent, `is_new` untouched, no `brief_runs` row written.

Three findings this session, in descending order of importance:

1. **Gemma fabricated a dollar figure.** It reported three CDC awards of $15M, $30M and $30M as *"totaling approximately $105 million."* No source states any total, and the correct sum is $75M. This is the first factual-integrity failure in this project and it is now the gate on send-wiring.
2. **The "oversized section degradation" from Entry #018 was a context-window ceiling, not model behavior.** Ollama was running `gemma4:e4b` at **4096 tokens for prompt and response combined**. A 19-document section overran it. The fix is one config line.
3. **The Aug 18–20 scrape gap was a dead battery, not sleep.** No `pmset` wake schedule can fix that, which changes what the durable fix has to be.

---

### Narrative

1. **Scraper `TYPE_MAP` fixed.** `TYPE_MAP` in `app/scheduling/scrapers/federal_register.py` now accepts **both** Federal Register vocabularies — the query-filter codes we send (`RULE`, `PRORULE`, `NOTICE`, `PRESDOCU`) and the display strings the API returns (`"Rule"`, `"Proposed Rule"`, `"Notice"`, `"Presidential Document"`). Lookup is `.strip().upper()`, so all eight keys are uppercase.

   Type mapping also moved out of `parse()` into its own `map_content_type()` method, which **logs at WARNING** with the document number when a type matches nothing before storing `'other'`. The original defect was silent for months; a third vocabulary now surfaces in `docker logs openclaw_fastapi` instead of quietly flattening the brief. Rebuilt and restarted; container came up clean at schema v6.

2. **Backfill — verified, not deduced.** 15 rows sat at `content_type = 'other'`. The tempting inference was that all 15 must be proposed rules or presidential documents, since `TARGET_TYPES` admits only four codes and two of them mapped correctly by coincidence. Rather than rely on that, each document number was read out of its stored `url_path` and **queried against the Federal Register API**, which reported all 15 as `Proposed Rule`. Two rows titled "Request for Information" and one titled "Restoring Flexibility To Support Head Start Program Access" would have been plausible misclassifications under the inference; the API settled them.

   `UPDATE` was scoped to the 15 explicit ids **and** `content_type = 'other'`, so nothing arriving mid-session could be swept in. Result: `UPDATE 15`. Live distribution is now `notice` 195, `final_rule` 26, `proposed_rule` 15, **zero `other`**.

   The `"document"` entry in `HIGH_SIGNAL` — the Entry #018 interim workaround — was removed along with its three-line note.

3. **`WINDOW_DAYS` returned to 7.** Before spending a Gemma run, the generator's exact filter (`project` + `is_new = TRUE` + 7-day cutoff) was run as a plain `SELECT`: 21 documents, all published 2026-08-17. Coverage now runs **April 24 → August 17**, further than Entry #018's August 3.

4. **THE CONTEXT CEILING.** The first v2 run at `WINDOW_DAYS = 7` truncated Cross-Program mid-sentence (*"The FDA also issued a proposed"*) and omitted the **first three** documents in the input list entirely — both IRS items and the California walnuts rule.

   Dropped from the front, cut off at the back: the signature of context overflow, not of a model losing the thread. `ollama_chat()` sent `options: {"temperature": ...}` and nothing else, so Ollama applied its own default. `ollama ps` confirmed: **CONTEXT 4096** — prompt *and* response. The Cross-Program prompt alone was roughly 3,700 tokens of document text.

   **Fix:** `NUM_CTX = 8192`, passed as `num_ctx` in the options dict. Re-run covered **all 19** Cross-Program documents in four coherent paragraphs, ending on a complete sentence.

   **This reframes Entry #018 item 7.** The symptoms recorded there at 51 documents — roman-numeral outlines, summary tables, self-contradiction, coverage of roughly a third of inputs, `[n]` index leakage — are what a model produces when most of its input silently fell out of the window. The recommended remedy there was a significance-ranking system. That may still be wanted for editorial reasons, but it is **not** the fix for that failure, and building it first would have solved nothing.

5. **FABRICATED FIGURE — first factual-integrity failure.** The v2 re-run stated the three CDC cooperative agreements were *"totaling approximately $105 million."* Checked against source: Ukraine $15,000,000, Zambia $30,000,000, Ethiopia $30,000,000 — **$75 million**. No abstract states a total. The model volunteered an aggregation nobody requested and got it wrong by 40%.

   This is more dangerous than the truncation it accompanied. Truncated text announces itself; a confident wrong number reads perfectly and ships. The existing system prompt already said *"Summarize only what the source documents state"* — Gemma did it anyway. **Prompting alone has now failed twice** (markdown in v1, arithmetic in v2), which is the same lesson `to_plain_text()` encoded.

   **Fix, enforce-twice pattern:**
   - System prompt: an explicit arithmetic prohibition — never add, total, sum, average or combine figures, within or across documents; report every number exactly as one source states it.
   - `verify_figures()`: extracts every currency amount from generated prose, normalizes units (`$15,000,000`, `$15 million` and `$15M` all reduce to `15000000.0`), and reports any value absent from that section's source text. Unit-tested against the real `$105M` case and against a `$50,000,000`-for-`$15,000,000` transcription error; stays silent on legitimate unit restatement.
   - **Currently a warning, not a failure.** The file header and the function docstring both record that an unverified figure must **hard-fail** the run before send-to-inbox wiring.

6. **Foreign-recipient content suppressed (operator decision).** Sheldon: *"I don't want to see any international activity. Simply does not apply."* Boundary chosen after review: **foreign recipients only**, not all foreign-referencing content.

   Suppression requires **both** a funding-instrument marker (`notice of award`, `cooperative agreement`, `to fund`, `grant to`) **and** a foreign-recipient marker (`ministry of health` / `ministry of` — no US agency is a ministry — or a word-boundary match against a curated country list). Requiring both is what keeps a domestic rule that merely cites another country.

   Validated on live data: the three CDC foreign awards suppressed; **kept** were the $1.5M Public Health Foundation award (domestic recipient, identical instrument), the Sections 362/365 entry-suspension order (names foreign countries, not a funding instrument), and a device rule citing a foreign manufacturer.

   Every suppressed document prints in a `SUPPRESSED (out of scope)` block above the brief with its reason. **This filter is never silent** — a false positive is a content gap the reader cannot see.

7. **Executive-summary scaffolding leak.** v2's summary said *"several final rules and proposed rules from the Cross-Program section"* — narrating its own internal filing bucket to the reader. Prompt now forbids naming internal sections.

8. **Scrape gap Aug 18–20 — root cause corrected.** Initially diagnosed as the Mac sleeping, on the Entry #018 pattern. `pmset -g sched` showed a single repeating wake at 03:55 for the backup and nothing near the 01:00 scrape, which fit. **The operator then reported the MacBook Air was unplugged and ran the battery flat.** That is a cold power-off, not sleep: `pmset wakepoweron` fires only on AC, and a machine that boots cold does not restore containers until someone logs in.

   Consequence: **`pmset` is not the fix.** The durable fix is scraper **catch-up logic** — computing `days_back` from the last successful `scraper_runs` entry rather than assuming 1 — which self-heals after any outage regardless of cause. `scraper_runs` exists (Migration 005) and already carries what is needed. Not built this session.

---

### Validated end state

Final v3 run: 21 documents in, 3 suppressed, 18 briefed. Cross-Program 16. No truncation, no markdown, no emoji, no `[n]` leakage, no fabricated total, no internal section names in reader-facing text. Proposed rules label correctly throughout — the SNAP administrative cost-sharing rule leads its section as a proposed rule with the comment period extended to September 8, 2026.

Spot-checked one date claim against source: the SNAP section's *"originally published in the Federal Register on June 24, 2026"* appears verbatim in the abstract. Correct transcription.

---

### Known gaps leaving this session

- **`verify_figures()` has not fired on a live run.** The documents carrying dollar amounts were the suppressed ones, so no currency reached the prose. Unit-tested only. Do not treat as proven.
- **Verification covers currency only.** Dates, Federal Register citations and counts are equally fabricable and equally damaging. Nothing checks them.
- **One document dropped from prose.** The FDA "Announcement of Office of Management and Budget Approvals" appears in the attribution addendum but not the narrative — 15 of 16 Cross-Program documents covered. The v2 run did include it.
- **ISO dates in reader-facing prose.** v3 writes *"published a proposed rule on 2026-08-17"*; v2 wrote *"August 17, 2026."* Reads as machine output in an executive email.
- **ORR routes to TANF.** The Burke Law Group withdrawal is an Office of Refugee Resettlement notice, routed to TANF because both sit under the Children and Families Administration. Fixing it requires deciding where ORR content belongs — a scope decision, not a bug fix.
- **Content gap August 18–20** from the battery outage. Not backfilled.
