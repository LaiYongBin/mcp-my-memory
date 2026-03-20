# skill-my-memory

个人长期记忆技能，支持：

- PostgreSQL 持久化
- pgvector 向量检索
- 显式长期记忆
- 自动候选提取
- review 候选审批/拒绝

## 安装

```bash
# 第一步：添加 marketplace（已添加过可跳过）
/plugin marketplace add LaiYongBin/skills-chinese-marketplace

# 第二步：安装插件
/plugin install skill-my-memory@skills-chinese-marketplace
```

## Codex 安装

Codex 当前没有 Claude marketplace 这一层，建议直接把 skill 链接到 `~/.codex/skills`：

```bash
mkdir -p ~/.codex/skills
ln -s ~/Desktop/skill-my-memory-plugin/skills/personal-memory ~/.codex/skills/personal-memory
```

## 安装后初始化

插件安装后，`skills/personal-memory/` 下会带上服务代码、脚本、SQL 和依赖清单。

在 Claude 或 Codex 安装目录对应的 skill 路径下执行：

```bash
cd ~/.claude/skills/personal-memory
# 或
cd ~/.codex/skills/personal-memory

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

psql -h "$LYB_SKILL_PG_ADDRESS" -p "$LYB_SKILL_PG_PORT" -U "$LYB_SKILL_PG_USERNAME" -d "$LYB_SKILL_PG_MY_PERSONAL_DATABASE" -f sql/001_schema.sql
psql -h "$LYB_SKILL_PG_ADDRESS" -p "$LYB_SKILL_PG_PORT" -U "$LYB_SKILL_PG_USERNAME" -d "$LYB_SKILL_PG_MY_PERSONAL_DATABASE" -f sql/002_indexes.sql
psql -h "$LYB_SKILL_PG_ADDRESS" -p "$LYB_SKILL_PG_PORT" -U "$LYB_SKILL_PG_USERNAME" -d "$LYB_SKILL_PG_MY_PERSONAL_DATABASE" -f sql/003_pgvector_upgrade.sql
psql -h "$LYB_SKILL_PG_ADDRESS" -p "$LYB_SKILL_PG_PORT" -U "$LYB_SKILL_PG_USERNAME" -d "$LYB_SKILL_PG_MY_PERSONAL_DATABASE" -f sql/004_review_candidates.sql
```

## 常用命令

```bash
cd ~/.claude/skills/personal-memory
# 或
cd ~/.codex/skills/personal-memory
. .venv/bin/activate

python3 scripts/ensure_service.py
python3 scripts/memory_capture.py --text "我喜欢黑咖啡"
python3 scripts/memory_capture.py --text "记住我对象喜欢花" --auto-persist
python3 scripts/review_candidates.py --limit 20
python3 scripts/review_action.py --id 1 --action approve
python3 scripts/memory_query.py --query "黑咖啡"
```

## 所需环境变量

```bash
export LYB_SKILL_PG_ADDRESS=
export LYB_SKILL_PG_PORT=5432
export LYB_SKILL_PG_USERNAME=
export LYB_SKILL_PG_PASSWORD=
export LYB_SKILL_PG_MY_PERSONAL_DATABASE=
export LYB_SKILL_MEMORY_USER=LYB

export LYB_SKILL_MEMORY_EMBED_API_KEY=
export LYB_SKILL_MEMORY_EMBED_BASE_URL=https://dashscope.aliyuncs.com/api/v1
export LYB_SKILL_MEMORY_EMBED_MODEL=text-embedding-v4
export LYB_SKILL_MEMORY_EMBED_DIM=1536
```
