# 08 — `SOP` 层设计原则

> **目的**：本文是面向开发者的设计原则文档，用于定义 xu-wiki 在 Agent 工作流中的 SOP（Standard Operating Procedure）层——用户/Agent 层的 5 类意图动词如何映射到 CLI 层的原子命令。
> **范围**：覆盖 SOP 与 CLI 的边界关系、5 大 SOP 的定义、SOP → CLI 的映射规则、以及 install/uninstall 与 SOP 的切割。
> **风格**：每条原则标 `[PRIN-SOP-N]` / `[BAN-SOP-N]` / `[CONST-SOP-N]` / `[DESIGN-SOP-N]`。

---

## 一、一句话定位

SOP 层是 xu-wiki skill 暴露给 Agent 的**5 个意图动词**（create / ingest / query / doctor / config），每个动词在内部编排一组 CLI 原子命令完成工作流。Agent 与 SOP 交互，**不与 CLI 子命令直接交互**——slash command `/xu-wiki <verb>` 是 SOP 入口，**不是** `xu-wiki <subcmd>` 的别名。

调用链的三个角色：

| 角色 | 看到什么 | 输出什么 |
|---|---|---|
| **User** | Agent UI（聊天框 / 语音） | 自然语言意图 |
| **Agent**（LLM + SKILL.md） | User 自然语言 + 4-key JSON | CLI 调用 |
| **CLI**（确定性引擎） | Agent 的调用 | 文件 / DB 变更 |

User 永远不直接调 CLI——CLI 的唯一调用方是 Agent（详见 [PRIN-SOP-8]）。

---

## 二、原则

### [PRIN-SOP-1] slash command 是 SOP 入口，不是 CLI 子命令——分层原则

`/xu-wiki <verb>` 命中 `<verb>` 这个 SOP，由 SOP 决定调哪些 CLI 命令、按什么顺序。Agent 永远不应把 `/xu-wiki config` 翻译成 `xu-wiki config`——后者在当前 CLI 里**根本不存在**。

理由：用户/Agent 的思维是「意图」（我要建库），不是「动词」（我要调 create）。意图与实现的解耦让 skill 描述稳定、CLI 命令可以独立演化。

### [PRIN-SOP-2] SOP 是多步编排，不是单次调用——编排原则

至少一个 SOP（ingest）必然要调 ≥ 2 个 CLI 命令（ingest-file → ingest-commit 两阶段，PRIN-ING-1），其他 SOP 也常需要多步（query 经常需要 query → 解读 hint → read / list show / report show）。SOP 是**编排**而非**包装**。

### [PRIN-SOP-3] CLI 是原子能力，SOP 是其按需组合——原子化原则

CLI 命令代表一项**原子能力**（atomic capability）：`delete-node` = 物理删除一个节点；`doctor-all` = 跑全部 6 项检查；`wikis` = 列出注册表；`rebuild` = 重衍生层。

**CLI 不「属于」任何 SOP**。任何 SOP 都可以按用户意图，**挑选并编排**这些原子能力来满足用户请求。

例子：

| 用户输入 | 进入的 SOP | 编排的 CLI |
|---|---|---|
| `/xu-wiki doctor 删除 NepTune 的 dangling 节点` | doctor | `doctor-all` → `delete-node --force` |
| `/xu-wiki config 全面清空 NepTune 的过时内容` | config | `doctor-all` → `delete-node` |
| `/xu-wiki ingest 重建 NepTune 的 dangling 关系` | ingest | `query-relation add` |

`delete-node` 同时被 doctor 和 config 引用——这不是「共享」，是「同一原子能力被两个 SOP 按各自意图嵌入使用」。

理由：用户意图是**自然语言**（「把 X 移到 Y」「删 Z」「检查 W」），不是 SOP 名也不是 CLI 名。SOP 必须能根据意图**挑选并编排**合适的 CLI。如果把 CLI 钉死给某个 SOP，就等于让 Agent 失去按意图编排的灵活性。

### [PRIN-SOP-4] SOP 的错误恢复必须显式定义——失败模式原则

每个 SOP 必须明确：
- 步骤失败的退出策略（abort / retry / skip-and-warn）
- 中间状态的持久化（partial work 留不留）
- 给 Agent 的下一步提示（hints）

理由：Agent 不知道失败后该回滚还是继续——SOP 必须显式规定。

### [PRIN-SOP-5] SOP 的副作用必须经由 CLI——封层原则

