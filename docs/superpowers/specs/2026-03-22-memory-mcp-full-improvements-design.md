# Memory MCP 全面改进设计规格

**日期：** 2026-03-22
**范围：** 18 项 Bug 修复、性能优化与新功能，覆盖 Group A–E
**执行顺序：** A → B → C → D → E（依赖递进，风险最低）

---

## 背景

`mcp/personal-memory/` 是一个基于 PostgreSQL + pgvector 的个人记忆 MCP 服务，提供 19 个 MCP 工具。通过全面审查，发现 3 类问题和若干新功能机会，统一在本规格中描述。

---

## Group A：Bug 修复（3 项）

### A1 — 否定语义误匹配修复

**问题：** `PERSONAL_QUERY_PATTERNS` 中的 `"喜欢"` 做子串匹配，导致 `"我不喜欢这个"` 也触发个性化加分。

**修复范围：** 仅修复 `_decide_recall()` 中对 `PERSONAL_QUERY_PATTERNS` 的调用，不涉及 `PERSONAL_MEMORY_PATTERNS`。

**新增函数（`service/mcp_server.py`）：**

```python
def _has_negated_pattern(text: str, patterns, negation_chars: str = "不没别未无非") -> bool:
    """若匹配位置紧前 2 字含否定词，视为否定命中，跳过；否则等同 _has_pattern。"""
    for pattern in patterns:
        idx = text.find(pattern)
        if idx < 0:
            continue
        prefix = text[max(0, idx - 2):idx]
        if any(neg in prefix for neg in negation_chars):
            continue
        return True
    return False
```

将 `_decide_recall` 中 `_has_pattern(user_message, PERSONAL_QUERY_PATTERNS)` 改为 `_has_negated_pattern(user_message, PERSONAL_QUERY_PATTERNS)`。

**文件：** `service/mcp_server.py`
**测试：** `tests/test_mcp_server.py` 新增 `NegationPatternTests`：
- `"我不喜欢这个"` → `should_recall=False`
- `"我喜欢咖啡"` → 命中
- `"完全不知道我喜欢什么"` → 命中（否定词不在紧前 2 字内）

---

### A2 — 中文滑窗匹配高频词假阳性修复

**问题：** `_shared_phrase_relevance()` 的高频词每次命中，错误将无关记忆推入 `contextual` 层。

**修复方案：** 在 `mcp_server.py` 顶部定义：

```python
_PHRASE_STOPWORDS = frozenset({
    "工作", "我们", "时候", "可以", "一个", "这个", "那个", "什么",
    "如何", "怎么", "为什么", "因为", "所以", "但是", "然后", "现在",
    "已经", "还是", "还有", "或者", "并且", "这样", "那样", "一些",
    "很多", "非常", "特别", "感觉", "觉得", "认为", "知道", "看到",
})
```

`_shared_phrase_relevance()` 中匹配到的 phrase 若在 `_PHRASE_STOPWORDS` 中，跳过不计分。

**文件：** `service/mcp_server.py`
**测试：** `tests/test_mcp_server.py` 新增 `PhraseStopwordTests`

---

### A3 — `consolidate_working_memories` 绕过证据门槛修复

**问题：** `consolidate_working_memories()` 当前用 `HAVING count(*) >= 2` 直接提升，绕过 `evidence_supports_promotion()` 保护。

**修复方案：**

`session_state` 表无 `subject`/`attribute`/`value` 字段，需从内容构造 `pseudo_item`。`conflict_scope` 应按内容独立积累而非共享（共享同一 slot 会导致所有 working memory 合并为同一条证据）：

```python
# 实际代码中循环变量为 row（for row in rows:），非 session_row
# conflict_scope 按内容哈希独立，避免不同内容竞争同一 slot
import hashlib
content_hash = hashlib.md5(row["summary"].encode()).hexdigest()[:8]

pseudo_item = {
    "subject": "user",
    "attribute": "working_memory",
    "value": row["summary"],
    "claim": row.get("source_text") or row["summary"],
    "category": "current_goal",
    "evidence_type": "observed",
    "time_scope": "short_term",
    "action": "long_term",    # 必须为 "long_term"，否则 evidence_supports_promotion() 直接返回 False
    "confidence": 0.6,
    "conflict_scope": f"user.working_memory.{content_hash}",
    "tags": [],
}
evidence = accumulate_evidence(user_code=user_code, item=pseudo_item)
if evidence and evidence_supports_promotion(pseudo_item, evidence):
    upsert_memory({
        "user_code": user_code,
        "memory_type": "fact",
        "title": row["summary"][:80],
        "content": row["summary"],
        "subject_key": "user",
        "attribute_key": "working_memory",
        "value_text": row["summary"],
        "confidence": promoted_confidence(pseudo_item, evidence),
        "source_type": "capture_cycle",
        "is_explicit": False,
        "status": "active",
    })
    # 标记已提升：accumulate_evidence/upsert_memory 已关闭之前的游标，必须新开连接块
    with get_conn() as conn2, conn2.cursor() as cur2:
        cur2.execute(
            "UPDATE session_state SET status = %s WHERE id = %s",
            (STATUS_ARCHIVED, row["id"])
        )
        conn2.commit()
# 不满足则保留在 session_state，等待下次积累（不做任何修改）
```

**文件：** `service/capture_cycle.py`
**测试：** `tests/test_capture_strategy.py` 新增 `WorkingMemoryPromotionTests`

---

## Group B：性能与参数优化（4 项）

