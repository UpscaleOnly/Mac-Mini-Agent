# KNOWLEDGE.md — federal_policy_brief

> Persona: Prototype (scraping delegated to Automate)
> Project: federal_policy_brief
> Last Updated: April 12, 2026
> Status: INITIAL SEED — domain knowledge pre-loaded from project specification

---

## Program Area Definitions

### K-001 · Medicaid and CHIP
Federal-state health insurance program for low-income individuals. CHIP covers children in families above Medicaid thresholds but below commercial insurance affordability. Key content types: waivers, state plan amendments, FMAP changes, enrollment policy, managed care rules. Primary federal sources: CMS (cms.gov), HHS (hhs.gov). Primary analysis sources: KFF (kff.org), MACPAC (macpac.gov), NASHP (nashp.org).

### K-002 · SNAP (Supplemental Nutrition Assistance Program)
Federally funded, state-administered nutrition assistance. Key content types: eligibility thresholds, work requirements, recertification, ABAWD (able-bodied adults without dependents) policy, E&T (employment and training) programs. Primary federal source: USDA/FNS (usda.gov). Primary analysis source: CBPP (cbpp.org).

### K-003 · TANF (Temporary Assistance for Needy Families)
Block grant program providing cash assistance and services to low-income families. Key content types: block grant policy, work participation rates, MOE (maintenance of effort) requirements, reauthorization activity. Primary federal source: ACF (acf.hhs.gov). Primary analysis sources: CBPP (cbpp.org), CLASP (clasp.org).

### K-004 · FMAP (Federal Medical Assistance Percentage)
The federal government's share of Medicaid costs, varying by state based on per capita income. Key content types: annual FMAP rate publications, enhanced match changes (e.g., ACA expansion, disaster FMAP, PHE-related adjustments). Source: CMS and Federal Register.

### K-005 · Cross-Program
Developments affecting multiple benefit programs simultaneously. Examples: omnibus budget legislation with provisions across Medicaid, SNAP, and TANF; executive orders affecting federal agency rulemaking broadly; government shutdown or continuing resolution impacts on benefit program operations.

---

## Functional Area Definitions

### K-010 · Rulemaking
The Federal Register process: advance notice of proposed rulemaking (ANPRM) → proposed rule (NPRM) → public comment period → final rule. Each stage has different urgency for state agencies. Final rules with short implementation timelines are highest priority.

### K-011 · Claims Processing
Federal financial participation (FFP) in state administrative costs. Changes to cost allocation methodologies, reimbursement rates, or claiming procedures directly affect state agency budgets. CMS is the primary source.

### K-012 · Benefit Eligibility
Income thresholds, categorical eligibility, continuous eligibility, redetermination procedures. Changes here affect who qualifies for benefits and how states process applications and renewals. IRS guidance on income definitions also relevant.

### K-013 · Comment Periods
Open Federal Register comment periods with deadlines. State agencies often submit comments. Tracking deadlines is a high-value service — missed comment periods cannot be reopened.

---

## Source Domain Intelligence

### K-020 · Federal Register API
federalregister.gov provides a public REST API (no authentication required). Supports searching by agency, document type, date range, and CFR citation. Returns structured JSON. This is the most automatable source — scraper should use the API rather than HTML scraping. Documentation at federalregister.gov/developers.

### K-021 · CMS Document Types
CMS publishes several document types relevant to this brief:
- **SMD Letters** (State Medicaid Director Letters) — policy guidance to state Medicaid directors
- **SHO Letters** (State Health Official Letters) — broader health policy guidance
- **PIBs** (Program Information Bulletins) — operational guidance
- **Informational Bulletins** — general updates
These are often published as PDFs on cms.gov without structured metadata. HTML scraping plus PDF text extraction likely required.

### K-022 · Congressional Tracking
congress.gov provides bill text, status, committee actions, and floor votes. The site has structured data but no public API equivalent to the Federal Register. Key tracking: bills referred to committees with jurisdiction over Medicaid, SNAP, TANF. Committee names vary by Congress but typically include Senate Finance, House Ways and Means, House Energy and Commerce, Senate HELP.

### K-023 · State Agency Naming Conventions
Target audience agencies have different names across states. Common variations:
- Department of Health and Human Services (most states)
- Department of Social Services
- Department of Transitional Assistance (e.g., Massachusetts)
- Department of Human Services
- Office of Medicaid (sometimes standalone)
- Health Care Authority (e.g., Washington)
Understanding these variations matters for subscriber outreach and marketing.

---

## Email Deliverability Knowledge

### K-030 · Spam Filter Considerations
State agency email systems typically run enterprise spam filters (Proofpoint, Mimecast, Microsoft Defender for Office 365). Key factors:
- Authenticated sender domain (SPF + DKIM + DMARC) is mandatory — unauthenticated email will be quarantined or rejected
- Plain text email body scores lower than HTML
- No embedded links in email body reduces spam score
- PDF attachments from authenticated domains are generally accepted
- Sender reputation warmup required — start with low volume and gradually increase
- List-Unsubscribe header reduces complaint rate

### K-031 · CAN-SPAM Requirements
Commercial email must include: sender identification, physical postal address, clear unsubscribe mechanism, honor opt-out within 10 business days. The daily brief is commercial email (paid subscription is the goal). Compliance is mandatory from beta distribution onward.

---

## Competitive Landscape

### K-040 · Existing Services
The brief occupies a gap between free-but-unfocused government monitoring tools and enterprise-priced platforms:
- **Regulations.gov** — free, focused on comment tracking, not curated briefings
- **GovTrack** — free, legislative tracking, not executive-level summaries
- **FiscalNote** — enterprise SaaS, comprehensive but expensive and overbuilt for a state agency policy director
- **CQ/Roll Call** — congressional tracking, subscription-based, not benefit-program-specific
- **Bloomberg Government** — comprehensive but premium-priced

The product value proposition: curated, program-specific, executive-level, affordable, delivered as a PDF to the inbox. No login required to read the brief.

### K-041 · State Agency Procurement
State agencies purchase SaaS through competitive procurement or sole-source micro-purchase. Micro-purchase thresholds vary by state but commonly range from $5,000 to $25,000. Pricing at or below the threshold enables direct purchase without formal RFP. Research task pending: identify specific thresholds in target states.

---

## Formatting Conventions

### K-050 · Brief Section Structure
Each detailed section in the daily brief includes:
1. Headline (plain language, not the official document title)
2. Summary (2–4 sentences, plain language)
3. Publishing agency or body
4. Publication date
5. Program area tag (Medicaid/CHIP, SNAP, TANF, Cross-Program)

### K-051 · Executive Summary Style
One paragraph, 3–5 sentences. Leads with the most significant development. Uses active voice. No acronyms without first use definition (except universally known: CMS, HHS, SNAP). Written for someone reading on a phone screen.

### K-052 · PDF Navigation
Internal navigation links connect executive summary items to their corresponding detailed sections. Reader can tap a headline in the executive summary to jump to the full detail.

---

## Session Notes

*This section grows as the agent works on the project. Each entry includes a session_id for traceability back to the full transcript in the sessions/ directory.*

*(No sessions recorded yet — project is in specification phase.)*
