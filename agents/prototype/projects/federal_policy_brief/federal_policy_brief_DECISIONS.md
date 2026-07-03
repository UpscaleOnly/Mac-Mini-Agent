# DECISIONS.md — federal_policy_brief

> Persona: Prototype (scraping delegated to Automate)
> Project: federal_policy_brief
> Last Updated: April 12, 2026
> ADR References: ADR-024 · ADR-027 · ADR-029 · ADR-030 · ADR-031 · ADR-035 · ADR-037

---

## Product Decisions

### D-001 · Product Format
Daily weekday PDF brief delivered by email. No HTML email body. No embedded links in email or PDF. Plain text email body with 2–3 sentence introduction and PDF attachment. This minimizes spam filter scoring for state agency recipients.

### D-002 · Friday Weekly Digest
Every Friday replaces the daily brief. Consolidates five daily briefs into a single narrative organized by program area (Medicaid/CHIP, SNAP, TANF, Cross-Program), not by date. Includes forward-looking section for upcoming deadlines. Length target 4–10 pages.

### D-003 · Source Attribution Addendum
Every brief includes a Source Attribution Addendum as the final PDF section. Agency name, document title, and publication date only — no URLs. Every factual claim has a corresponding citation. Phase 2 adds a subscriber portal with clickable source links behind email-based authentication.

### D-004 · No Embedded URLs
Deliberate design decision. No clickable links in email body or PDF attachment. Avoids spam filter triggers. Recipients locate originals using agency name and document title. Phase 2 subscriber portal resolves this for subscribers.

### D-005 · Target Audience
Primary: State HHS agency leadership and policy staff — commissioners, directors, deputy directors, policy staff, eligibility directors, finance office leadership. Secondary: Governor's office policy staff, state legislative fiscal offices, state budget offices. Market scope: 50 states plus territories.

### D-006 · Delivery Timing
Daily brief delivered by 6:00 AM Eastern Time. Scraping runs 1:00–4:00 AM ET. Brief generation begins at 5:00 AM ET.

### D-007 · Length Targets
Daily: 2–6 pages, designed for under 10-minute read. Weekly digest: 4–10 pages.

---

## Architectural Decisions

### D-010 · Persona Split
Automate persona owns nightly data collection (scraping, parsing, deduplication, chunking, embedding). Prototype persona owns brief generation and delivery (query ChromaDB, generate content, build PDF, send email, log delivery). This separation enforces least privilege — Automate has egress to source domains, Prototype has egress to email infrastructure.

### D-011 · Inference Routing
Brief generation uses local Tier 2 inference (14B model) by default. This is a cost elimination decision — the brief runs daily and must not accumulate cloud API costs. Escalation to Tier 3 (32B local) permitted if quality validation fails. Cloud escalation (OpenRouter) is not used for routine brief generation.

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
