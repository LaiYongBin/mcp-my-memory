# Memory Usage

## Memory Types

- `fact`: stable personal facts
- `preference`: likes, dislikes, habits
- `rule`: instructions about how to collaborate
- `relationship`: facts about close people
- `project`: longer-lived project context
- `context`: short-lived but important context

## Explicit Promotion

When the user says phrases like:

- 记住
- 不要忘了
- 以后都按这个来

Store the content with:

- `is_explicit = true`
- higher confidence
- higher importance

## Automatic Capture

Safe candidates:

- clearly stated user preferences
- repeated collaboration rules
- stable personal metadata

Unsafe candidates:

- emotional inference
- health judgments
- relationship inference without explicit statement
- ambiguous interpretation

Use lower confidence for unsafe candidates and prefer confirmation.

Current preferred runtime:

- run `scripts/ensure_service.py` first
- prefer MCP tools from the local memory server
- use Python CLI scripts for maintenance or fallback debugging
- do not treat every normal turn as a memory-extraction event
- when the user explicitly invokes memory work, sync the relevant transcript into `conversation_event`
- create a segment-level context snapshot for the current discussion chunk
- merge segment snapshots into a larger topic-level snapshot
- merge same-topic summaries across sessions into a `global_topic` snapshot
- only then, if the request is really about memory extraction, persist a structured `memory_analysis_result` and decide what durable memory to write
- represent durable memory as slots such as `subject + attribute + value`
- resolve conflicts by slot, not by raw text
- persist long-term memory automatically when confidence is high
- accumulate repeated observed or inferred evidence before promoting role, personality, or profile conclusions
- preserve both raw conversation events and higher-level summaries, so later questions can trace back from topic summary to concrete discussion context
- for long transcripts, context sync and analyzer timeouts should be configurable instead of fixed

User-facing behavior:

- memory should usually be invisible to the user
- the assistant should reply to the conversational meaning first, not narrate internal storage steps
- the assistant should not say it is querying or writing memory unless the user explicitly asks
- the assistant may proactively recall relevant memory during ordinary conversation when it materially improves relevance or personalization
- normal statements like `我最喜欢的运动是自行车` should be treated as conversation plus silent background memory capture
- explicit requests like `记住这个` are the main case where acknowledging the memory action is appropriate
- the visible reply should be driven by conversational intent, not by the fact that memory capture is happening
- memory is a hidden side effect of the conversation, not the subject of the response

Recommended context layers:

- `conversation_event`
  raw turns for traceability
- `conversation_context_snapshot` with `snapshot_level=segment`
  one smaller discussion chunk summary
- `conversation_context_snapshot` with `snapshot_level=topic`
  one larger topic-level summary built from segment summaries
- `conversation_context_snapshot` with `snapshot_level=global_topic`
  one cross-session topic summary built from multiple topic snapshots
- `memory_item`
  only stable personal memory, not all conversation history

Conflict examples:

- `user.favorite_drink = 黑咖啡`
- `user.favorite_food = 白菜`
  These coexist because they are different slots.

- `user.favorite_drink = 黑咖啡`
- `user.favorite_drink = 奶茶`
  These conflict because they are the same slot, so the newer one should usually replace the older one.

## Candidate Extraction

Current version prefers model-based structured analysis and falls back to generic structural heuristics when the analyzer is unavailable.

Auto-persist immediately:

- `记住...`
- `不要忘了...`

Auto-persist by default when low risk:

- `我喜欢...`
- `我不喜欢...`
- `以后请...`
- `默认用...`
- `我是一个...的人`
- `我是个...的人`
- `我很...`

Do not auto-persist when content looks sensitive or ambiguous. Keep those as reviewable candidates.

Examples:

- `我对象是不是不爱我了`
- `我最近是不是抑郁了`
- `他是不是讨厌我`

Review actions:

- approve: promote candidate into formal memory and mark candidate approved
- reject: mark candidate rejected without promoting

Extract as candidates first:

- `我喜欢...`
- `我不喜欢...`
- `我习惯...`
- `以后请...`
- `默认用...`
- `我是一个...的人`
- `我是个...的人`
- `我很...`

Working-memory oriented examples:

- `这周先优先排查支付模块的超时问题`
- `当前先别动数据库迁移`
- `最近先按中文输出`

## Vector Retrieval

The system now distinguishes:

- `search_vector`: PostgreSQL full-text index for lexical search
- `memory_embedding.embedding`: pgvector column for semantic retrieval

Hybrid retrieval should prefer:

1. lexical rank and vector similarity
2. explicitness as a small bonus
3. importance and confidence as smaller bonuses
