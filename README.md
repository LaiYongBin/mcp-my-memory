# skill-my-memory

个人长期记忆 MCP 服务，支持：

- PostgreSQL 持久化
- pgvector 向量检索
- MCP 工具化的记忆查询、范围查询、写入、删除、上下文同步
- MCP 工具化的单轮捕获 `capture_turn`、近期摘要查询 `search_recent_dialogue_summaries`
- 轻量实体/关系摘要查询：`search_entities`
- 持久化关系图查询：`search_entity_relationships`
- 实体图重建维护：`maintain_entity_graph`
- taxonomy registry 与 domain candidate 治理工具：`list_domain_values`、`search_domain_candidates`、`approve_domain_candidate`、`reject_domain_candidate`、`merge_domain_alias`
- 宿主编排与维护工具：`orchestrate_turn_memory`、`maintain_memory_store`
- 记忆生命周期：`fresh/stable/cold/stale/conflicted`
- 敏感度与披露策略：`public/normal/sensitive/restricted` 与 `normal/gentle/user_confirm/internal_only`
- 显式长期记忆
- 自动候选提取
- 多轮证据累积后再升级推断型记忆
- review 候选审批/拒绝
- 回答前主动召回相关记忆与上下文

默认交互原则：

- 优先走本地 MCP 服务
- 记忆读写默认是隐形操作，不向用户汇报内部查询或写入过程
- 正常聊天时允许隐式调用记忆召回，而不是只在用户点名时才查
- 会话上下文摘要与长期记忆分开存储
- 同一主题可跨多个 session 聚合成全局主题摘要

## Schema V2

当前运行时已经切到重构后的表结构：

- `memory_record`：长期记忆主表
- `memory_vector_chunk`：向量分块与 embedding
- `session_state`：短期工作记忆
- `memory_candidate`：待确认候选
- `conversation_turn`：原始对话事件
- `memory_inference`：AI 分析结果
- `memory_signal`：证据累积
- `conversation_summary`：segment/topic/global_topic 摘要

legacy 表已经由 cleanup 迁移删除，MCP 服务运行时只依赖 v2 表。
当前 `bootstrap.py` 也只执行 v2 安装链：`010_schema_v2.sql` 和 `011_cleanup_legacy.sql`。
现在还会继续执行 `012_constraints_v2.sql`，为 `status`、`action`、`snapshot_level`、`role`、`event_type` 等关键字段补数据库级 CHECK 约束。
同时会执行 `013_indexes_v2.sql`，为最近摘要、时间窗记忆查询、主动召回排序、短期状态读取补 v2 专用索引。
现在也会执行 `014_domain_registry.sql`，为 `memory_type`、`source_type` 提供 registry、alias 和 candidate 治理表；其中 `action`、`snapshot_level` 这类执行语义仍保持固定枚举，不开放自动新增。
现在还会执行 `015_memory_governance_v4.sql`，补充 `category`、`attribute_key` registry seed，以及 `lifecycle_state`、`sensitivity_level`、`disclosure_policy`、`recall_count` 等治理字段。
现在还会执行 `016_entity_graph.sql`，把 `subject_key` 派生并固化为 `entity_profile` 与 `entity_edge`，让“涉及到谁、与用户是什么关系”可被稳定查询。
现在还会执行 `017_related_subjects.sql`，为关系型记忆补 `related_subject_key / related_subject` 第二实体槽位，支持真正的 `entity -> entity` 关系边。

## 安装

### 1. 克隆仓库

```bash
git clone git@github.com:LaiYongBin/mcp-my-memory.git
cd mcp-my-memory
```

### 2. 配置环境变量

```bash
cp .env.memory.example .env.memory
# 编辑 .env.memory，填入你的 PostgreSQL 连接信息和 embedding API key
source .env.memory
```

也可以将变量直接写入 `~/.zshrc` 或 `~/.bashrc` 永久生效。

### 3. 一键初始化

```bash
./install.sh
```

这一步会自动完成：

- 创建 `mcp/personal-memory/.venv`
- 安装 Python 依赖
- 连接 PostgreSQL 执行建表和索引 SQL
- 检查 `pgvector`
- 启动本地 MCP memory 服务并做一次监听检查
- 后续可以按需把当前会话同步成小摘要和大主题摘要，再在显式 memory 工作时提取长期记忆

