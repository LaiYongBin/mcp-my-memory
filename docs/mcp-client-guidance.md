# Personal Memory MCP Client Guidance

这个项目现在只提供本地 MCP 服务，不再作为 Claude/Codex 的 skill 安装。

## Codex

```bash
ROOT="$HOME/Desktop/skill-my-memory-plugin/mcp/personal-memory"

codex mcp add personalMemory \
  --env PYTHONPATH="$ROOT" \
  -- "$ROOT/.venv/bin/python" -m service.mcp_server --transport stdio
```

## Claude

```bash
ROOT="$HOME/Desktop/skill-my-memory-plugin/mcp/personal-memory"

claude mcp add-json -s user personalMemory \
  "{\"command\":\"$ROOT/.venv/bin/python\",\"args\":[\"-m\",\"service.mcp_server\",\"--transport\",\"stdio\"],\"env\":{\"PYTHONPATH\":\"$ROOT\"}}"
```

## Recommended Host Guidance

建议把下面这类规则写入宿主的全局提示文件，例如 `~/.claude/CLAUDE.md` 和 `~/.codex/AGENTS.md`：

- 当用户明确要求记住、删除、查询、更新记忆时，直接调用 `personalMemory` MCP 工具。
- 普通聊天时，优先调用 `orchestrate_turn_memory`，统一拿到本轮 `recall`、`capture_plan`、`recommended_sequence`，减少宿主自己拼接时机判断。
- 普通聊天时，遇到值得保留的单轮对话或连续几轮对话，可隐式调用 `capture_turn`，把当前 user/assistant 内容写入事件流，同时做记忆分析与上下文快照同步。
- 如果宿主已经自己维护了 turn buffer，也可以调用 `add_context(..., extract_memory=true)` 批量同步上下文并从摘要里提取记忆。
- 当用户要看某段时间里的长期记忆、最近更新过的记忆时，调用 `search_memory_window`。
- 当你想知道当前话题涉及到哪些人、关系对象或项目时，调用 `search_entities`，或者直接使用 `recall_for_response` 返回的 `related_entities`。
- 当你需要显式查看用户与某个实体之间的关系边，例如“这是朋友、家人还是项目对象”，调用 `search_entity_relationships`。
- 当你更新了实体命名规则、回填了旧记忆，或怀疑 entity profile / edge 漂移时，调用 `maintain_entity_graph` 触发一次图层重建。
- 普通聊天中，如果旧记忆能明显提升答案的相关性、连续性或个性化程度，可以主动、隐式调用 `recall_for_response`。
- `recall_for_response` 返回 `should_recall`、`decision_reasons` 和 `suggested_integration_style` 时，应优先按这三个字段决定是否把旧记忆带入可见回答。
- `recall_for_response` 还会返回 `direct_memories`、`contextual_memories`、`expansive_memories`、`suppressed_memories`。优先只使用 `direct_memories` 和 `contextual_memories`。
- `recall_for_response` 还会返回 `related_entities`。这层信息适合做“这一轮涉及到谁/什么关系对象”的内部线索，不等于必须把该实体显式说出来。
- 如果关系型记忆里提供了第二实体槽位，例如 `subject=user` 且 `related_subject=friend_xiaowang`，或者 `subject=friend_xiaowang` 且 `related_subject=project_memory_mcp`，entity graph 会生成更明确的 `entity -> entity` 边。
- 如果 `suppressed_memories` 或 `disclosure_warnings` 显示某条记忆属于 `internal_only` 或 `user_confirm`，默认仅作内部参考，不直接对用户说出。
- `recall_for_response` 还会返回 `recent_contexts` 和 `suggested_followup_hooks`。当主回答已经完成，但你希望自然展示“我记得最近聊过什么”时，可以从这里挑 1 条轻量带入。
- 当用户想回顾最近聊过的主题、最近提过的事情，或你需要主动寻找最近可延展的话题时，调用 `search_recent_dialogue_summaries`。
- 如果 taxonomy 出现了新值，先用 `search_domain_candidates` 查看。默认优先用 `approve_domain_candidate(candidate_id, canonical_value_key=...)` 直接并入已有 canonical；只有确实需要单独维护 alias 时，再调用 `merge_domain_alias`。不要让宿主直接硬编码新增分类。
- 定期调用 `maintain_memory_store`，给长期记忆重算 `lifecycle_state`、`sensitivity_level`、`disclosure_policy`，避免冷记忆和敏感记忆长期维持错误状态。
- 记忆查询、记忆写入和上下文同步默认是隐形操作，不要向用户汇报工具调用过程。
- 若没有召回到真正有帮助的记忆，就正常回答，不要为了展示记忆而硬提旧事。

## Expected User Experience

- 用户问“我最喜欢的饮料是什么”，应该直接回答结论，而不是先解释内部检索流程。
- 用户讨论新知识点时，如果召回到确实相关的朋友、偏好或历史话题，可以自然地融入回答。
- 如果召回的是第三人健康、关系或其他敏感信息，系统应优先保守处理，只在确有必要且合适时轻量提示，或完全不显式说出。
- 用户刚聊过新的计划、项目或生活近况时，后续对话里可以偶尔顺带提到最近摘要，让用户感知到“你确实记得最近聊过什么”。
- 用户只是日常聊天时，不应暴露“skill 触发”或“我现在去查记忆”这类中间过程。
