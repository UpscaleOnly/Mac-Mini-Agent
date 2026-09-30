# DECISIONS.md — federal_policy_brief

> Persona: Prototype (scraping delegated to Automate)
> Project: federal_policy_brief
> Last Updated: April 12, 2026 · Amended September 30, 2026 (Entry #050 — operator decisions on links, layout, scope and the IT Governance section)
> ADR References: ADR-024 · ADR-027 · ADR-029 · ADR-030 · ADR-031 · ADR-035 · ADR-037 · ADR-039 · ADR-047 · ADR-048

> **Reading this file:** the April 12 text is the original design record and is kept as written. Where a later operator decision changes it, a dated **Amendment** follows the original text. The amendment governs. What runs today is described in `CURRENT_STATE.md` and in the header of `generate_brief_review.py`.

---

## Product Decisions

### D-001 · Product Format
Daily weekday PDF brief delivered by email. No HTML email body. No embedded links in email or PDF. Plain text email body with 2–3 sentence introduction and PDF attachment. This minimizes spam filter scoring for state agency recipients.

**Amendment (September 30, 2026, operator decision):** the brief is delivered **weekly** as a **multipart email** — a plain-text part plus an **HTML part with clickable Federal Register links** — self-sent to the operator's own inbox (ADR-039 H4 sub-decision). There is no PDF at this stage. The spam-scoring rationale does not apply at an audience of one; revisit it before any distribution to recipients (D-020 step 2).

### D-002 · Friday Weekly Digest
Every Friday replaces the daily brief. Consolidates five daily briefs into a single narrative organized by program area (Medicaid/CHIP, SNAP, TANF, Cross-Program), not by date. Includes forward-looking section for upcoming deadlines. Length target 4–10 pages.

**Amendment (September 30, 2026):** the weekly brief is the only product today. See D-008 for the current section structure. The forward-looking deadlines section is not built; it depends on storing Federal Register comment-close and effective dates (finding F15).

### D-003 · Source Attribution Addendum
Every brief includes a Source Attribution Addendum as the final PDF section. Agency name, document title, and publication date only — no URLs. Every factual claim has a corresponding citation. Phase 2 adds a subscriber portal with clickable source links behind email-based authentication.

**Amendment (September 30, 2026, operator decision):** now **Appendix A — Sources for This Brief**, with each document's Federal Register link. Each section also ends with its own linked Sources list. Links come from stored metadata after verification; the model never writes them. See D-008 for Appendices B and C.

### D-004 · No Embedded URLs
Deliberate design decision. No clickable links in email body or PDF attachment. Avoids spam filter triggers. Recipients locate originals using agency name and document title. Phase 2 subscriber portal resolves this for subscribers.

**SUPERSEDED (September 30, 2026, operator decision):** clickable links are wanted so a reviewer can go straight to the source. Generator v9.5 added links to the source list, and v9.7 added the HTML part and per-section Sources. Only `https://www.federalregister.gov/` and register URLs (uscode.house.gov, ecfr.gov, irs.gov, cms.gov, ssa.gov) are rendered as links, and all text is escaped. Links inside the model-written prose are deferred: they need citation markers and a verifier check.

### D-005 · Target Audience
Primary: State HHS agency leadership and policy staff — commissioners, directors, deputy directors, policy staff, eligibility directors, finance office leadership. Secondary: Governor's office policy staff, state legislative fiscal offices, state budget offices. Market scope: 50 states plus territories.

### D-006 · Delivery Timing
Daily brief delivered by 6:00 AM Eastern Time. Scraping runs 1:00–4:00 AM ET. Brief generation begins at 5:00 AM ET.

### D-007 · Length Targets
Daily: 2–6 pages, designed for under 10-minute read. Weekly digest: 4–10 pages.

### D-008 · Section Structure and Appendices *(added September 30, 2026, operator decisions; generator v9.8–v9.9)*
Body, every section every week: Executive Summary → CMS (Medicaid/CHIP/Medicare) → SNAP → TANF → **IT Governance** → Cross-Program. A section with no documents carries one fixed line; the model is not called for it.
- **IT Governance** (ADR-048): SSA, CMS and IRS Privacy Act matching and system of records notices, and documents naming safeguarding terms. It points to Appendix C. Automated change monitoring of the frameworks (ADR-048 Part B) is not yet approved.
- **Appendix A** — sources for this brief (D-003).
- **Appendix B** — earlier documents published 8–30 days ago, in scope, whether or not an earlier brief carried them. Catches documents that missed their 7-day window. Reference only: never marked as briefed.
- **Appendix C** — IT Governance reference: SSA TSSR, CMS ARC-AMPE and IRS Publication 1075 with current versions, plus their governing statutes and regulations, all linked. Read from the tracked register `it_governance_sources.json`, whose citations were retrieved from uscode.house.gov and ecfr.gov, never from memory.

### D-009 · Scope Filters *(added September 30, 2026, operator decisions; generator v9.6–v9.7)*
Applied before the model; every drop is printed in the review output.
- **USDA:** kept only if the sub-agency is the Food and Nutrition Service or Food and Nutrition **Administration** (its current name), or the document mentions SNAP. Other USDA documents (marketing orders, Forest Service, APHIS …) are out of scope.
- **IRS:** kept only if HHS-adjacent — EITC, child tax credit, premium tax credit, dependent care, ACA / health coverage, Medicaid / Medicare / SNAP / TANF, child support, Treasury offset, federal tax information and safeguarding, and the IT Governance terms. Tax credits unrelated to HHS (LIHTC) and corporate items are always excluded.
- Unchanged: foreign-content drop; routine Cross-Program instruments dropped; CMS, SNAP and TANF keep every instrument.

---

## Architectural Decisions

### D-010 · Persona Split
Automate persona owns nightly data collection (scraping, parsing, deduplication, chunking, embedding). Prototype persona owns brief generation and delivery (query ChromaDB, generate content, build PDF, send email, log delivery). This separation enforces least privilege — Automate has egress to source domains, Prototype has egress to email infrastructure.

### D-011 · Inference Routing
Brief generation uses local Tier 2 inference (the single deployed local model — `gemma4:e4b` as of September 29, 2026; ADR-047) by default. This is a cost elimination decision — the brief runs daily and must not accumulate cloud API costs. Escalation to Tier 3 (32B local) permitted if quality validation fails. Cloud escalation (OpenRouter) is not used for routine brief generation.

**Amendment (September 30, 2026; ADR-047 §7–§8):** there is no 32B local model. Tier 3 is now the Claude API standard tier, and it is **disabled until built**. A rebuilt cloud path goes to the Anthropic API directly, not OpenRouter; escalation is explicit only, and briefs contain public data only. (This reference was missed by the ADR-046 F9 cleanup; corrected in Entry #050.)

### D-012 · Source Domain Allowlist
16 curated domains. No open crawl. No dynamically discovered sources. Adding a new domain requires operator approval, ADR-030 network policy update, ADR-024 Little Snitch allowlist entry, and ADR-031 change management log entry. The allowlist is a product differentiator.

### D-013 · Deduplication
Content deduplication via hash comparison against prior scrape cycle. Raw content stored in PostgreSQL with source domain, URL path, scrape timestamp, and content hash. Only new or changed content gets chunked and embedded into ChromaDB.

### D-014 · ChromaDB Namespace
All project content stored under the `federal_policy_brief` namespace in ChromaDB. Prototype queries for content added since the prior brief's generation timestamp.

### D-015 · Email Infrastructure
Own sender domain with SPF, DKIM, and DMARC configured. No free email providers. CAN-SPAM compliant unsubscribe mechanism. List-Unsubscribe header in every email. Sending infrastructure selection pending (Amazon SES, Postmark, or Mailgun).

### D-016 · PDF Filename Convention
Daily: `Federal_Policy_Brief_YYYY-MM-DD.pdf`
Weekly: `Federal_Policy_Weekly_Digest_YYYY-MM-DD.pdf`

### D-017 · Audit Logging
Every scrape, generation, and delivery event recorded in agent_actions (ADR-029). Brief generation sessions logged with session_id, token counts, and delivery status (ADR-027). Delivery logged with recipient count, send status, and any bounce/error.

---

## Go-to-Market Decisions

### D-020 · Launch Sequence
1. Internal proof of concept — operator review only
2. Beta — free distribution to known state agency contacts
3. Source domain expansion from recipient feedback (ADR-031 governed)
4. Paid subscription — pricing informed by competitive analysis
5. Bundle with state_policy_brief

### D-021 · Pricing Strategy
Target at or below state agency micro-purchase threshold to eliminate procurement overhead. Research task pending: identify thresholds in target states.

### D-022 · Product Boundary
Federal policy only. State-level legislative tracking is the scope of the companion state_policy_brief project. When a federal development has a direct state implication, the federal brief notes the implication but does not track the state response.

---

## Behavioral Rules

### B-001 · Token Conservation
This project runs daily. No cloud API costs for routine generation. Local inference only unless quality validation triggers escalation.

### B-002 · Source Fidelity
Every claim in the brief must trace to a specific source document. No uncited content. No hallucinated policy developments.

### B-003 · Tone and Style
Executive-level. Plain language. No jargon without definition. Designed to be read by a commissioner on a phone at 6:15 AM.

### B-004 · No Editorializing
The brief summarizes and attributes. It does not advocate, predict outcomes, or recommend action. Factual reporting only.
