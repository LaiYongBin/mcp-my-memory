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
2. Prefer the local service endpoints over Python CLI scripts.
3. When the service is healthy, call it with `curl` first to reduce Python process startup cost.
4. Do not extract long-term memory on every turn.
5. Only when the user explicitly invokes this skill for memory work, sync the relevant current-session transcript and then extract memory if needed.
6. Store session context snapshots separately from durable personal memory.
7. Merge same-topic summaries across sessions into a higher-level `global_topic` snapshot.
8. Only if the service cannot be reached, fall back to the direct scripts in `scripts/`.

## Response Style

- When the user asks a direct memory question such as "你知道我最喜欢的饮料是什么吗", answer the memory result directly first.
- Memory reads and writes are hidden operations by default.
- Do not narrate the lookup or write process unless the user explicitly asks what you are doing, or the lookup fails.
- Prefer one short answer sentence for successful lookups.
- Add nuance only if the stored memory is ambiguous or only approximately matches the question.
- When the user is simply talking, respond like a normal conversation partner. Do not say things like "我来记录一下" or "我先查一下" unless the user explicitly asks about the memory mechanism.
- User-facing replies must be determined by conversational intent, not by the memory workflow.
- Do not let memory operations shape the visible answer.

## Hidden Memory Behavior

- Long-term memory extraction is no longer a default every-turn action.
- Current conversation context already lives in the active model context, so it does not need to be persisted immediately on every turn.
- When the user explicitly invokes this skill, do two separate things:
  1. sync the relevant conversation transcript into context snapshots
  2. extract durable memory only if the current request is really about memory
- Do not transform normal conversation into operational narration.
- Do not turn the reply into a demonstration of the skill.
- The assistant should focus on what the user is talking about, not on how memory is stored.
- Bad style:
  - `我用 personal-memory 记录你的偏好。`
  - `我先查一下是否已经有这条记忆。`
  - `我现在把它补成一条明确的偏好记忆。`
- Correct principle:
  - If the user is chatting, reply as chat.
  - If the user is asking for advice, reply with advice.
  - If the user is asking a memory question, answer the memory result directly.
  - In all of those cases, memory capture stays in the background unless explicitly requested.
- Only surface the memory action when the user explicitly asks you to remember, forget, update, or explain what you stored.

## Automatic Capture

- For explicit phrases such as `记住` and `不要忘了`, persist directly as stronger long-term memory.
- Do not auto-extract long-term memory from every ordinary turn.
- Stable facts and preferences should be extracted from the current session only when this skill is explicitly invoked.
- Inferred traits, roles, and personality signals should still accumulate as evidence before promotion.
- Store context snapshots for small discussion segments and larger topic summaries, so later questions such as `你上次说 xxx` can be traced back to the original discussion context.
- Also maintain a cross-session `global_topic` summary for the same topic across multiple days or conversations.
- Sensitive or ambiguous content should go to review automatically.
- Durable memory should be slot-based whenever possible, for example `user.favorite_drink = 黑咖啡`.
- Conflict detection should be based on slot identity, not raw-text similarity.
- Use `scripts/context_sync.py` to sync a session transcript into segment/topic summaries.
- Use memory extraction only as an explicit follow-up action during memory work.
- `scripts/memory_capture.py` remains available for one-off sentence extraction.

## Safety Rules

- Explicit phrases such as "记住" and "不要忘了" should promote content into stronger long-term memory.
- Automatic memory capture is allowed for clear low-risk facts and task context, but inferred personal facts should use lower confidence.
- Do not physically delete by default. Use archive or logical delete.
- Always scope reads and writes by `LYB_SKILL_MEMORY_USER`.

## Core Commands

```bash
python3 scripts/ensure_service.py
curl -s http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8787/memory/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"最喜欢的饮料","limit":5}'
curl -s http://127.0.0.1:8787/context/sync \
  -H 'Content-Type: application/json' \
  -d '{"session_key":"life-talk-2026-03-19","topic_hint":"人生观讨论","turns":[{"role":"user","content":"我现在越来越认同戈尔泰的人生观。"},{"role":"assistant","content":"你更认同的是哪一部分？"}],"extract_memory":true}'
curl -s http://127.0.0.1:8787/context/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"戈尔泰 人生观","snapshot_level":"topic","limit":5}'
curl -s http://127.0.0.1:8787/context/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"戈尔泰 人生观","snapshot_level":"global_topic","limit":5}'
python3 scripts/context_sync.py --session-key life-talk-2026-03-19 --topic-hint "人生观讨论" --turn "user:我现在越来越认同戈尔泰的人生观。" --turn "assistant:你更认同的是哪一部分？" --extract-memory
python3 scripts/context_search.py --query "戈尔泰 人生观" --snapshot-level topic --limit 5
python3 scripts/context_search.py --query "戈尔泰 人生观" --snapshot-level global_topic --limit 5
python3 scripts/memory_analysis_results.py --session-key default
python3 scripts/memory_evidence.py --limit 20
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
