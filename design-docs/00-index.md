# 设计原则文档 — 索引

> 面向开发者的设计原则参考。原则标 `PRIN-{doc-id}-N` / `BAN-{doc-id}-N` / `CONST-{doc-id}-N` / `DESIGN-{doc-id}-N` / `BUG-{doc-id}-N`。

## 文档清单

| # | 模块 | 核心问题 |
|---|---|
| 01 | [01-wiki-architecture.md](01-wiki-architecture.md) | 两层节点架构 + 50 条关系 |
| 06 | [06-query.md](06-query.md) | 两层介入检索 |
| 07 | [07-doctor.md](07-doctor.md) | 两层节点不变量检查 |
| 08 | [08-sop-architecture.md](08-sop-architecture.md) | 意图→CLI 编排 |
| 09 | [09-skill-architecture.md](09-skill-architecture.md) | Agent skill 文档架构 |

## 核心架构

> **面向 AI Agent 的关系驱动型 wiki 引擎**——Page（知识层/藏书）+ Entity/List/Report（学习层/笔记）。

## 两层节点

| 层 | 职责 | 可变性 |
|---|---|---|
| **Page** | 物理事实切片（知识层/藏书） | 不可变（修订走 patches） |
| **Entity/List/Report** | 逻辑聚合/对比/推理（学习层/笔记） | 可改、可重建 |

Page 不生产原始事实之外的评价；学习层不生产原始事实（由 Page 提供）。

## 50 条关系上限

LRU 链表：建立进队首 → 命中前挪 → 满 50 弹队尾。无分类、无打分。要固化走 List。

## 4 键 JSON 协议

`{status, data, message, hints}`

## 跨文档核心原则（摘要）

1. **图书馆哲学** — 收集但不写书
2. **Page 不可变** — 修订走 patches 表
3. **Agent 不直写文件** — 所有写走 CLI
4. **CLI 不调 LLM** — 确定性到底
5. **歧义即停** — 宁可问不要猜
6. **50 条关系上限** — LRU 置换
7. **uninstall 不动知识库**
8. **doctor 默认只读**
9. **SKILL.md 自给自足** — 重复胜于污染

详情见各模块文档。

## 实现里程碑

| 阶段 | 内容 |
|---|---|
| M1 | install + create（能装能建空库） |
| M2 | ingest + query + read（Page 闭环）⭐ |
| M3 | query-relation（50 LRU） |
| M4 | list + report（List/Report） |
| M5 | doctor + delete-node + rebuild + uninstall |

**顺序铁律**：M2 之前不碰 List/Report。