所有写动作（写 wiki DB、改 raws/、改 registry、改全局 config）必须经由 CLI 命令。SOP 编排层**只**调用 CLI，不自己 open() 文件、不自己 exec SQL。

理由：CLI 是唯一有审计、错误处理、约束校验的层；SOP 直接动 FS 会绕过这些护栏（[BAN-SOP-2]）。

### [PRIN-SOP-6] SOP 边界由用户意图决定，不由 CLI 决定——意图分层原则

SOP 不是「这一组 CLI 的别名」，而是「**这一类用户意图**的承接入口」。

正确框架（按意图归类）：
- **破坏性 / 修复性意图**（删、改、查后修、移位）→ doctor SOP
- **配置性意图**（注册、别名、密钥、路径）→ config SOP
- **构建性意图**（建库、入库、建关系）→ create / ingest SOP
- **检索性意图**（找内容、列节点、读全文）→ query SOP

反例（按 CLI 归类，是错误的）：
- 「`doctor-*` 命令归 doctor SOP」← 这是 CLI 视角，**不是** SOP 视角

同一 CLI 可跨越 SOP 边界，**这是设计意图，不是例外**：
- `wikis`：被 create 用来「建完验证」，被 config 用来「看注册表」
- `nodes`：被 query 用来「找 UID」，被 doctor 用来「找 dangling」，被 config 用来「看 DB」
- `delete-node`：被 doctor 用来「清 dangling」，未来也可被 config 用来「清库」

理由：如果 CLI 决定 SOP 边界，SOP 就退化成「CLI 命令的别名分类」，失去 SOP 层存在的意义。SOP 的价值在于**按意图重新组合** CLI，不是按 CLI 重新分类。

### [PRIN-SOP-7] SOP 接受自然语言意图，不是只接受动词命令——意图层原则

SOP 是 Agent 层的**自然语言入口**。Agent 进入 SOP 后，根据用户的具体意图（自然语言短语）挑选 CLI。

错误框架：把 SOP 当 verb-only 命令解释。

```
用户：/xu-wiki doctor 删除 X 节点
错误响应：请用 xu-wiki delete-node --wiki W --uid X  ← 把 SOP 当 CLI 别名
```

正确框架：SOP 解析意图 → 编排 CLI。

```
用户：/xu-wiki doctor 删除 X 节点
正确响应：Agent 在 doctor SOP 内识别意图 = 物理删除
         → 调用 delete-node --wiki W --uid X（必要时 --force）
```

SOP recipe 必须覆盖**意图 → CLI** 的映射，不仅列 CLI 步骤。本文档 §五每个 SOP 都必须包含「典型用户意图 → 编排」表。

**意图不可达时必须显式拒绝**（这是 SOP 编排的自然延伸）：

```
用户：/xu-wiki doctor 请将 X 节点移位到 Y 目录下
正确响应：SOP 识别意图 = 移动节点位置
         → 当前无对应 CLI（节点无「目录」概念）
         → 拒绝并解释：建议用「删 + 重建」或「重新 ingest」代替
```

理由：如果 SOP 不显式拒绝，Agent 会**强行调一个不相关的 CLI**凑合（这是上一轮 `/xu-wiki config` 仿真时 Agent 调 `create --alias` 幂等分支凑合的根因）。

### [PRIN-SOP-8] 用户永不直接调用 CLI——Agent 是 CLI 的唯一调用方

完整调用链：

```
User (通过 Agent UI / 自然语言)
    ↓ chat / 语音 / 文字
Agent (LLM + SKILL.md + SOP 编排)
    ↓ 多个工具，按意图路由：
    ├─ subprocess.run(["xu", ...])  →  xu CLI
    │      - 5 SOP（create / ingest / query / doctor / config）
    │      - 卸载 xu-wiki（`xu uninstall --execute`，只卸程序本体）
    └─ bash / shell 工具             →  pip install / pip upgrade / pip show
                                          （install 类不经过 xu CLI）
CLI (确定性引擎)
    ↓ 文件 / DB
Wiki data
```

**用户**与系统交互的唯一通道是 **Agent 的 UI**（聊天框、语音、IM 客户端……），用户的输入永远是自然语言意图，不是 shell 命令。**Agent** 是 **xu CLI** 的**唯一合法调用方**——CLI 看不到 User、只看到 Agent；User 看不到 CLI、只看到 Agent。

