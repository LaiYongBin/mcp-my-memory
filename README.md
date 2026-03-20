# skill-my-memory

个人长期记忆技能，支持：

- PostgreSQL 持久化
- pgvector 向量检索
- 显式长期记忆
- 自动候选提取
- 多轮证据累积后再升级推断型记忆
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
source ./.env.memory.example  # 先填好再 source，或写进 ~/.zshrc
./install.sh
```

这一步会自动完成：

- 创建 `skills/personal-memory/.venv`
- 安装 Python 依赖
- 连接 PostgreSQL 执行建表和索引 SQL
- 检查 `pgvector`
- 启动本地 memory 服务并做一次 health check
- 后续对话可以通过槽位化分析自动做冲突解析、证据累积和更新

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
python3 scripts/bootstrap.py --print-env-template
```

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
export LYB_SKILL_MEMORY_EMBED_API_KEY=
export LYB_SKILL_MEMORY_EMBED_BASE_URL=https://dashscope.aliyuncs.com/api/v1
export LYB_SKILL_MEMORY_EMBED_MODEL=text-embedding-v4
export LYB_SKILL_MEMORY_EMBED_DIM=1536
```

如果只想先跑数据库记忆，不启用语义检索，可以暂时不配 `LYB_SKILL_MEMORY_EMBED_API_KEY`。

## 常用命令

```bash
cd ~/.claude/skills/personal-memory
# 或
cd ~/.codex/skills/personal-memory
. .venv/bin/activate

python3 scripts/ensure_service.py
python3 scripts/bootstrap.py
python3 scripts/memory_capture_cycle.py --async-mode --session-key default --user-text "我是一个很感性的人" --assistant-text "我记下来了。"
python3 scripts/memory_capture_cycle.py --async-mode --session-key default --user-text "这周先优先排查支付模块的超时问题" --assistant-text "收到，我会先围绕支付超时排查。"
python3 scripts/memory_analysis_results.py --session-key default
python3 scripts/memory_evidence.py --limit 20
python3 scripts/memory_consolidate.py --list-only --session-key default
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
- 服务没起来
  先看 `/tmp/my_skillproject-memory-service.log`
- embedding 没生效
  先检查 `LYB_SKILL_MEMORY_EMBED_API_KEY` 和模型维度是否匹配 `1536`
