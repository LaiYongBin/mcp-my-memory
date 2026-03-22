# Memory MCP Tools Spec

## Requirements

### Requirement: Expose memory and context operations as MCP tools

The skill MUST provide a local MCP server exposing memory and context operations instead of requiring the FastAPI API as the primary interface.

Scenarios:

- When the local MCP server starts, the client can discover memory and context tools.
- When a caller wants to add a memory, the caller uses an MCP tool instead of an HTTP endpoint.
- When a caller wants to query context snapshots, the caller uses an MCP tool instead of an HTTP endpoint.

Traceability:

- Design: [[design.md#architecture]]
- Tests: [[test-plan.md#tool-registration-and-execution]]

### Requirement: Support filter-based memory queries

The MCP interface MUST support querying memories by text and structured filters.

Scenarios:

- When a caller passes `memory_type`, only that type is returned.
- When a caller passes `tags`, only matching memories are returned.
- When a caller passes confidence, importance, or explicitness filters, non-matching rows are excluded.

Traceability:

- Design: [[design.md#data-and-query-design]]
- Tests: [[test-plan.md#memory-filtering]]

### Requirement: Support range-based memory queries

The MCP interface MUST support querying memories over a selected time field and bounded range.

Scenarios:

- When a caller requests a created-at range, only rows in that window are returned.
- When a caller requests an updated-at range with extra filters, both the range and filters apply.
- When no start or end bound is provided, the remaining bound still applies.

Traceability:

- Design: [[design.md#range-query]]
- Tests: [[test-plan.md#range-query-behavior]]

### Requirement: Preserve safe delete semantics

The MCP interface MUST support archive or logical delete and MUST not physically delete by default.

Scenarios:

- When a caller requests archive, the memory remains stored but is no longer active.
- When a caller requests delete, the row is logically deleted.

Traceability:

- Design: [[design.md#error-handling]]
- Tests: [[test-plan.md#delete-semantics]]

## Task Links

- [[tasks.md#1-memory-mcp-server]]

## Traceability

### Forward Links

- [[../test-plan.md#tool-registration-and-execution]]
- [[../test-plan.md#memory-filtering]]
- [[../test-plan.md#range-query-behavior]]
- [[../test-plan.md#delete-semantics]]

### Back Links

- [[../../tasks.md#1-memory-mcp-server]]