关键澄清：**PRIN-SOP-8 的管辖范围是 `xu` CLI，不是 Agent 的所有工具**。Agent 通常自带一整套工具：

| Agent 的工具 | 用途 | 是否属 PRIN-SOP-8 管辖 |
|---|---|---|
| `xu` CLI（subprocess） | 5 SOP + uninstall 全走这条 | ✅ 是 — User 绝不直接调 |
| bash / shell 工具 | pip install / pip upgrade / pip show | ❌ 否 — pip install 类不归 xu CLI |
| 文件读写工具 | 读 wiki 文件（只读场景） | ❌ 否 — 仅在 SOP 编排内使用 |
| 网络工具 | （xu 不应使用） | n/a |

具体到**软件生命周期**：

- **install / upgrade / version 查询**：用户在人话里说"装 / 升 / 查版本"，Agent 用自己的 **bash 工具**跑 pip 命令。这条路径**不经过 xu CLI**——`xu` 不重复造 pip 的轮子（[CONST-SOP-3] 上半段）。
- **uninstall**：用户说"卸载 xu-wiki"，Agent 调用 `xu uninstall --execute` 即可——CLI 自己处理 skill bundle 清理（读 manifest 反向删除）、pip/pipx 卸载、config 目录清理。Wiki 数据（知识库）永远不动——这条路径**禁止**出现删除 wiki 数据的选项。

由此推导的设计约束：

1. **CLI 的人类可读性是次要的**：CLI 的输出（4-key JSON）是给 Agent 解析的，不是给用户看的。文档不应假设「用户直接跑 `xu query ...`」。任何「给用户看的输出」必须由 Agent 在 SOP 层把 JSON 翻译成自然语言。
2. **CLI 错误信息也要给 Agent 看，不是给用户看**：`data.error_class` 是给 Agent 路由用的；Agent 拿到 error 之后才能决定「该问用户」「该换个 CLI」「该直接拒绝」。
3. **User 看不到 CLI，但 SOP 错误要让 User 能理解**：Agent 是 User 的翻译官；User 的反馈（「不对」「我没说创建」「换一种问法」）必须经 Agent 重新理解后再决定调什么 CLI——User 永远不直接调 CLI。
4. **测试可以由开发者直接跑 CLI**：[BAN-TEST-1] 反例——开发者在自己的 shell 里跑 `xu query --wiki kb ...` 验证逻辑是合理的，因为开发者**临时扮演 Agent**。但这不是 User 的常态；自动化测试脚本也不算 User。
5. **README 的「Quick start」示例是给 Agent 看的**：不是给 User 看的——User 通过 `/xu-wiki <verb>` 进入 SOP，Agent 在 SOP 内调这些 CLI。把 Quick start 误读成「给 User 的使用教程」会让 User 误以为需要手动敲命令，从而绕过 Agent 的意图判断（违反 [PRIN-SAFETY]）。
6. **CLI 必须对 Agent 友好，不对 User 友好**：参数命名以 Agent 解析的清晰度为先，不以「用户好记」为先（User 反正不直接调）。

理由：把 User 排除在 CLI 调用链外，才能把「意图判断」交给 Agent（[PRIN-QRY-1] / [PRIN-SAFETY]）；如果 User 直接调 CLI，CLI 必须同时承担「意图判断」和「执行」两个职责，反而破坏了「CLI 不调 LLM、确定性到底」的 [PRIN-QRY-3]。分层就是为这个分工服务的。

反例（要禁止的）：
- 「让 User 在终端手动跑 `xu create ...`」——绕开 Agent 的「先问用户再执行」环节（[PRIN-SAFETY]），可能用错 `--name` / `--path` 污染数据。
- 「CLI 输出做成人话格式给 User 看」——既增加 CLI 复杂度（要判断 LLM 是否在场），又打破分层；正确做法是 Agent 翻译。
- 「文档教 User 用 CLI」——把 Skill 的 SOP 编排能力废弃了，User 永远不会知道某个 CLI 已经 deprecated。

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

### [BAN-SOP-5] 文档不许教 User 直接跑 CLI

README / SOP / SKILL.md 不应出现「用户直接运行 `xu <verb> ...`」的指引——CLI 的用户是 Agent，不是 User。任何 CLI 调用示例必须明确标注「这是 Agent 内部调用的示例」（[PRIN-SOP-8]）。允许的例外：