### B1 — `maintain_memory_store` 增加精准过滤参数

**问题：** 每次全扫描，随库增大线性变慢。

**方案：** 新增三个可选参数，SQL 动态追加（**使用 `ANY(%s)` 参数化，禁止字符串拼接**）：

```python
conditions = ["user_code = %s"]
params: List[Any] = [user_code]
if lifecycle_states:
    conditions.append("lifecycle_state = ANY(%s)")
    params.append(lifecycle_states)   # 直接传 list，psycopg 自动处理
if memory_types:
    conditions.append("memory_type = ANY(%s)")
    params.append(memory_types)
if categories:
    conditions.append("category = ANY(%s)")
    params.append(categories)
where_sql = " AND ".join(conditions)
```

`schemas.py` 中 `MaintenanceResult` 新增：
```python
filter_applied: Dict[str, Any] = Field(default_factory=dict)
```

`memory_ops.maintain_memory_store()` 返回的 dict 中包含 `filter_applied` 键，值为传入的非 None 过滤条件。

**`mcp_server.py` 工具函数签名同步更新：**

```python
# maintain_memory_store_tool 新增三个可选参数
async def maintain_memory_store_tool(
    user_code: Optional[str] = None,
    limit: int = 200,
    dry_run: bool = False,
    include_archived: bool = False,
    lifecycle_states: Optional[List[str]] = None,   # 新增
    memory_types: Optional[List[str]] = None,        # 新增
    categories: Optional[List[str]] = None,          # 新增
) -> MaintenanceResult:
    result = maintain_memory_store(
        user_code=user_code,
        limit=limit,
        dry_run=dry_run,
        include_archived=include_archived,
        lifecycle_states=lifecycle_states,
        memory_types=memory_types,
        categories=categories,
    )
    return MaintenanceResult(**result)
```

**文件：** `service/memory_ops.py`、`service/mcp_server.py`、`service/schemas.py`
**测试：** `tests/test_memory_ops.py` 新增 `MaintainMemoryStoreFilterTests`

---

### B2 — `capture_turn` 批次触发摘要

**问题：** 每次 capture 都触发 context sync，高频对话产生大量碎片 segment。

**方案（不新增参数，修改 `orchestrate_turn_memory` 内部逻辑）：**

`capture_turn` 工具已有 `sync_context: bool = True` 参数，**本次不新增** `skip_context_sync` 参数。

在 `orchestrate_turn_memory` 工具新增 `sync_every_n_turns: int = 0`（0=每次都同步，N>0=每 N 轮同步一次）。

`orchestrate_turn_memory` 内部实现调用链（基于实际代码结构，`orchestrate_turn_memory_tool` 为同步函数）：
```python
# 1. 先调用 recall（实际函数名为 _build_recall_result，非异步）
recall_result = _build_recall_result(
    user_message=user_message,
    draft_response=draft_response,
    topic_hint=topic_hint,
    memories=memories,
    contexts=contexts,
    recent_contexts=recent_contexts,
)

# 2. 确定是否需要同步
if sync_every_n_turns > 0:
    turn_count = _increment_turn_count(session_key)
    should_sync = (turn_count % sync_every_n_turns == 0)
else:
    should_sync = True

# 3. 若 capture_after_response，执行 capture 流程
# 实际代码通过 _execute_capture_turn(sync_context=...) 控制是否同步
# should_sync=True  → sync_context=True  → _execute_capture_turn 内部会调用 sync_session_context()
# should_sync=False → sync_context=False → _execute_capture_turn 内部跳过 sync_session_context()
if capture_after_response:
    executed_capture = _execute_capture_turn(
        user_text=user_message,
        assistant_text=assistant_text,
        user_code=user_code,
        session_key=session_key,
        topic_hint=topic_hint,
        source_ref=source_ref,
        sync_context=should_sync,   # 将 should_sync 传入，控制是否同步
        consolidate=consolidate,
    )
```

"不同步"等同于向 `_execute_capture_turn` 传 `sync_context=False`，由其内部决定是否调用 `sync_session_context()`，不在外层单独判断。

**turn 计数（进程内存字典，无 DB 依赖）：**

```python
# mcp_server.py 模块级
_session_turn_counts: Dict[str, int] = {}

def _increment_turn_count(session_key: str) -> int:
    count = _session_turn_counts.get(session_key, 0) + 1
    _session_turn_counts[session_key] = count
    return count
```

> 进程重启后计数归零（对渐进式使用场景可接受），无需 DB schema 变更。

**文件：** `service/mcp_server.py`（仅修改 `orchestrate_turn_memory` 工具处理函数）
**测试：** `tests/test_mcp_server.py` 新增 `TurnCountTests`

---

### B3 — Hybrid Search 数据库层合并

**问题：** `search_memories()` 串行两次 DB 查询，性能瓶颈明显。

**方案：**

新增环境变量 `LYB_SKILL_MEMORY_DB_HYBRID_SEARCH=true`（默认 false）。在 `constants.py` 中定义（`constants.py` 已有 B4 的 `import os`，复用）：

```python
# constants.py 中新增（与 B4 的 RECALL_SCORE_WEIGHTS 同处，共用 import os）
HYBRID_SEARCH_ENABLED = os.getenv("LYB_SKILL_MEMORY_DB_HYBRID_SEARCH", "false").lower() == "true"
```

在 `search_memories()` 函数入口：

```python
if not (HYBRID_SEARCH_ENABLED and query_vec is not None):
    return _search_memories_two_pass(...)  # 回退两路查询
```

