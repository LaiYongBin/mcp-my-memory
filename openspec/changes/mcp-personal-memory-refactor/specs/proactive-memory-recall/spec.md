# Proactive Memory Recall Spec

## Requirements

### Requirement: Provide a recall tool for hidden answer enrichment

The MCP server MUST expose a tool that returns relevant durable memories and context snippets for the current conversational turn.

Scenarios:

- When the caller provides a new user message, the tool returns the most relevant memories.
- When the caller also provides topic hints or a draft answer, the tool uses them to improve recall relevance.
- When no relevant memory exists, the tool returns an empty but successful result.

Traceability:

- Design: [[design.md#proactive-recall-model]]
- Tests: [[test-plan.md#recall-tool-behavior]]

### Requirement: Keep proactive recall invisible to the user by default

The client integration guidance MUST instruct the assistant to use proactive recall as a hidden operation and to surface only the improved conversational answer.

Scenarios:

- When prior memory is relevant, the assistant may incorporate it without narrating the lookup.
- When prior memory is irrelevant, the assistant answers normally without forced memory mentions.

Traceability:

- Design: [[design.md#proactive-recall-model]]
- Tests: [[test-plan.md#skill-guidance]]

### Requirement: Allow implicit invocation

The client integration MUST make the recall flow available during normal conversation, not only explicit memory commands.

Scenarios:

- When the host guidance enables implicit MCP usage, personal memory recall remains eligible during ordinary chat.
- When a user discusses a topic connected to stored memory, the assistant can consult memory before responding.

Traceability:

- Design: [[design.md#mcp-server]]
- Tests: [[test-plan.md#skill-guidance]]

## Task Links

- [[tasks.md#2-proactive-memory-recall]]

## Traceability

### Forward Links

- [[../test-plan.md#recall-tool-behavior]]
- [[../test-plan.md#skill-guidance]]

### Back Links

- [[../../tasks.md#2-proactive-memory-recall]]
