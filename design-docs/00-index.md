# 设计原则文档 — 索引

> **目的**：本文档集是面向开发者的「设计原则」参考，用于实现一个**关系驱动型三层架构**wiki 引擎。
> **风格**：每条原则标 `PRIN-{doc-id}-N`（原则）/ `BAN-{doc-id}-N`（禁令）/ `CONST-{doc-id}-N`（约束）/ `DESIGN-{doc-id}-N`（设计取舍）/ `BUG-{doc-id}-N`（已知 bug）。
> **覆盖范围**：8 份文档（00 索引 + 01-08 模块）对应系统的核心模块。

---

## 文档清单

| # | 文件 | 模块 | 核心问题 |
|---|---|---|---|
| 01 | [01-wiki-architecture.md](01-wiki-architecture.md) | 三层架构（Page/List/Report + 50 条关系） | 三层各做什么？关系如何不爆炸？ |
| 02 | [02-create.md](02-create.md) | create | 如何为三层节点 + 弹性 Rebuild 铺路？ |
| 03 | [03-install.md](03-install.md) | install | 装的是能力还是数据？怎么不污染系统？ |
| 04 | [04-uninstall.md](04-uninstall.md) | uninstall | 卸载软件还是卸载数据？ |
| 05 | [05-ingest.md](05-ingest.md) | ingest | L1 不可变怎么实现？IDF/patches 何时入库？ |
| 06 | [06-query.md](06-query.md) | query | 三层介入怎么打分？Fast Pass 怎么动态？ |
| 07 | [07-doctor.md](07-doctor.md) | doctor | 三层不变量 + 50 条上限 + L1 不可变怎么检？ |
| 08 | [08-sop-architecture.md](08-sop-architecture.md) | **SOP 层**（create / ingest / query / doctor / config） | 用户/Agent 层意图动词如何映射到 CLI 子命令？slash command 为什么不是 CLI 子命令别名？ |

---

## 核心架构（一句话）

> **面向 AI Agent 的关系驱动型三层架构 wiki 引擎**——让 Agent 像图书管理员一样管理知识（**收集但不写**），通过「底层确定性（L1 不可变）+ 上层灵活性（L3 Report）」的架构闭环，实现知识的高熵减。

---

## 三层节点架构

| 层 | 名称 | 职责 | 可变性 | 命令 |
|---|---|---|---|---|
| **L1** | **Node_Page** | 物理事实切片、原文留痕 | **不可变**（修订走 patches 表） | `ingest-commit` |
| **L2** | **Node_List** | 横向聚合、对比表格 | 可改 | `list create` |
| **L3** | **Node_Report** | 逻辑推演、因果总结 | 可改、可重建 | `report create` |

**职责分离**：
- L1 不评价、不对比、不推演
- L2 只对比不评价
- L3 承载所有 LLM 推理，**必须有证据链**

---

## 命令名映射（动作 → 命令）

> **命令的具体名称由实现决定**，但**同一个动作必须自始至终用同一个命令名**——本表统一「概念动作 → 命令」的语义映射，消除歧义。下列名称为**推荐基准**；实现若改名，须全局一致，且本文档其他章节出现的命令名以本表语义为准。

| 概念动作 | 推荐命令 | 作用层 | 备注 |
|---|---|---|---|
| 建 Node_Page | `ingest-commit` | L1 | 唯一写盘入口（[PRIN-ING-1]）；L1 不可变 |
| 建相册 L1 | `ingest-album` | L1 | 单次写入多张图 → 1 个 L1（[PRIN-ING-13] 表格形态 / [PRIN-ING-14] 单次原则） |
| 写代码块 L1 | `ingest-commit --native` | L1 | [PRIN-ING-13] 代码块形态 |
| 建 Node_List | `list create` | L2 | **不是** `page create`——`page` 字面属 L1，易误解 |
| 建 Node_Report | `report create` | L3 | 必须引用 L1/L2 证据链 |
| 读单节点全文 | `read --uid` | L1/L2/L3 通用 | 叠加 patches 还原当前视图；三层皆可读 |
| 读 List 对比表 | `list show` | L2 | 横向对比视图 |
| 读 Report 结论 | `report show` | L3 | 推理结论 + 证据链 |
| 检索 | `query` | 三层介入 | L1 物理定位 + L2/L3 hint |
| 改字段 | `revise` | 各层 | 改 metadata；L1 不动 body（走 patches） |
| 建/管关系 | `query-relation add` | 关系层 | 50 条 LRU 上限 |
| 删节点 | `delete-node` | 各层 | 物理删除 + 审计 + 删前查引用 |
| 读 table 行 | `table` | L1（table 形态） | 不走搜索 |
| 读 gallery 项 | `gallery` | L1（gallery 形态） | 不走搜索 |
| DB 元数据查询 | `nodes`（节点）/ `wikis`（库） | — | 只读，不走 ripgrep；勿与建 L2 的 `list` 混淆 |