也可以直接在服务目录执行：

```bash
cd "$HOME/Desktop/skill-my-memory-plugin/mcp/personal-memory"

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 scripts/bootstrap.py
```

## 挂载到 Codex

```bash
ROOT="$(pwd)/mcp/personal-memory"

codex mcp add personalMemory \
  --env PYTHONPATH="$ROOT" \
  -- "$ROOT/.venv/bin/python" -m service.mcp_server --transport stdio
```

`bootstrap.py` 也支持附加参数：

```bash
python3 scripts/bootstrap.py --backfill-embeddings
python3 scripts/bootstrap.py --skip-service
python3 scripts/bootstrap.py --skip-db
python3 scripts/bootstrap.py --print-env-template
```

## 挂载到 Claude

```bash
ROOT="$(pwd)/mcp/personal-memory"

claude mcp add-json -s user personalMemory \
  "{\"command\":\"$ROOT/.venv/bin/python\",\"args\":[\"-m\",\"service.mcp_server\",\"--transport\",\"stdio\"],\"env\":{\"PYTHONPATH\":\"$ROOT\"}}"
```

## 推荐的全局行为提示

MCP 只负责提供工具。要让 Claude/Codex 在普通聊天中也会主动结合旧记忆，需要给宿主补一段全局提示，建议分别写进：

- `~/.claude/CLAUDE.md`
- `~/.codex/AGENTS.md`

原则应当是：

- 用户显式说“记住 / 忘掉 / 查一下”时，直接调用相应 MCP 工具
- 普通聊天里，优先让宿主通过 `orchestrate_turn_memory` 统一拿到本轮 recall 结果、capture 计划和建议调用顺序
- 普通聊天时，优先用 `capture_turn` 隐式记录单轮对话；如果宿主自己维护了上下文批次，则用 `add_context(..., extract_memory=true)`
- 普通聊天里，如果旧记忆能明显提升回答质量，可以隐式调用 `recall_for_response`
- taxonomy 漂移时，先用 `search_domain_candidates` 查看；如果只是要把候选并入已有 canonical，优先直接用 `approve_domain_candidate(candidate_id, canonical_value_key=...)`，只有需要显式维护 alias 时再用 `merge_domain_alias`
- `recall_for_response` 现在会按 `direct/contextual/expansive/suppressed` 分层返回记忆，优先只使用 direct/contextual
- `recall_for_response` 现在还会返回 `related_entities`，让宿主知道本轮相关的人/对象/项目是谁，再决定是否自然带入
- 如果需要明确查看“用户和谁有什么关系边”，可直接调用 `search_entity_relationships`
- 如果你更新了实体显示名规则、补录了旧记忆，或想把历史 `subject_key` 重新固化进图层，调用 `maintain_entity_graph`
- 如果后续 analyzer 或手工写入提供了 `related_subject_key`，entity graph 会额外生成 `subject -> related_subject` 的关系边，而不再只有 `user -> entity`
- 如果 `suppressed_memories` 或 `disclosure_warnings` 提示 `internal_only` / `user_confirm`，默认只内部参考，不直接说给用户
- `recall_for_response` 返回 `recent_contexts` 与 `suggested_followup_hooks` 时，可以在合适场景轻量带入最近话题，增强连续性
- 用 `maintain_memory_store` 定期给老记忆做 lifecycle / sensitivity / disclosure 的重算，避免库里长期漂移
- 记忆查询和写入默认对用户隐藏，不要在回答里汇报“我查了记忆”
- 只有记忆确实相关时才自然融入回答，不要硬提

更完整的双端挂载与提示模板见 [docs/mcp-client-guidance.md](docs/mcp-client-guidance.md)。

## 最小可运行配置

至少要有这些变量：

```bash
export LYB_SKILL_PG_ADDRESS=
export LYB_SKILL_PG_USERNAME=
export LYB_SKILL_PG_PASSWORD=
export LYB_SKILL_PG_MY_PERSONAL_DATABASE=
```

建议同时设置：