`query_vec` 生成方式与现有 `embeddings.py` 中 `get_embedding()` 相同（返回 `List[float]` 或 `None`）。传给 psycopg 时直接作为参数即可，pgvector 适配器已通过 `register_vector(conn)` 在 `db.py` 初始化时注册。

**单次 SQL（与项目现有代码保持一致，使用 `websearch_to_tsquery`）：**

```sql
SELECT mr.*,
       ts_rank_cd(mr.search_vector, websearch_to_tsquery('simple', %s)) AS rank_score,
       (mvc.embedding <=> %s::vector) AS vector_distance,
       COALESCE(
           ts_rank_cd(mr.search_vector, websearch_to_tsquery('simple', %s)) * 0.4
           + (1.0 - (mvc.embedding <=> %s::vector)) * 0.6,
           ts_rank_cd(mr.search_vector, websearch_to_tsquery('simple', %s)) * 0.4
       ) AS hybrid_score
FROM memory_record mr
LEFT JOIN memory_vector_chunk mvc ON mvc.memory_id = mr.id AND mvc.chunk_index = 0
WHERE mr.user_code = %s
  AND (
    mr.search_vector @@ websearch_to_tsquery('simple', %s)
    OR (mvc.embedding IS NOT NULL AND (mvc.embedding <=> %s::vector) < 0.5)
  )
ORDER BY hybrid_score DESC NULLS LAST
LIMIT %s
```

**参数元组（按 %s 顺序）：**
```python
params = (
    query_text,   # rank_score 的 websearch_to_tsquery
    query_vec,    # vector_distance 的 <=>
    query_text,   # COALESCE 内 rank 的 websearch_to_tsquery
    query_vec,    # COALESCE 内 vector 的 <=>
    query_text,   # COALESCE else 分支的 websearch_to_tsquery
    user_code,    # WHERE mr.user_code
    query_text,   # WHERE search_vector @@
    query_vec,    # WHERE embedding <=>
    limit,        # LIMIT
)
```

**关键说明：**
- `LEFT JOIN`：确保无 embedding 的记忆不从全文结果消失
- `ORDER BY hybrid_score DESC NULLS LAST`：PostgreSQL `DESC` 默认 NULLS FIRST，**必须显式指定 NULLS LAST**

**文件：** `service/memory_ops.py`、`service/constants.py`
**测试：** `tests/test_memory_ops.py` 新增 `HybridSearchFallbackTests`

---

### B4 — 召回评分权重配置化

**方案：** 在 `constants.py` 新增：

```python
RECALL_SCORE_WEIGHTS = {
    "high_confidence_memory": float(os.getenv("LYB_SKILL_MEMORY_WEIGHT_HIGH_CONF", "0.45")),
    "usable_memory_match": float(os.getenv("LYB_SKILL_MEMORY_WEIGHT_USABLE", "0.25")),
    "explicit_memory": float(os.getenv("LYB_SKILL_MEMORY_WEIGHT_EXPLICIT", "0.15")),
    "strong_semantic": float(os.getenv("LYB_SKILL_MEMORY_WEIGHT_STRONG_SEM", "0.25")),
    "moderate_semantic": float(os.getenv("LYB_SKILL_MEMORY_WEIGHT_MOD_SEM", "0.12")),
    "personal_memory_signal": float(os.getenv("LYB_SKILL_MEMORY_WEIGHT_PERS_MEM", "0.20")),
    "personal_query_signal": float(os.getenv("LYB_SKILL_MEMORY_WEIGHT_PERS_QRY", "0.15")),
    "topic_continuity": float(os.getenv("LYB_SKILL_MEMORY_WEIGHT_TOPIC", "0.15")),
}
```

`_decide_recall()` 将硬编码常量替换为 `RECALL_SCORE_WEIGHTS["xxx"]` 引用。

**文件：** `service/constants.py`、`service/mcp_server.py`
**测试：** `tests/test_mcp_server.py` 新增 `RecallWeightConfigTests`（patch `os.environ` 验证覆盖生效）

---

## Group C：记忆生命周期工具（3 项）

### C1 — 记忆合并去重工具

**新 MCP 工具：** `merge_duplicate_memories`

**`find_duplicate_pairs` SQL（两侧均过滤 `user_code`，防止跨用户配对）：**

```sql
SELECT a.memory_id AS master_candidate_id,
       b.memory_id AS slave_candidate_id,
       (a.embedding <=> b.embedding) AS distance
FROM memory_vector_chunk a
JOIN memory_vector_chunk b
    ON b.memory_id > a.memory_id
    AND b.chunk_index = 0
    AND b.user_code = %s
WHERE a.chunk_index = 0
  AND a.user_code = %s
  AND (a.embedding <=> b.embedding) < (1.0 - %s)
ORDER BY distance ASC
LIMIT %s
-- params: (user_code, user_code, similarity_threshold, limit * 2)
```

Python 层：批量 IN 查询 `memory_record WHERE id = ANY(%s)` 获取 `status`，过滤掉已 `status='archived'` 的配对。

**合并逻辑（`merge_memory_pair` 函数）：**
1. 每对中保留 `confidence` 更高者（相同则取 `updated_at` 更新的）为 master，另一条为 slave
2. slave 的 `content` 以 `"\n\n---\n"` 分隔追加到 master 的 `content` 末尾；超 4000 字则截断加 `"…（已截断）"`
3. slave 设置：`status='archived'`（直接 SQL UPDATE，不走 `upsert_memory`）
4. master 设置：`supersedes_id = slave.id`（`upsert_memory()` 不更新此列，必须单独写 SQL）
5. master 的 `tags` 更新为两条 tags 的并集（Python 层合并后写入）

