# 07 — `doctor` 模块设计原则

> **目的**：本文是面向开发者的设计原则文档，用于实现 wiki 风格的健康检查命令。
> **范围**：所有 `doctor*` 命令。
> **风格**：每条原则标 [PRIN-N] / [BAN-N] / [CONST-N] / [DESIGN-N] / [BUG-N]。

---

## 一、一句话定位

`doctor` 是 wiki 的体检医生：扫描实例、发现一致性问题、可选修复。**默认只读**——绝不擅自改动数据。检查的内容 = ingest / commit / query 时承诺的不变量。

## 二、原则

### [PRIN-DOC-1] 默认只读——最小副作用原则

`doctor` 默认**不修改任何数据**——只报告。

理由：
- doctor 是诊断工具，不是修复工具——修复必须有用户显式意愿
- 自动修复可能误删用户数据（orphan file 不一定真该删——可能是 doctor 漏了索引）
- 「只读」是 doctor 与其它命令的**最大区别**——破坏这条边界会让用户对所有命令都失去信任

LLM 重写时务必把 doctor 默认行为锁成只读。任何写操作必须显式 `--fix`。

### [PRIN-DOC-2] doctor 检查 = 三层架构的不变量

新设计引入三层节点（L1 Page / L2 List / L3 Report）+ 两张副表（patches）+ 50 条关系上限——doctor 必须**全检**这些不变量：

```
L1 Page 不变性  →  Markdown 不可被外部修改 / patches 表有 v1 初值
L3 Report 证据  →  Report 必引用 L1/L2 证据链 / 无悬挂引用
关系上限         →  每节点出边 ≤ 50 / LRU 链表无重复、无悬挂边
词频表一致性     →  名词频次与 Page 实际一致 / 无悬挂词
三层一致性       →  Page/List/Report 之间的引用无悬挂
```

任何「节点的合法状态」都有对应的 doctor 检查项；任何 doctor 检查项都对应 ingest 的某个承诺。**两者一一对应**。

### [PRIN-DOC-3] 修复是 ingest 的逆操作，不是凭感觉

`--fix` 修复的逻辑必须**与 ingest 的写盘逻辑对称**：

```
ingest 写 Page → doctor --fix 删除 orphan Page（逆向）
ingest 写  → doctor --fix 重建  频次（逆向）
ingest 写 patches → doctor --fix 重建 v1 初值（逆向）
ingest 写关系 → doctor --fix 删除悬挂边 / 修剪超出 50 条上限的队尾（逆向）
ingest 时规划 node_path → doctor --fix 时调用 xu reorganize 迁移到新分区（逆向）
```

LLM 重写时不要让 doctor --fix 凭「我觉得该删」删东西——必须有 ingest 的对称操作做依据。

### [PRIN-DOC-4] 子命令专题化——单一职责原则

| 子命令 | 检查 |
|---|---|
| `doctor`（总入口） | 快速检查（fields / files / relations / l1-immutable / report-evidence / node-path-organization） |
| `doctor-fields` | frontmatter 必填字段、类型、格式 |
| `doctor-files` | 文件系统与 DB 一致性 |
| `doctor-relations` | 关系完整性（含 50 条上限 + 无悬挂边） |
| `doctor-l1-immutable` | L1 Page Markdown 未被外部修改 + patches v1 初值存在 |
| `doctor-report-evidence` | L3 Report 证据链完整（无悬挂引用） |
| `doctor-node-path-organization` | 检测根级堆积 + 给出迁移建议（--fix 调用 xu reorganize） |
| `doctor-all` | 串行调上述所有子 doctor |

LLM 重写时不要发明「万能 doctor」——每个专题独立可调用。

### [PRIN-DOC-5] --fix 必须显式 flag——安全护栏原则

任何 doctor 写操作必须 `--fix`：
- ❌ 默认行为 = 写
- ✅ 默认行为 = 只读 + `--fix` = 写

`--fix` 必须在 help 文案和 dry-run 输出里**显式列出将做什么**——不能 silent 写。

### [PRIN-DOC-6] --fix 后的边界——软删 vs 硬删

`--fix` 行为在不同子命令间**可能不一致**（这是当前实现的现状，LLM 重写时建议统一）：

- `doctor-relations --fix`：物理 DELETE（不软删）
- `doctor-files --fix`：物理 unlink（不软删）
- `doctor-fields --fix`：upsert_node 补字段（不是删）
- `doctor-l1-immutable --fix`：检测到外部修改时 → 报警告 + 提示走 patches 重写，**绝不自动覆盖**（L1 不可变）
- `doctor --fix`：重建  词频（安全，可自动）
- `doctor-report-evidence --fix`：列出悬挂 Report 由 Agent 决定**绝不自动删 Report**

