# Design: MCP-First Personal Memory

## Overview

The current implementation already has reusable storage and recall primitives in `service.memory_ops` and `service.context_snapshots`. The refactor keeps those modules as the domain layer and replaces the FastAPI transport with an MCP server that exposes a focused tool surface.

## Architecture

### MCP Server

Add `service/mcp_server.py` as the main entrypoint. It will:

- create the MCP application
- register memory and context tools
- validate tool inputs with Pydantic models shared with the service layer
- return structured JSON-compatible objects

The server runs locally from the service directory and is intended to be launched by the MCP client or manually for local development.

### Domain Layer Reuse

Keep PostgreSQL access in:

- `service.memory_ops`
- `service.context_snapshots`

Add small helpers where current behavior is insufficient, especially for range-based filtering and proactive recall ranking.

### Tool Surface

The MCP server will expose at least these tools:

- `search_memories`
  Filter-based search by text, type, tags, archived status, importance/confidence bounds, explicit flag, and time range.
- `search_memory_window`
  Range query over memories by created/updated/valid timestamps with optional secondary filters.
- `add_memory`
  Add or update a memory entry explicitly.
- `delete_memory`
  Archive or logically delete a memory entry.
- `add_context`
  Sync or append conversation context snapshots.
- `search_context`
  Query stored context snapshots.
- `recall_for_response`
  Given the current user message and optional draft answer/topic hints, return the most relevant memories and context snippets for hidden answer enrichment.

## Proactive Recall Model

The MCP server itself cannot decide to invoke tools without the assistant/client. Therefore the “proactive” behavior will be implemented through two layers:

1. `recall_for_response` provides a single MCP tool optimized for hidden pre-answer recall.
2. Client guidance and host-level prompts explicitly allow implicit invocation and instruct the assistant to call recall when prior memory could materially improve relevance, personalization, or continuity.

This keeps the behavior deterministic and inspectable while matching the user’s desired conversational effect.

## Data and Query Design

### Schema V2

To make proactive capture, recent-summary recall, and evidence promotion easier to reason about, the storage model is re-centered around eight canonical tables:

- `memory_record`: durable long-term memory records
- `memory_vector_chunk`: embedding storage for semantic recall
- `session_state`: short-lived working memory for current focus
- `memory_candidate`: inbox/review queue for uncertain captures
- `conversation_turn`: append-only raw conversation events
- `memory_inference`: analyzer output for each turn or summary segment
- `memory_signal`: accumulated evidence across repeated observations
- `conversation_summary`: segment/topic/global-topic context summaries

Legacy tables remain only as migration sources. Runtime queries and writes target the v2 tables.

### Domain Governance V3 Direction

The current v2 schema still treats several semantic fields as `VARCHAR + CHECK` constrained literals. That is acceptable for execution-oriented enums but becomes brittle for expandable business taxonomies.

The next evolution should split these fields into two governance classes:

- fixed execution enums: `action`, `snapshot_level`, `status`, `event_type`, `role`, `evidence_type`, `time_scope`, `conflict_mode`
- registry-backed taxonomies: `memory_type`, `source_type`, and later `category` plus `attribute_key`

The key design rule is:

- execution enums may remain code constants and strong database constraints because new values require code behavior
- taxonomy values may move into registry tables because new values mostly describe data instead of changing runtime control flow

### Domain Registry Model

Add a small registry subsystem centered on four tables:

- `domain_registry`
  Declares each governable domain, for example `memory_type` or `source_type`
- `domain_value`
  Stores canonical allowed values for a domain
- `domain_value_alias`
  Maps synonyms or legacy spellings back to canonical values
- `domain_value_candidate`
  Stores AI-discovered or runtime-proposed values before approval

Suggested columns:

- `domain_registry`
  - `domain_name`
  - `domain_kind` such as `taxonomy` or `execution_enum`
  - `governance_mode` such as `fixed`, `manual_review`, `auto_approve`
  - `description`
  - `is_system`
- `domain_value`
  - `domain_name`
  - `value_key`
  - `display_name`
  - `description`
  - `status`
  - `is_builtin`
  - `created_by`
  - `metadata`
- `domain_value_alias`
  - `domain_name`
  - `alias_key`
  - `canonical_value_key`
- `domain_value_candidate`
  - `domain_name`
  - `proposed_value_key`
  - `normalized_value_key`
  - `source`
  - `source_ref`
  - `reason`
  - `confidence`
  - `status`

### Registry Resolution Flow

When the analyzer or an MCP mutation produces a value for a governable field:

1. normalize the raw value
2. resolve aliases for the target domain
3. if the value exists in `domain_value`, use it
4. if the domain is `fixed`, reject or fall back to a known default
5. if the domain is `manual_review`, insert a `domain_value_candidate`
6. if the domain is `auto_approve`, promote the candidate to `domain_value` and record provenance

This allows the model to discover new business classifications without allowing it to invent new runtime behaviors.

### Why Not Auto-Extend All Constants

Fields such as `action` and `snapshot_level` do not merely label data; they drive persistence, evidence promotion, review routing, and recall behavior. Storing a new value in the database is insufficient because the application still needs matching behavior branches.

Therefore:

- `action` and `snapshot_level` should remain fixed enums
- `memory_type` and `source_type` should become registry-backed first
- `category` and `attribute_key` may follow after the registry path proves stable

### Migration Strategy For Registry Adoption

The least disruptive rollout is:

1. create registry tables and seed built-in values for `memory_type` and `source_type`
2. keep existing string columns in `memory_record` and related tables for compatibility
3. add service-layer resolution helpers so all writes normalize through the registry
4. add MCP tools to inspect candidates and approve or reject them
5. only after the registry stabilizes, consider adding foreign keys or parallel `*_id` columns

This preserves read compatibility while letting taxonomy governance evolve incrementally.

### Memory Filtering

Extend memory search inputs with:

- `created_after` / `created_before`
- `updated_after` / `updated_before`
- `valid_at`
- `min_importance`
- `min_confidence`
- `is_explicit`

### Range Query

`search_memory_window` will support:

- selecting a time field: `created_at`, `updated_at`, `valid_from`, `valid_to`
- inclusive start and end bounds
- optional text/type/tag filters

### Recall Ranking

`recall_for_response` will:

- search durable memories by the user message and optional topic hints
- search context snapshots by the same inputs
- merge results into a concise recall bundle
- prefer explicit and high-confidence memories
- return reasons to help the caller decide whether to incorporate the memory into the visible reply

## Migration Strategy

- keep the storage layer intact
- remove FastAPI-specific startup assumptions from scripts
- convert helper scripts to local Python wrappers over the same domain layer or MCP-compatible behavior
- update install/bootstrap docs to install MCP dependencies instead of FastAPI/uvicorn
- introduce taxonomy registry tables without immediately breaking existing string columns
- seed built-in domain values from the current canonical constants before enabling candidate promotion

## Error Handling

- database or configuration failures should surface as structured MCP tool errors
- delete defaults to archive/logical delete unless hard delete is explicitly implemented later
- proactive recall must degrade safely to empty results rather than blocking the reply path

## Traceability

- `memory-mcp-tools`: [[specs/memory-mcp-tools/spec.md#requirements]]
- `proactive-memory-recall`: [[specs/proactive-memory-recall/spec.md#requirements]]
- `memory-domain-governance`: [[specs/memory-domain-governance/spec.md#requirements]]
