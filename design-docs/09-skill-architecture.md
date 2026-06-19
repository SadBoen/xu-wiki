# 09 — Skill 文档架构设计原则

> **目的**：本文定义 xu-wiki Skill 文档（`src/xu/skills/`）的目录组织、文件结构、内容划分原则。
> **范围**：SKILL.md 主入口的职责、5 个 SOP 任务文件的组织、`scripts/` 与 `reference/` 的取舍、跨文件引用的纪律。
> **风格**：每条原则标 `[PRIN-SKILL-N]` / `[BAN-SKILL-N]` / `[CONST-SKILL-N]` / `[DESIGN-SKILL-N]`。

---

## 一、一句话定位

Skill 文档的目标是**让 Agent 在执行具体 SOP 任务时只加载与该任务相关的内容**——不被无关信息污染、不会被跨文件引用强制加载不相关的全部内容。文件结构、内容划分、命名规范都服务于这一个目的。

---

## 二、当前文件结构

```
src/xu/skills/
├── SKILL.md          # 唯一索引：5 SOP 总览、跨切 hard rules、response 格式、quick start
├── create.md         # /xu-wiki create 任务全文（自给自足）
├── ingest.md         # /xu-wiki ingest 任务全文（自给自足）
├── query.md          # /xu-wiki query 任务全文（自给自足）
├── doctor.md         # /xu-wiki doctor 任务全文（自给自足）
├── config.md         # /xu-wiki config 任务全文（自给自足）
└── reference/        # 预占位目录：空文件是引导（PRIN-SKILL-7）
    ├── error-catalog.md   # 空 — 未来 error_class 集中地
    └── pitfalls.md        # 空 — 未来踩坑记录集中地
```

**不创建** `scripts/`（CLI 已是确定性层）。`reference/` **当前只放空占位**——任务流（5 SOP）不放在这里。**不创建** `sop/` 等自定义子目录（违反 Anthropic 官方 Skill 框架的扁平约定）。

---

## 三、原则

### [PRIN-SKILL-1] 任务文件自给自足——零跨文件引用

每个 SOP 任务文件（`create.md` / `ingest.md` / `query.md` / `doctor.md` / `config.md`）必须**自给自足**：
- 不引用其他 SOP 文件（不允许 `ingest.md → query.md`）
- 不引用 `reference/` 之类的共享层（不存在）
- 不引用 `scripts/` 之类的代码层（不存在）
- **只允许**引用 SKILL.md（"见 SKILL.md §X"）——因为 SKILL.md 已加载，引用是 0-token 的导航

**理由**：Agent 加载文件是**整文件加载**，不存在"读片段"操作。一旦引用，引用目标**全文加载**——为了一句相关，污染整个视野。

例子：若 `ingest.md` 写到「可以用 `query` SOP 验证」，正确写法是「走 `query` SOP（见 SKILL.md）」——通过 SKILL.md 路由；**错误**写法是 `[query](query.md)`——直接链触发 query.md 全量加载。

### [PRIN-SKILL-2] 跨切内容进 SKILL.md——不抽 reference/

如果某条信息**所有 SOP 都需要**（hard rules、response 格式、原则索引、quick start、5 SOP 总览），写在 SKILL.md。
**不要**抽到 `reference/common.md` 然后让每个 SOP 引用——那等于让每个 SOP 全量加载 reference。

如果某条信息**两个 SOP 都需要且只两个**，**内联两遍**到各自 SOP 文件——**重复胜于污染**。

### [PRIN-SKILL-3] 不创建 `scripts/`——CLI 已是确定性层

`scripts/` 只在 Skill **没有完整 CLI** 时使用——例如 PDF skill 的「填 PDF 表单」是脚本级操作，CLI 没有对应子命令。

xu-wiki 的 CLI 已经覆盖所有确定性操作（ingest-file / ingest-commit / ingest-album / query / read / delete-node / doctor-all / 等），`scripts/` 是徒增一层——脚本调 CLI、Agent 调脚本，等于绕路。

**特例**：若以后真出现「CLI 不该做、但 Agent 又要做」的边角操作（如临时格式转换、临时校验），可单独加文件并写清楚"为什么这个不进 CLI"——但**默认不创建**。

