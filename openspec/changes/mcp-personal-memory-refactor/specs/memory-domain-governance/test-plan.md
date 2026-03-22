# Memory Domain Governance Test Plan

## Execution Enum Guardrails

- Verify unknown `action` values are rejected before persistence.
- Verify unknown `snapshot_level` values are rejected before persistence.
- Verify existing fixed execution enums still round-trip correctly after registry tables are introduced.

Traceability:

- Requirement: [[spec.md#requirement-separate-fixed-execution-enums-from-expandable-taxonomies]]

## Registry Resolution

- Verify built-in `memory_type` and `source_type` values seed into the registry.
- Verify alias resolution maps a non-canonical value to the canonical `value_key`.
- Verify registry-backed writes persist normalized canonical values.

Traceability:

- Requirement: [[spec.md#requirement-provide-registry-backed-canonical-values-for-expandable-domains]]

## Candidate Governance

- Verify unknown taxonomy values in `manual_review` mode create candidate rows.
- Verify `auto_approve` mode can promote a candidate into a canonical registry value with provenance.
- Verify `fixed` mode refuses unknown values rather than auto-registering them.

Traceability:

- Requirement: [[spec.md#requirement-capture-unknown-taxonomy-values-as-governed-candidates]]

## Migration Compatibility

- Verify introducing registry tables does not break reads from existing v2 rows.
- Verify legacy string values can be normalized during new writes without rewriting all historic rows first.
- Verify migration seeding is idempotent.

Traceability:

- Requirement: [[spec.md#requirement-support-incremental-migration-from-v2-string-columns]]