**步骤 3–5 的 SQL 实现（单事务）：**

```python
with get_conn() as conn, conn.cursor() as cur:
    # 3. slave 归档
    cur.execute(
        "UPDATE memory_record SET status = 'archived', updated_at = now() WHERE id = %s",
        (slave_id,)
    )
    # 4. master 设置 supersedes_id
    cur.execute(
        "UPDATE memory_record SET supersedes_id = %s, updated_at = now() WHERE id = %s",
        (slave_id, master_id)
    )
    # 5. master 更新 content 和 tags（Python 层已合并）
    cur.execute(
        "UPDATE memory_record SET content = %s, tags = %s::jsonb, updated_at = now() WHERE id = %s",
        (merged_content, json.dumps(merged_tags), master_id)
    )
    conn.commit()
```

**参数：** `user_code`、`similarity_threshold: float = 0.92`、`dry_run: bool = False`、`limit: int = 50`

**返回：** `MergeResult`（新建 schema），含 `merged_pairs: List[Dict]`、`merged_count: int`、`dry_run: bool`

**文件：** `service/memory_ops.py`（新增 `find_duplicate_pairs` + `merge_memory_pair`）、`service/mcp_server.py`、`service/schemas.py`
**测试：** `tests/test_memory_ops.py` 新增 `MergeDuplicateMemoriesTests`（含 dry_run 验证不写 DB）

---

### C2 — 主动验证工具

**新 MCP 工具：** `get_stale_memories_for_challenge`

**逻辑：** 查询 `lifecycle_state IN ('cold', 'stale')` 且 `is_explicit = false` 且 `last_recalled_at < now() - interval '%s days'` 的记忆，按 `confidence DESC, importance DESC` 排序，返回前 N 条。

**`suggested_question` 生成（规则模板）：**

```python
def _suggested_challenge_question(memory: Dict) -> str:
    attr = memory.get("attribute_key") or ""
    # 优先 value_text（原子值），其次 title，防止 title 带格式前缀（如 "favorite_drink: 黑咖啡"）
    value = (memory.get("value_text") or "").strip()
    title = (memory.get("title") or value or "").strip()
    if attr.startswith("favorite_"):
        return f"你还喜欢{value or title}吗？"
    if attr.startswith("dislike_"):
        return f"你现在还不喜欢{value or title}吗？"
    if attr in ("current_focus", "current_goal"):
        return f"关于"{value or title}"，这个目标现在还在推进吗？"
    return f"关于"{title}"，现在情况还一样吗？"
```

**参数：** `user_code`、`limit: int = 5`、`min_days_since_recall: int = 30`、`memory_types: Optional[List[str]] = None`

**返回：** `ItemListResult`（复用），每条附带 `suggested_question` 字段

**文件：** `service/memory_ops.py`（新增 `get_stale_for_challenge`）、`service/mcp_server.py`
**测试：** `tests/test_memory_ops.py` 新增 `StaleMemoryChallengeTests`

---

### C3 — global_topic 防膨胀

**问题：** `conversation_summary.summary`（global_topic 行）随时间无限增长。

**数据结构说明（基于实际代码）：**

`sync_session_context()` 调用链：`_latest_global_topic_snapshot()` → `merge_topic_summary()` → `_save_snapshot()`。`conversation_summary.summary` 存储的是 `merge_topic_summary()` 返回 dict 中 `"summary"` 键的**纯文本字符串**（不是整个 dict 的 JSON 序列化）。

**截断逻辑（防前缀叠加）：**

> **注意：** `constants.py` 当前无 `import os`，B4 的 `RECALL_SCORE_WEIGHTS` 已引入 `import os`；C3 的常量定义与 B4 同文件，共用该 import。

```python
MAX_GLOBAL_TOPIC_CHARS = int(os.getenv("LYB_SKILL_MEMORY_MAX_GLOBAL_TOPIC_CHARS", "2000"))
_COMPRESSION_PREFIX = "[早期内容已压缩]\n"

# 在 sync_session_context() 中，获取 existing_global_topic 后、调用 merge_topic_summary() 前：
existing_summary_str = existing_global_topic.get("summary") or ""
if len(existing_summary_str) > MAX_GLOBAL_TOPIC_CHARS:
    # 去重前缀，防止每轮都叠加 "[早期内容已压缩]"
    clean_str = existing_summary_str
    while clean_str.startswith(_COMPRESSION_PREFIX):
        clean_str = clean_str[len(_COMPRESSION_PREFIX):]
    keep_from = max(0, len(clean_str) - int(MAX_GLOBAL_TOPIC_CHARS * 0.8))
    existing_global_topic = {
        **existing_global_topic,
        "summary": _COMPRESSION_PREFIX + clean_str[keep_from:]
    }
# 然后调用 merge_topic_summary(existing_global_topic, segment)
```

**文件：** `service/context_snapshots.py`、`service/constants.py`
**测试：** `tests/test_context_snapshots.py` 新增 `GlobalTopicAntiInflationTests`（含多轮调用验证前缀不叠加）

---

## Group D：新查询 / 报告工具（4 项）

### D1 — 记忆版本时间线

**新 MCP 工具：** `get_memory_timeline`

**遍历算法（含循环防护和双向遍历）：**

