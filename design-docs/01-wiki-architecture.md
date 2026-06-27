# 01 — Wiki 三层架构设计原则

## 安全总纲

### [PRIN-SAFETY] 歧义即停——宁可问，不要猜

| 角色 | 行为 |
|---|---|
| **CLI** | 确定性——参数合法就跑，缺失/非法就报错。意图判断不是 CLI 的职责。 |
| **Agent** | 护栏在这一层——改变状态的命令之前，意图不明确就先问用户，绝不猜。 |

**边界**：「判断一个值」（内容归哪个分区）= 本职；「猜意图」（写错库名就建新库）= 必须停。

## 三层节点架构

```
Report — 主观智能（为什么/怎么办/如果…）
List  — 严谨对比（同属于/同类设备）
Page  — 冷冰冰客观（这页说了什么）
```

### [PRIN-ARCH-1] 三层各司其职

| 层 | 做 | 不做 |
|---|---|---|
| Page | 物理事实切片、原文留痕 | 不评价、不对比、不推演 |
| List | 横向聚合、YAML 成员 | 不评价、不推演 |
| Report | 逻辑推演、因果总结 | 不生产原始事实 |

### [PRIN-ARCH-2] 图书馆哲学

Page = 书，List = 索引，Report = 导读。Page 永远是 ground truth；List/Report 可重建。

### [PRIN-ARCH-3] Page 不可变 + 修订表

Page 生成后不直接修改 Markdown。修订走 frontmatter 内嵌 patches 字段（YAML 列表）叠加。

### [PRIN-ARCH-4] List 只对比不评价

### [PRIN-ARCH-5] Report 承载 LLM 推理，必须有证据链

### [PRIN-ARCH-6] [PRIN-ARCH-6a] Rebuild 粒度可调，Page 永远不动

## 关系管理

### [PRIN-ARCH-7] 每节点出边上限 50 条

### [PRIN-ARCH-8] 关系不分类，平等 LRU 链表

### [PRIN-ARCH-9] 满 50 条 → 弹队尾最久未触碰者

### [PRIN-ARCH-10] 建关系 = 触碰（进队首）；查询命中 = 前挪一位

## 检索工作流

### [PRIN-ARCH-11] 三层介入：Page 物理定位 → List 结构对齐 → Report 逻辑提炼

### [PRIN-ARCH-12] 关键词由 Agent 生成（含中英文），CLI 不做语义判断

### [PRIN-ARCH-13] 打分 = 标题×5 + body命中 + 层权重（Entity=2, Report=3, List=1, Page=0）

## 存储与元数据

### [PRIN-ARCH-15] Markdown + YAML Frontmatter — 可移植性，脱离 DB 知识完整

### [PRIN-ARCH-16] frontmatter + YAML — 结构化字段 + 灵活扩展

### [PRIN-ARCH-17] Markdown 是 ground truth，DB 可重建

### [PRIN-ARCH-18] 强 Schema 是质量底线

### [PRIN-ARCH-19] 物理分区防 IO 崩溃（node_path 即目录结构）

### [PRIN-ARCH-22] UID 稳定引用，永不重用

### [PRIN-ARCH-23] 三件套：`raws/` + `nodes/` + `.xu/`

### [PRIN-ARCH-24] node_path：用户指定优先，否则 Agent 判定

### [PRIN-ARCH-25] nodes 与 raws 按 node_path 镜像，reorganize 原子联动

### [PRIN-ARCH-26] 过程层（audit.jsonl）只用于诊断 SOP，不参与内容/修订

三层各司其职：内容层在 nodes/.md，修订层在 patches 表，过程层在 audit.jsonl。

## 模板与节点身份

### [PRIN-ARCH-21] 模板只决定内容形态（article/table/gallery），不决定层级

## 设计取舍

### [DESIGN-ARCH-1] List/Report 只存 .md，不存 SQLite

### [DESIGN-ARCH-2] Page 切分粒度 = 300 行正文（按余数）

### [DESIGN-ARCH-3] ripgrep 是检索底层引擎

### [DESIGN-ARCH-4] LLM 介入点：检索前生成关键词 / List 抽取维度 / Report 生成推理

### [DESIGN-ARCH-5] 删除是物理删除 + 审计 + 引用检查（删前查 List/Report 引用）

### [DESIGN-ARCH-6] 切片窗口：前后第一个标点，或 50 字符上限

### [DESIGN-ARCH-7] 邻域合并半径：物理距离 < 阈值则合并

## 禁令

### [BAN-ARCH-1] Agent 不直写任何 wiki 文件

### [BAN-ARCH-2] UID 永不重用

### [BAN-ARCH-3] Page 不改 Markdown

### [BAN-ARCH-4] List 不做评价

### [BAN-ARCH-5] Report 不可凭空生成

### [BAN-ARCH-6] 关系不无限增长

### [BAN-ARCH-7] 路径不越界

## 约束

### [CONST-ARCH-1] 4 键 JSON 协议

### [CONST-ARCH-2] frontmatter 必填：状态 bool / 层级 ∈ {Page,List,Report} / 形态 ∈ {article,table,gallery}

### [CONST-ARCH-3] UID 格式：8 位大写字母数字

### [CONST-ARCH-4] 关系是无分类 LRU 链表

### [CONST-ARCH-5] 写盘原子

### [CONST-ARCH-6] 每条 CLI 调用记一行 process-layer 日志（双路：per-wiki + global）

### [CONST-ARCH-7] frontmatter patches 字段（YAML list）

## 节点 CRUD

| 动作 | 命令 |
|---|---|
| 建 Page | `ingest-commit` |
| 建 List | `list create` |
| 建 Report | `report create` |
| 读 Page | `read --uid` |
| 删节点 | `delete-node` |
| 建关系 | `query-relation add` |
| 重建 | `rebuild --granularity keep-page\|keep-page-list\|full` |
