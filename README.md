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

## 一键初始化

如果是从 Git 仓库直接使用，推荐在仓库根目录执行：

```bash
cd ~/path/to/skill-my-memory-plugin
./install.sh
```

这一步会自动完成：

- 创建 `skills/personal-memory/.venv`
- 安装 Python 依赖
- 连接 PostgreSQL 执行建表和索引 SQL
- 检查 `pgvector`
- 启动本地 memory 服务并做一次 health check

如果你已经装到了 Claude/Codex 的 skill 目录里，也可以直接在 skill 目录执行：

```bash
cd ~/.claude/skills/personal-memory
# 或
cd ~/.codex/skills/personal-memory

python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 scripts/bootstrap.py
```

## Codex 安装

Codex 当前没有 Claude marketplace 这一层，建议直接把 skill 链接到 `~/.codex/skills`：

```bash
mkdir -p ~/.codex/skills
ln -s ~/Desktop/skill-my-memory-plugin/skills/personal-memory ~/.codex/skills/personal-memory
```

`bootstrap.py` 也支持附加参数：

```bash
python3 scripts/bootstrap.py --backfill-embeddings
python3 scripts/bootstrap.py --skip-service
python3 scripts/bootstrap.py --skip-db
```

## 常用命令

```bash
cd ~/.claude/skills/personal-memory
# 或
cd ~/.codex/skills/personal-memory
. .venv/bin/activate

python3 scripts/ensure_service.py
python3 scripts/bootstrap.py
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
