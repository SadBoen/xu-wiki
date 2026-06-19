# 08 — `SOP` 层设计原则

> **目的**：本文是面向开发者的设计原则文档，用于定义 xu-wiki 在 Agent 工作流中的 SOP（Standard Operating Procedure）层——用户/Agent 层的 5 类意图动词如何映射到 CLI 层的原子命令。
> **范围**：覆盖 SOP 与 CLI 的边界关系、5 大 SOP 的定义、SOP → CLI 的映射规则、以及 install/uninstall 与 SOP 的切割。
> **风格**：每条原则标 `[PRIN-SOP-N]` / `[BAN-SOP-N]` / `[CONST-SOP-N]` / `[DESIGN-SOP-N]`。

---

## 一、一句话定位

SOP 层是 xu-wiki skill 暴露给 Agent 的**5 个意图动词**（create / ingest / query / doctor / config），每个动词在内部编排一组 CLI 原子命令完成工作流。Agent 与 SOP 交互，**不与 CLI 子命令直接交互**——slash command `/xu-wiki <verb>` 是 SOP 入口，**不是** `xu-wiki <subcmd>` 的别名。

---

## 二、原则

### [PRIN-SOP-1] slash command 是 SOP 入口，不是 CLI 子命令——分层原则

`/xu-wiki <verb>` 命中 `<verb>` 这个 SOP，由 SOP 决定调哪些 CLI 命令、按什么顺序。Agent 永远不应把 `/xu-wiki config` 翻译成 `xu-wiki config`——后者在当前 CLI 里**根本不存在**。

理由：用户/Agent 的思维是「意图」（我要建库），不是「动词」（我要调 create）。意图与实现的解耦让 skill 描述稳定、CLI 命令可以独立演化。

### [PRIN-SOP-2] SOP 是多步编排，不是单次调用——编排原则

至少一个 SOP（ingest）必然要调 ≥ 2 个 CLI 命令（ingest-file → ingest-commit 两阶段，PRIN-ING-1），其他 SOP 也常需要多步（query 经常需要 query → 解读 hint → read / list show / report show）。SOP 是**编排**而非**包装**。

### [PRIN-SOP-3] 同一 CLI 可被多个 SOP 共享——共享原则

`xu-wiki wikis`（列出已注册 wiki）被 `SOP: create` 用来验证建库结果，被 `SOP: config` 用来查看注册表。共享 CLI 不破坏 SOP 边界——边界由 Agent 入口决定，不由 CLI 决定。

### [PRIN-SOP-4] SOP 的错误恢复必须显式定义——失败模式原则

每个 SOP 必须明确：
- 步骤失败的退出策略（abort / retry / skip-and-warn）
- 中间状态的持久化（partial work 留不留）
- 给 Agent 的下一步提示（hints）

理由：Agent 不知道失败后该回滚还是继续——SOP 必须显式规定。

### [PRIN-SOP-5] SOP 的副作用必须经由 CLI——封层原则

所有写动作（写 wiki DB、改 raws/、改 registry、改全局 config）必须经由 CLI 命令。SOP 编排层**只**调用 CLI，不自己 open() 文件、不自己 exec SQL。

理由：CLI 是唯一有审计、错误处理、约束校验的层；SOP 直接动 FS 会绕过这些护栏（[BAN-SOP-2]）。

---

## 三、禁令

### [BAN-SOP-1] Agent 不许把 `/xu-wiki <verb>` 当成 `xu-wiki <verb>` 调用

SKILL.md 必须把 5 SOP 完整列出；如果一个 `<verb>` 不在 SOP 列表里，Agent 必须报错而不是猜。找不到 SOP ≠ 找最近的 CLI 命令。

### [BAN-SOP-2] SOP 不许绕过 CLI 直接写文件 / 改 DB

SOP 编排层只调 `subprocess.run(["xu-wiki", ...])` 或等价机制；不许直接读写 wiki 的 `.xu/`、`raws/`、`nodes/`、`registry.yaml`。

### [BAN-SOP-3] SOP 不许发明新的 CLI 子命令

