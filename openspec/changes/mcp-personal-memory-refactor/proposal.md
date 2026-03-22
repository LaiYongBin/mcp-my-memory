# Proposal: Refactor Personal Memory Skill Into a Local MCP Server

## Why

The current `personal-memory` skill exposes a local FastAPI service plus Python scripts. That works for explicit memory tasks, but it keeps memory access as a mostly manual, trigger-driven workflow. The user requirement is broader:

- memory operations should be exposed as MCP tools instead of ad-hoc HTTP endpoints
- the local Python process should run as an MCP server
- the assistant should be able to pull related memory proactively during ordinary conversation, not only when the user explicitly asks for memory lookup

## Scope

This change replaces the current service-facing contract with an MCP-first contract while preserving the PostgreSQL-backed data model and core memory logic. It also updates the client guidance so proactive recall becomes a default hidden behavior when it can improve the answer.

The change also defines a next-step schema evolution path for governable memory taxonomies so expandable fields such as `memory_type` and `source_type` can move from hard-coded literals toward registry-backed values without weakening execution semantics such as `action` or `snapshot_level`.

## Capabilities

- `memory-mcp-tools`
- `proactive-memory-recall`
- `memory-domain-governance`

## Non-Goals

- redesigning the PostgreSQL schema from scratch
- building a standalone GUI for memory management
- making the MCP server autonomously initiate conversations without a client request
- allowing the model to invent new execution semantics such as arbitrary `action` values without corresponding code behavior

## Expected Impact

- one local MCP server process becomes the primary integration point
- existing memory CRUD and context operations remain available through MCP tools
- normal conversational replies can be enriched with relevant prior memory when the model judges it useful
- business taxonomies can evolve through governed registry workflows instead of requiring every new classification to start as an application literal