**关键澄清**：`page` 不作为独立命令名出现——建 Page 走 `ingest-commit`，建 List 走 `list create`。文档历史版本中若有 `page create` 表述，一律指 `list create`（建 L2）。

---

## 50 条关系上限（LRU 排序链表）

每个节点的出边总数上限 **50 条**——不分类、不打分，按「最近被触碰」排序：

| 动作 | 效果 |
|---|---|
| 建立关系 | 视为一次触碰，插入**队首** |
| 查询命中关系 | 该关系**前挪一位** |
| 链表满（默认 50）再来新关系 | 挤掉**队尾**（最久没被触碰的那条） |

**没有强/弱/热点之分，没有评分公式**——被挤掉的关系下次查询命中时会自动重新生成。真正需要长期固化的关联应升级为 **Node_List（L2）**——List 本身就是「把关系固化成一个节点」。

哲学：关系链表是**易失的临时关联记忆**（丢了不心疼）；要固化的关系进 L2。

---

## 检索三阶段

```
L1 物理定位 → L2 结构对齐 → L3 逻辑提炼
```

| 阶段 | 工具 | 关键参数 |
|---|---|---|
| L1 | ripgrep + 弹性切片 | 切片窗口 **软上限 + 硬上限**（软优先寻标点，硬上限兜底）；合并半径 = 紧凑关联阈值（具体数值由实现决定） |
| L1 评分 | 重平衡算法 | `(覆盖分 + 稀有分) × 密度奖励`，**核心词权重远大于扩展词**（防同义词噪音淹没实体），密度奖励 **密度奖励系数（> 1）** |
| L1 稀有分 | IDF 表 | `稀有度权重 = 常量 / (库内频次 + 1)` |
| L1 加速 | Fast Pass | 动态阈值：Top1 显著高于均值 → 自动附 body；**命中数极少时直接附 body**（均值法在低命中下失效，见 [PRIN-QRY-12]） |
| L2/L3 | Agent 决定 | CLI 只返 hint（list_hint / report_hint） |

---

## 跨文档核心原则（14 条）

### 1. 图书馆哲学（[PRIN-ARCH-2]）

> **图书馆收集书，但不写书。**

Node_Page = 书（客观事实）；Node_List = 索引（结构化）；Node_Report = 导读（推理）。SQLite = 借阅记录。

### 2. 三层职责分离（[PRIN-ARCH-1]）

L1 不评价、L2 不推演、L3 不生产事实——**层层只能向上一层推演，不能向下污染**。

### 3. L1 不可变（[PRIN-ARCH-3] / [BAN-ARCH-3]）

Page Markdown 一旦写入**绝不直接修改**。修订通过 SQLite `patches 表` 叠加 patch 还原当前视图。

### 4. Markdown 是 ground truth（[PRIN-ARCH-17]）

DB 是索引层，可重建。Markdown 永远是真相——任何时刻 100% 可重建 SQLite。

### 5. 强 Schema 是质量底线（[PRIN-ARCH-18]）

SQLite 层强约束 关键字段（如标题 / 时间） 等关键字段——Agent 提交字段缺失直接拦截。

### 6. UID 是稳定引用（[PRIN-ARCH-22] / [BAN-ARCH-2]）

