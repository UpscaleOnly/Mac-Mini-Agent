# Next-session opener — paste this as your first message

*(Written August 20, 2026 at the close of Entry #019. Everything below is stated inline so the session does not depend on memory or on project knowledge.)*

---

Starting a new OpenClaw session. Read this first — it carries current state
inline and supersedes memory. Project knowledge is still a lagging mirror
(rebuild pending), so trust this message and disk/Git over it. Memory is never
authoritative.

PRIORITY THIS SESSION: production over governance. The federal_policy_brief
agent is the deliverable. Governance and housekeeping are opportunistic and do
not block shipping.

SOURCE OF TRUTH: Disk (~/openclaw) + Git are canonical; GitHub in sync at
commit cb03e58 (Aug 20, 2026). Live PostgreSQL schema is version 6.
~/openclaw/CURRENT_STATE.md is current as of Aug 20 — read it.

SHIPPED LAST SESSION (Aug 20, Entry #019):
- Scraper TYPE_MAP fixed. It now accepts BOTH Federal Register vocabularies —
  the query-filter codes we send (RULE, PRORULE, NOTICE, PRESDOCU) and the
  display strings the API returns ("Rule", "Proposed Rule", ...). Unknown
  types now log a WARNING with the document number instead of silently
  becoming 'other'. Rebuilt and running.
- 15 banked rows relabeled to proposed_rule. Each document number was checked
  against the Federal Register API rather than inferred. content_type is now
  notice 195, final_rule 26, proposed_rule 15, other 0.
- generate_brief_review.py is at v3. WINDOW_DAYS back to 7.
- Removed the "document" HIGH_SIGNAL workaround (no longer needed).

THE FINDING THAT MATTERS MOST — GEMMA FABRICATED A DOLLAR FIGURE.
It reported three CDC awards ($15M + $30M + $30M = $75M) as "totaling
approximately $105 million." No source states any total; the number is wrong
by 40%. The system prompt already said "summarize only what the sources
state" — prompting alone did not hold, the same lesson as markdown in v1.
v3 adds an explicit arithmetic prohibition plus verify_figures(), which checks
every currency amount in generated prose against that section's source text.
TWO IMPORTANT CAVEATS:
  - verify_figures() has NOT yet fired on a live run. The documents carrying
    dollar amounts were the ones suppressed as out-of-scope. Unit-tested only.
    Do not treat it as proven.
  - It checks CURRENCY ONLY. A fabricated date or Federal Register citation
    is equally damaging and nothing catches one.
This is the gate on send-wiring. Task 1 below.

THE OTHER BIG FINDING — ENTRY #018's DIAGNOSIS WAS WRONG.
Entry #018 recorded "oversized sections degrade output" (roman-numeral
outlines, self-contradiction, covering a third of inputs, [n] index leakage)
and proposed building a significance-ranking system. The real cause was that
Ollama ran gemma4:e4b at a 4096-token context — prompt AND response combined.
A 19-document section overran it, so the earliest documents fell out unseen
and the response truncated mid-sentence. Setting NUM_CTX = 8192 fixed it in
one line; the re-run covered all 19 documents in clean prose. Ranking may
still be wanted for editorial reasons, but do NOT build it as a fix for
truncation. If WINDOW_DAYS ever rises, check NUM_CTX first.

LIVE-STATE FACTS TO CARRY (do not re-discover these):
- scraped_content is project-scoped: every query MUST filter
  WHERE project = 'federal_policy_brief'.
- Coverage is Apr 24 -> Aug 17. GAP: Aug 18-20, not backfilled. All rows are
  still is_new = TRUE. A 7-day window on Aug 20 returned 21 documents.
- raw_content is title + abstract only (~569 chars avg), by design.
- Generator model: gemma4:e4b (llama3.2 is the lightweight fallback).
- DB PASSWORD: the live openclaw role password is NOT "changeme". Container
  env and Keychain both hold that stale placeholder; the real value is in
  ~/openclaw/.env. Host-run scripts need it exported in EVERY new terminal
  window. Read it WITHOUT printing it:
    export POSTGRES_PASSWORD=$(grep -m1 '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)
  Verify with a length check, not by echoing the value.
- DB queries can skip the password entirely by going through the container:
    docker exec openclaw_postgres psql -U openclaw -d openclaw -c "..."
- SCRAPER RELIABILITY: the nightly scrape is APScheduler INSIDE
  openclaw_fastapi. Two gaps so far. Aug 9-16 was Docker down; Aug 18-20 was
  the MacBook Air unplugged and run flat — a cold power-off, which no pmset
  wake fixes (wakepoweron is AC-only, and a cold boot does not restore
  containers until someone logs in). macOS also allows only ONE repeating
  power event, so a 00:55 wake would displace the 03:55 backup wake. Do not
  reach for pmset; build catch-up logic. Check `docker ps` early either way.

IMMEDIATE TASKS (production-first):

1. Extend fabrication verification beyond currency — HIGH, do this first.
   Dates, Federal Register citations and counts need the same treatment
   verify_figures() gives dollar amounts. Also decide the failure mode: while
   review-only an unverified figure is a warning, but before send-wiring it
   must HARD-FAIL the run rather than send. Both the file header and the
   verify_figures() docstring carry that note.

2. Scraper catch-up logic.
   Compute days_back from the last successful scraper_runs entry instead of
   assuming 1, so any outage self-heals on the next run regardless of cause.
   The scraper_runs table already exists (Migration 005). This is the durable
   answer to both data gaps. Requires docker compose build fastapi + up -d.

3. Output polish (small, do when convenient):
   - v3 writes ISO dates into reader-facing prose ("published a proposed rule
     on 2026-08-17"). v2 wrote "August 17, 2026". Fix the prompt.
   - One document was dropped from the prose in the final v3 run: the FDA
     "Announcement of Office of Management and Budget Approvals" is in the
     attribution addendum but not the narrative. 15 of 16 covered.
   - ORR content routes to TANF (the Burke Law Group withdrawal is an Office
     of Refugee Resettlement notice). Both sit under the Children and
     Families Administration. Fixing this means deciding where ORR belongs —
     a scope decision, not a bug fix.

4. Once the brief reads clean: wire send-to-inbox — delivery mechanism +
   brief_runs logging + flip is_new on consumed rows. Still gated on the
   ADR-039 email-provider and sender-domain decisions.

HOUSEKEEPING (opportunistic — never ahead of the above):
- v3.0 instructions refresh: schema 4->6; "read changelog first"->"read
  CURRENT_STATE.md first"; "governance precedes features"->"governance serves
  shipping"; retire the weekly-reupload mandate as load-bearing; 39+->41+
  ADRs; ADR-014 OPEN->operative.
- Rebuild project knowledge as a clean one-way mirror of disk.
- Reconcile the stale credential stores (container env, Keychain) with the
  live Postgres password; finish rotation.
- Close ADR-041 as "not needed" if that still holds.
- Fix Ctrl+C not interrupting in Terminal. Less urgent now — a 7-day run takes
  about a minute, not twenty.

WORKING RULES (unchanged): one command at a time, no shell on the Mac, approve
before building, .py delivered as .txt, git commit -m only, token conservation.

PRACTICAL NOTES:
- A code block in chat means "run this." Illustrative code and mappings belong
  in prose — pasted into zsh they just produce "command not found."
- Back up a working file before replacing it: cp file.py file.py.bak.vN.
- Browser download collisions: a second download of the same filename becomes
  name_1.txt. Check `ls -lt ~/Downloads | head -4` and match the byte count
  before copying. `cp source.txt dest.py` renames in one step. A one- or
  two-byte size difference is usually characters vs bytes in a UTF-8 file —
  diff it before assuming corruption.
- Granting the Claude desktop app read access to ~/openclaw makes verification
  fast: every file written this session was read back off disk and diffed
  against what was built before moving on. That is file transfer, not shell
  execution, so ADR-014 is untouched. Write access remains declined.
- Prefer an authoritative source over a clever inference. The 15-row backfill
  could have been deduced from which type codes could possibly have gotten
  in; querying the Federal Register API instead took one call and removed the
  guess — and two "Request for Information" titles would have been plausible
  wrong calls.
