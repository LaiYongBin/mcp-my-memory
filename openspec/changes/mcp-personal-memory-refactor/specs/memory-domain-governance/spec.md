# Memory Domain Governance Spec

## Requirements

### Requirement: Separate fixed execution enums from expandable taxonomies

The memory system MUST distinguish between fields whose values control runtime behavior and fields whose values only classify data.

Scenarios:

- When a field such as `action` or `snapshot_level` is processed, only built-in values are accepted.
- When a field such as `memory_type` or `source_type` is processed, the value may be resolved through a domain registry.
- When a caller attempts to introduce a new execution enum, the system rejects it instead of silently storing an unknown behavior token.

Traceability:

- Design: [[design.md#domain-governance-v3-direction]]
- Tests: [[test-plan.md#execution-enum-guardrails]]

### Requirement: Provide registry-backed canonical values for expandable domains

The system MUST support canonical registry entries and alias resolution for expandable taxonomy fields.

Scenarios:

- When a value already exists in the registry, writes resolve to that canonical value.
- When a legacy spelling or synonym is used, the system maps it through an alias to the canonical value.
- When built-in values are seeded, the registry contains at least the current canonical `memory_type` and `source_type` values.

Traceability:

- Design: [[design.md#domain-registry-model]]
- Tests: [[test-plan.md#registry-resolution]]

### Requirement: Capture unknown taxonomy values as governed candidates

The system MUST not silently accept unknown taxonomy values without governance.

Scenarios:

- When an analyzer proposes a new `memory_type` and the domain is `manual_review`, the system creates a candidate instead of mutating production taxonomy immediately.
- When a domain is `auto_approve`, the system can promote a normalized candidate into a canonical registry value with provenance.
- When a domain is `fixed`, unknown values are rejected or mapped to a configured fallback.

Traceability:

- Design: [[design.md#registry-resolution-flow]]
- Tests: [[test-plan.md#candidate-governance]]

### Requirement: Support incremental migration from v2 string columns

The registry rollout MUST preserve compatibility with the existing v2 schema while taxonomy governance is introduced.

Scenarios:

- When registry tables are introduced, existing `VARCHAR` columns continue to work during migration.
- When built-in values are seeded, current rows remain readable without destructive rewrites.
- When registry resolution is enabled, new writes normalize values before persistence.

Traceability:

- Design: [[design.md#migration-strategy-for-registry-adoption]]
- Tests: [[test-plan.md#migration-compatibility]]

## Task Links

- [[../../tasks.md#3-memory-domain-governance]]

## Traceability

### Forward Links

- [[test-plan.md#execution-enum-guardrails]]
- [[test-plan.md#registry-resolution]]
- [[test-plan.md#candidate-governance]]
- [[test-plan.md#migration-compatibility]]

### Back Links

- [[../../tasks.md#3-memory-domain-governance]]