跨节点引用**永远用 UID**，永不重用（命名空间足够大）。

### 7. 50 条关系不爆炸（[PRIN-ARCH-7] / [PRIN-ARCH-10]）

每节点出边上限 50——满了按 LRU 排序链表挤掉队尾最久未触碰的关系，不允许无限增长。不分类、不打分；要长期固化的关联升级为 L2 List。

### 8. Agent 不直写文件（[BAN-ARCH-1] / [BAN-ING-1]）

LLM 永远不直写 .md / DB。所有写操作走 CLI。CLI 校验、写盘原子化、维护一致性。

### 9. CLI 不调 LLM（[PRIN-QRY-3] / [BAN-QRY-1]）

CLI 全程确定性。**关键词分级是 LLM 的责任**——CLI 做基础分词（jieba），Agent 做语义分级（实体识别 + 同义词扩展）。

### 10. install 装能力不装数据（[PRIN-INST-1]）

install 装 CLI/venv/SKILL/配置 schema。**不**动用户已有的任何 wiki 实例（含 patches 表 / IDF 表）。

### 11. uninstall 不动 L1 历史（[PRIN-UNINST-1] / [BAN-UNINST-4]）

卸载 = 把 install 装进系统的东西原样拆出来。**永远不动**知识库本体、patches 表、IDF 表。

### 12. doctor 默认只读（[PRIN-DOC-1]）

诊断而非治疗。修复必须显式 `--fix`，且**L1 不可变性绝不让 --fix 覆盖、L3 Report 不自动删**。

### 13. 歧义即停——宁可问，不要猜（[PRIN-SAFETY]）

> **知识库是长期信任资产，一次错误写入的代价远超一次追问。**

跨模块最高安全原则，**正式定义见 01-wiki-architecture.md 的 [PRIN-SAFETY]**。护栏在 **Agent 层**:意图不明确时(尤其在改变状态的命令之前),先问用户,绝不猜默认值或自作主张新建对象。CLI 保持确定性,参数合法就跑——意图判断不是 CLI 的职责。「判断一个值」(如内容归哪个分区)是本职,不算猜意图;「揣测操作意图」(如写错库名就建新库)必须停下来问。

### 14. L1 body 样式与内容类型匹配——内容形态原则（[PRIN-ING-13]）

L1 body 不是「一段 markdown 字符串」——它必须与承载的内容形态对齐。当前三类内容形态,对应三种 body 样式:

| 内容类型 | body 样式 | 典型 CLI |
|---|---|---|
| 表格化 (一图一行 / 一项一行) | markdown 表格 | `ingest-album` (相册) |
| 散文 (普通文档) | prose 段落、标题、列表 | `ingest-file` → `ingest-commit` |
| 代码 / 命令块 | fenced code block | `ingest-commit --native` |

Agent 编排 SOP 时,**第一步就是问用户「这些内容是表格化 / 散文 / 代码块」**。body 形态由内容类型决定,**不**由 template 名决定——template 是 frontmatter 标签,body 形态是文件实际写出去的 markdown 结构,二者正交。相册是这一原则的典型落地场景。

---

## 三层边界（跨模块）

| 层 | 它是什么 | 动的命令 |
|---|---|---|
| **L0 软件** | 工具本身 | install / uninstall / update |
| **L1 系统注册表** | 系统认得哪些 wiki | create / register / unregister / alias |
| **L2 知识库本体** | wiki 里的所有节点 | ingest / query / revise / delete-node / table / gallery / page / report |

**铁律**：
- uninstall 默认只动 L0+L1，**永远不动 L2**
- unregister 只动 L1，**永远不动 L2**
- 删除 L2 必须用 delete-node，**不用 uninstall**

---

## 物理布局（[PRIN-ARCH-23]）

```
<wiki_root>/
├── raws/            # 原始文件（与 nodes/page 按 node_path 镜像）
├── nodes/
│   ├── page/        # Node_Page（按 node_path 分区）
│   ├── list/        # Node_List（DB-only）
│   ├── report/      # Node_Report（DB-only）
│   └── pending/     # ingest 暂存
└── .xu/
    ├── 主 SQLite DB           # SQLite（JSONB）
    ├── config.yaml
    ├── state.json
    ├── patches 表      # L1 修订表
    └── IDF 词频表     # IDF 词频表
```

