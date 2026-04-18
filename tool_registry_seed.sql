-- ============================================================================
-- OpenClaw Tool Registry — Phase 1 + Phase 1.5 Seed Data
-- ============================================================================
-- ADR-035 §5.5: All tools INSERT with enabled = FALSE.
-- Operator enables individually after implementation code is confirmed.
--
-- 11 Phase 1 tools + 2 Phase 1.5 tools = 13 total rows
--
-- Run as: docker exec -i openclaw_postgres psql -U openclaw -d openclaw -f -
--         < tool_registry_seed.sql
--
-- Date: April 13, 2026
-- Step: ADR-035 Implementation Sequence Step 9
-- ============================================================================

-- Prevent duplicate inserts if run more than once
BEGIN;

-- ============================================================================
-- PHASE 1 — CORE (3 tools)
-- ============================================================================

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'llm_query',
    'Send a prompt to the configured LLM (Ollama local or OpenRouter cloud) and return the completion. Core reasoning capability for all personas. Model tier selection governed by ADR-021 LayerModel routing.',
    ARRAY['prototype', 'automate', 'research'],
    'low',
    0,          -- read-only reasoning, no side effects
    1,          -- all trust tiers
    FALSE,
    NULL,       -- no direct network egress; LLM routing layer handles connectivity
    NULL,       -- unlimited within session budget
    NULL,       -- input_schema populated when implementation confirmed
    NULL,       -- output_schema populated when ADR-022 validation wired
    'phase1',
    FALSE,
    NOW()
);

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'web_search_local',
    'Query the Brave Search API and summarize results through Tier 1 local Ollama model before context injection. Max 5 results per query. Caps context contribution at 200-400 tokens per query. Every call logged to agent_actions with query string, result count, and summarized output. Brave API key stored in environment variables under openclaw account only. ADR-033 Session 10 custom skill.',
    ARRAY['research'],
    'low',
    0,          -- read-only search, no side effects
    1,
    FALSE,
    ARRAY['api.search.brave.com'],
    3,          -- max 3 queries per session without operator approval (ADR-033 Session 10)
    NULL,
    NULL,
    'phase1',
    FALSE,
    NOW()
);

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'web_fetch',
    'Fetch the contents of a URL. Used for scraping government data sources (Federal Register, HHS, USDA, state legislature sites, NH municipal domains). Permitted destinations must be a subset of the persona ADR-030 network policy YAML.',
    ARRAY['prototype', 'automate'],
    'low',
    0,          -- read-only fetch, no side effects
    2,          -- low-risk write tier required (network egress)
    FALSE,
    NULL,       -- populated per-persona from ADR-030 YAML when policy files are created
    NULL,       -- unlimited within session budget
    NULL,
    NULL,
    'phase1',
    FALSE,
    NOW()
);

-- ============================================================================
-- PHASE 1 — FILESYSTEM (3 tools)
-- ============================================================================

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'file_write_staging',
    'Write a file to the ~/openclaw/staging/ directory. This is the only writable directory for agent-produced files. Files here are reviewed by the operator before being moved to final locations. No overwrites without operator approval.',
    ARRAY['prototype', 'automate'],
    'low',
    5,          -- low-risk write to sandboxed directory
    2,          -- low-risk write tier
    FALSE,
    NULL,       -- no network egress
    NULL,
    NULL,
    NULL,
    'phase1',
    FALSE,
    NOW()
);

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'file_read',
    'Read the contents of a file from the ~/openclaw/staging/ directory or the persona workspace directory. Required for iteration — agents must be able to read back their own output. Read-only, no side effects.',
    ARRAY['prototype', 'automate', 'research'],
    'low',
    0,          -- read-only
    1,
    FALSE,
    NULL,       -- no network egress
    NULL,
    NULL,
    NULL,
    'phase1',
    FALSE,
    NOW()
);

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'file_list',
    'List files and directories in the ~/openclaw/staging/ directory or the persona workspace directory. Returns file names, sizes, and modified timestamps. Prevents blind writes and duplicate files.',
    ARRAY['prototype', 'automate', 'research'],
    'low',
    0,          -- read-only
    1,
    FALSE,
    NULL,       -- no network egress
    NULL,
    NULL,
    NULL,
    'phase1',
    FALSE,
    NOW()
);

