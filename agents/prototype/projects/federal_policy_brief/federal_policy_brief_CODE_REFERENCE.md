# CODE_REFERENCE.md — federal_policy_brief

> Persona: Prototype (scraping delegated to Automate)
> Project: federal_policy_brief
> Last Updated: April 12, 2026
> Status: PRE-IMPLEMENTATION — schemas defined, code not yet written

---

## Project Directory Structure

```
/agents/prototype/projects/federal_policy_brief/
├── DECISIONS.md              # Architectural and product decisions
├── CODE_REFERENCE.md         # This file — technical reference
├── KNOWLEDGE.md              # Domain knowledge and learned facts
├── config/
│   └── source_domains.yaml   # 16 whitelisted source domains
├── scraper/                  # Automate persona — nightly collection
│   ├── scrapers/             # Per-domain scraper modules
│   └── dedup.py              # Content hash deduplication
├── generator/                # Prototype persona — brief generation
│   ├── query_chroma.py       # Query ChromaDB for new content
│   ├── generate_brief.py     # Local inference brief generation
│   └── build_pdf.py          # PDF assembly with attribution addendum
├── delivery/                 # Email sending
│   ├── send_brief.py         # Email dispatch
│   └── subscriber_mgmt.py   # List management, bounce handling
├── templates/
│   └── brief_template.py     # PDF layout and formatting
└── sessions/                 # ADR-037 session transcripts (auto-generated)
```

*Note: Directory structure is planned. Implementation begins after Phase 1 stack is stable.*

---

## Database Schema

### PostgreSQL Tables (this project uses)

**scraped_content** — Raw scraped data stored by Automate persona
```sql
CREATE TABLE scraped_content (
    id              SERIAL PRIMARY KEY,
    source_domain   VARCHAR(255) NOT NULL,
    url_path        TEXT NOT NULL,
    content_hash    VARCHAR(64) NOT NULL,     -- SHA-256 for dedup
    raw_content     TEXT NOT NULL,
    scrape_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    content_type    VARCHAR(50),              -- e.g., 'proposed_rule', 'guidance', 'legislation'
    publishing_agency VARCHAR(255),
    document_title  TEXT,
    publication_date DATE,
    is_new          BOOLEAN DEFAULT TRUE,     -- FALSE after processed into brief
    UNIQUE(source_domain, content_hash)
);
CREATE INDEX idx_scraped_content_timestamp ON scraped_content(scrape_timestamp);
CREATE INDEX idx_scraped_content_new ON scraped_content(is_new) WHERE is_new = TRUE;
```

**brief_runs** — Record of each brief generation and delivery
```sql
CREATE TABLE brief_runs (
    id              SERIAL PRIMARY KEY,
    run_date        DATE NOT NULL,
    brief_type      VARCHAR(10) NOT NULL,     -- 'daily' or 'weekly'
    session_id      UUID REFERENCES sessions(session_id),
    generation_start TIMESTAMP WITH TIME ZONE,
    generation_end  TIMESTAMP WITH TIME ZONE,
    tokens_used     INTEGER,
    model_tier      INTEGER DEFAULT 2,        -- Tier 2 = 14B local
    pdf_filename    VARCHAR(255),
    pdf_size_bytes  INTEGER,
    sections_count  INTEGER,
    sources_cited   INTEGER,
    send_status     VARCHAR(20),              -- 'sent', 'failed', 'pending'
    recipients_count INTEGER,
    bounces         INTEGER DEFAULT 0,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(run_date, brief_type)
);
```

### ChromaDB

- **Namespace:** `federal_policy_brief`
- **Embedding model:** Local (Ollama)
- **Metadata per chunk:** source_domain, url_path, scrape_timestamp, content_hash, publishing_agency, document_title, publication_date, content_type, program_area
- **Query pattern:** Filter by `scrape_timestamp > last_brief_generation_timestamp`

### ADR-035 Tables (shared infrastructure)

- `sessions` — session tracking with trust_tier
- `session_budget` — per-session token budget tracking
- `tool_registry` — permitted tools per persona
- `session_state` — crash recovery state
- `agent_actions` — partitioned audit log (input_tokens, output_tokens columns)

