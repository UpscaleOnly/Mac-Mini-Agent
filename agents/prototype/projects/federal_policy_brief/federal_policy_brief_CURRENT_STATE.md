# CURRENT_STATE.md — federal_policy_brief

> Persona: Prototype (scraping delegated to Automate)
> Project: federal_policy_brief
> Last Updated: April 12, 2026
> Session: Initial seed — no agent sessions yet

---

## Project Phase

**SPECIFICATION COMPLETE — PRE-IMPLEMENTATION**

The project specification (Version 1.0, April 11, 2026) is finalized and in the knowledge base. Knowledge files (DECISIONS.md, CODE_REFERENCE.md, KNOWLEDGE.md) are seeded. No code has been written. No infrastructure specific to this project has been deployed.

---

## Infrastructure Dependencies

| Dependency | Status | Notes |
|-----------|--------|-------|
| Phase 1 stack (Docker, PostgreSQL, Ollama, ChromaDB, FastAPI) | RUNNING | On MacBook Air (interim hardware) |
| FastAPI skeleton | COMMITTED | GitHub UpscaleOnly/mac-mini-agent, Option B |
| ADR-035 tables (sessions, session_budget, tool_registry, session_state) | SCHEMA DEFINED | Not yet created in PostgreSQL |
| ADR-037 TranscriptManager | DESIGNED | Not yet implemented |
| ADR-037 HealthMonitor | DESIGNED | Not yet implemented |
| Automate persona Docker sandbox | NOT DEPLOYED | Required before scraping begins |
| Prototype persona Docker sandbox | NOT DEPLOYED | Required before brief generation begins |
| Ollama 14B model (Tier 2) | NOT PULLED | Required for brief generation |
| Telegram bots (per persona) | NOT CREATED | Required for operator notifications |

---

## Project-Specific Components

### Scrapers (Automate Persona) — 0 of 16 built

| # | Domain | Scraper Status | Method | Notes |
|---|--------|---------------|--------|-------|
| 1 | congress.gov | NOT STARTED | HTML scrape | No public API |
| 2 | federalregister.gov | NOT STARTED | REST API | Public API available — build first |
| 3 | hhs.gov | NOT STARTED | HTML scrape | |
| 4 | cms.gov | NOT STARTED | HTML scrape + PDF extract | SMD/SHO letters often published as PDFs |
| 5 | usda.gov | NOT STARTED | HTML scrape | FNS guidance pages |
| 6 | acf.hhs.gov | NOT STARTED | HTML scrape | |
| 7 | irs.gov | NOT STARTED | HTML scrape | |
| 8 | ssa.gov | NOT STARTED | HTML scrape | |
| 9 | kff.org | NOT STARTED | HTML scrape | |
| 10 | cbpp.org | NOT STARTED | HTML scrape | |
| 11 | clasp.org | NOT STARTED | HTML scrape | |
| 12 | nashp.org | NOT STARTED | HTML scrape | |
| 13 | ncsl.org | NOT STARTED | HTML scrape | |
| 14 | nga.org | NOT STARTED | HTML scrape | |
| 15 | aphsa.org | NOT STARTED | HTML scrape | |
| 16 | macpac.gov | NOT STARTED | HTML scrape | |

*Recommended build order: federalregister.gov first (structured API, highest volume), then cms.gov and hhs.gov (primary Medicaid sources), then remaining federal, then nonprofit/research, then legislative tracking.*

### Database Tables — 0 of 2 created

| Table | Status | Notes |
|-------|--------|-------|
| scraped_content | NOT CREATED | Schema defined in CODE_REFERENCE.md |
| brief_runs | NOT CREATED | Schema defined in CODE_REFERENCE.md |

### Brief Generation Pipeline (Prototype Persona)

| Component | Status | Notes |
|-----------|--------|-------|
| ChromaDB query module | NOT STARTED | Query by scrape_timestamp > last brief |
| Brief generator (Tier 2 inference) | NOT STARTED | Executive summary + detailed sections |
| Source Attribution Addendum builder | NOT STARTED | From scrape metadata |
| PDF builder | NOT STARTED | Library selection pending (Open Item #3) |
| Internal navigation links (PDF) | NOT STARTED | Depends on PDF library selection |

### Email Delivery

| Component | Status | Notes |
|-----------|--------|-------|
| Sending infrastructure | NOT SELECTED | SES vs Postmark vs Mailgun (Open Item #1) |
| Sender domain | NOT PURCHASED | Requires DNS config: SPF, DKIM, DMARC (Open Item #2) |
| Send module | NOT STARTED | Depends on infrastructure selection |
| Subscriber management | NOT STARTED | Required before beta distribution |
| CAN-SPAM compliance | NOT STARTED | List-Unsubscribe header, unsubscribe mechanism |

### Network Policy

| File | Status | Notes |
|------|--------|-------|
| automate_network_policy.yaml | NOT CREATED | Must include all 16 source domains |
| prototype_network_policy.yaml | NOT CREATED | Must include email infrastructure domain |
| ADR-024 Little Snitch allowlist entries | NOT CREATED | 16 source domains + email domain |

---

## Open Decisions Pending Operator Input

| # | Decision Needed | Impact | Blocking |
|---|----------------|--------|----------|
| 1 | Email sending infrastructure (SES vs Postmark vs Mailgun) | Determines egress domain, SDK, pricing model | Email delivery module, network policy, DNS config |
| 2 | Sender domain name | Determines DNS records, sender reputation, brand identity | Domain purchase, DNS setup, email warmup |
| 3 | PDF generation library (ReportLab vs WeasyPrint vs FPDF2) | Determines PDF build approach, internal link support | PDF builder module |

---

## Blocking Chain

The implementation sequence has a clear critical path:

1. **Phase 1 stack must be stable** — personas deployed, ADR-035 tables created, ADR-037 services running
2. **Automate persona operational** — Docker sandbox, network policy, Telegram bot
3. **First scraper built** (federalregister.gov) — proves the pipeline end-to-end
4. **scraped_content table created** — stores raw scraped data
5. **ChromaDB embedding pipeline** — chunks and embeds scraped content
6. **Brief generator** — queries ChromaDB, generates content via Tier 2 inference
7. **PDF builder** — requires library selection decision
8. **Email infrastructure** — requires sender domain and infrastructure selection decisions
9. **Internal proof of concept** — operator-only brief delivery
10. **Beta distribution** — free to known contacts, requires subscription management

Steps 1–2 are shared infrastructure (not project-specific).
Steps 3–6 can proceed without the email and PDF decisions.
Steps 7–8 are blocked on operator decisions #1, #2, #3 above.

---

## Milestones

| Milestone | Target | Status |
|-----------|--------|--------|
| Specification complete | April 11, 2026 | DONE |
| Knowledge files seeded | April 12, 2026 | DONE |
| Phase 1 stack stable | TBD | PENDING — on MacBook Air, Mac Studio deferred to M5 |
| First scraper operational | TBD | NOT STARTED |
| End-to-end pipeline test | TBD | NOT STARTED |
| Internal proof of concept | TBD | NOT STARTED |
| Beta distribution | TBD | NOT STARTED |
| Paid subscription launch | TBD | NOT STARTED |

---

## Last Session Summary

*No agent sessions recorded yet. This section will be auto-updated by the TranscriptManager (ADR-037) at the end of each session that touches this project.*

---

## Active Errors / Warnings

None. Project is in pre-implementation phase.
