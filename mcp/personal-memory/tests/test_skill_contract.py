from __future__ import annotations

import unittest
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVICE_ROOT.parents[1]


class PersonalMemoryMcpContractTests(unittest.TestCase):
    def test_repository_uses_mcp_directory_layout(self) -> None:
        self.assertTrue((PROJECT_ROOT / "mcp" / "personal-memory").is_dir())
        self.assertFalse((PROJECT_ROOT / "skills" / "personal-memory").exists())

    def test_client_guidance_mentions_proactive_recall(self) -> None:
        content = (
            PROJECT_ROOT / "docs" / "mcp-client-guidance.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Claude", content)
        self.assertIn("Codex", content)
        self.assertIn("recall_for_response", content)
        self.assertIn("capture_turn", content)
        self.assertIn("search_recent_dialogue_summaries", content)
        self.assertIn("search_entities", content)
        self.assertIn("search_entity_relationships", content)
        self.assertIn("maintain_entity_graph", content)
        self.assertIn("orchestrate_turn_memory", content)
        self.assertIn("maintain_memory_store", content)
        self.assertIn("related_subject", content)
        self.assertIn("隐形", content)
        self.assertIn("主动", content)
        self.assertIn('ROOT="$HOME/Desktop/skill-my-memory-plugin/mcp/personal-memory"', content)

    def test_readme_documents_mcp_mount_instead_of_skill_install(self) -> None:
        content = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("codex mcp add personalMemory", content)
        self.assertIn("claude mcp add-json", content)
        self.assertIn("capture_turn", content)
        self.assertIn("search_recent_dialogue_summaries", content)
        self.assertIn("search_entities", content)
        self.assertIn("search_entity_relationships", content)
        self.assertIn("maintain_entity_graph", content)
        self.assertIn("orchestrate_turn_memory", content)
        self.assertIn("maintain_memory_store", content)
        self.assertIn("related_subject", content)
        self.assertIn('cd "$HOME/Desktop/skill-my-memory-plugin/mcp/personal-memory"', content)
        self.assertNotIn("~/.codex/skills/personal-memory", content)
        self.assertNotIn("~/.claude/skills/personal-memory", content)

    def test_install_script_targets_mcp_directory(self) -> None:
        content = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('SERVICE_DIR="${ROOT_DIR}/mcp/personal-memory"', content)
        self.assertNotIn('SERVICE_DIR="${ROOT_DIR}/skills/personal-memory"', content)

    def test_bootstrap_verifies_refactored_schema_tables(self) -> None:
        content = (
            PROJECT_ROOT / "mcp" / "personal-memory" / "scripts" / "bootstrap.py"
        ).read_text(encoding="utf-8")
        self.assertIn("memory_record", content)
        self.assertIn("memory_vector_chunk", content)
        self.assertIn("session_state", content)
        self.assertIn("memory_candidate", content)
        self.assertIn("conversation_turn", content)
        self.assertIn("memory_inference", content)
        self.assertIn("memory_signal", content)
        self.assertIn("conversation_summary", content)
        self.assertNotIn("'memory_item'", content)
        self.assertNotIn("'working_memory'", content)
        self.assertNotIn("'memory_review_candidate'", content)
        self.assertNotIn("'conversation_event'", content)
        self.assertNotIn("'memory_analysis_result'", content)
        self.assertNotIn("'memory_evidence'", content)
        self.assertNotIn("'conversation_context_snapshot'", content)

    def test_sql_manifest_includes_schema_v2_migration(self) -> None:
        content = (
            PROJECT_ROOT / "mcp" / "personal-memory" / "scripts" / "bootstrap.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"010_schema_v2.sql"', content)
        self.assertIn('"011_cleanup_legacy.sql"', content)
        self.assertIn('"012_constraints_v2.sql"', content)
        self.assertIn('"013_indexes_v2.sql"', content)
        self.assertIn('"014_domain_registry.sql"', content)
        self.assertIn('"015_memory_governance_v4.sql"', content)
        self.assertIn('"016_entity_graph.sql"', content)
        self.assertIn('"017_related_subjects.sql"', content)
        self.assertNotIn('"001_schema.sql"', content)
        self.assertNotIn('"002_indexes.sql"', content)
        self.assertNotIn('"004_review_candidates.sql"', content)
        self.assertNotIn('"005_capture_cycle.sql"', content)
        self.assertNotIn('"006_memory_analysis.sql"', content)
        self.assertNotIn('"007_slot_memory.sql"', content)
        self.assertNotIn('"008_evidence_accumulation.sql"', content)
        self.assertNotIn('"009_context_snapshots.sql"', content)

    def test_cleanup_migration_drops_legacy_tables(self) -> None:
        content = (
            PROJECT_ROOT / "mcp" / "personal-memory" / "sql" / "011_cleanup_legacy.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("DROP TABLE IF EXISTS memory_embedding", content)
        self.assertIn("DROP TABLE IF EXISTS memory_review_candidate", content)
        self.assertIn("DROP TABLE IF EXISTS working_memory", content)
        self.assertIn("DROP TABLE IF EXISTS conversation_event", content)
        self.assertIn("DROP TABLE IF EXISTS memory_analysis_result", content)
        self.assertIn("DROP TABLE IF EXISTS memory_evidence", content)
        self.assertIn("DROP TABLE IF EXISTS conversation_context_snapshot", content)
        self.assertIn("DROP TABLE IF EXISTS memory_item", content)

    def test_constraints_migration_adds_schema_guards(self) -> None:
        content = (
            PROJECT_ROOT / "mcp" / "personal-memory" / "sql" / "012_constraints_v2.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("memory_record", content)
        self.assertIn("session_state", content)
        self.assertIn("memory_candidate", content)
        self.assertIn("conversation_turn", content)
        self.assertIn("memory_inference", content)
        self.assertIn("conversation_summary", content)
        self.assertIn("CHECK", content)
        self.assertIn("snapshot_level", content)
        self.assertIn("action", content)
        self.assertIn("status", content)

    def test_index_migration_targets_hot_query_paths(self) -> None:
        content = (
            PROJECT_ROOT / "mcp" / "personal-memory" / "sql" / "013_indexes_v2.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("memory_record", content)
        self.assertIn("conversation_summary", content)
        self.assertIn("session_state", content)
        self.assertIn("memory_signal", content)
        self.assertIn("created_at DESC", content)
        self.assertIn("updated_at DESC", content)
        self.assertIn("coalesce(ended_at, updated_at, created_at)", content)

    def test_domain_registry_migration_defines_registry_tables(self) -> None:
        content = (
            PROJECT_ROOT / "mcp" / "personal-memory" / "sql" / "014_domain_registry.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS domain_registry", content)
        self.assertIn("CREATE TABLE IF NOT EXISTS domain_value", content)
        self.assertIn("CREATE TABLE IF NOT EXISTS domain_value_alias", content)
        self.assertIn("CREATE TABLE IF NOT EXISTS domain_value_candidate", content)
        self.assertIn("memory_type", content)
        self.assertIn("source_type", content)

    def test_memory_governance_migration_adds_lifecycle_and_disclosure_fields(self) -> None:
        content = (
            PROJECT_ROOT / "mcp" / "personal-memory" / "sql" / "015_memory_governance_v4.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE memory_record", content)
        self.assertIn("lifecycle_state", content)
        self.assertIn("sensitivity_level", content)
        self.assertIn("disclosure_policy", content)
        self.assertIn("category", content)
        self.assertIn("attribute_key", content)

    def test_entity_graph_migration_adds_entity_tables(self) -> None:
        content = (
            PROJECT_ROOT / "mcp" / "personal-memory" / "sql" / "016_entity_graph.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS entity_profile", content)
        self.assertIn("CREATE TABLE IF NOT EXISTS entity_edge", content)
        self.assertIn("INSERT INTO entity_profile", content)
        self.assertIn("INSERT INTO entity_edge", content)

    def test_related_subjects_migration_adds_second_entity_slot(self) -> None:
        content = (
            PROJECT_ROOT / "mcp" / "personal-memory" / "sql" / "017_related_subjects.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("ALTER TABLE memory_record", content)
        self.assertIn("related_subject_key", content)
        self.assertIn("ALTER TABLE memory_inference", content)
        self.assertIn("related_subject", content)


if __name__ == "__main__":
    unittest.main()