- **开发者临时扮演 Agent**：在本机 shell 跑 `xu query ...` 验证逻辑；这是 [PRIN-SOP-8] 第 4 条的反例豁免，不算 User。
- **CI / 自动化测试脚本**：`tests/` 下的 `e2e_verify.sh` 等可直跑 CLI，因为脚本**扮演 Agent**，且其输出会被测试框架解析。

但 README 的 Quick start、SOP 的「Workflow」、SKILL.md 的「Quick start for the agent」——**这些文档的读者都不是 User**：

| 文档 | 读者 |
|---|---|
| README Quick start | **Agent**（读 SKILL.md 的 Agent 上下文） |
| SKILL.md Quick start | **Agent**（被加载到 Agent 的 system prompt） |
| SOP 的 Workflow 段 | **Agent**（被加载到 Agent 的上下文） |
| 设计文档（design-docs/） | **开发者**（本机 shell 跑 CLI 验证逻辑） |

User 不读这些文档；User 通过 `/xu-wiki <verb>` 进入 SOP，然后 Agent 在 SOP 内自己查这些文档。

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

### [CONST-SOP-3] install 与 uninstall **不对称**：install 走 pip；uninstall = skill bundle（Agent 自删）+ program body（`xu` CLI）

**这是非对称设计**：

| 操作 | 谁负责 | 为什么 |
|---|---|---|
| **install** | `pip install xu-wiki[parse,nlp,vision]` | pip 一行就能装上；不需要 CLI 包装。User 或任何 Agent 用 bash tool 调一次 pip 即可。 |
| **uninstall** | `xu uninstall` 全包（skill bundle + 程序本体 + config） | 见下。 | |

**为什么 uninstall 必须有 CLI 命令**（不能也走 pip）：

1. **xu-wiki 是 GitHub 项目，不是预装品牌**。User 在真实场景中是把 **GitHub URL** 给 Agent，Agent 从 URL 读 `SKILL.md` 才知道 xu-wiki 是什么。没有 `/xu-wiki` slash 命令、没有 SKILL.md，Agent 不知道 xu-wiki 这个项目存在，更不知道如何卸载。
2. **可发现性原则**：为了让 Agent 能帮助 User 卸载，必须有一个**在 SKILL.md 里可见的、agent 可调用的入口**——这个入口就是 `xu uninstall`。如果只有 `pip uninstall xu-wiki`，SKILL.md 里不会写"卸载靠 pip"——因为 pip 不属于 xu-wiki 项目，SKILL.md 是 xu-wiki 自己的文档。
3. **不对称原则**：`xu uninstall` 读 manifest 自己删 skill bundle；程序本体由 `xu uninstall` 处理；**wiki 数据（用户的知识）永远不删**。

**为什么 install 不需要 CLI 命令**（保持简单）：

1. `pip install xu-wiki` 是单行命令，不需要编排。
2. 没有"副作用范围选择"——装就是装，没有"只装包不装依赖"之类的选项需要 UI。
3. User 直接跑 pip 或 Agent 用 bash tool 跑 pip 都一样简单；包一层 CLI 反而违反「别人的软件就是安装很顺利」原则。
4. 装失败时 pip 的报错已经很清晰，不需要 xu 翻译。

**调用入口**：

- **install** — Agent 用自己的 bash / shell 工具（不是 `xu` CLI）执行 `pip install`。`xu` CLI **不参与 install**。
- **uninstall** — Agent 用自己的 skill 管理器删除 skill bundle；然后调用 `xu uninstall --execute`（不走 bash tool 直接调 pip）。

**User 输入到工具的完整路由**：

| User 输入 | 意图 | Slash 命令 | Agent 的工具 |
|---|---|---|---|
| 任何 wiki 数据请求 | 5 SOP 之一 | `/xu-wiki <verb>` | `xu` CLI（subprocess.run） |
| `把 xu-wiki 卸了` / `uninstall xu-wiki` / `remove xu-wiki` | 卸载软件 | `/xu-wiki config`（uninstall 入口） | Agent 自删 skill bundle + `xu` CLI（`xu uninstall --execute`） |
| `装一下 xu-wiki` / `install xu-wiki` | 装软件 | （**没有 slash 命令**） | bash tool（`pip install`） |
| `升级 xu-wiki` / `upgrade xu-wiki` | 升软件 | （**没有 slash 命令**） | bash tool（`pip install --upgrade`） |
| `xu-wiki 是不是最新版` / `version of xu-wiki` | 查版本 | （**没有 slash 命令**） | bash tool（`pip show xu-wiki`） |

