# xu-wiki 需求文档

十条核心规则，优先级从高到低排列。

---

## 1. 歧义即停

意图不明确时先问用户，绝不猜默认值。CLI 只管执行，意图判断交给调用者。

> 例：用户给了一个不存在的知识库名字 → 报错，不自作主张新建一个。

## 2. L1 不可变

Node_Page 一旦创建，正文永不直接修改。修订走叠加记录。

> 原始知识是地面真相。错字也不改原文——追加纠正补丁。

## 3. 只能通过 CLI 写入

禁止绕过 CLI 直接操作知识库文件或数据库。任何写入必须经过命令入口。

> 审计完整性依赖唯一写入口。绕过 CLI 的写入不记日志、不过校验、不留修订。

## 4. UID 永不重用

UID 包含时间戳分量，不同时间点生成的 UID 天然不碰撞。节点删后 UID 永久退役。

> 格式：2 位 base36 时间计数器 + 6 位随机字符 = 8 位。全局唯一。

## 5. 重复摄入不覆盖

同一文件二次摄入 → 直接拒绝，不创建新页面。去重检查在解析之前完成，不浪费计算资源。

> 按源文件 SHA256 去重。想更新内容用修订，不是重新摄入。

## 6. L3 不可凭空生成

报告必须有 ≥1 条 L1/L2 节点的引用。零引用的报告在创建时直接拒绝。

> 每条结论都必须有据可查。

## 7. 关系有硬上限

每个节点的关系边最多 50 条。超出则淘汰最久未访问的边（LRU）。

> 不分类、不评分。新边进队首，命中前移，满了弹尾。

## 8. 创建知识库不覆盖已有内容

目标路径已存在且非空 → 直接报错。库内容永远不因新建被覆盖或损坏。

## 9. 卸载不动知识库数据

无论怎么卸载、什么参数，知识库数据永不被删。卸载只动程序本体和技能包。

> 知识库是用户的资产，不是程序的附属品。

## 10. 两阶段摄入

解析与写入分离：
- **阶段一**：原始文件 → 解析器链 → 临时文件。不创建任何节点。
- **阶段二**：校验 → 去重 → 分页 → 原子写入（节点、修订记录、词频）。

两个阶段之间，调用者读取临时文件内容做语义判断（标题、分区、关系）。

### 中间查询（ingest-context）

Phase 1 解析成功后，Agent 调此命令获取决策依据：

```bash
xu ingest-context --wiki W --keywords "船舶,设计,规范"
```

**内部逻辑（纯确定性）**：
```
1. raws_tree = SELECT DISTINCT raw_path FROM node_page → 提取父目录层级
2. related_nodes = 逐 node_page/derived.body 扫 keywords → match_count → top 10
```

**返回值**：
```json
{"raws_tree": ["船舶/","证书/"], "related_nodes": [{"uid":"A001","title":"船舶设计规范","layer":"Page","match_count":3}]}
```

Agent 据此决定 `--raw-path` 和 `--relations`。

## 11. CLI 不调 LLM

CLI 全程确定性，不调用任何大模型。语义判断、关键词分级、同义词扩展——这些都是调用者的工作。

## 12. 4 键 JSON 协议

所有命令返回统一结构：`{status, data, message, hints}`。

| status | 含义 |
|--------|------|
| `success` | 完全成功 |
| `warning` | 部分成功 |
| `error` | 完全失败（`data.error_class` 标识错误类型） |

`hints` 是 CLI 给调用者的下一步建议。

## 13. Body 样式与内容类型匹配

L1 body 不是通用字符串——必须对齐内容形态：

| 类型 | body 格式 | 校验 |
|------|-----------|------|
| `article` | 自由文本 | 不校验 |
| `table` | YAML 列表，每项为 dict | 写入前校验格式 |
| `gallery` | YAML 列表，每项含 `filename` 字段 | 写入前校验格式 |

