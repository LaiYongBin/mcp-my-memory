# mcp-my-memory

个人长期记忆 MCP 服务，基于 PostgreSQL + pgvector，支持向量检索、实体图、证据累积、生命周期治理与间隔重复复习。

## 核心能力

### 记忆管理
- 显式长期记忆写入、更新、归档、删除
- 自动候选提取与 review 候选审批/拒绝
- 多轮证据累积后再升级推断型记忆
- 记忆生命周期：`fresh / stable / cold / stale / conflicted`
- 记忆版本时间线（`supersedes` 链）与回滚（`revert_memory_to_version`）
- 间隔重复复习调度（SM-2 简化版）：基于 `recall_count` 自动计算 `next_review_at`

### 召回与上下文
- 回答前主动召回相关记忆（`recall_for_response`），按 `direct / contextual / expansive / suppressed` 四层分级返回
- 多会话隔离：`recall_for_response` 支持 `session_key` 参数，防止多会话上下文污染
- `search_entities` / `search_entity_relationships` 轻量实体与关系查询
- 两跳实体推理：`find_two_hop_connections` 挖掘间接关联
- 会话上下文摘要（segment / topic / global_topic 三层）独立于长期记忆存储

### 治理与安全
- 敏感度：`public / normal / sensitive / restricted`
- 披露策略：`normal / gentle / user_confirm / internal_only`
- taxonomy registry + domain candidate 治理，防止字段值漂移
- stability_score 衰减：时效性属性（`current_goal`、`current_focus` 等）衰减快，频繁召回的记忆衰减慢
- importance 衰减：`stale` / `cold` 生命周期的时效属性自动降低 importance，避免过时记忆持续占据搜索前位
- recall_count 稳定性乘数：高频召回（≥5次）减缓 age_penalty，长期活跃记忆保持稳定

### 性能优化（Round-5）
- 批量证据累积：`accumulate_evidence_batch` 替代 N×1 DB 往返
- 批量 Embedding：`generate_embeddings_batch` 一次 HTTP 请求替代 N 个并行请求
- 递归 CTE 时间线：`WITH RECURSIVE` 单次查询替代 O(N) 链式 SELECT
- UNNEST 批量实体图写入：`executemany` + `UNNEST` 替代 N+1 INSERT
- 最近记忆缓存 TTL 延长至 300 秒，`upsert_memory` 写入后主动失效缓存
- Fire-and-forget 后台任务添加 `done_callback` 记录异常，不再静默丢失错误

---

## MCP 工具列表（37 个）

### 核心记忆 CRUD
| 工具 | 说明 |
|------|------|
| `add_memory` | 写入或更新一条长期记忆 |
| `search_memories` | 全文 + 向量混合检索记忆（支持 subject_key / attribute_key / sentiment 过滤） |
| `search_memories_by_time_range` | 按时间范围检索记忆 |
| `search_memory_window` | 滑动时间窗检索 |
| `delete_memory` | 归档（软删除）一条记忆 |

### 召回与上下文
| 工具 | 说明 |
|------|------|
| `recall_for_response` | 回答前召回相关记忆与上下文，支持 `session_key` 隔离多会话 |
| `search_context` | 检索会话上下文快照 |
| `search_recent_dialogue_summaries` | 查询最近对话摘要（segment/topic/global_topic） |

### 对话捕获与编排
| 工具 | 说明 |
|------|------|
| `capture_turn` | 记录单轮对话并触发记忆提取流水线 |
| `add_context` | 批量写入多轮上下文，可选触发记忆提取 |
| `orchestrate_turn_memory` | 统一编排：recall + capture，一次调用拿到本轮所有结果 |
| `batch_ingest_turns` | 批量导入历史对话（支持限速，防止 LLM 速率超限） |

### 记忆治理与维护
| 工具 | 说明 |
|------|------|
| `maintain_memory_store` | 批量重算 lifecycle_state、stability_score，自动归档过期记忆 |
| `maintain_entity_graph` | 重建或增量更新实体图 |
| `merge_duplicate_memories` | 检测并合并相似重复记忆 |
| `generate_memory_report` | 生成记忆统计报告（含情感分布） |

### 记忆版本与挑战
| 工具 | 说明 |
|------|------|
| `get_memory_timeline` | 查询记忆版本时间线（WITH RECURSIVE CTE 单次查询） |
| `revert_memory_to_version` | 将当前记忆回滚到历史版本 |
| `get_stale_memories_for_challenge` | 获取待挑战的过期记忆列表 |
| `submit_challenge_answer` | 提交记忆挑战结果，confirmed=True 更新内容并按 SM-2 调度下次复习，confirmed=False 归档并重置召回计数 |

