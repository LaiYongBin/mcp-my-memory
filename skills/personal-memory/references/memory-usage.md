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

## Candidate Extraction

Current version uses heuristics instead of model inference.

Auto-persist immediately:

- `记住...`
- `不要忘了...`

Auto-persist by default when low risk:

- `我喜欢...`
- `我不喜欢...`
- `以后请...`
- `默认用...`

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

## Vector Retrieval

The system now distinguishes:

- `search_vector`: PostgreSQL full-text index for lexical search
- `memory_embedding.embedding`: pgvector column for semantic retrieval

Hybrid retrieval should prefer:

1. explicit long-term memories
2. lexical rank
3. vector similarity