---

## UID 约束

- 格式：正则格式（年份前缀 + 大写字母数字短码）
- 全局唯一，**永不重用**（[BAN-ARCH-2]）
- 所有跨节点引用都用 UID

---

## frontmatter 必填（Node_Page）

每个 Page 的 frontmatter 必须含一组基础必填字段：**身份标识、标题、层级字段、形态字段、状态字段、时间、内容哈希**等。三个字段有取值约束：

- 〈状态字段〉：必须是 bool（不是 0/1）
- 〈层级字段〉：∈ {Page, List, Report}
- 〈形态字段〉：∈ {article, table, gallery, …}（集合可由实现扩展）

字段命名由实现决定（详见 [CONST-ARCH-2]）。

---

## 4 键 JSON 协议

```json
{"status": "success | warning | error", "data": ..., "message": "...", "hints": [...]}
```

- `success` = 完全成功
- `warning` = 部分成功（如 relations 部分失败、内容哈希撞重）
- `error` = 完全失败（`data.error_class` 便于分类）
- `hints` = CLI 给 Agent 的最大帮助——告诉下一步该做什么

---

## 设计溯源

本套文档（00-07）由一份**早期手写设计稿**提炼而来——原稿含三层架构、检索 SOP、强 Schema、50 条关系、rebuild 粒度等核心想法，以及一组具体参数值。

```
早期手写设计稿（设计输入）
    ↓ 提炼原则 + 砍具体数值 + 拆模块
00-07.md（本套文档，唯一权威产出）
```

原稿的**原则**已全部吸收进 00-07；原稿的**具体参数值**（切片窗口、IDF 常量、权重比等）按「设计文档不指定 magic number」原则未写入正文，但作为**经验参考值**保留在上文「原则 ↔ 具体值对照」表里。原稿本身已无需单独保留——本套文档即唯一权威来源。

---

## 已知 Bug 与陷阱（开发时务必处理）

1. **BUG-DOC-1**：模块命名不一致导致引用错误 → 统一各专题诊断模块的命名前缀。
2. **安装后 wiki 实例内部结构**：patches 表 / IDF 词频表 由 create 负责，install 不能越界。
3. **目录名 `raws/`（带 s）**：不是 `raw/`。
4. **删除是物理删除 + 审计**：不是软删——不靠 `is_active=0` 标志留鬼节点。
5. **切片窗口软/硬双上限、合并距离阈值**：硬指标,具体数值由实现定。
6. **50 条关系上限**：硬上限，不能因为「业务需要」就放宽。要固化的关联升级为 L2 List。
7. **L1 不可变性**：patch 叠加，不覆盖；doctor --fix 绝不自动覆盖被外部修改的 Page。

---

## 使用建议

1. **先读本文**（索引），理解 7 份文档的关系。
2. **从 01 开始读**（架构 + CRUD 是地基），落地 PRIN 与 BAN。
3. **依次读 02-07**，按编号落地每个模块的 PRIN / BAN / CONST。
4. **每份文档末尾的「自检清单」** 是开发者实现时的 checklist。
5. **「作者注」** 标出了该模块最容易踩的坑。
6. **跨文档的核心原则归纳**（本文档）是开发者全局决策的快速参考。

---

## 实现里程碑（建议落地顺序）

> 设计文档是**全景**，但实现不必一次铺满。以下里程碑按「最小可用闭环」递进——先让主线跑通，再补周边。每个里程碑结束都应有一个**可演示的能力**。

**M1 — 软件骨架**（能装、能建空库）
- `install`（[03]）+ `create`（[02]）
- 验收：装好 CLI，建出一个空 wiki，三件套目录 + DB schema + 两张副表（patches / IDF）就位
- 这一步**不碰**任何节点逻辑，只搭地基

