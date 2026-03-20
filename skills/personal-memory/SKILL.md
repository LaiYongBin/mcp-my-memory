---
name: personal-memory
description: 管理个人长期记忆与上下文记忆。当用户要求记住某件事、不要忘记某件事、查询过去提过的信息、更新个人偏好或维护多用户隔离的记忆数据时使用。
---

# Personal Memory

## Overview

Use this skill to manage durable personal memory in PostgreSQL.

This skill is self-contained. The service code, scripts, SQL, and references live inside the installed `personal-memory` skill directory. If the local FastAPI service is not running, start it automatically. If it still cannot run, fall back to the Python scripts that talk to PostgreSQL directly.

## Trigger Cases

- "记住 xxx"
- "不要忘了 xxx"
- "我之前提过的 xxx 是什么"
- "更新我的偏好/状态/规则"
- "查一下我对象的 xxx"

## Runtime Order

1. Run `scripts/ensure_service.py`.
2. For direct lookup, use the service endpoints.
3. At the end of each user turn, call `scripts/memory_capture_cycle.py` with the user message and the final assistant answer.
4. If startup fails, use the direct scripts in `scripts/`.
5. Prefer `--async-mode` in normal chat flows so memory analysis does not block the user-facing reply.

## Response Style

- When the user asks a direct memory question such as "你知道我最喜欢的饮料是什么吗", answer the memory result directly first.
- Do not narrate the lookup process unless the user explicitly asks what you are doing, or the lookup fails.
- Prefer one short answer sentence for successful lookups.
- Add nuance only if the stored memory is ambiguous or only approximately matches the question.

## Automatic Capture

- For explicit phrases such as `记住` and `不要忘了`, persist directly as stronger long-term memory.
- For each turn, capture memory from the whole turn instead of waiting for a fixed trigger phrase.
- Stable facts and preferences should become long-term memory automatically.
- Inferred traits, roles, and personality signals should first accumulate as evidence across turns before promotion.
- time-scoped project context should go to `working_memory` automatically.
- Sensitive or ambiguous content should go to review automatically.
- Durable memory should be slot-based whenever possible, for example `user.favorite_drink = 黑咖啡`.
- Conflict detection should be based on slot identity, not raw-text similarity.
- Use `scripts/memory_capture_cycle.py` as the default path.
- `scripts/memory_capture.py` remains available for one-off sentence extraction.

## Safety Rules

- Explicit phrases such as "记住" and "不要忘了" should promote content into stronger long-term memory.
- Automatic memory capture is allowed for clear low-risk facts and task context, but inferred personal facts should use lower confidence.
- Do not physically delete by default. Use archive or logical delete.
- Always scope reads and writes by `LYB_SKILL_MEMORY_USER`.

## Core Commands

```bash
python3 scripts/ensure_service.py
python3 scripts/memory_capture_cycle.py --async-mode --session-key default --user-text "我是一个很感性的人" --assistant-text "我记下来了。"
python3 scripts/memory_capture_cycle.py --async-mode --session-key default --user-text "这周先优先排查支付模块的超时问题" --assistant-text "收到，我会先围绕支付超时排查。"
python3 scripts/memory_analysis_results.py --session-key default
python3 scripts/memory_evidence.py --limit 20
python3 scripts/memory_consolidate.py
python3 scripts/memory_consolidate.py --list-only --session-key default
python3 scripts/memory_query.py --query "最近喜欢什么"
python3 scripts/memory_upsert.py --promote --explicit --memory-type preference --content "我喜欢黑咖啡"
python3 scripts/memory_capture.py --text "我喜欢黑咖啡"
python3 scripts/memory_capture.py --text "记住我对象喜欢花" --auto-persist
python3 scripts/review_candidates.py --limit 20
python3 scripts/review_action.py --id 1 --action approve
python3 scripts/review_action.py --id 1 --action reject
python3 scripts/memory_delete.py --id 123 --archive
```

## Environment Variables

- `LYB_SKILL_PG_ADDRESS`
- `LYB_SKILL_PG_PORT`
- `LYB_SKILL_PG_USERNAME`
- `LYB_SKILL_PG_PASSWORD`
- `LYB_SKILL_PG_MY_PERSONAL_DATABASE`
- `LYB_SKILL_MEMORY_USER`
- `LYB_SKILL_MEMORY_EMBED_API_KEY` (optional)
- `LYB_SKILL_MEMORY_EMBED_BASE_URL` (optional, default `https://dashscope.aliyuncs.com/api/v1`)
- `LYB_SKILL_MEMORY_EMBED_MODEL` (optional, default `text-embedding-v4`)
- `LYB_SKILL_MEMORY_EMBED_DIM` (optional, default `1536`)

## References

Read `references/memory-usage.md` for the data model and trigger policy.
