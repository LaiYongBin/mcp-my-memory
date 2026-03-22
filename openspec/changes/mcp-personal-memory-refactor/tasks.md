## 1. Memory MCP Server

Depends on: none

Traceability:
- Requirements: [[specs/memory-mcp-tools/spec.md#requirement-expose-memory-and-context-operations-as-mcp-tools]]
- Requirements: [[specs/memory-mcp-tools/spec.md#requirement-support-filter-based-memory-queries]]
- Requirements: [[specs/memory-mcp-tools/spec.md#requirement-support-range-based-memory-queries]]
- Tests: [[specs/memory-mcp-tools/test-plan.md#tool-registration-and-execution]]
- Tests: [[specs/memory-mcp-tools/test-plan.md#memory-filtering]]
- Tests: [[specs/memory-mcp-tools/test-plan.md#range-query-behavior]]

- [ ] 1.1 RED: add failing tests for MCP tool registration and delegation [[specs/memory-mcp-tools/spec.md#requirement-expose-memory-and-context-operations-as-mcp-tools]] [[specs/memory-mcp-tools/test-plan.md#tool-registration-and-execution]]
- [ ] 1.2 RED: run targeted tests and confirm failure
- [ ] 1.3 RED: add failing tests for filter and range query behavior [[specs/memory-mcp-tools/spec.md#requirement-support-filter-based-memory-queries]] [[specs/memory-mcp-tools/spec.md#requirement-support-range-based-memory-queries]] [[specs/memory-mcp-tools/test-plan.md#memory-filtering]] [[specs/memory-mcp-tools/test-plan.md#range-query-behavior]]
- [ ] 1.4 RED: run targeted tests and confirm failure
- [ ] 1.5 GREEN: implement MCP server entrypoint and tool handlers
- [ ] 1.6 GREEN: extend storage queries for structured filtering and time windows
- [ ] 1.7 GREEN: run targeted tests and confirm pass
- [ ] 1.8 REFACTOR: simplify shared schemas and script helpers while keeping tests green

## 2. Proactive Memory Recall

Depends on: 1

Traceability:
- Requirements: [[specs/proactive-memory-recall/spec.md#requirement-provide-a-recall-tool-for-hidden-answer-enrichment]]
- Requirements: [[specs/proactive-memory-recall/spec.md#requirement-keep-proactive-recall-invisible-to-the-user-by-default]]
- Requirements: [[specs/proactive-memory-recall/spec.md#requirement-allow-implicit-invocation]]
- Tests: [[specs/proactive-memory-recall/test-plan.md#recall-tool-behavior]]
- Tests: [[specs/proactive-memory-recall/test-plan.md#client-guidance]]

- [ ] 2.1 RED: add failing tests for recall bundle construction [[specs/proactive-memory-recall/spec.md#requirement-provide-a-recall-tool-for-hidden-answer-enrichment]] [[specs/proactive-memory-recall/test-plan.md#recall-tool-behavior]]
- [ ] 2.2 RED: run targeted tests and confirm failure
- [ ] 2.3 GREEN: implement recall tool and ranking/merge behavior
- [ ] 2.4 GREEN: update client guidance and mounting docs for implicit proactive recall [[specs/proactive-memory-recall/spec.md#requirement-keep-proactive-recall-invisible-to-the-user-by-default]] [[specs/proactive-memory-recall/spec.md#requirement-allow-implicit-invocation]] [[specs/proactive-memory-recall/test-plan.md#client-guidance]]
- [ ] 2.5 GREEN: run targeted tests and confirm pass
- [ ] 2.6 REFACTOR: trim obsolete HTTP-first documentation and startup paths

## 3. Memory Domain Governance

Depends on: 1, 2

Traceability:
- Requirements: [[specs/memory-domain-governance/spec.md#requirement-separate-fixed-execution-enums-from-expandable-taxonomies]]
- Requirements: [[specs/memory-domain-governance/spec.md#requirement-provide-registry-backed-canonical-values-for-expandable-domains]]
- Requirements: [[specs/memory-domain-governance/spec.md#requirement-capture-unknown-taxonomy-values-as-governed-candidates]]
- Requirements: [[specs/memory-domain-governance/spec.md#requirement-support-incremental-migration-from-v2-string-columns]]
- Tests: [[specs/memory-domain-governance/test-plan.md#execution-enum-guardrails]]
- Tests: [[specs/memory-domain-governance/test-plan.md#registry-resolution]]
- Tests: [[specs/memory-domain-governance/test-plan.md#candidate-governance]]
- Tests: [[specs/memory-domain-governance/test-plan.md#migration-compatibility]]

- [ ] 3.1 RED: add failing tests for fixed enum rejection and taxonomy registry lookup [[specs/memory-domain-governance/spec.md#requirement-separate-fixed-execution-enums-from-expandable-taxonomies]] [[specs/memory-domain-governance/spec.md#requirement-provide-registry-backed-canonical-values-for-expandable-domains]]
- [ ] 3.2 RED: run targeted tests and confirm failure
- [ ] 3.3 GREEN: add registry tables and seed built-in `memory_type` and `source_type` values [[specs/memory-domain-governance/spec.md#requirement-support-incremental-migration-from-v2-string-columns]]
- [ ] 3.4 GREEN: implement alias resolution and candidate persistence helpers [[specs/memory-domain-governance/spec.md#requirement-provide-registry-backed-canonical-values-for-expandable-domains]] [[specs/memory-domain-governance/spec.md#requirement-capture-unknown-taxonomy-values-as-governed-candidates]]
- [ ] 3.5 GREEN: expose MCP/domain-management operations for listing and reviewing domain candidates
- [ ] 3.6 GREEN: run targeted tests and confirm pass
- [ ] 3.7 REFACTOR: remove scattered taxonomy literals from application write paths while preserving fixed execution enums