-- ============================================================================
-- PHASE 1 — MEMORY / VECTOR STORE (2 tools)
-- ============================================================================

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'chromadb_ingest',
    'Insert documents into the persona ChromaDB namespace. Each persona has its own isolated namespace. Documents are chunked and embedded before storage. Used for RAG corpus building.',
    ARRAY['prototype', 'automate'],
    'low',
    5,          -- write to vector store, but append-only and namespace-isolated
    2,          -- low-risk write tier
    FALSE,
    NULL,       -- ChromaDB is internal, no network egress
    NULL,
    NULL,
    NULL,
    'phase1',
    FALSE,
    NOW()
);

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'chromadb_query',
    'Query the persona ChromaDB namespace for relevant documents. Returns ranked results with similarity scores. Used for RAG retrieval at inference time. Read-only, no side effects.',
    ARRAY['prototype', 'automate', 'research'],
    'low',
    0,          -- read-only query
    1,
    FALSE,
    NULL,       -- ChromaDB is internal, no network egress
    NULL,
    NULL,
    NULL,
    'phase1',
    FALSE,
    NOW()
);

-- ============================================================================
-- PHASE 1 — DATABASE (2 tools)
-- ============================================================================

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'pg_read',
    'Execute a read-only SQL query against the agentdb PostgreSQL database. SELECT statements only. Used for metrics retrieval, session history lookup, and data queries. No DDL or DML permitted.',
    ARRAY['prototype', 'automate', 'research'],
    'low',
    0,          -- read-only
    1,
    FALSE,
    NULL,       -- PostgreSQL is internal, no network egress
    NULL,
    NULL,
    NULL,
    'phase1',
    FALSE,
    NOW()
);

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'pg_write',
    'Execute an INSERT or UPDATE against allowed PostgreSQL tables in agentdb. DELETE and DDL statements are prohibited. Allowed tables defined in implementation. Used for persisting agent-produced data, knowledge updates, and project records.',
    ARRAY['prototype', 'automate'],
    'medium',
    15,         -- moderate write risk; wrong data persisted is correctable but costly
    2,          -- low-risk write tier
    FALSE,
    NULL,       -- PostgreSQL is internal, no network egress
    NULL,
    NULL,
    NULL,
    'phase1',
    FALSE,
    NOW()
);

-- ============================================================================
-- PHASE 1 — EXECUTION (1 tool)
-- ============================================================================

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'shell_exec',
    'Execute a shell command within ADR-014 guardrails. Every invocation requires operator Telegram approval regardless of irreversibility score. Commands are logged to agent_actions with full command string, exit code, stdout, and stderr. Prohibited commands enforced by interceptor allowlist.',
    ARRAY['prototype'],
    'high',
    25,         -- shell execution carries meaningful risk
    3,          -- operator-approved tier required
    TRUE,       -- every call requires Telegram Y/N regardless of score
    NULL,       -- no network egress from shell commands
    5,          -- hard cap per session; forces agent to be deliberate
    NULL,
    NULL,
    'phase1',
    FALSE,
    NOW()
);

-- ============================================================================
-- PHASE 1.5 — DEFERRED (2 tools)
-- Registered now for visibility. Enabled after Phase 1 is stable.
-- ============================================================================

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'schema_introspect',
    'Inspect PostgreSQL table structure: list tables, columns, types, indexes, and constraints. Read-only metadata query against information_schema and pg_catalog. Enables agents to compose their own SQL queries accurately without hardcoded schema knowledge.',
    ARRAY['prototype', 'automate', 'research'],
    'low',
    0,          -- read-only metadata
    1,
    FALSE,
    NULL,       -- PostgreSQL is internal, no network egress
    NULL,
    NULL,
    NULL,
    'phase1.5',
    FALSE,
    NOW()
);

INSERT INTO tool_registry (
    tool_name, description, permitted_personas, risk_level,
    irreversibility_score, min_trust_tier, requires_approval,
    permitted_network_destinations, max_calls_per_session,
    input_schema, output_schema, phase_available, enabled, last_reviewed_at
) VALUES (
    'code_run_python',
    'Execute a Python script in a sandboxed environment within the FastAPI container. Returns stdout, stderr, and exit code. No filesystem access outside ~/openclaw/staging/. No network access. Used for data transformations, validation logic, and computation that does not require shell-level access.',
    ARRAY['prototype', 'automate'],
    'medium',
    10,         -- sandboxed execution, limited blast radius
    2,          -- low-risk write tier (produces output files)
    FALSE,
    NULL,       -- no network egress; sandbox enforced
    10,         -- reasonable per-session cap
    NULL,
    NULL,
    'phase1.5',
    FALSE,
    NOW()
);

COMMIT;

-- ============================================================================
-- Verification query — run after INSERT to confirm all 13 rows
-- ============================================================================
SELECT tool_name, phase_available, risk_level, irreversibility_score,
       min_trust_tier, requires_approval, enabled,
       array_to_string(permitted_personas, ', ') AS personas
FROM tool_registry
ORDER BY phase_available, tool_name;