### [PRIN-SKILL-4] 任务流不进 `reference/`——任务不是 reference data

`reference/` 在 Anthropic Skill 框架中的语义是「lookup data / schemas / reference tables」（如 `bigquery-skill` 的 `reference/finance.md`、`reference/sales.md`）。任务流程（5 SOP）**不是** reference data，**不要套用这个命名**——5 个 SOP 文件放根目录，不放 `reference/`。

如果内容是"Agent 偶尔查一下的表"（如 error_class 全集速查），**两种情况**：
- 跨切通用且短 → 放 SKILL.md（已加载即免费）
- 跨切通用但**会增长** → 放 `reference/<type>.md`（见 [PRIN-SKILL-7]，空文件是预占位）

如果内容是"某个 SOP 内需要查的表"（如 ingest 的 body-form 三选一判定表），放**该 SOP 任务文件**内——任务专属、自给自足。

### [PRIN-SKILL-5] 任务文件扁平放根目录——遵循官方框架

5 个 SOP 文件直接放 `src/xu/skills/` 根目录，命名即任务动词（`create.md` / `ingest.md` / `query.md` / `doctor.md` / `config.md`），**不创建** `sop/` 之类自定义子目录。

理由：
- 符合 Anthropic 官方 Skill 框架的扁平约定（参见 [https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)）
- Agent 通过 `ls` 或文件系统发现时一目了然
- 避免命名创新引入的理解成本

### [PRIN-SKILL-6] SKILL.md 是唯一索引——任务文件之间平行

SKILL.md 列出 5 个 SOP 入口及对应文件名。任务文件之间是**平行关系**，不是引用关系：
- 一个 SOP 文件提到「可以用 query」时，**不**直接链到 `query.md`——只写「走 query SOP（见 SKILL.md）」
- 一个 SOP 文件需要某个 CLI 命令的详细说明时，**不**链到 reference（不存在）——直接在该文件内联必要细节

SKILL.md 是 Agent 的**唯一导航枢纽**。所有 SOP 间的跳转都通过它路由。

### [PRIN-SKILL-7] `reference/` 用占位文件做引导——空文件也是结构信号

当 `reference/` 目录下某类内容**预期会增长**（error 集、踩坑集、术语表…），**提前创建**仅含引导头的空文件作为占位。这不是"未完成"，而是"**结构化未来**"——空文件本身在告诉 Agent：

1. **这一类内容有家**——别建 `weird-bug.md` / `error-log-2026.md` / `notes-today.md` 之类的散文件
2. **有约定的格式**——文件头里写好 entry 模板，Agent 照着填
3. **有约定的命名**——同类内容集中在同一个文件，跨 entry 可比较

**占位文件的最小内容**（不能更少）：

- 一句话定位（这个文件是给什么内容用的）
- 未来 entry 的格式约定（标题 + 字段模板）
- "**不要删除此空文件**" 的明确声明（指向本原则）

**当前 xu-wiki 的占位**：

| 文件 | 用途 | 当前状态 |
|---|---|---|
| `reference/error-catalog.md` | 所有 `error_class` 的触发 / 修复 速查 | 空 |
| `reference/pitfalls.md` | 非显然踩坑、坑的成因、绕过办法 | 空 |

**触发条件**（什么时候建新占位文件）：

- 出现新的「会增长」类内容类型（不是「一次性查表」）
- 该类内容**预期在多个 SOP / 多个会话中累积**
- 没有现成 SOP 文件或 SKILL.md 适合收纳

**反例**（不要建占位）：

- 一次性查表 → 放 SKILL.md
- SOP 专属 → 放该 SOP 文件
- 真的不需要累积 → 不建

---

## 四、禁令

### [BAN-SKILL-1] 禁止跨 SOP 直接链

不允许：`ingest.md` 中出现 `[query](query.md)`、`[doctor SOP](doctor.md)` 之类的**直接链**。

允许：`ingest.md` 中出现「走 query SOP（见 SKILL.md）」的**间接指**——Agent 通过 SKILL.md 路由。

判断方法：在 Markdown 渲染中，跨 SOP 链接的 href **只能**是 SKILL.md（或 SKILL.md 的锚点），不能是其他 `.md` 文件。