**关键约束**：
- Agent **绝不**直接调 `pip uninstall`——绕过 SKILL.md 可发现性。一律走 `xu uninstall --execute`。
- Agent **绝不**自己发明 `/xu-wiki install` / `/xu-wiki uninstall` / `/xu-wiki upgrade` slash 命令——它们都不存在，install/upgrade 由 bash tool 负责，uninstall 由 `/xu-wiki config` 内部的 `xu uninstall` 负责。
- Agent **绝不**在 uninstall 时提出或执行删除 wiki 数据的操作——wiki 数据是用户的知识，不属于任何软件。
- User **绝不**直接调 `pip` 任何命令——PRIN-SOP-8：User 永远不接触 CLI / shell，Agent 是唯一合法执行者。

### [CONST-SOP-4] 5 SOP 数量固定，不轻易增减

新增 SOP 是重大架构变更，需要新增独立设计文档并触发 skill description 重写。当前 5 个是闭合集合。

---

## 五、五大 SOP 定义

### 5.1 SOP: create — 建库

**意图**：用户说「我要建一个知识库」。

**调用步骤**：
1. （隐含前置）机器上已 `pip install xu-wiki[parse,nlp,vision]`（[PRIN-CRT-1]）
2. Agent 必须先问齐 `--name` 与 `--path`（hard rule 8）
3. 调用 `xu create --name <n> --path <abs> [--alias <a>]`
4. （可选）调用 `xu wikis` 验证注册成功

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
2. **第一步：识别内容形态**（[PRIN-ING-13]）
   - 「散文 / 文档」(PDF / DOCX / Markdown / 文本) → 走两阶段
   - 「代码 / 命令块」 → `ingest-commit --native` 直接 commit
   - 「表格化 / 相册」(一组图片 / 一组参数) → 走 `ingest-album` 单次
3. **散文 / 文档**:对每个源文件执行两阶段（[PRIN-ING-1]）：
   - Phase 1：`xu-wiki ingest-file --wiki <w> --file <abs>`
   - Phase 2：`xu-wiki ingest-commit --wiki <w> --title <t> --content-type article`
4. **代码块**:`xu-wiki ingest-commit --wiki <w> --title <t> --content-type article --native "<code block>"`
5. **相册 (album) [PRIN-ING-14 单次原则]**:
   - 必问 1:每张图要不要加 vision 描述?(`--vision` 标志,见 [PRIN-SOP-7])
   - 必问 2:主题 title / node-path / layout (table 默认)
   - 一次调用:`xu-wiki ingest-album --wiki <w> --title T --files abs1,abs2,... --node-path P --layout table`
6. （可选）建关系：`xu-wiki query-relation add --wiki <w> --from-uid ... --to-uid ...`
7. （可选）建 L2 / L3：`xu-wiki list create` / `xu-wiki report create`
8. （可选）调用 `xu-wiki nodes --wiki <w> --layer Page` 验证写入

**失败模式**：
- Phase 1 失败 → 文件解析失败，不创建 L1 节点
- Phase 2 失败 → temp 文件保留（不删），Agent 报告用户决定
- Album 任一 source_hash 命中已存在 → 重复图片跳过，其余正常写入；全部命中才拒绝（[BAN-ING-4] / [CONST-ING-3]）
- Album 缺 title / files / node-path → 必问用户，不许猜（[PRIN-ING-11]）
- 关系数 > 50 → 自动 LRU 淘汰队尾（[PRIN-ARCH-7~10]）
- Report 缺证据链 → `EmptyEvidence`（[BAN-ARCH-5]）

**成功标志**：Phase 2 或 `ingest-album` 返回 `data.uid`。

### 5.3 SOP: query — 检索

**意图**：用户说「我要找知识」。

**调用步骤**：
1. Agent 把用户查询词分词后合成逗号分隔的 `--keywords` 列表（[PRIN-ARCH-12]）
2. `xu-wiki query --wiki <w> --keywords <kw,kw,kw> [--top-k N]`
3. 命中后按用户意图调：
   - 读单节点 → `xu-wiki read --wiki <w> --uid <uid>`
   - 看 L2 对比 → `xu-wiki list show --wiki <w> --uid <uid>`
   - 看 L3 结论 → `xu-wiki report show --wiki <w> --uid <uid>`