## 14. 删前查引用

被 List 或 Report 引用的节点不能直接删除。先清引用，再删节点，防止悬挂引用。

| 约束 | 说明 |
|------|------|
| L1 Page | 被 List 或 Report 引用时拒绝删除 |
| L2 List | 被 Report 引用时拒绝删除 |
| L3 Report | 可直接删除（无下游引用） |

## 15. 图书馆哲学

知识库收集知识，但不生产知识。Node_Page = 馆藏（客观事实），Node_List = 目录（结构化索引），Node_Report = 导读（推理结论）。

## 16. SQLite 是 ground truth

所有节点数据存在 SQLite，无 .md 文件。SQLite 是唯一数据源——任何时刻状态由数据库决定。

## 17. 强 Schema 是质量底线

SQLite 层强约束关键字段。Agent 提交字段缺失或类型错误 → 直接拦截，不放行到写入层。

## 18. install 装能力不装数据

安装只装 CLI、依赖、技能包。不动用户已有的任何知识库实例及其数据。

## 19. 失败原子回滚

任何写入操作：先在临时区完成全部步骤，全成功再 atomically rename。中途失败 → 清临时区，原状态不变。

## 20. 名字全局唯一

知识库名称在注册表内全局唯一。name 冲突 → 拒绝创建。alias 冲突 → 创建但 alias 不绑定（warning）。

## 21. 不跨知识库查询

一次 query 只在一个 wiki 内检索。不跨库搜索、不跨库关联。

---

## 查询框架（LLM 驱动循环）

### 配置项（`<wiki>/.xu/config.yaml`）

```yaml
query:
  snippet_max: 50       # 返回 snippet 合并块数量上限
  body_max: 20          # expand 一次返回 body 数量上限
  snippet_radius: 50    # 命中点前后各取多少字
  merge_radius: 80      # 同 UID 内小于此距离的块合并
```

### CLI 命令

| 命令 | 用途 |
|------|------|
| `xu query --wiki W --core "A,B" --expansion "C,D"` | 扫全库，返回 snippet 合并块 |
| `xu expand --wiki W --uids "X,Y"` | 按 UID 拉 body + relations |

### query 内部流程（纯确定性）

```
1. 扫 node_page.body，找 core + expansion 命中点
2. 每个命中点取前后 snippet_radius 字 → snippet
3. 同 UID 内距离 < merge_radius 的块合并
4. 评分：score = 核心命中数×3 + 扩展命中数×1
5. 降序排列 → 取 top snippet_max → 返回
   [{uid, title, layer, score, snippet}]
```

### 完整循环（LLM 驱动，最高 5 次）

```
LOOP:
  LLM 生成 related words → xu query → 读 snippets 判断
    ├─ 有结论 → 答复用户 ✅
    ├─ 不够，知道要拉哪些 UID → xu expand → 读 body+relations
    │   ├─ 有结论 → 答复 ✅
    │   └─ 不够 → 按 relation 图搜拉新 UID / 或扩展关键词回到 LOOP
    └─ 不够，也不知道要拉谁 → 扩展关键词回到 LOOP

超过 5 次 → 问用户是否扩大搜索
```

---

## 三层架构

| 层 | 名称 | 职责 | 存储 |
|---|---|---|---|
| L1 | Node_Page | 客观知识，从原始文件摄入 | `node_page` 表 |
| L2 | Node_List | 横向对比、归类聚合 | `node_derived` 表（body 内嵌 YAML） |
| L3 | Node_Report | 推理结论，附带证据链 | `node_derived` 表（body 内嵌 YAML） |

## 数据表

| 表 | 用途 |
|---|---|
| `node_page` | L1 不可变知识页 |
| `node_derived` | L2 List + L3 Report |
| `patches` | L1 修订叠加记录 |
| `relations` | 节点间关系边（LRU，≤50） |
| `idf` | 名词词频权重（查询打分） |