```python
def get_memory_timeline(*, user_code, memory_id=None, subject_key=None,
                         attribute_key=None, limit=20) -> List[Dict]:
    visited_ids: set = set()
    result = []

    # 1. 确定起点
    start = _fetch_start_memory(user_code, memory_id, subject_key, attribute_key)
    if not start:
        return []

    # 提前将 start["id"] 加入 visited_ids，防止向新遍历时循环指回 start
    visited_ids.add(start["id"])

    # 2. 向新：反向查找谁 supersedes 了 start（可能有多层，递归向上到最新版）
    current = start
    newer_chain = []
    while True:
        # SELECT * FROM memory_record WHERE supersedes_id = %s AND user_code = %s LIMIT 1
        newer = _fetch_where_supersedes_id(user_code, current["id"])
        if not newer or newer["id"] in visited_ids:
            break
        visited_ids.add(newer["id"])
        newer_chain.append(newer)
        current = newer
    # newer_chain 最后一条是最新版
    for row in newer_chain:
        result.append({**row, "timeline_position": "current" if row is newer_chain[-1] else "superseded",
                        "changed_at": row["updated_at"]})

    # 3. 起点（若无更新版则 current，否则 superseded）
    start_position = "superseded" if newer_chain else "current"
    result.append({**start, "timeline_position": start_position, "changed_at": start["updated_at"]})
    # 注意：start["id"] 已在第 2 步前加入 visited_ids，此处无需重复添加

    # 4. 向旧：沿 supersedes_id 链追溯
    row = start
    while row.get("supersedes_id") and len(result) < limit:
        if row["supersedes_id"] in visited_ids:
            break  # 防止循环引用
        older = _fetch_by_id(user_code, row["supersedes_id"])
        if not older:
            break
        visited_ids.add(older["id"])
        result.append({**older, "timeline_position": "superseded", "changed_at": older["updated_at"]})
        row = older

    # 5. 冲突链（仅追加 start 的直接冲突）
    if start.get("conflict_with_id") and start["conflict_with_id"] not in visited_ids:
        conflict = _fetch_by_id(user_code, start["conflict_with_id"])
        if conflict and len(result) < limit:
            result.append({**conflict, "timeline_position": "conflicted", "changed_at": conflict["updated_at"]})

    return result[:limit]
```

`_fetch_where_supersedes_id(user_code, memory_id)` 定义：
```python
def _fetch_where_supersedes_id(user_code: str, memory_id: int) -> Optional[Dict]:
    """查找取代了指定记忆的记录（若有多条，取最新的一条）。"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM memory_record WHERE supersedes_id = %s AND user_code = %s "
            "ORDER BY updated_at DESC LIMIT 1",
            (memory_id, user_code)
        )
        row = cur.fetchone()
        return dict(row) if row else None
```

**参数：** `user_code`、`memory_id`、`subject_key`、`attribute_key`、`limit: int = 20`

**返回：** `ItemListResult`，每条带 `timeline_position`（`current/superseded/conflicted`）和 `changed_at`

**文件：** `service/memory_ops.py`（新增 `get_memory_timeline`、`_fetch_where_supersedes_id`）、`service/mcp_server.py`
**测试：** `tests/test_memory_ops.py` 新增 `MemoryTimelineTests`（含循环引用防护测试）

---

### D2 — Search-and-Cite（来源引用）

**前置修改（`service/capture_cycle.py`）：**

在 `run_capture_cycle()` 中，写入 `conversation_turn` 得到 `user_event["id"]` 后，若调用方传入的 `source_ref` 为空，自动生成并写回：

```python
def _update_turn_source_ref(turn_id: int, source_ref: str) -> None:
    """写回 source_ref 到已插入的 conversation_turn 行。失败不影响主流程。"""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE conversation_turn SET source_ref = %s WHERE id = %s",
                (source_ref, turn_id)
            )
            conn.commit()
    except Exception as e:
        logging.getLogger(__name__).warning("update turn source_ref failed: %s", e)

# run_capture_cycle() 中，record_conversation_event 之后：
if not source_ref and user_event and user_event.get("id"):
    auto_ref = f"{session_key}:{int(user_event['id'])}"
    _update_turn_source_ref(int(user_event["id"]), auto_ref)
    # assistant turn 也设置同一个 auto_ref（两条共享来源）
    if assistant_event and assistant_event.get("id"):
        _update_turn_source_ref(int(assistant_event["id"]), auto_ref)
```

**`fetch_source_turns()` 批量查询：**

```python
def fetch_source_turns(source_refs: List[str]) -> Dict[str, Dict]:
    """批量查询 conversation_turn，返回 {source_ref: turn_row}。"""
    exact: Dict[str, int] = {}    # source_ref → turn_id
    fuzzy: Dict[str, str] = {}    # source_ref → session_key

    for ref in source_refs:
        if not ref:
            continue
        if ":" in ref:
            sk, _, tid = ref.partition(":")
            try:
                exact[ref] = int(tid)
            except ValueError:
                fuzzy[ref] = ref
        else:
            fuzzy[ref] = ref

    results: Dict[str, Dict] = {}
    with get_conn() as conn, conn.cursor() as cur:
        if exact:
            ids = list(exact.values())
            cur.execute("SELECT * FROM conversation_turn WHERE id = ANY(%s)", (ids,))
            id_to_row = {int(row["id"]): dict(row) for row in cur.fetchall()}
            for ref, tid in exact.items():
                if tid in id_to_row:
                    results[ref] = id_to_row[tid]
        for ref, sk in fuzzy.items():
            cur.execute(
                "SELECT * FROM conversation_turn WHERE session_key = %s AND role = 'user' "
                "ORDER BY created_at DESC LIMIT 1",
                (sk,)
            )
            row = cur.fetchone()
            if row:
                results[ref] = dict(row)
    return results
```

