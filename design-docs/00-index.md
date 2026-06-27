# 设计原则文档 — 索引

> 面向开发者的设计原则参考。原则标 `PRIN-{doc-id}-N` / `BAN-{doc-id}-N` / `CONST-{doc-id}-N` / `DESIGN-{doc-id}-N` / `BUG-{doc-id}-N`。

## 文档清单

| # | 模块 | 核心问题 |
|---|---|
| 01 | [01-wiki-architecture.md](01-wiki-architecture.md) | 三层架构 + 50 条关系 |
| 02 | [02-create.md](02-create.md) | 建空库骨架 |
| 03 | [03-install.md](03-install.md) | 装能力不装数据 |
| 04 | [04-uninstall.md](04-uninstall.md) | 卸载软件不动知识 |
| 05 | [05-ingest.md](05-ingest.md) | L1 不可变 + 两阶段入库 |
| 06 | [06-query.md](06-query.md) | 三层介入检索 |
| 07 | [07-doctor.md](07-doctor.md) | 三层不变量检查 |
| 08 | [08-sop-architecture.md](08-sop-architecture.md) | 意图→CLI 编排 |
| 09 | [09-skill-architecture.md](09-skill-architecture.md) | Agent skill 文档架构 |

## 核心架构

> **面向 AI Agent 的关系驱动型三层 wiki 引擎**——图书管理员管理知识，不写书。

## 三层节点

| 层 | 职责 | 可变性 |
|---|---|---|
| **L1 Page** | 物理事实切片 | 不可变（修订走 patches） |
| **L2 List** | 横向聚合 | 可改 |
| **L3 Report** | 逻辑推演 | 可改、可重建 |

L1 不评价，L2 不推演，L3 不生产原始事实。

## 50 条关系上限

LRU 链表：建立进队首 → 命中前挪 → 满 50 弹队尾。无分类、无打分。要固化走 L2。

## 4 键 JSON 协议

`{status, data, message, hints}`

## 跨文档核心原则（摘要）

1. **图书馆哲学** — 收集但不写书
2. **L1 不可变** — 修订走 patches 表
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
| M2 | ingest + query + read（L1 闭环）⭐ |
| M3 | query-relation（50 LRU） |
| M4 | list + report（L2/L3） |
| M5 | doctor + delete-node + rebuild + uninstall |

**顺序铁律**：M2 之前不碰 L2/L3。
