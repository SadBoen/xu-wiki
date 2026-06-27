# 04 — `uninstall` 模块设计原则

> **目的**：本文是面向开发者的设计原则文档，用于实现 `uninstall` 风格的卸载命令。
> **范围**：仅覆盖 uninstall 命令本身。
> **风格**：每条原则标 [PRIN-N]（原则）/ [BAN-N]（禁令）/ [CONST-N]（约束）。
> **不在本文档**：具体参数、命令、路径——这些是实现细节，由开发者决定。

---

## 一、一句话定位

`uninstall` 是**软件的逆操作**：把 install 装进系统的东西原样拆出来。**它不动用户的知识**——只动软件自己。

## 二、原则

### [PRIN-UNINST-1] 卸载的是软件，不是知识

把 xu-wiki 想象成**图书馆管理员**——管理员辞职（卸载）→ 不能销毁图书馆、不能拆除书架、不能烧书。办公室的工牌、工位、私人物品要清理，但藏书完整保留。

这是 uninstall 的**最高原则**，优先级高于一切其他原则。任何与它冲突的「清理动作」都是 bug。

### [PRIN-UNINST-2] 清理必须彻底——零残留

凡是 install 写进系统的东西，uninstall 必须能反向拆除。**残留 = bug**。

开发时要穷举 install 的每一步输出，把每一项对应到 uninstall 的清理项——少一项就是留垃圾。

### [PRIN-UNINST-3] 安装的反函数——对称性原则

> **安装时往系统里装了什么，卸载就要拆什么。**

这是 [PRIN-UNINST-2] 的实现策略——不是凭感觉列清单，而是**逐行对照 install 步骤**，每个 install 动作对应一个 uninstall 动作。

判断「要不要删」的唯一方法 = 「install 是不是写过这里」。不是看文件名像不像、不是看路径像不像。

### [PRIN-UNINST-4] Agent 管的资源，让 Agent 自己拆——协同原则

SKILL / 包索引 / Agent 内部缓存——这些资源**不属于本程序直接控制**。必须**调用那个资源所在系统的 API** 让它自己拆。

例如 SKILL：
- ❌ 错：直 rm Agent 私有目录
- ✅ 对：调 Agent 自己的「卸载 SKILL」接口，让它决定怎么拆

理由：
1. 被调用方可能有引用、缓存、备份、审计记录——直删会留下脏状态
2. 未来版本可能改变文件位置——走 API 让被调用方决定
3. 跨 Agent 兼容性——不同 Agent 私有目录路径不同

### [PRIN-UNINST-5] 卸完再查一次——验证原则

Agent 卸载 SKILL 后，**不能假定它真删干净了**——必须**再查一次**：
- SKILL 目录是否还在
- SKILL 在 Agent 索引里的条目是否还有
- 其他 install 写过的文件是否还在

残留发现 → **继续清理**（按 uninstall 的逻辑，不是 install 的逻辑）。这是 [PRIN-UNINST-2] 的兜底——即使前面漏了，这里再补。

### [PRIN-UNINST-6] 默认是 dry-run——安全护栏

`uninstall` 默认**不实际执行任何破坏性操作**。必须显式确认才真删。

理由：卸载是不可逆的——一旦删了 venv，重装要重新装几百个包；删了配置，用户填的 API key 也要重填。

dry-run 必须**穷举将做什么**，包括 [PRIN-UNINST-1] 例外（明示「知识库本体不动」），让用户清楚边界。

## 三、禁令

### [BAN-UNINST-1] 绝不删除知识库本体

> **任何情况下，uninstall 都不能删除知识库本体。**

这是 [PRIN-UNINST-1] 的硬编码版。即使：
- 用户传 `--purge` → 删的是**项目目录**（软件本体），不是知识库本体所在目录
- 用户传 `--all` / `--force` → **仍然不删**知识库
- 没有任何参数能让它删知识库

