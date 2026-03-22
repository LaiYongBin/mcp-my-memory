# Proactive Memory Recall Test Plan

## Recall Tool Behavior

- verify `recall_for_response` queries memory and context layers with the current message
- verify the tool merges results into a structured recall bundle
- verify empty storage returns an empty recall bundle rather than an exception

Links:

- Requirements: [[spec.md#requirement-provide-a-recall-tool-for-hidden-answer-enrichment]]

## Client Guidance

- verify `docs/mcp-client-guidance.md` describes proactive recall during ordinary conversation
- verify the guidance documents Claude/Codex MCP mounting instead of skill installation
- verify the guidance does not require visible narration of memory lookups

Links:

- Requirements: [[spec.md#requirement-keep-proactive-recall-invisible-to-the-user-by-default]]
- Requirements: [[spec.md#requirement-allow-implicit-invocation]]

## Task Links

- [[../../tasks.md#2-proactive-memory-recall]]