`recall_for_response` 工具新增 `include_cited_sources: bool = False`；`RecallResult` 新增 `cited_sources: List[Dict] = []`。

**文件：** `service/schemas.py`、`service/mcp_server.py`、`service/memory_ops.py`、`service/capture_cycle.py`
**测试：** `tests/test_memory_ops.py` 新增 `FetchSourceTurnsTests`

---

### D3 — 隐私分层导出

**新 MCP 工具：** `export_memories`

**SQL（处理 `disclosure_policy` 为 NULL 的情况）：**

```sql
WHERE COALESCE(disclosure_policy, 'normal') != 'internal_only'
  AND sensitivity_level = ANY(%s)
  -- 若 memory_types 非空：AND memory_type = ANY(%s)
  -- 若 include_archived=False：AND status != 'archived'
ORDER BY updated_at DESC
```

> `COALESCE(disclosure_policy, 'normal')` 确保 `disclosure_policy IS NULL` 的记录（尚未被治理的行）不被错误排除。

**参数：** `user_code`、`sensitivity_levels: List[str] = ["public", "normal"]`、`format: Literal["json","jsonl"] = "json"`、`include_archived: bool = False`、`memory_types: Optional[List[str]] = None`

**返回：** `ExportResult`（新建），含 `records: List[Dict]`（去掉 embedding 字段）、`export_count: int`、`sensitivity_levels_included: List[str]`

**文件：** `service/memory_ops.py`（新增 `export_memory_records`）、`service/mcp_server.py`、`service/schemas.py`
**测试：** `tests/test_memory_ops.py` 新增 `ExportMemoriesTests`（含 NULL disclosure_policy 不被排除的验证）

---

### D4 — 周期记忆报告

**新 MCP 工具：** `generate_memory_report`

**逻辑（纯统计）：** 按 category 统计新建数、更新数、`lifecycle_state IN ('cold','stale')` 数、`is_explicit=true` 数、Top 5 `recall_count`。

**参数：** `user_code`、`period_days: int = 30`

**返回：** `MemoryReport`（新建），含 `period_days`、`new_memories_by_category`、`updated_count`、`stale_count`、`explicit_count`、`top_recalled`

**文件：** `service/memory_ops.py`、`service/mcp_server.py`、`service/schemas.py`
**测试：** `tests/test_memory_ops.py` 新增 `MemoryReportTests`

---

## Group E：高级功能（4 项，含 schema 扩展）

### E1 — 批量历史导入

**新 MCP 工具：** `batch_ingest_turns`

**配对逻辑（完整实现，含所有边界情况）：**

```python
def _pair_turns(turns: List[Dict]) -> Tuple[List[Tuple[Dict, Dict]], List[Dict]]:
    """将 turns 列表配对为 (user_turn, assistant_turn) 列表。"""
    pairs: List[Tuple[Dict, Dict]] = []
    failed: List[Dict] = []
    pending_assistant_content: List[str] = []  # 暂存连续 assistant 内容

    i = 0
    while i < len(turns):
        turn = turns[i]
        role = turn.get("role")

        if role not in ("user", "assistant"):
            failed.append({"index": i, "reason": "unknown role", "turn": turn})
            i += 1
            continue

        if role == "assistant":
            # 积累连续 assistant 内容（等下一个 user 出现时作为该轮回复）
            pending_assistant_content.append(turn.get("content") or "")
            i += 1
            continue

        # role == "user"
        user_turn = turn
        i += 1

        if i < len(turns) and turns[i].get("role") == "assistant":
            # 标准配对：合并积累的 assistant + 当前 assistant
            combined_parts = pending_assistant_content + [turns[i].get("content") or ""]
            assistant_turn = {**turns[i], "content": "\n".join(combined_parts).strip()}
            pending_assistant_content = []
            i += 1
        elif pending_assistant_content:
            # 前面积累了 assistant 内容，但下一条又是 user 或到末尾
            assistant_turn = {"role": "assistant", "content": "\n".join(pending_assistant_content).strip()}
            pending_assistant_content = []
        else:
            # 末尾孤立 user 或下一条是另一个 user
            assistant_turn = {"role": "assistant", "content": ""}

        pairs.append((user_turn, assistant_turn))

    # 末尾积累的孤立 assistant 直接忽略（无对应 user）
    return pairs, failed
```

**参数：** `turns: List[Dict]`、`session_key`、`user_code`、`topic_hint`、`analyze: bool = True`、`rate_limit_ms: int = 500`

**返回：** `IngestResult`（新建），含 `ingested_turns`、`created_memories`、`failed_turns`

**文件：** `service/capture_cycle.py`、`service/mcp_server.py`、`service/schemas.py`、`scripts/batch_ingest.py`
**测试：** `tests/test_capture_strategy.py` 新增 `BatchIngestPairingTests`（覆盖所有边界情况，不需要 DB）

---

### E2 — 实体关系推断优化

**修改方案（基于实际代码，`_relationship_semantic(item: Dict)` 接收 item dict）：**

**步骤 1：** 在 `_relationship_semantic()` 内部追加新关键词规则（使用实际代码的 `if any(kw in text for kw in [...]):` 风格，`text` 来自 item 内容拼接）：