本体只能由用户用 `rm -rf` 主动销毁，或通过 CLI 的 `delete-node` / `unregister` 命令——**绝不能**由 uninstall 顺手删。

### [BAN-UNINST-2] 不直删 Agent 管的资源

与 [PRIN-UNINST-4] 对应——Agent 私有目录、Agent 索引条目、包管理器的索引——必须走对应系统的 API，不直删。

### [BAN-UNINST-3] 不自动做超出「卸载」的事

uninstall 不应该：
- 自动 clean 用户的 home 目录
- 自动 remove 用户的 shell 配置
- 自动 reset 用户的环境变量

这些是用户后续自己决定的事。

### [BAN-UNINST-4] 不动 L1 修订历史

即使 wiki 本体被 `delete-node` / `unregister` 操作影响，patches（L1 修订历史）也必须**按对应数据生命周期处理**——不能由 uninstall 顺手删。

理由：
- patches 是 frontmatter 内嵌字段，是 wiki 自己的状态，不是软件配置
- L1 不可变性要求修订历史可追溯——uninstall 删这些字段 = 销毁知识库历史 = 违反 [PRIN-ARCH-3]

## 四、约束

### [CONST-UNINST-1] 必须有项目标识才能识别

卸载前必须确认目标目录**确实是 xu-wiki 项目**——必须含约定的 marker（如 `pyproject.toml` 等）。

理由：防误删用户目录。

### [CONST-UNINST-2] 幂等性

重复执行 uninstall 结果一致——第二次开始基本是 no-op，不报错。这是 [PRIN-UNINST-2] 的副作用：删过的就不在了，再删一次等于不存在。

### [CONST-UNINST-3] 顺序敏感性

某些资源必须**先卸后删**——比如先卸 SKILL，再删 CLI 入口（否则调 Agent API 时 PATH 里找不到 CLI）。

开发时务必按 install 的**反向顺序**排列清理动作——先卸的 install 时**最后**装的，后卸的 install 时**最先**装的。

### [CONST-UNINST-4] 4 键 JSON 协议

返回 `status/data/message/hints`——dry-run 时 `data` 含「将删除列表」，执行后 `data` 含「实际删除列表」，便于审计。

### [CONST-UNINST-5] 不调 LLM

纯确定性逻辑：路径判断、文件操作、调用其他系统 CLI。无 LLM 调用。

## 五、自检清单（开发时勾选）

**原则**：
- [ ] 卸载的是软件不是知识（[PRIN-UNINST-1]）
- [ ] 清理彻底零残留（[PRIN-UNINST-2]）
- [ ] 安装的反函数——对称性（[PRIN-UNINST-3]）
- [ ] Agent 资源让 Agent 自己拆（[PRIN-UNINST-4]）
- [ ] 卸完再查一次（[PRIN-UNINST-5]）
- [ ] 默认 dry-run（[PRIN-UNINST-6]）

**禁令**：
- [ ] 绝不删知识库本体（[BAN-UNINST-1]）
- [ ] 不直删 Agent 资源（[BAN-UNINST-2]）
- [ ] 不自动做超出卸载的事（[BAN-UNINST-3]）

**约束**：
- [ ] 项目标识校验（[CONST-UNINST-1]）
- [ ] 幂等性（[CONST-UNINST-2]）
- [ ] 清理顺序按 install 反向（[CONST-UNINST-3]）
- [ ] 4 键 JSON（[CONST-UNINST-4]）
- [ ] 不调 LLM（[CONST-UNINST-5]）

---

**作者注**：uninstall 的灵魂是 [PRIN-UNINST-1]（软件 vs 知识）和 [PRIN-UNINST-3]（对称性）。开发时不要陷入「列步骤」的陷阱——先想 install 装了什么，再想 install 没装什么（不能动的部分）。

具体清理哪些文件、调什么 API、走什么路径——这些是实现细节，由开发者决定。设计文档只回答「为什么这样」「什么不能动」——不回答「具体怎么写脚本」。