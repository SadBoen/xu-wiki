# 03 — `install` 模块设计原则

> **目的**：本文是面向开发者的设计原则文档，用于实现 `install` 风格的安装流程。
> **范围**：仅覆盖安装流程本身。
> **风格**：每条原则标 [PRIN-N]（原则）/ [BAN-N]（禁令）/ [CONST-N]（约束）。
> **不在本文档**：具体参数、命令、路径——这些是实现细节，由开发者决定。

---

## 一、一句话定位

`install` 把整套工具**装到用户机器上**，让 CLI 可用、让 Agent 能看到 SKILL、让配置可读写。它**不动**用户已有的知识——安装前后用户的知识完整无损。

## 二、原则

### [PRIN-INST-1] install 装的是「能力」，不是「数据」

把 install 想象成给图书馆管理员配装备：发工牌、安排工位、装办公软件。**不**搬图书馆、**不**动藏书。

推论：install 完成后，CLI 能跑、SKILL 已注册、配置可读写——但任何 wiki 实例的「藏书」必须完好如初。

### [PRIN-INST-2] 隔离是 install 的存在理由

如果 install 跟系统 Python、系统 PATH、全局配置混在一起，那 install 跟「把软件 cp 到 /usr/bin」没有本质区别——污染系统、版本冲突、卸不干净。

install 必须与系统保持**清晰边界**。具体如何隔离是实现细节，但**「不污染系统」**是 install 的存在理由。

### [PRIN-INST-3] Agent 管的资源，让 Agent 自己装——协同原则

SKILL 属于 Agent 的索引体系。install 不该绕开 Agent 自己操作这些资源。

正确做法：调用 Agent 的「安装 SKILL」接口（如 hermes 的对应命令），由 Agent 决定：
- 装到哪个 category
- 怎么索引、备份、升级

直 cp 到 `~/.hermes/` 是蛮力——绕开 Agent 的引用、缓存、审计，会留下脏状态。

### [PRIN-INST-4] 幂等性

用户可能装过一次、中途失败、再装；可能装过老版本想升级；可能只想确认安装状态。

每种情况下重复 install 都不应该破坏已建好的东西——venv 不重建、配置不覆盖、用户数据绝不动。

### [PRIN-INST-5] 失败不留半成品

install 中途失败（pip 装一半、网络超时、磁盘满），必须能回滚到 install 开始前的状态。

推论：先在临时位置建完整结构，全成功再落位；失败时清理已建的临时东西。**已存在的用户数据绝不动**——回滚只清 install 自己建的东西。

### [PRIN-INST-6] 步骤顺序由因果决定，不是由优化决定

install 步骤之间有强因果关系——后一步依赖前一步。开发时不要为了「并行」、「跳步」、「优化」打乱因果链——确定性安装流程里，并行只引入 bug。

## 三、禁令

### [BAN-INST-1] 绝不碰用户数据

install 永远不动用户已有的任何 wiki 实例。即使项目目录已存在、即使里面有 `raws/` `nodes/` `/.xu/`，都视为「复用」，**绝不**删、**绝不**覆盖。

### [BAN-INST-2] 绝不装到系统级 Python

系统 Python / 系统 site-packages / 系统 PATH——install 永远不该主动改这些地方。

理由：PEP 668 / externally-managed-environment / 多项目版本冲突——这些都是「不隔离」的副作用。开发时务必保持隔离。

### [BAN-INST-3] 绝不直写 Agent 的资源目录

与 [PRIN-INST-3] 对应——必须走 Agent 的 API，不直 rm / 直 cp 到 `~/.hermes/`、`~/.aider/` 等任何 Agent 的私有目录。

### [BAN-INST-4] 绝不假设 Python 路径

不能假设任何具体 Python 路径一定可用（如系统级 `python` / `python3` / 各类绝对路径）。开发时需要探测多种可能的 Python 来源，按优先级降级尝试。

### [BAN-INST-5] 不自动做超出「安装」的事

install 不应该：
- 自动 clone 到用户没指定的目录
- 自动跑测试
- 自动 create 一个示例 wiki
- 自动给 Agent 配置额外的 hooks

这些都是用户后续自己决定的事。

## 四、约束

### [CONST-INST-1] 隔离策略：venv 必须隔离（pipx 推荐，项目本地作备选）

**最有约束力的默认约定**：