SOP 编排必须基于**已实现**的 CLI 子命令。如果某个 SOP 需要新能力，**先**在 02-07 系列设计文档里加新 CLI，再让 SOP 调用。

理由：CLI 子命令是稳定的契约；SOP 是灵活的编排。契约稳定、编排灵活才是健康的分层。

### [BAN-SOP-4] SOP 不许隐式触发副作用

每一步的副作用必须可在 SOP 文档里看到。如果某个步骤「顺带」改了状态（不是其主功能的一部分），属于隐式副作用——要么写进文档，要么剥离到独立 CLI。

---

## 四、约束

### [CONST-SOP-1] SOP 必须在 SKILL.md 完整文档化

每个 SOP 在 SKILL.md 里必须有：
- 意图定义（什么场景用）
- 调用步骤（按顺序调哪些 CLI、传什么参数）
- 失败模式与恢复
- 成功标志（返回什么 data 字段视为完成）

### [CONST-SOP-2] SOP → CLI 映射必须显式且唯一反向可查

SKILL.md 的 SOP map 段必须列出每个 SOP 对应的全部 CLI 命令；任一 CLI 命令必须能反向查到至少一个 SOP（无主孤儿命令）。

### [CONST-SOP-3] install / uninstall 不属于 5 SOP

`xu-wiki install` 与 `xu-wiki uninstall` 是软件生命周期的前置 / 反向前置，**不属于** 5 SOP。它们动的是**软件本体**（venv / CLI symlink / SKILL deploy），不是 wiki 数据。

### [CONST-SOP-4] 5 SOP 数量固定，不轻易增减

新增 SOP 是重大架构变更，需要新增独立设计文档并触发 skill description 重写。当前 5 个是闭合集合。

---

## 五、五大 SOP 定义

### 5.1 SOP: create — 建库

**意图**：用户说「我要建一个知识库」。

**调用步骤**：
1. （隐含前置）机器上已 `xu-wiki install` 过一次（[PRIN-CRT-1]）
2. Agent 必须先问齐 `--name` 与 `--path`（hard rule 8）
3. 调用 `xu-wiki create --name <n> --path <abs> [--alias <a>]`
4. （可选）调用 `xu-wiki wikis` 验证注册成功

**失败模式**：
- `--name` 缺失 / 不合法 → `MissingName` / `InvalidName`（[BAN-CRT-3] / [CONST-CRT-4]）
- `--path` 非空 → `DirNotEmpty`（[BAN-CRT-1]）
- 同名异路径 → `NameConflict`（[CONST-CRT-4]）
- 同路径已是 wiki → `warning` 复用（[CONST-CRT-3]）

**成功标志**：`data.path` 字段存在。

### 5.2 SOP: ingest — 入库

**意图**：用户说「我要把资料塞进知识库」。

**调用步骤**：
1. （隐含前置）目标 wiki 已建好（`xu-wiki wikis` 可见）
2. 对每个源文件执行两阶段（[PRIN-ING-1]）：
   - Phase 1：`xu-wiki ingest-file --wiki <w> --file <abs>`
   - Phase 2：`xu-wiki ingest-commit --wiki <w> --title <t> --template article`
3. （可选）建关系：`xu-wiki query-relation add --wiki <w> --from-uid ... --to-uid ...`
4. （可选）建 L2 / L3：`xu-wiki list create` / `xu-wiki report create`
5. （可选）调用 `xu-wiki nodes --wiki <w> --layer Page` 验证写入

**失败模式**：
- Phase 1 失败 → 文件解析失败，不创建 L1 节点
- Phase 2 失败 → pending 文件保留（不删），Agent 报告用户决定
- 关系数 > 50 → 自动 LRU 淘汰队尾（[PRIN-ARCH-7~10]）
- Report 缺证据链 → `EmptyEvidence`（[BAN-ARCH-5]）

**成功标志**：Phase 2 返回 `data.uid`。

### 5.3 SOP: query — 检索

**意图**：用户说「我要找知识」。