**强烈建议** LLM 重写时统一为「硬删 + 审计日志」——与 ingest / delete-node 的策略一致。**例外**：L1 不可变性绝不让 --fix 覆盖。

## 三、禁令

### [BAN-DOC-1] 默认不写数据

重复强调：doctor 默认**只读**。任何「顺手修一下」都是 bug。

### [BAN-DOC-2] 不发明「智能修复」

`--fix` 必须是**机械的、对称的、可预测的**：
- ✅ 「重建  词频」——可预测
- ✅ 「检测 L1 外部修改并报警」——可预测
- ❌ 「用 LLM 重新推断 frontmatter」——不可预测
- ❌ 「询问用户该删还是该恢复」——超出 CLI 边界

### [BAN-DOC-3] 不静默修改

`--fix` 执行前必须输出「将做什么」清单；执行后必须输出「做了什么」清单。让用户对每一步都有审计可能。

### [BAN-DOC-4] 不调 LLM

doctor 全程确定性逻辑：DB 查询 + 文件状态比对 + 结构化输出。**不允许**调 LLM 推断「这个 orphan 是不是该删」——让用户决定。

### [BAN-DOC-5] L1 不可变性绝不让 --fix 覆盖

`doctor-l1-immutable --fix` 检测到 Markdown 被外部修改时：
- ❌ 绝不自动覆盖回原内容
- ❌ 绝不调 LLM「猜测」原内容
- ✅ 报警告 + 列出哪些 Page 被外部修改 + 提示走 patches 表重写

理由：L1 不可变性是 [PRIN-ARCH-3] 的核心——doctor --fix 不能破坏这一原则。

### [BAN-DOC-6] L3 Report 本身不自动删；但悬挂引用可 auto-fix

`doctor-report-evidence` 检测到 Report 引用问题：
- ❌ 绝不自动删 Report（L3 的价值是固化 LLM 推理成果，自动删 = 知识丢失）
- ✅ 悬挂引用（指向不存在节点）和失效引用（指向 inactive 节点）可 auto-fix：从 `evidence` 表删除该引用行（机械操作，ingest-commit 的逆操作）
- ⚠️ "Report 无任何引用"保持只读；让 Agent 决定是删除 Report 还是补充引用

## 四、约束

### [CONST-DOC-1] 三层一致性检查

每个 doctor 都必须能回答「三层是否一致」：

1. DB 里有 Page 记录 → 对应的 `nodes/page/<node_path>/<slug>.md` 文件存在？
2. raw_path 非空 → `raws/<node_path>/<filename>` 存在？且与 nodes 侧**按 node_path 镜像对应**（[PRIN-ARCH-25]）？
3. `nodes/` 和 `raws/` 实际文件 → DB 有对应记录？
4. 压缩图片 → 两个 SHA256（压缩前用于查重、压缩后用于完整性）都在场（[PRIN-ING-12]）？

任一不一致 → 在对应 doctor 子命令的输出里报告。

### [CONST-DOC-2] L1 不变性检查

`doctor-l1-immutable` 必须验证：
1. `patches 表` 中每个 Page 都有 version=1 的 create 记录
2. Page Markdown 的 SHA256 = 创建时的 SHA256（未被外部修改）
3. 后续修订都通过 patches 叠加（不是直接覆盖 Markdown）

如果发现 Page Markdown SHA256 与创建时不同 → 报警（**不修复**——L1 不可变原则）。

### [CONST-DOC-3] L3 证据链检查

`doctor-report-evidence` 必须验证：
1. 每个 Report 的 `references` 字段指向的 uid 在 DB 中存在
2. 指向的 Page / List 处于 active 状态
3. Report body 中显式引用的节点 UID 全部有效

任一失败 → 报警 + 列出悬挂引用。

### [CONST-DOC-4] 关系上限检查

`doctor-relations` 必须验证：
1. 每节点出边总数 ≤ 50
2. 关系链表无重复边（同一对 (from, to, relation_name) 不应出现两次）
3. 无悬挂边（to_uid 指向的节点存在且 active）
4. 没有 cycle / 自引用（视具体业务决定）

**注意**：不检查任何「分类配额」或「评分」——关系是无分类的 LRU 链表（[PRIN-ARCH-8]），没有强/热点/弱之分，也没有评分公式。

### [CONST-DOC-5]词频表一致性检查

`doctor` 必须验证：
1. `词频表` 中每个词的 频次 字段与实际 Page 出现频次一致
2. 没有 deleted Page 留下的悬挂名词（频次 > 0 但无 Page 引用）
3.  权重公式应用一致（权重 = 常量（具体数值由实现决定） / (频次 + 1)）

`--fix` 可重建（机械操作）。

### [CONST-DOC-6] --fix 必须先列「将做什么」

