---
name: "xu-wiki"
description: "Manage a relation-driven wiki via 5 SOPs. Deterministic CLI, no LLM calls."
---

# xu-wiki

> **Important:** All wiki operations must be invoked via CLI (`xu ...`) in a shell terminal. Do NOT use `execute_code`, `run_python`, or any sandboxed Python tool — those environments do not inherit the host's `PATH` (including `~/.local/bin` where pipx installs live). Environment variables (e.g., `MINERU_API_KEY`) can be passed through the shell command prefix.

Relation-driven wiki for AI agents. All content is `.md` files on disk — no
DB, no lock, git-friendly.

## 核心概念

**Wiki 是节点的集合，每节点是一个 `.md` 文件。**

| 类型 | 存储位置 | 说明 |
|---|---|---|
| Page | `nodes/pages/` | 原始知识切片，immutable，SHA256 去重 |
| List | `nodes/lists/` | 对 Page 的比较 / 聚合，frontmatter 含成员 UID |
| Report | `nodes/reports/` | 推理 + 结论，必须附 ≥1 证据 Page |
| Entity | `nodes/entities/` | 实体描述符，一等公民节点 |

**关系**：每个节点有最多 50 条出边（LRU），`query-relation` 管理。

**CLI 设计原则**：
- 全离线，不调用 LLM
- 每次调用返回 `{status, data, message, hints}` — `hints` 是 **post-mortem 信号**，不是 pre-flight 提示
- 你（Agent）是 `xu` 的唯一调用者，用户不直接操作 CLI

**`hints` 字段语义**：hints 在命令**完成后**告诉你"刚才的命令留了什么尾巴"。常见模式：
- 命令成功 + 创建了节点 → hints 可能说"新节点未挂 entity 链"（参见 `/xu-wiki wire`）
- 命令成功 + 节点建在根目录 → hints 说"考虑下个 commit 传 --node-path"
- 命令失败 → hints 告诉你是去查哪个 doctor 子命令

**`hints` 不是"future suggestion"**——是"**past action 的 deferred work**"。读 hints 时把它当成 todo list，而不是 advisory。

## 哲学

**分离关注点**：语义判断（哪些关键词、要不要创建 List）由 Agent 负责；存储和检索由 xu 负责。

**节点不可变**：Page 写入后不修改内容；增量通过 frontmatter 中的 `patches` 字段实现（`{op, delta, created_at}` 列表）。Report 必须有证据链，防止空对空推理。

**不对称创建偏好**：ingest 后倾向于扩展 List，query 后倾向于生成 Report。Agent 自主决定，不需用户确认。创建前先 query 是否已有相似的，有则扩展，无则新建。

**Hard rule：SOP 内部决策不向用户确认。** Reflection → create → wire 是原子循环，用户只看最终结果。

## SOP 入口

6 个 SOP，覆盖 wiki 内容操作和生命周期管理：

| 命令 | 职责 | 详情 |
|---|---|---|
| `/xu-wiki lifecycle` | wiki 创建/注册/注销 + 程序更新/卸载 | `lifecycle.md` |
| `/xu-wiki config` | 别名 / 注册表 / MinerU key | `config.md` |
| `/xu-wiki ingest` | 导入内容（PDF/DOCX/图片/相册） | `ingest.md` |
| `/xu-wiki query` | 搜索 + 多轮展开 + 反射 | `query.md` |
| `/xu-wiki wire` | ingest/query 后的 relation 挂链反射（Entity/List/Report） | （见 ingest.md "Reflection triggers" 段） |
| `/xu-wiki doctor` | 一致性检查 / 修复 / 重建 | `doctor.md` |

每个 SOP 的详细步骤、flag 说明、常见陷阱均在对应的 `references/*.md` 中。

**SOP 调用纪律**：
- `/xu-wiki wire` 不是独立子命令——它是 ingest/query 末尾的反射动作（`xu query-relation add` / `xu list modify` / `xu report modify`），不是单独跑的命令
- ingest 流程结尾**必须**做一次 `xu query --keywords "<新节点主题>"` 找已有 Entity，再决定是否挂 describes 链
- 任何 ingest session 结束前跑 `xu doctor-node-path-organization` 做"未分类节点"体检