**调用步骤**：
1. Agent 把用户查询词分成 `--core`（实体，高权）与 `--expansion`（同义词，低权）（[PRIN-ARCH-12]）
2. `xu-wiki query --wiki <w> --core <kw,kw> --expansion <kw,kw> [--top-k N]`
3. 命中后按用户意图调：
   - 读单节点 → `xu-wiki read --wiki <w> --uid <uid>`
   - 看 L2 对比 → `xu-wiki list show --wiki <w> --uid <uid>`
   - 看 L3 结论 → `xu-wiki report show --wiki <w> --uid <uid>`
4. （可选）查节点是否存在 → `xu-wiki nodes --wiki <w>`

**失败模式**：
- `--core` 空 → Agent 必须问用户（hard rule 8）
- 0 命中 → 不许自动切换模式，告知用户换关键词
- `list_hint` / `report_hint` 提示 → Agent 决定是否跟进，CLI 不擅自动作（[PRIN-QRY-1]）

**成功标志**：`query` 返回 `data.hits` 非空。

### 5.4 SOP: doctor — 检查与修复

**意图**：用户说「我要检查 wiki 健康」或「wiki 出问题了」。

**调用步骤**：
1. `xu-wiki doctor-all --wiki <w>` 跑全部 6 项检查
2. 若有 issue：
   - 若 `--fix` 支持的（fields / files / l1-immutable 等机械修复），先告诉用户再应用
   - 若需手工决策（如 L2/L3 引用冲突），给 Agent hint，不擅自动作
3. （可选）重衍生层：`xu-wiki rebuild --wiki <w> --granularity keep-l1`（默认不动 L1）

**失败模式**：
- `--fix` 失败 → 不自动重试，告知用户
- 任何 doctor 报错 → 不许跳过；列出全部 issue
- rebuild 必须先确认粒度（[PRIN-ARCH-6]）

**成功标志**：`doctor-all` 返回 `data.total_issues = 0`。

### 5.5 SOP: config — 配置管理

**意图**：用户说「我要管理 wiki / 全局配置」（别名、注册、密钥、查看）。

**调用步骤**（按子任务）：
- **设置 / 修改别名** → `xu-wiki alias set --wiki <name|alias> --alias <new>`（专用命令，不动 `created_at`）
- **解除别名** → `xu-wiki alias unset --wiki <name|alias>`
- **查看别名** → `xu-wiki alias show --wiki <name|alias>`
- **查看注册表** → `xu-wiki wikis`（只读）
- **注册已有目录** → `xu-wiki register --name <n> --path <abs> [--alias <a>]`（不写文件）
- **取消注册** → `xu-wiki unregister --name <n>`（不动 wiki 本体）
- **设置 MinerU key** → `xu-wiki config set-mineru-key`（从 `MINERU_API_KEY` 环境变量读）
- **查看全局配置** → `xu-wiki config show`（密钥 masked）
- **查全局配置路径** → `xu-wiki config path`

**失败模式**：
- 别名冲突 → `warning` 不绑定（[CONST-CRT-4]）
- 取消注册时 wiki 不存在 → `NameNotFound`
- MinerU key 写入失败 → 不影响其他 SOP，提示用户改用环境变量

**成功标志**：`xu-wiki wikis` 返回中可见新别名 / 新注册项 / 新 key。

---

## 六、SOP → CLI 映射总表

| SOP | CLI 命令 | 在 SOP 内的角色 |
|---|---|---|
| **create** | `create` | 主命令 |
| | `wikis` | 验证 |
| **ingest** | `ingest-file` | Phase 1（PRIN-ING-1） |
| | `ingest-commit` | Phase 2 |
| | `query-relation add` | 建关系（可选） |
| | `list create` | 建 L2（可选） |
| | `report create` | 建 L3（可选） |
| | `nodes` | 验证 |
| **query** | `query` | 主命令 |
| | `read` | 读单节点 |
| | `list show` | 读 L2 对比 |
| | `report show` | 读 L3 结论 |
| | `nodes` | 元数据查询 |
| **doctor** | `doctor-all` | 全部检查 |
| | `doctor-fields / files / relations / l1-immutable / report-evidence / idf` | 细分 |
| | `rebuild` | 修复（衍生层） |
| | `delete-node` | 清理（删 dangling 节点） |
| **config** | `wikis` | 查看注册表 |
| | `alias set / unset / show` | 别名管理 |
| | `register` | 注册已有目录（不写文件） |
| | `unregister` | 取消注册（不动 wiki 本体） |
| | `config set-mineru-key / show / path` | 全局配置读写 |
| **不属于 SOP** | `install` | 软件生命周期前置 |
| | `uninstall` | 软件生命周期反向前置 |