- venv 必须与系统 site-packages 隔离
- **推荐**：`pipx` — 全局隔离 venv（`~/.local/share/pipx/venvs/xu-wiki/`），PEP 668 安全，CLI 软链到 `~/.local/bin/`
- **备选**：项目本地 venv（`<project>/.venv/`），适合需要项目级隔离的场景

理由：pipx 提供一键隔离（venv + symlink + PEP 668 处理），是当前最佳实践。项目本地 venv 适合手动管理或 pipx 不可用的环境。两者都满足隔离要求。

### [CONST-INST-2] CLI 是软链不是真文件

CLI 入口必须用软链（symlink）——这样代码更新时软链不用改，源码改了立即生效。

开发时不要把 CLI 入口复制成独立文件——那是反模式。

### [CONST-INST-3] 项目标识校验

复用项目目录前，必须确认是 xu-wiki 项目（含约定的 marker）。否则拒绝继续——防误把别的项目当 xu-wiki 覆盖。

### [CONST-INST-3a] install 不创建 wiki 内部结构

install 只装软件本身——不创建任何 wiki 实例的内部组件(`raws/` `nodes/` patches 表 IDF 词频表 等由 `create` 命令负责)。这些是 wiki 自己的事,install 时不存在。误启动「自动 create 示例 wiki」会污染用户数据空间(违反 [BAN-INST-5])。

### [CONST-INST-4] 4 键 JSON 协议

返回 `status/data/message/hints`——虽然 install 主流程可能是 shell 脚本，但脚本末尾调用的任何 CLI 命令必须遵循 4 键协议。

### [CONST-INST-5] 不调 LLM

纯确定性逻辑：路径判断、文件操作、调用其他系统 CLI。无 LLM 调用。

### [CONST-INST-6] 安装文档的唯一权威源是 README

安装 / 部署的步骤说明**只写在仓库根目录的 `README.md`**——因为 README 在 `pip install` 之前就能在 GitHub 上读到，是用户/Agent 拿到项目时的第一入口。

约束：

- 安装命令、PATH 配置、`xu deploy skill`、selfcheck 验证流程——**全部以 README 为准**，单点维护。
- skill bundle（`src/xu/skills/`）**不**包含任何安装内容（见 `09-skill-architecture.md` [BAN-SKILL-3a]）——bundle 是装后资源，写安装说明是时序悖论。
- 其他文档（SKILL.md、各 SOP）提到安装时，**只写一句指向 README**，绝不复述步骤——复述就是漂移的根。

理由：安装说明在多个文件各写一份，必然随时间漂移、互相矛盾。唯一权威源 + 一句话指路，是杜绝漂移的唯一办法。

## 五、自检清单（开发时勾选）

**原则**：
- [ ] install 装能力不装数据（[PRIN-INST-1]）
- [ ] install 与系统隔离（[PRIN-INST-2]）
- [ ] SKILL 走 Agent API（[PRIN-INST-3]）
- [ ] 幂等性（[PRIN-INST-4]）
- [ ] 失败原子回滚（[PRIN-INST-5]）
- [ ] 步骤顺序由因果决定（[PRIN-INST-6]）

**禁令**：
- [ ] 不碰用户数据（[BAN-INST-1]）
- [ ] 不装到系统 Python（[BAN-INST-2]）
- [ ] 不直写 Agent 目录（[BAN-INST-3]）
- [ ] 不假设 Python 路径（[BAN-INST-4]）
- [ ] 不自动做超出安装的事（[BAN-INST-5]）

**约束**：
- [ ] venv 隔离（pipx 推荐 / 项目本地备选）（[CONST-INST-1]）
- [ ] CLI 软链（[CONST-INST-2]）
- [ ] 项目标识校验（[CONST-INST-3]）
- [ ] install 不创建 wiki 内部结构（[CONST-INST-3a]）
- [ ] 4 键 JSON（[CONST-INST-4]）
- [ ] 不调 LLM（[CONST-INST-5]）
- [ ] 安装文档唯一权威源 = README（[CONST-INST-6]）

---

**作者注**：本模块的灵魂是 [PRIN-INST-1]（能力 vs 数据）和 [PRIN-INST-2]（隔离）。具体怎么隔离、装到哪个目录、调什么 API——这些都是实现细节，由开发者决定。

设计文档只回答「为什么这样」「什么不能动」——不回答「具体怎么写脚本」。