```python
# 追加到现有规则末尾
if any(kw in text for kw in ["室友", "同住", "合租"]):
    return "lives_with"
if any(kw in text for kw in ["兄弟", "姐妹", "兄妹", "弟妹"]):
    return "sibling_of"
if any(kw in text for kw in ["上司", "老板", "汇报"]):
    return "reports_to"
if any(kw in text for kw in ["导师", "mentor", "带我入"]):
    return "mentor_of"
```

**步骤 2：** 在 `infer_edge_relation_type(item)` 外层增加优先级规则（基于 `attribute_key` 和 `related_subject_key`，**不基于 `category`**，因为调用点不传 `category`）：

```python
def infer_edge_relation_type(item: Dict) -> str:
    attribute_key = item.get("attribute_key") or ""
    related_subject_key = item.get("related_subject_key") or item.get("target_subject_key") or ""

    if "favorite_" in attribute_key or "preference_" in attribute_key:
        return "associated_preference"
    if related_subject_key:
        # 有第三方 subject 且 attribute_key 含 health/responsible 提示
        if any(kw in attribute_key for kw in ["health", "care", "responsible"]):
            return "responsible_for"
    # 内容关键词匹配
    return _relationship_semantic(item) or "knows"
```

> **注意：** 调用点（`refresh_entity_graph_for_subject()`）目前只传 `subject_key` 和 `related_subject_key`。为使 `attribute_key` 规则生效，需同步修改调用点：

```python
# refresh_entity_graph_for_subject() 中，调用 infer_edge_relation_type 的位置改为：
# 从当前 row（_load_subject_memories 结果行）中同时传入 attribute_key
relation_type = infer_edge_relation_type({
    "subject_key": cleaned_subject,
    "related_subject_key": related_subject_key,
    "attribute_key": row.get("attribute_key") or "",   # 新增：从记忆行取 attribute_key
})
```

**文件：** `service/entity_graph.py`
**测试：** `tests/test_entity_graph.py` 新增 `InferEdgeRelationTypeTests`

---

### E3 — 两跳实体推理

**调用位置：** 在 `_build_recall_result()` 中，`_enrich_related_entities()` 完成后：
- `source_subject_keys`：从 `related_entities` 列表取 `subject_key` 组成的列表
- `exclude_subject_keys`：已在 `related_entities` 中的 `subject_key` 列表（排除重复），函数内部固定追加 `"user"`

**实现（`entity_graph.py` 新增）：**

```python
def find_two_hop_connections(
    source_subject_keys: List[str],
    exclude_subject_keys: Optional[List[str]] = None,
    user_code: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if not source_subject_keys:
        return []
    # exclude 固定含 "user"；因 exclude 不为空，始终使用 != ALL 分支
    exclude = list(set(exclude_subject_keys or []) | {"user"})
    # 注意：!= ALL(ARRAY[]::text[]) 返回 NULL 而非 TRUE，但此处 exclude 永不为空（含"user"）
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT source_subject_key AS via_entity,
                   target_subject_key, relation_type
            FROM entity_edge
            WHERE source_subject_key = ANY(%s)
              AND target_subject_key != ALL(%s)
              AND (%s IS NULL OR user_code = %s)
        """, (source_subject_keys, exclude, user_code, user_code))
        return [dict(row) for row in cur.fetchall()]
```

二阶实体追加到 `related_entities` 末尾，带 `hop=2` 和 `via_entity` 字段，`visibility='internal_only'`。

**`RecallResult` 变更（dict 层，非 Pydantic schema 修改）：** `related_entities` 字段类型为 `List[Dict[str, Any]]`，无需修改 Pydantic schema。只需在 `_enrich_related_entities()` 返回的每个 dict 中追加 `hop=1`（默认）和 `via_entity=None`；在 `find_two_hop_connections()` 返回的每个 dict 中追加 `hop=2` 和对应的 `via_entity`。

**`RecommendedResponsePlan` 变更：** `internal_only` 新增两跳实体线索文本。

**文件：** `service/entity_graph.py`、`service/mcp_server.py`、`service/schemas.py`
**测试：** `tests/test_entity_graph.py` 新增 `TwoHopConnectionTests`（mock DB，验证批量查询、空输入返回空）

---

### E4 — 情感/情绪维度

**Schema 变更（`sql/018_sentiment.sql`，两张表均需）：**

```sql
ALTER TABLE memory_record
    ADD COLUMN IF NOT EXISTS sentiment VARCHAR(16) DEFAULT 'neutral'
        CHECK (sentiment IN ('neutral', 'positive', 'negative', 'mixed'));

ALTER TABLE memory_inference
    ADD COLUMN IF NOT EXISTS sentiment VARCHAR(16) DEFAULT 'neutral'
        CHECK (sentiment IN ('neutral', 'positive', 'negative', 'mixed'));
```

**字段传递完整链路：**

1. `_analysis_prompt()` 末尾新增 prompt 指令，要求输出 JSON 包含 `"sentiment"` 字段
2. `_normalize_item()` 新增（含合法值白名单校验）：
   ```python
   _VALID_SENTIMENTS = frozenset({"neutral", "positive", "negative", "mixed"})
   sentiment_raw = str(item.get("sentiment") or "neutral").strip().lower()
   sentiment_value = sentiment_raw if sentiment_raw in _VALID_SENTIMENTS else "neutral"
   ```
   同时更新 `build_analysis_item()` 签名，添加可选参数：
   ```python
   def build_analysis_item(
       ...,
       sentiment: str = "neutral",   # 新增可选参数，默认 "neutral"
   ) -> Dict[str, Any]:
       return {
           ...,
           "sentiment": sentiment,   # 新增字段
       }
   ```
   `_normalize_item()` 调用 `build_analysis_item(...)` 时传入 `sentiment=sentiment_value`（使用上方计算好的局部变量 `sentiment_value`，非从 `normalized` dict 取值）。