`--fix` 的 dry-run 必须逐条列出待执行的修复动作及其原因（哪条记录、为什么修),让用户在真正写入前看清全部影响面。输出形态由实现决定,但「先列清单后执行」不可省。

### [CONST-DOC-7] 4 键 JSON 返回

返回 `status/data/message/hints`。data 应分层汇总:各检查项的 issues 明细 + 总览统计(总问题数、可自动修复数、只读项数,并按 L1/L2/L3 分层计数)。hints 含「跑 --fix」建议。

### [CONST-DOC-8] 修复后立即重新检查

`--fix` 执行后，应能立即再跑一次同一 doctor 验证修复结果——如果还在 issue，说明修复没起作用，报告给用户。

### [CONST-DOC-9] 不修复〈形态字段〉与 body 不匹配

`doctor-content-type` 检测到〈形态字段〉= table 但 body 不是 markdown 表格 → **只报告**，不修复。

理由：修复需要 Agent 重新生成 body——超出 doctor 的确定性逻辑范围。

### [CONST-DOC-10] 不调 LLM

所有 doctor 路径无 LLM 调用。

## 五、已知 Bug（开发时务必避免）

### [BUG-DOC-1] 模块引用错误

任何 doctor 子命令引用的内部模块必须真实存在——避免引用重命名后的旧模块名。LLM 重写时统一各专题诊断模块的命名规范,用一致前缀。

## 六、与相关模块的关系

- **ingest**：doctor 检查 ingest 留下的不变量（L1 不可变、patches v1、 入库）
- **query**：doctor 检查 query 依赖的前提（词频表存在、关系出边未超 50）
- **create**：doctor 检查 wiki 三件套完整性（含 patches 表 存在性）
- **delete-node**：doctor 检查删除是否彻底（不留 orphan Page / 关系）
- **report**：doctor 检查 Report 证据链完整

## 七、自检清单（开发时勾选）

**原则**：
- [ ] 默认只读（[PRIN-DOC-1]）
- [ ] 检查项对应三层架构不变量（[PRIN-DOC-2]）
- [ ] --fix 是 ingest 的逆操作（[PRIN-DOC-3]）
- [ ] 子命令专题化（[PRIN-DOC-4]）
- [ ] --fix 必须显式（[PRIN-DOC-5]）
- [ ] --fix 边界明确（L1 不可覆盖、Report 不自动删）（[PRIN-DOC-6]）

**禁令**：
- [ ] 默认不写（[BAN-DOC-1]）
- [ ] 不发明智能修复（[BAN-DOC-2]）
- [ ] 不静默修改（[BAN-DOC-3]）
- [ ] 不调 LLM（[BAN-DOC-4]）
- [ ] L1 不可变性绝不让 --fix 覆盖（[BAN-DOC-5]）
- [ ] L3 Report 悬挂不自动删（[BAN-DOC-6]）

**约束**：
- [ ] 三层一致性（[CONST-DOC-1]）
- [ ] L1 不变性检查（[CONST-DOC-2]）
- [ ] L3 证据链检查（[CONST-DOC-3]）
- [ ] 关系上限检查 50 条 + 无悬挂边（[CONST-DOC-4]）
- [ ] --fix 输出将做什么（[CONST-DOC-6]）
- [ ] 4 键 JSON + by_layer 字段（[CONST-DOC-7]）
- [ ] 修复后重检查（[CONST-DOC-8]）
- [ ] 不修〈形态字段〉与 body 不匹配（[CONST-DOC-9]）
- [ ] 不调 LLM（[CONST-DOC-10]）
- [ ] node-path-organization 检查含建议路径（[CONST-DOC-N]）

**已知 Bug**：
- [ ] 统一模块命名规范避免 import 错（[BUG-DOC-1]）

---

**作者注**：doctor 看似简单，但新设计让它的检查范围从「单层 Page 一致性」扩展到了「三层架构 + 两张副表 + 50 条关系」。三个最关键的「不可让 --fix 越界」：
1. **L1 不可变**（[BAN-DOC-5]）——doctor 检测到外部修改只能报警，不能覆盖
2. **L3 Report 不删**（[BAN-DOC-6]）——悬挂引用只能让 Agent 决定
3. **删 Page 前查引用**（[DESIGN-ARCH-5]）——被 L2/L3 引用的 Page 不能闷头删，否则制造悬挂证据链

关系链表本身是**易失的**（LRU、丢了会重建），所以悬挂边、超 50 条的队尾可以在 `--fix` 下机械清理——但 doctor 默认仍只读，清理必须显式 `--fix` 并列出将做什么。

「doctor 顺手修一下」是危险的设计冲动——CLI 一旦默认修改数据，用户对所有命令都会失去信任。务必保持 doctor 的「诊断而非治疗」定位。