### [BAN-SKILL-2] 禁止为"省字数"而抽 reference

不允许：「这几个 SOP 都用到的内容抽到 `reference/common.md`」「命令全集抽到 `reference/commands.md`」。

理由：抽到 reference/ 后，所有引用方**全量加载**该 reference——污染源从 1 个变成 N 个（每个引用方都是污染源）。表面看是省了重复字数，实际是给每个任务 context 注入了不相关内容。

**重复胜于污染**。

### [BAN-SKILL-3] 禁止在 `reference/` 之外创建参考性 / 踩坑 / 错误收集类文件

所有「同类内容累积型」的文件——`error-catalog` / `pitfalls` / `glossary` / `changelog` / `notes-<date>` / `bug-<id>` / `weird-issue`——**必须**进 `reference/<type>.md`。

理由（[PRIN-SKILL-7](file:///Users/boen/Coding/xu-wiki-2/xu-wiki/design-docs/09-skill-architecture.md)）：
- `reference/` 的空占位文件是**结构信号**——告诉 Agent "这一类内容有家"
- 散文件（`error1.md` / `bug-2026-06-20.md`）**违反**这个信号，导致同主题内容散落
- 散文件无法跨 entry 比较，无法 grep 全文，无法在 install / uninstall 时被一致管理

如果新类型的内容**没有对应的占位文件**：
1. 先**创建占位文件**（带引导头）
2. 再**把内容写到那里**
3. 永远不要建 `notes-<date>.md` 之类的临时散文件

---

## 五、约束

### [CONST-SKILL-1] 遵循 Anthropic Skill 框架的扁平结构

Skill 目录结构以 Anthropic 官方文档为准。允许的子目录只有 `scripts/`（代码）和 `reference/`（lookup data）——前者默认不创建，后者禁止用于任务流。

新增任何子目录前必须先回答：这是 `scripts/`（确定性代码）、`reference/`（lookup data），还是**都不属于**？都不属于 → 不创建。

### [CONST-SKILL-2] Agent 加载粒度为整文件

Agent 通过 `Read` 工具或 `cat` 加载文件时，**整文件加载**。不存在"读片段"操作、`head -50` 也只是预览，不保证读到关键段落。

设计含义：任何文件只要被引用，就**全文进入 context**。引用即污染，引用即开销。

---

## 六、设计取舍

### [DESIGN-SKILL-1] 选择"自给自足任务文件"模式，放弃"共享 reference"模式

**问题**：5 个 SOP 文件之间有公共内容（如命令清单、hard rules），如何组织？

**备选 A：共享 reference 模式**
```
SKILL.md
reference/
  ├── commands.md       # 全量 CLI 命令清单
  ├── hard-rules.md     # 12 条 hard rules
  └── error-classes.md  # 全部 error_class
sop/create.md
sop/ingest.md
...
```
每个 SOP 文件通过引用加载必要的 reference 子集。

**优点**：节省字数、避免重复。
**缺点**：每个 SOP 任务加载时，**全量**加载被引用的 reference。reference 一旦膨胀，所有任务都被污染。

**备选 B：自给自足任务文件模式（采用）**
```
SKILL.md
create.md       # 该任务需要的全部内容内联
ingest.md       # 该任务需要的全部内容内联
...
```
跨切内容放 SKILL.md；多 SOP 共享的小段内容**内联两遍**；多 SOP 共享的大段内容**不存在**——要么在 SKILL.md，要么降级为「只在该 SOP 出现」。

**优点**：每个任务加载的内容 100% 相关于该任务，零污染。
**缺点**：少量重复。

**决定**：**重复胜于污染**。当一个事实需要"出现在两个 SOP"时，复制到两个文件，而不是抽 reference 再让两边都加载整个 reference。

触发反例（什么时候要重新考虑此决定）：如果某条信息需要在 **3 个以上 SOP 出现且长度 > 50 行**，则提到 SKILL.md（接受 SKILL.md 膨胀）；如果 5 个 SOP 都需要且确实很长，**重新拆任务**而不是重新加 reference。

---

## 七、内容归属速查

| 内容性质 | 进哪里 | 理由 |
|---|---|---|
| 5 SOP 总览（slash command ↔ CLI 编排） | `SKILL.md` | 跨切通用 |
| Hard rules（12 条护栏） | `SKILL.md` | 跨切通用 |
| Response 格式 | `SKILL.md` | 跨切通用 |
| Quick start | `SKILL.md` | 跨切通用 |
| 原则索引（PRIN/BAN/CONST 速查） | `SKILL.md` | 跨切通用 |
| ingest 两阶段流程 | `ingest.md` | ingest 专属 |
| body-form 三选一判定 | `ingest.md` | ingest 专属 |
| album 单子流 | `ingest.md` | ingest 专属 |
| vision 意图标记 | `ingest.md` | ingest 专属 |
| query 关键词分级 | `query.md` | query 专属 |
| query --neighbors 行为 | `query.md` | query 专属 |
| doctor 6 项子检查 | `doctor.md` | doctor 专属 |
| `--fix` 安全边界 | `doctor.md` | doctor 专属 |
| alias / register / unregister | `config.md` | config 专属 |
| MinerU key 管理 | `config.md` | config 专属 |
| create --name / --path 校验 | `create.md` | create 专属 |
| process-layer audit 日志规范 | `SKILL.md`（简）+ `01-wiki-architecture.md` §五·五（详） | SKILL.md 只放一句指路，详细在架构文档 |
| error_class 速查（短 / 静态） | `SKILL.md` | 跨切通用，跨频率不高 |
| error_class 完整 catalog（**会增长**） | `reference/error-catalog.md` | 占位文件，未来累积（PRIN-SKILL-7） |
| 踩坑记录、坑的成因、绕过办法 | `reference/pitfalls.md` | 占位文件，未来累积（PRIN-SKILL-7） |

---

## 八、与现有设计原则的关系

| 现有原则 | 关系 |
|---|---|
| [PRIN-ARCH-26] 元数据三层 | process-layer audit 的细节在 01-wiki-architecture.md，SKILL.md 只放 Agent 操作级的一句话 |
| [PRIN-SOP-1~7] | 5 个 SOP 任务文件实现 SOP 编排的"导航"；SKILL.md 是 SOP 入口的索引 |
| [CONST-ARCH-6] | process-layer audit 的双路写入由 CLI 保证；Skill 文档只描述 Agent 视角的观察 |

---

## 九、自检清单

- [ ] `src/xu/skills/` 根目录有 `SKILL.md` + 5 个 SOP 文件 + `__init__.py`（PRIN-SKILL-5）
- [ ] `reference/` 子目录存在，且**只**含预占位文件（PRIN-SKILL-7）
- [ ] 没有 `scripts/` 文件夹（PRIN-SKILL-3）
- [ ] 没有 `sop/` 之类自定义子目录（PRIN-SKILL-5）
- [ ] 5 个 SOP 文件**全部放在根目录**（PRIN-SKILL-4）
- [ ] 5 个 SOP 文件之间无直接链（BAN-SKILL-1）
- [ ] 跨切内容（hard rules、response、quick start）在 SKILL.md（PRIN-SKILL-2）
- [ ] 没有「省字数」抽 reference 的痕迹（BAN-SKILL-2）
- [ ] SKILL.md 是所有任务文件的唯一入口（PRIN-SKILL-6）
- [ ] 没有散文件（`error1.md` / `notes-<date>.md` / `bug-<id>.md`）—— 累积型内容全进 `reference/<type>.md`（BAN-SKILL-3）

---

**作者注**：本模块有两层灵魂。

**第一层——防污染**：[PRIN-SKILL-1]（自给自足）+ [BAN-SKILL-1]（禁跨链）+ [CONST-SKILL-2]（整文件加载）。**前者保证"加载即相关"、后者保证"不被强制加载"**——三者结合是"零污染" Skill 文档的架构闭环。

**第二层——结构引导**：[PRIN-SKILL-7]（reference/ 空占位）+ [BAN-SKILL-3]（禁散文件）。**前者用空文件做未来内容的结构信号、后者用禁令阻止 Agent 乱建文件**——两者结合是"内容累积有序" Skill 文档的维护闭环。