### ADR-037 Tables (shared infrastructure)

- `session_transcripts` — full session capture
- `agent_heartbeat` — heartbeat during long-running tasks
- `service_health` — infrastructure health checks
- `knowledge_updates` — knowledge extraction log

---

## Source Domains (16 total)

### Federal Government (8)
| Domain | Agency | Content Type |
|--------|--------|-------------|
| congress.gov | Federal legislation | Bills, status, committee actions, votes |
| federalregister.gov | Federal Register | Proposed/final rules, notices, comments |
| hhs.gov | HHS | SMD letters, SHO letters, PIBs |
| cms.gov | CMS | Medicaid/CHIP bulletins, FMAP, waivers |
| usda.gov | USDA | SNAP policy memos, FNS guidance |
| acf.hhs.gov | ACF | TANF guidance, program instructions |
| irs.gov | IRS | Benefit eligibility/reporting guidance |
| ssa.gov | SSA | SSI/SSDI policy, COLA updates |

### Nonprofit/Research (4)
| Domain | Organization | Focus |
|--------|-------------|-------|
| kff.org | Kaiser Family Foundation | Medicaid/CHIP analysis |
| cbpp.org | CBPP | SNAP, Medicaid, TANF analysis |
| clasp.org | CLASP | TANF, child care, workforce |
| nashp.org | NASHP | State health policy, Medicaid trends |

### Legislative Tracking (4)
| Domain | Organization | Focus |
|--------|-------------|-------|
| ncsl.org | NCSL | Federal impact on states |
| nga.org | NGA | Governor policy positions |
| aphsa.org | APHSA | State HHS agency perspectives |
| macpac.gov | MACPAC | Medicaid/CHIP recommendations |

*Note: federalregister.gov has a public API. Most others require HTML scraping. Each domain requires custom parsing logic.*

---

## Pipeline Flow (runtime sequence)

1. **1:00–4:00 AM ET** — Automate scrapes all 16 domains
2. Raw content → PostgreSQL `scraped_content` table
3. Hash comparison deduplicates against prior cycle
4. New/changed content → chunk → embed into ChromaDB (`federal_policy_brief` namespace)
5. **5:00 AM ET** — Prototype queries ChromaDB for content since last brief
6. Local Tier 2 inference (14B) generates executive summary + detailed sections
7. Source Attribution Addendum generated from scrape metadata
8. PDF built and attached to email
9. Email sent via sender domain by 6:00 AM ET
10. Delivery logged to `agent_actions` and `brief_runs`

---

## Network Policy

**Automate persona** (`automate_network_policy.yaml`):
- All 16 source domains permitted for scraping

**Prototype persona** (`prototype_network_policy.yaml`):
- Email sending infrastructure domain (TBD — SES/Postmark/Mailgun)
- All 16 source domains (for reference, though scraping is Automate's job)

---

## Open Implementation Items

| # | Item | Status |
|---|------|--------|
| 1 | Email sending infrastructure selection | OPEN — SES vs Postmark vs Mailgun |
| 2 | Sender domain acquisition + DNS (SPF/DKIM/DMARC) | OPEN |
| 3 | PDF generation library (ReportLab vs WeasyPrint vs FPDF2) | OPEN |
| 4 | Per-domain scraper implementation | OPEN — 16 scrapers needed |
| 5 | Quality validation for generated content | OPEN — Phase 2 |
| 6 | Subscription management system | OPEN — required before beta |
| 7 | Subscriber portal (Phase 2) | DEFERRED |
| 8 | `scraped_content` table creation | OPEN — setup day |
| 9 | `brief_runs` table creation | OPEN — setup day |

---

## Container Context

- **FastAPI container:** `openclaw_fastapi` — runs Prototype persona brief generation
- **Ollama container:** `openclaw_ollama` — serves 14B model for Tier 2 inference
- **PostgreSQL container:** `openclaw_postgres` — stores scraped content, brief runs, audit logs
- **ChromaDB container:** `openclaw_chromadb` — vector store for embedded content chunks