```bash
export LYB_SKILL_PG_PORT=5432
export LYB_SKILL_MEMORY_USER=LYB
export LYB_SKILL_MEMORY_SERVICE_HOST=127.0.0.1
export LYB_SKILL_MEMORY_SERVICE_PORT=8787
export LYB_SKILL_MEMORY_MCP_PATH=/mcp
export LYB_SKILL_MEMORY_EMBED_API_KEY=
export LYB_SKILL_MEMORY_EMBED_BASE_URL=https://dashscope.aliyuncs.com/api/v1
export LYB_SKILL_MEMORY_EMBED_MODEL=text-embedding-v4
export LYB_SKILL_MEMORY_EMBED_DIM=1536
export LYB_SKILL_MEMORY_ANALYZE_TIMEOUT=90
export LYB_SKILL_MEMORY_CONTEXT_SYNC_TIMEOUT=180
```

如果只想先跑数据库记忆，不启用语义检索，可以暂时不配 `LYB_SKILL_MEMORY_EMBED_API_KEY`。

## 常用命令

```bash
cd mcp/personal-memory
. .venv/bin/activate

python3 scripts/ensure_service.py
python3 -m service.mcp_server --transport streamable-http --host 127.0.0.1 --port 8787 --path /mcp
python3 scripts/bootstrap.py
python3 scripts/context_sync.py --session-key life-talk-2026-03-19 --topic-hint "人生观讨论" --turn "user:我现在越来越认同戈尔泰的人生观。" --turn "assistant:你更认同的是哪一部分？" --extract-memory
python3 scripts/context_search.py --query "戈尔泰 人生观" --snapshot-level topic --limit 5
python3 scripts/context_search.py --query "戈尔泰 人生观" --snapshot-level global_topic --limit 5
python3 scripts/memory_capture_cycle.py --user-text "记住我最近开始每天骑车通勤" --assistant-text "我记下来了"
python3 scripts/memory_analysis_results.py --session-key default
python3 scripts/memory_evidence.py --limit 20
python3 scripts/memory_capture.py --text "我喜欢黑咖啡"
python3 scripts/memory_capture.py --text "记住我对象喜欢花" --auto-persist
python3 scripts/review_candidates.py --limit 20
python3 scripts/review_action.py --id 1 --action approve
python3 scripts/memory_query.py --query "黑咖啡"
python3 scripts/memory_query.py --memory-type preference --updated-after "2026-03-01T00:00:00"
python3 scripts/memory_maintenance.py --dry-run --limit 50
python3 scripts/memory_maintenance.py --include-archived
```

## 所需环境变量

```bash
export LYB_SKILL_PG_ADDRESS=
export LYB_SKILL_PG_PORT=5432
export LYB_SKILL_PG_USERNAME=
export LYB_SKILL_PG_PASSWORD=
export LYB_SKILL_PG_MY_PERSONAL_DATABASE=
export LYB_SKILL_MEMORY_USER=LYB
export LYB_SKILL_MEMORY_SERVICE_HOST=127.0.0.1
export LYB_SKILL_MEMORY_SERVICE_PORT=8787
export LYB_SKILL_MEMORY_MCP_PATH=/mcp

export LYB_SKILL_MEMORY_EMBED_API_KEY=
export LYB_SKILL_MEMORY_EMBED_BASE_URL=https://dashscope.aliyuncs.com/api/v1
export LYB_SKILL_MEMORY_EMBED_MODEL=text-embedding-v4
export LYB_SKILL_MEMORY_EMBED_DIM=1536
```

仓库根目录也提供了现成模板：

```bash
cat .env.memory.example
```

## 首次安装失败排查

- `missing_env`
  说明数据库环境变量没配全，先执行 `python3 scripts/bootstrap.py --print-env-template`
- `connection refused` 或数据库连不上
  先确认目标机器能访问 PostgreSQL 地址和端口
- `vector extension` 不可用
  说明目标 PostgreSQL 没开 `pgvector`
- MCP 服务没起来
  先看 `/tmp/my_skillproject-memory-service.log`
- embedding 没生效
  先检查 `LYB_SKILL_MEMORY_EMBED_API_KEY` 和模型维度是否匹配 `1536`