> **约束 [CONST-SOP-2]**：上表每一个 CLI 命令都必须能反向查到至少一个 SOP。无主命令 = 设计漏洞。

---

## 七、与 install / uninstall 的边界

| 命令 | 性质 | 归属 |
|---|---|---|
| `xu-wiki install` | 装软件本体（venv + CLI symlink + SKILL deploy） | **不属于 5 SOP**（[CONST-SOP-3]） |
| `xu-wiki uninstall` | 卸软件本体（默认 dry-run，[PRIN-UNINST-6]） | **不属于 5 SOP** |

理由：install / uninstall 动的是**软件本体**，不是 wiki 数据。install 是 SOP-create 的强前置（[PRIN-CRT-1]），但本身属于「软件生命周期」而非「知识库工作流」。

---

## 八、与其他设计文档的关系

| 文档 | 关系 |
|---|---|
| 01-wiki-architecture.md | SOP 层建立在三层节点 + 50 条关系架构之上 |
| 02-create.md | 是 SOP-create 的 CLI 实现文档 |
| 03-install.md | 是 install 命令的设计文档（不在 5 SOP 内） |
| 04-uninstall.md | 是 uninstall 命令的设计文档（不在 5 SOP 内） |
| 05-ingest.md | 是 SOP-ingest 的 CLI 实现文档 |
| 06-query.md | 是 SOP-query 的 CLI 实现文档 |
| 07-doctor.md | 是 SOP-doctor 的 CLI 实现文档 |
| **08-sop-architecture.md（本文）** | **定义 SOP 层与 CLI 层的边界** |

> 本文档（08）是 SOP 层的**总纲**；02 / 05 / 06 / 07 是各 SOP 的 CLI 实现细节。未来若 SOP-config 落地，应新增 `09-config.md` 作为 SOP-config 的 CLI 实现文档。

---

## 九、自检清单

**原则**：
- [ ] slash command ≠ CLI 子命令（[PRIN-SOP-1]）
- [ ] SOP 是多步编排（[PRIN-SOP-2]）
- [ ] 同一 CLI 可被多 SOP 共享（[PRIN-SOP-3]）
- [ ] 错误恢复显式定义（[PRIN-SOP-4]）
- [ ] 副作用必须经由 CLI（[PRIN-SOP-5]）

**禁令**：
- [ ] Agent 不许把 SOP 当 CLI 调（[BAN-SOP-1]）
- [ ] SOP 不许绕过 CLI 直接写文件（[BAN-SOP-2]）
- [ ] SOP 不许发明新 CLI（[BAN-SOP-3]）
- [ ] SOP 不许隐式副作用（[BAN-SOP-4]）

**约束**：
- [ ] SOP 在 SKILL.md 完整文档化（[CONST-SOP-1]）
- [ ] SOP → CLI 映射显式且唯一反向可查（[CONST-SOP-2]）
- [ ] install / uninstall 不属 5 SOP（[CONST-SOP-3]）
- [ ] 5 SOP 数量固定（[CONST-SOP-4]）

---

**作者注**：SOP 层是 Agent 时代 wiki 引擎的关键抽象——它把「用户在说什么」与「代码在做什么」解耦，让 skill 描述稳定、CLI 命令独立演化、Agent 工作流可验证。建议把 SOP 视为**协议级契约**：每加一个 SOP 是 API 加一个端点，必须有设计文档 + SKILL.md 段落 + 至少一个 SOP-recipe 样例三件套，缺一不可。