**M2 — L1 主线闭环**（能存、能查）⭐ 最关键
- `ingest-commit`（[05]，含两阶段、SHA256 去重、frontmatter 校验、patches v1、IDF 入库）+ `query`（[06]，ripgrep + 切片 + 打分 + Fast Pass）+ `read`
- 验收：摄入一个 PDF → 切成 Node_Page → query 能命中 → read 能取全文
- **这是整个系统的心脏**——M2 跑通，产品就有了核心价值。L2/L3 都是在 L1 之上的增量

**M3 — 关系网**（节点能互联）
- `query-relation`（50 条 LRU 链表，[PRIN-ARCH-7~10]）+ query 的 `--neighbors`
- 验收：节点间建关系、查询命中关系前挪、满 50 条弹队尾

**M4 — L2/L3 上层**（对比与推理）
- `list create` / `list show`（L2）+ `report create` / `report show`（L3，证据链）
- 验收：把多个 Page 聚成对比 List，基于 L1/L2 生成有证据链的 Report

**M5 — 体检与运维**（一致性保障）
- `doctor` 系列（[07]）+ `delete-node`（删前查引用）+ `uninstall`（[04]）+ rebuild
- 验收：doctor 能检出三层不变量违规，--fix 机械修复，卸载不动知识库

**顺序铁律**：M2 之前不要碰 L2/L3。先有干净的 L1 事实底座，再有上层推演——**反过来会陷入「先做 Report 后补 Page」的架构债**（见末尾作者注）。

---

## 原则 ↔ 具体值对照（经验参考值）

本套文档**有意不写死**切片窗口、IDF 常量、核心/扩展权重比、密度奖励系数、Fast Pass 倍数等具体数值（遵循「设计文档不指定 magic number」原则）。但实现总要有个起点——下表给出一组**经验参考值**（来自项目早期手写设计稿，作者实跑可用），供开发者作为缺省起点：

| 原则编号 | 主题 | 经验参考值 |
|---|---|---|
| [PRIN-ARCH-13] / [PRIN-QRY-10] | 打分公式 | 总分 = (A 覆盖分 + B 稀有分) × C 密度奖励 |
| 同上 · A 覆盖分 | 核心/扩展词权重 | 核心词命中数 × 2000 + 扩展词命中数 × 500 |
| 同上 · C 密度奖励 | 多词共现系数 | 共现时 ×1.5（[CONST-QRY-5] 要求 > 1） |
| [CONST-QRY-4] | 核心:扩展权重比 | 约 4 : 1（核心远大于扩展） |
| [PRIN-ARCH-20] / [PRIN-QRY-11] | IDF 稀有度常量 | 权重 = 10000 / (库内频次 + 1) |
| [PRIN-QRY-8] / [DESIGN-ARCH-6] | 切片窗口软/硬上限 | 软上限 80 字符 / 硬上限 150 字符 |
| [PRIN-QRY-9] / [DESIGN-ARCH-7] | 邻域合并半径 | 物理距离 < 80 字符（或边界重叠）则合并 |
| [PRIN-QRY-12] | Fast Pass 阈值倍数 | 动态：top1 分数 > 均值 × 3 倍 |
| [PRIN-ING-4] | Page 切分粒度 | 300 行正文（本套文档已定为硬默认，见 [PRIN-ING-4]） |

**用法**：这些是**起点不是契约**——实现者可按硬件、库规模、领域特性调整。它们是「作者跑过、能用」的经验值，不是「必须如此」的规范。**唯一例外**是 [PRIN-ING-4] 的 300 行——那是本套文档明确定下的默认值（可经库内 config 调），其余各项纯属参考。

---

**作者注**：本套文档的核心是「**三层架构 + 50 条关系**」。开发者实现时务必先落地三层边界（[PRIN-ARCH-1]）、再实现关系排序链表（[PRIN-ARCH-9]），最后是检索的三层介入（[PRIN-QRY-1]）——**顺序反了会陷入「先做 Page 后想 Report」的陷阱**。

每条「原则」回答的是「为什么这样做」「什么不能动」——**不回答「具体怎么实现」**,具体数值与实现细节留给开发者权衡。