### 工作记忆（短期状态）
| 工具 | 说明 |
|------|------|
| `search_memories` | 同上，支持 `memory_type=working` 过滤 |
| `delete_working_memory` | 立即删除指定 working memory（无需等待 7 天过期） |

### 实体图
| 工具 | 说明 |
|------|------|
| `search_entities` | 检索实体档案 |
| `search_entity_relationships` | 查询实体关系边 |

### Review 候选
| 工具 | 说明 |
|------|------|
| `search_domain_candidates` | 查看待治理的候选值 |
| `approve_domain_candidate` | 批准候选值（可指定并入已有 canonical） |
| `reject_domain_candidate` | 拒绝候选值 |
| `merge_domain_alias` | 合并 alias 到 canonical |
| `list_domain_values` | 查看 domain 已有枚举值 |

### 其他工具
| 工具 | 说明 |
|------|------|
| `search_entity_relationships` | 查询实体关系 |
| `get_memory_report` | 获取记忆统计 |
| `export_memory_records` | 导出记忆记录（按敏感度过滤） |
| `fetch_source_turns` | 通过 source_ref 溯源原始对话轮次 |

---

## 数据库 Schema

当前运行时使用重构后的 v2 表结构：

| 表名 | 用途 |
|------|------|
| `memory_record` | 长期记忆主表 |
| `memory_vector_chunk` | 向量分块与 embedding |
| `session_state` | 短期工作记忆 |
| `memory_candidate` | 待确认候选 |
| `conversation_turn` | 原始对话事件 |
| `memory_inference` | AI 分析结果 |
| `memory_signal` | 证据累积（含 `status=promoted` 标记已晋升信号） |
| `conversation_summary` | segment / topic / global_topic 摘要 |
| `entity_profile` | 实体档案 |
| `entity_edge` | 实体关系边 |

Migration 执行顺序：
- `010_schema_v2.sql` — v2 主表
- `011_cleanup_legacy.sql` — 清理 legacy 表
- `012_constraints_v2.sql` — CHECK 约束
- `013_indexes_v2.sql` — 专用索引
- `014_domain_registry.sql` — taxonomy registry
- `015_memory_governance_v4.sql` — lifecycle / sensitivity / disclosure 治理字段
- `016_entity_graph.sql` — entity_profile + entity_edge
- `017_related_subjects.sql` — related_subject_key 第二实体槽位

---

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
- 安装 Python 依赖（Python 3.11+）
- 连接 PostgreSQL 执行建表和索引 SQL
- 检查 `pgvector` 扩展
- 启动本地 MCP memory 服务并做监听检查

也可以逐步手动执行：

```bash
cd mcp/personal-memory
python3.11 -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 scripts/bootstrap.py
```

> **Windows 注意**：`requirements.txt` 使用 `psycopg[binary]`，已内置 libpq，无需额外安装 PostgreSQL 客户端。若遇到 DLL 被安全软件拦截，将 `.venv\Lib\site-packages\psycopg` 目录加入杀软白名单即可。

`bootstrap.py` 支持附加参数：

```bash
python3 scripts/bootstrap.py --backfill-embeddings  # 补全历史记忆的向量
python3 scripts/bootstrap.py --skip-service          # 只建表，不启动服务
python3 scripts/bootstrap.py --skip-db               # 只启动服务，跳过建表
python3 scripts/bootstrap.py --print-env-template    # 打印环境变量模板
```

---

## 挂载到 Claude Code

```bash
ROOT="$(pwd)/mcp/personal-memory"

claude mcp add-json -s user personalMemory \
  "{\"command\":\"$ROOT/.venv/bin/python\",\"args\":[\"-m\",\"service.mcp_server\",\"--transport\",\"stdio\"],\"env\":{\"PYTHONPATH\":\"$ROOT\"}}"
```

## 挂载到 Codex

```bash
ROOT="$(pwd)/mcp/personal-memory"

codex mcp add personalMemory \
  --env PYTHONPATH="$ROOT" \
  -- "$ROOT/.venv/bin/python" -m service.mcp_server --transport stdio
```

---

## 环境变量

### 必填

```bash
export LYB_SKILL_PG_ADDRESS=        # PostgreSQL 地址
export LYB_SKILL_PG_USERNAME=       # 用户名
export LYB_SKILL_PG_PASSWORD=       # 密码
export LYB_SKILL_PG_MY_PERSONAL_DATABASE=  # 数据库名
```

### 推荐配置

