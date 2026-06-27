---
name: "xu-wiki"
description: "Manage a relation-driven wiki via 5 SOPs. Deterministic CLI, no LLM calls."
---

# xu-wiki

Relation-driven wiki for AI agents. All content is `.md` files on disk — no
DB, no lock, git-friendly.

## 核心概念

**Wiki 是节点的集合，每节点是一个 `.md` 文件。**

| 类型 | 存储位置 | 说明 |
|---|---|---|
| Page | `nodes/page/` | 原始知识切片，immutable，SHA256 去重 |
| List | `nodes/list/` | 对 Page 的比较 / 聚合，frontmatter 含成员 UID |
| Report | `nodes/report/` | 推理 + 结论，必须附 ≥1 证据 Page |
| Entity | `nodes/entity/` | 实体描述符，一等公民节点 |

**关系**：每个节点有最多 50 条出边（LRU），`query-relation` 管理。

**CLI 设计原则**：
- 全离线，不调用 LLM
- 每次调用返回 `{status, data, message, hints}` — `hints` 供 Agent 后续步骤参考，不是给用户看的
- 你（Agent）是 `xu` 的唯一调用者，用户不直接操作 CLI

## 哲学

**分离关注点**：语义判断（哪些关键词、要不要创建 List）由 Agent 负责；存储和检索由 xu 负责。

**节点不可变**：Page 写入后不修改内容；增量通过 frontmatter 中的 `patches` 字段实现（`{op, delta, created_at}` 列表）。Report 必须有证据链，防止空对空推理。

**不对称创建偏好**：ingest 后倾向于扩展 List，query 后倾向于生成 Report。Agent 自主决定，不需用户确认。创建前先 query 是否已有相似的，有则扩展，无则新建。

## SOP 入口

| 命令 | 职责 | 详情 |
|---|---|---|
| `/xu-wiki create` | 创建空 wiki | `create.md` |
| `/xu-wiki ingest` | 导入内容（PDF/DOCX/图片/相册） | `ingest.md` |
| `/xu-wiki query` | 搜索 + 多轮展开 + 反射 | `query.md` |
| `/xu-wiki doctor` | 一致性检查 / 修复 / 重建 | `doctor.md` |
| `/xu-wiki config` | 别名 / 注册表 / 卸载 | `config.md` |

每个 SOP 的详细步骤、flag 说明、常见陷阱均在对应的 `references/*.md` 中。
