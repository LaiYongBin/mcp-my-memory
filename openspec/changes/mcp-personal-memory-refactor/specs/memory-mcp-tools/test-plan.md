# Memory MCP Tools Test Plan

## Tool Registration And Execution

- verify the MCP server registers the expected memory/context tools
- verify calling `add_memory` delegates to the storage layer and returns the created row
- verify calling `add_context` delegates to context sync and returns the snapshot payload

Links:

- Requirements: [[spec.md#requirement-expose-memory-and-context-operations-as-mcp-tools]]

## Memory Filtering

- verify `search_memories` forwards structured filters correctly
- verify explicitness, confidence, and importance bounds are honored in SQL filtering

Links:

- Requirements: [[spec.md#requirement-support-filter-based-memory-queries]]

## Range Query Behavior

- verify the range query selects the requested time field
- verify open-ended start/end bounds work
- verify invalid time field values are rejected

Links:

- Requirements: [[spec.md#requirement-support-range-based-memory-queries]]

## Delete Semantics

- verify archive returns archived status
- verify delete performs logical deletion
- verify missing ids produce a not-found style error

Links:

- Requirements: [[spec.md#requirement-preserve-safe-delete-semantics]]

## Task Links

- [[../../tasks.md#1-memory-mcp-server]]