3. `save_analysis_results()` 在 INSERT `memory_inference` 时写入 `sentiment` 列：
   在 `analyzer.py` 的 `save_analysis_results()` 中，找到 INSERT 语句的列列表（当前末列为 `tags`），在其后追加 `sentiment`；在 VALUES 参数元组末尾追加 `item.get("sentiment", "neutral")`；在 RETURNING 子句末尾追加 `sentiment`。
4. `_build_memory_payload_from_analysis()` 从 `memory_inference` 行读取并透传 `sentiment`
5. `upsert_memory()` 写入 `memory_record.sentiment`

**MCP 工具变更：**
- `search_memories` 新增 `sentiment: Optional[str]` 过滤，追加 `AND sentiment = %s` 条件
- `RecallResult` 新增 `dominant_sentiment: str`（从 `direct_memories` 的 sentiment 取众数，默认 `"neutral"`）
- `RecommendedResponsePlan` 新增 `tone_hint: str`（由 `dominant_sentiment` 推导：`positive`→`"match_positive"`，`negative`→`"acknowledge_negative"`，其他→`"neutral"`）

**文件：** `sql/018_sentiment.sql`、`service/schemas.py`、`service/analyzer.py`、`service/memory_ops.py`、`service/mcp_server.py`、`scripts/bootstrap.py`
**测试：** `tests/test_mcp_server.py` 新增 `SentimentFilterTests`（含 None/默认值和无效值的降级测试）

---

## 数据库变更汇总

| Migration | 内容 | Group |
|-----------|------|-------|
| `018_sentiment.sql` | `memory_record` 和 `memory_inference` 各增加 `sentiment` 字段 | E4 |

**其余 Group A–D 无 schema 变更，均为纯 Python 改动。**

B2 使用进程内存字典存储 turn 计数，不需要 DB schema 变更。

---

## 测试策略

每个改动点均需：
- 单元测试覆盖核心逻辑路径（含边界情况）
- 不改动数据库 schema 的改动：现有测试全套通过（`--ignore=tests/test_domain_registry.py`）
- schema 变更（Group E4）：需要数据库环境运行完整测试

**各 Group 测试类名汇总：**

| Group | 测试文件 | 测试类名 | 关键边界测试 |
|-------|----------|----------|-------------|
| A1 | `tests/test_mcp_server.py` | `NegationPatternTests` | 否定词不在紧前 2 字时命中 |
| A2 | `tests/test_mcp_server.py` | `PhraseStopwordTests` | 停用词不计分 |
| A3 | `tests/test_capture_strategy.py` | `WorkingMemoryPromotionTests` | 不满足条件时不提升 |
| B1 | `tests/test_memory_ops.py` | `MaintainMemoryStoreFilterTests` | 多参数组合过滤 |
| B2 | `tests/test_mcp_server.py` | `TurnCountTests` | N 轮后才触发 sync |
| B3 | `tests/test_memory_ops.py` | `HybridSearchFallbackTests` | 无 embedding 行不丢失 |
| B4 | `tests/test_mcp_server.py` | `RecallWeightConfigTests` | env 覆盖生效 |
| C1 | `tests/test_memory_ops.py` | `MergeDuplicateMemoriesTests` | dry_run 不写 DB |
| C2 | `tests/test_memory_ops.py` | `StaleMemoryChallengeTests` | 模板各分支 |
| C3 | `tests/test_context_snapshots.py` | `GlobalTopicAntiInflationTests` | 多轮调用前缀不叠加 |
| D1 | `tests/test_memory_ops.py` | `MemoryTimelineTests` | 循环引用防护 |
| D2 | `tests/test_memory_ops.py` | `FetchSourceTurnsTests` | 格式解析、模糊降级 |
| D3 | `tests/test_memory_ops.py` | `ExportMemoriesTests` | `internal_only` 强制排除、NULL disclosure_policy 不排除 |
| D4 | `tests/test_memory_ops.py` | `MemoryReportTests` | 空库返回零值 |
| E1 | `tests/test_capture_strategy.py` | `BatchIngestPairingTests` | 连续 user/assistant、末尾孤立 |
| E2 | `tests/test_entity_graph.py` | `InferEdgeRelationTypeTests` | 优先级顺序 |
| E3 | `tests/test_entity_graph.py` | `TwoHopConnectionTests` | 空输入、批量单次查询 |
| E4 | `tests/test_mcp_server.py` | `SentimentFilterTests` | 无效值降级为 `neutral` |

所有新增 MCP 工具需在 `tests/test_mcp_server.py` 的 `test_registers_expected_tools` 里更新工具集合列表（新增：`merge_duplicate_memories`、`get_stale_memories_for_challenge`、`get_memory_timeline`、`export_memories`、`generate_memory_report`、`batch_ingest_turns`）。

---

## 执行顺序与隔离

- Group A–D：纯代码改动，无 schema 变更，可在任何环境直接运行
- Group E：需要数据库环境（`018_sentiment.sql`），建议在开发库上先验证 migration
- 每个 Group 完成后独立 commit，便于回滚