```bash
export LYB_SKILL_PG_PORT=5432
export LYB_SKILL_MEMORY_USER=LYB
export LYB_SKILL_MEMORY_SERVICE_HOST=127.0.0.1
export LYB_SKILL_MEMORY_SERVICE_PORT=8787
export LYB_SKILL_MEMORY_MCP_PATH=/mcp
export LYB_SKILL_MEMORY_ANALYZE_TIMEOUT=90
export LYB_SKILL_MEMORY_CONTEXT_SYNC_TIMEOUT=180
```

### Embedding（可选，不配则禁用语义检索）

```bash
export LYB_SKILL_MEMORY_EMBED_API_KEY=
export LYB_SKILL_MEMORY_EMBED_BASE_URL=https://dashscope.aliyuncs.com/api/v1
export LYB_SKILL_MEMORY_EMBED_MODEL=text-embedding-v4
export LYB_SKILL_MEMORY_EMBED_DIM=1536
```

仓库根目录提供了现成模板：

```bash
cat .env.memory.example
```

---

## 推荐的全局行为提示

MCP 只负责提供工具。要让 Claude/Codex 在普通聊天中主动结合旧记忆，建议在以下文件中补充全局提示：

- `~/.claude/CLAUDE.md`
- `~/.codex/AGENTS.md`

核心原则：

- 用户显式说"记住 / 忘掉 / 查一下"时，直接调用相应 MCP 工具
- 普通聊天里，优先用 `orchestrate_turn_memory` 统一拿到本轮 recall + capture 结果
- 普通聊天时，用 `capture_turn` 隐式记录单轮对话；如果维护了上下文批次，改用 `add_context(..., extract_memory=true)`
- 如果旧记忆能明显提升回答质量，可隐式调用 `recall_for_response`
- `recall_for_response` 返回 `should_recall=false` 时，不要强行提及旧记忆
- `recall_for_response` 的 `suppressed_memories` / `disclosure_warnings` 提示 `internal_only` / `user_confirm` 时，默认只内部参考
- 用 `maintain_memory_store` 定期重算老记忆的 lifecycle / stability，避免库里长期漂移
- 记忆查询和写入默认对用户隐藏，不要在回答里汇报"我查了记忆"

更完整的双端挂载与提示模板见 [docs/mcp-client-guidance.md](docs/mcp-client-guidance.md)。

---

## 常用命令

```bash
cd mcp/personal-memory
. .venv/bin/activate

# 服务管理
python3 scripts/ensure_service.py
python3 -m service.mcp_server --transport streamable-http --host 127.0.0.1 --port 8787 --path /mcp

# 初始化/迁移
python3 scripts/bootstrap.py

# 上下文同步
python3 scripts/context_sync.py --session-key my-session --topic-hint "讨论主题" \
  --turn "user:用户说了什么" --turn "assistant:助手回复了什么" --extract-memory

# 上下文检索
python3 scripts/context_search.py --query "搜索关键词" --snapshot-level topic --limit 5

# 记忆捕获
python3 scripts/memory_capture_cycle.py --user-text "记住我最近开始每天骑车通勤" --assistant-text "我记下来了"
python3 scripts/memory_capture.py --text "我喜欢黑咖啡"
python3 scripts/memory_capture.py --text "记住我对象喜欢花" --auto-persist

# 记忆查询
python3 scripts/memory_query.py --query "黑咖啡"
python3 scripts/memory_query.py --memory-type preference --updated-after "2026-01-01T00:00:00"

# Review 候选
python3 scripts/review_candidates.py --limit 20
python3 scripts/review_action.py --id 1 --action approve

# 维护
python3 scripts/memory_maintenance.py --dry-run --limit 50
python3 scripts/memory_maintenance.py --include-archived

# 证据与分析
python3 scripts/memory_evidence.py --limit 20
python3 scripts/memory_analysis_results.py --session-key default
```

---

## 运行测试

```bash
cd mcp/personal-memory
python3.11 -m pytest tests/ --ignore=tests/test_domain_registry.py -v
# 预期：198+ 通过，1 个需要真实 DB 连接的测试预期失败
```

---

## 故障排查

| 现象 | 处理方式 |
|------|---------|
| `missing_env` | 先执行 `python3 scripts/bootstrap.py --print-env-template` 确认变量已配 |
| `connection refused` / 数据库连不上 | 确认目标机器可访问 PostgreSQL 地址和端口 |
| `vector extension` 不可用 | 目标 PostgreSQL 未开启 `pgvector` 扩展 |
| MCP 服务未启动 | 查看 `/tmp/my_skillproject-memory-service.log` |
| embedding 未生效 | 检查 `LYB_SKILL_MEMORY_EMBED_API_KEY` 和 `LYB_SKILL_MEMORY_EMBED_DIM` 是否与模型匹配 |
| `AttributeError: module has no attribute` | 确认 Python 版本为 3.11+，并已激活正确的 `.venv` |