4. （可选）查节点是否存在 → `xu-wiki nodes --wiki <w>`

**失败模式**：
- `--keywords` 空 → Agent 必须问用户（hard rule 8）
- 0 命中 → 不许自动切换模式，告知用户换关键词
- `list_hint` / `report_hint` 提示 → Agent 决定是否跟进，CLI 不擅自动作（[PRIN-QRY-1]）

**成功标志**：`query` 返回 `data.hits` 非空。

### 5.4 SOP: doctor — 检查 / 修复 / 破坏性操作

**意图**：用户说「我要检查 wiki 健康」「删一个节点」「移位节点」「重衍生层」等一切涉及**修改 wiki 内容**或**修复不一致**的操作。

**典型用户意图 → CLI 编排**（按 [PRIN-SOP-7] 必须显式列出）：

| 用户意图 | 编排 |
|---|---|
| 「全面检查」「健康检查」 | `doctor-all --wiki <w>` |
| 「检查 fields / files / relations / l1-immutable / report-evidence」 | 对应 `doctor-{xxx} --wiki <w>` |
| 「修了再告诉我」（自动修） | `doctor-all --wiki <w> --fix`（先告诉用户再应用） |
| 「删节点 X」 | `delete-node --wiki <w> --uid X`（若被 L2/L3 引用则先确认 `--force`） |
| 「移位 / 移动 节点 X 到 Y」 | **当前无对应 CLI** → SOP 拒绝并解释（见下） |
| 「重衍生层」「重建 LRU」 | `rebuild --wiki <w> --granularity keep-l1`（默认不动 L1） |

**意图不可达的显式拒绝**（[PRIN-SOP-7]）：

> 用户：「请将 X 节点移位到 Y 目录下」
>
> Agent 在 doctor SOP 内识别意图 = 移动节点位置，但当前 CLI 集合无对应原子能力（节点无「目录」概念）。
>
> 正确响应：
> ```
> {
>   "status": "warning",
>   "data": {
>     "intent": "move_node",
>     "supported": false,
>     "reason": "xu-wiki nodes have no filesystem location; moves are not first-class"
>   },
>   "message": "node-move intent is not supported by current CLI capabilities",
>   "hints": [
>     "if you want to relocate data: delete X (--force if referenced) and re-ingest at Y",
>     "if you want to reclassify layer: this is a semantic change, not a move; open an issue"
>   ]
> }
> ```

**调用步骤**（按典型路径）：
1. Agent 解析用户意图 → 选 CLI（按上表）
2. 编排时遇 `--fix`：先告诉用户会改什么，再应用
3. 遇 `delete-node`：先 `doctor-all` 或 `nodes` 检查 L2/L3 引用，按需 `--force`
4. 遇 `rebuild`：必须先确认 `--granularity`（[PRIN-ARCH-6]）

**失败模式**：
- `--fix` 失败 → 不自动重试，告知用户
- 任何 doctor 报错 → 不许跳过；列出全部 issue
- `delete-node` 被 L2/L3 引用且无 `--force` → `NodeReferenced`
- `rebuild` 必须先确认粒度（[PRIN-ARCH-6]）
- **意图无对应 CLI** → SOP 拒绝并给 hints（[PRIN-SOP-7]）

**成功标志**：
- 检索意图：`doctor-all` 返回 `data.total_issues = 0`
- 删除意图：`delete-node` 返回 `data.deleted = true`
- 重建意图：`rebuild` 返回 `data.layers_rebuilt` 非空
- 不可达意图：`status = warning` 且 `data.supported = false`

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
| **ingest** | `ingest-file` | Phase 1（PRIN-ING-1，散文/文档形态） |
| | `ingest-commit` | Phase 2（含 `--native` 走代码块形态） |
| | **`ingest-album`** | **相册子流 (PRIN-ING-14, 表格形态, 单次写入)** |
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
| | `doctor-fields / files / relations / l1-immutable / report-evidence` | 细分 |
| | `rebuild` | 修复（衍生层） |
| | `delete-node` | 清理（删 dangling 节点） |
| | `nodes` | 找 dangling（doctor 也需要看节点列表，[PRIN-SOP-3] 共享） |
| **config** | `wikis` | 查看注册表 |
| | `alias set / unset / show` | 别名管理 |
| | `register` | 注册已有目录（不写文件） |
| | `unregister` | 取消注册（不动 wiki 本体） |
| | `config set-mineru-key / show / path` | 全局配置读写 |
| | `nodes` | 看 DB 内容（config 也可检视 DB） |
| | `delete-node` | 未来若 SOP-config 加「清空数据」子意图，可嵌入 |
| **不属于 SOP** | (none — install/uninstall 由 pip 处理) | pip 包管理，不属于 CLI 范畴 |

> **约束 [CONST-SOP-2]**：上表每一个 CLI 命令都必须能反向查到至少一个 SOP。无主命令 = 设计漏洞。
>
> 注意：「嵌入」≠「所属」。表里只列**当前会嵌入**的 SOP；如果将来某 SOP 有了新意图用到同一 CLI，就再加一行——这是按需嵌入，不是固化绑定（[PRIN-SOP-3] / [PRIN-SOP-6]）。

---

## 七、与 pip 的边界（install / uninstall 由 pip 处理）

`pip install xu-wiki[parse,nlp,vision]` 是安装入口；程序本体的卸载通过 `xu uninstall --execute`（不走 pip）。CLI 的职责边界：管理 wiki 数据（通过 5 SOP）；程序本体的卸载（`xu uninstall --execute`）；不动 venv / symlink / 任何「让 CLI 自身能跑起来」的东西。**注意**：wiki 数据（用户的知识）是用户自己的，Agent 在 uninstall 时不得提出或执行删除 wiki 数据的操作。

---

## 八、与其他设计文档的关系

| 文档 | 关系 |
|---|---|
| 01-wiki-architecture.md | SOP 层建立在三层节点 + 50 条关系架构之上 |
| 02-create.md | 是 SOP-create 的 CLI 实现文档 |
| 03-install.md | install 由 pip 处理（见该文档） |
| 04-uninstall.md | uninstall 原则见本文 [CONST-SOP-3]；程序本体由 `xu uninstall` 卸，skill bundle 由 Agent 自删，wiki 数据永不删除 |
| 05-ingest.md | 是 SOP-ingest 的 CLI 实现文档 |
| 06-query.md | 是 SOP-query 的 CLI 实现文档 |
| 07-doctor.md | 是 SOP-doctor 的 CLI 实现文档 |
| **08-sop-architecture.md（本文）** | **定义 SOP 层与 CLI 层的边界** |

> 本文档（08）是 SOP 层的**总纲**；02 / 05 / 06 / 07 是各 SOP 的 CLI 实现细节。未来若 SOP-config 落地，应新增 `10-config.md` 作为 SOP-config 的 CLI 实现文档。

---

## 九、自检清单

**原则**：
- [ ] slash command ≠ CLI 子命令（[PRIN-SOP-1]）
- [ ] SOP 是多步编排（[PRIN-SOP-2]）
- [ ] CLI 是原子能力，SOP 是其按需组合（[PRIN-SOP-3]）
- [ ] 错误恢复显式定义（[PRIN-SOP-4]）
- [ ] 副作用必须经由 CLI（[PRIN-SOP-5]）
- [ ] SOP 边界由用户意图决定，不由 CLI 决定（[PRIN-SOP-6]）
- [ ] SOP 接受自然语言意图，不是只接受动词命令（[PRIN-SOP-7]）

**禁令**：
- [ ] Agent 不许把 SOP 当 CLI 调（[BAN-SOP-1]）
- [ ] SOP 不许绕过 CLI 直接写文件（[BAN-SOP-2]）
- [ ] SOP 不许发明新 CLI（[BAN-SOP-3]）
- [ ] SOP 不许隐式副作用（[BAN-SOP-4]）

**约束**：
- [ ] SOP 在 SKILL.md 完整文档化（[CONST-SOP-1]）
- [ ] SOP → CLI 映射显式且唯一反向可查（[CONST-SOP-2]）
- [ ] install / uninstall 由 pip 处理，不属 5 SOP（[CONST-SOP-3]）
- [ ] 5 SOP 数量固定（[CONST-SOP-4]）

---

**作者注**：SOP 层是 Agent 时代 wiki 引擎的关键抽象——它把「用户在说什么」与「代码在做什么」解耦，让 skill 描述稳定、CLI 命令独立演化、Agent 工作流可验证。建议把 SOP 视为**协议级契约**：每加一个 SOP 是 API 加一个端点，必须有设计文档 + SKILL.md 段落 + 至少一个 SOP-recipe 样例三件套，缺一不可。
