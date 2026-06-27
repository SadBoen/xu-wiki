# 02 — `create` 模块设计原则

> **目的**：本文是面向开发者的设计原则文档，用于实现 `create` 风格的「创建 wiki 实例」命令。
> **范围**：仅覆盖 create 命令本身。
> **风格**：每条原则标 [PRIN-N] / [BAN-N] / [CONST-N] / [DESIGN-N]。

---

## 一、一句话定位

`create` 在指定目录**从零初始化一个新 wiki 实例**：建三件套目录（raws/nodes/.xu）、初始化索引层、写库内配置、在系统注册表登记。它**不写**任何节点内容——只搭骨架。

## 二、原则

### [PRIN-CRT-1] create 是 install 之后的第二步——分工原则

把整套工具想象成开图书馆：
- `install` = 雇图书馆管理员（装软件）
- `create` = 管理员上任第一天，建一座新图书馆（建 wiki 实例）
- `register` = 图书馆已经存在，现在登记到管理员的辖区里

LLM 重写时务必区分：「软件」和「软件管理的对象」是两个不同层级。create 操作的是「软件管理的对象」，不动软件本身。

### [PRIN-CRT-2] create 建的是空骨架——边界原则

create 完成后，wiki 应该有：
- 三个空目录（raws/nodes/.xu）
- 一个可工作的 DB（schema 完整但无数据）
- 一个库内 config（含版本号）
- 一条全局注册表项

create **不创建**任何节点页、任何原始文件、任何示例数据。**空就是空**——让用户决定装什么内容。

### [PRIN-CRT-3] 三层边界清晰——不动其他层

create 只动「软件本体」+「系统注册表」两层：
- ✅ 动：raws/ nodes/ .xu/ 目录、库内 config、注册表项
- ❌ 不动：CLI、venv、SKILL、安装元数据（这是 install 的领域）
- ❌ 不动：任何已存在的 wiki 实例（这是 delete-node 的领域）

### [PRIN-CRT-4] 为三层节点预留位置——架构先于内容

新建的 wiki 必须**立即支持三层节点结构**——虽然空库没有节点，但 schema / 目录结构 / 索引表必须为 Page / List / Report 三种节点类型预留好位置。

理由：Node_Page / Node_List / Node_Report 是核心架构（见 [PRIN-ARCH-1]）——如果 create 时只建了 Page / List 的位置，Report 节点后续将无处安放。

推论：
- 目录结构必须为三种节点（Page / List / Report）各自预留独立子目录
- DB schema 必须为三种层级预留位置，并为 L3 的特殊查询（如 Report 的证据链）建索引

### [PRIN-CRT-5] 为弹性 Rebuild 预留开关——多档位支持

create 时必须在库内 config / DB schema 里预留 **Rebuild 粒度开关**,支持后续按档位重建(只重建结构层 / 只清报告层 / 全量)。这是 [PRIN-ARCH-6]（弹性 Rebuild）的工程落地——create 必须为它铺好路。

### [PRIN-CRT-6] 为 L1 不可变 /  词频建表——wiki 内部组件

create 时必须为 wiki 实例创建**两张衍生表**：

```
patches 表    —— L1 修订历史（每次 Page 创建/修订追加一条 patch）
词频表    —— 名词库内频次（ingest-commit 时增量更新）
```

这两张表是 wiki 自己的状态，不是软件配置——create 必须为它们预留 schema 与索引。

理由：
- patches 表是 [PRIN-ARCH-3] L1 不可变原则的工程实现——没有它，L1 修改无法追溯
-词频表是 [PRIN-ARCH-20] 检索稀有度加成的数据源——没有它，query 的 B 稀有分拿不到数据

推论：create 不能只建 Page / List / Report 三类节点表——必须**同时建这两张衍生表**。

## 三、禁令

### [BAN-CRT-1] 绝不覆盖已有内容

如果目标目录**已存在且非空** → 拒绝执行。绝不允许「合并」、「追加」、「替换」已有内容。

理由：用户的目录里可能有宝贵数据——「自动合并」会让用户失去对数据的控制。

唯一例外：同路径已是一个 xu-wiki wiki（识别 [CONST-CRT-1]）→ 返回 warning 告知「已存在」，由用户决定是用还是 `rm -rf` 重来。

### [BAN-CRT-2] create 不碰 install 管辖的东西

绝不修改：
- CLI 软链
- venv 目录
- Agent SKILL
- 全局 config 的非 wikis 段（如 API key）

create 的「写全局 config」**只写 wikis 段**，不动其他段。

### [BAN-CRT-3] 不自动决定 wiki 名字

用户必须显式给 `--name`。如果省略：
- ❌ 不允许「自动用 basename」、「自动用 UUID」、「自动问 LLM」
- ✅ 必须 error 提示「需要 --name」

理由：名字是用户在所有后续命令里使用的标识——必须由用户**主动**确定，不能由程序猜。

**与 [PRIN-SAFETY] 的关系**:CLI 只负责「没给 name 就报错」。更重要的护栏在 Agent 侧——用户在别的命令里写了查无此库的名字时,Agent 绝不能转头调 create 造新库(这正是「写错库名→自动建错库」的事故根源),必须先问用户是写错了还是要新建。

### [BAN-CRT-4] 不预填示例数据

create 完成后 wiki 必须是**真·空库**——不允许自动 create 几个示例 Node_Page / Node_List / Node_Report。

理由：示例数据会让用户误以为「这就是模板」——但每个 wiki 的内容应该由该 wiki 的领域决定，不是由工具决定。

## 四、约束

### [CONST-CRT-1] 必须能被识别为 xu-wiki 项目

create 完成后，目标目录必须含可识别 xu-wiki 的标记——典型做法：含 `pyproject.toml`（含 xu-wiki marker）或等价文件。

### [CONST-CRT-2] 失败原子回滚

任何中途失败（DB schema 写一半、config 写到一半），必须回滚到「create 开始前」的状态——不留半成品。

实现策略：先在临时目录建完整结构，全成功再原子换名到目标位置；任一步失败清掉临时目录。

### [CONST-CRT-3] 幂等性

同名 + 同路径重复 create → warning 复用，不重建 DB、不覆盖节点数据、不覆盖库内 config（保留用户已填的内容）。

### [CONST-CRT-4] 名字合法性

- 字符集限字母数字 + 连字符 + 下划线,限长
- 全局唯一（在系统注册表里不与任何已有 wiki 的 name 或 alias 冲突）
- 冲突处理：name 冲突 → error；alias 冲突 → warning（wiki 仍创建，但 alias 不绑定）

### [CONST-CRT-5] 路径越界防护

用户输入的目录路径必须规范化（解析符号链接）后断言仍在合法磁盘位置。symlink 逃逸 → error。

### [CONST-CRT-6] 库内 config 必含版本号

`<wiki>/.xu/config.yaml` 必须含 `version` 字段——后续 `update wiki` 用此判断 wiki 格式是否需要升级。

库内 config 应预留的键：

```yaml
version: "<版本号>"
templates: {}                 # 自定义模板扩展位（当前留空）
query:
  # 切片软上限 / 硬上限 / 邻域合并半径 —— 具体数值由实现决定
  scoring:
    # 核心/扩展权重比、密度奖励系数等 —— 具体数值由实现决定
  fast_pass:
    enabled: true
    dynamic: true             # 动态阈值（Top1 显著高于均值时触发，倍数由实现决定）
relation:
  max_edges: <上限>           # 出边总数上限（默认建议 50）
  policy: lru                 # 不分类、不打分：建立进队首 / 命中前挪 / 满了弹队尾
asset:
  compress_over: <阈值>       # 图片超过此大小才压缩（小图原样落盘）
  preserve_exif: true         # 压缩时保留 EXIF（[PRIN-ING-12]）
  # 压缩质量 / 目标尺寸等由实现决定
rebuild:
  granularity: ["keep-l1", "keep-l1-l2", "full"]  # 允许的档位
```

### [CONST-CRT-7] 4 键 JSON 返回

返回 `status/data/message/hints`——其中 alias 冲突是 `warning`，目录非空是 `error`。

### [CONST-CRT-8] 不调 LLM

create 全程确定性逻辑：路径校验、目录创建、DB schema 注册、config 写入。无 LLM 调用、无外部网络请求。

## 五、节点 CRUD 矩阵（概念层）

| 节点类型 | 层级字段值 | 文件位置 | 创建命令 |
|---|---|---|---|
| **Node_Page** | `Page` | `nodes/page/<按层级分区>/<slug>.md` | `ingest-commit` |
| **Node_List** | `List` | `nodes/list/<node_path>.md`（frontmatter 含 split_index/parent_uid；body 是 YAML list） | `list create` |
| **Node_Report** | `Report` | `nodes/report/<node_path>.md`（frontmatter 含 split_index/parent_uid；body 是报告正文） | `report create` |

create 命令本身不创建节点——但必须为三种类型预留 schema。

## 六、与相关命令的边界

| 命令 | 动什么 |
|---|---|
| `install` | 装软件本体（CLI/venv/SKILL） |
| `create` | 建新 wiki 实例（空骨架 + 注册表项） |
| `register` | 把已有目录登记到注册表（**不创建**任何文件） |
| `wikis` | 列出注册表项（只读） |
| `alias` | 给已注册 wiki 起别名 |
| `unregister` | 从注册表移除（**不动** wiki 本体） |

## 七、自检清单（开发时勾选）

**原则**：
- [ ] create 是 install 之后的第二步（[PRIN-CRT-1]）
- [ ] 只建空骨架，不预填数据（[PRIN-CRT-2] / [BAN-CRT-4]）
- [ ] 只动「软件本体 + 注册表」两层（[PRIN-CRT-3]）
- [ ] 为三层节点预留位置（[PRIN-CRT-4]）
- [ ] 为弹性 Rebuild 预留开关（[PRIN-CRT-5]）

**禁令**：
- [ ] 不覆盖已有内容（[BAN-CRT-1]）
- [ ] 不碰 install 管辖的东西（[BAN-CRT-2]）
- [ ] name 必须显式给（[BAN-CRT-3]）
- [ ] 不预填示例数据（[BAN-CRT-4]）

**约束**：
- [ ] 必须含 xu-wiki 标记（[CONST-CRT-1]）
- [ ] 失败原子回滚（[CONST-CRT-2]）
- [ ] 幂等性（[CONST-CRT-3]）
- [ ] name 合法性校验（[CONST-CRT-4]）
- [ ] 路径越界防护（[CONST-CRT-5]）
- [ ] config 含 version + 预留 query/relation/rebuild 字段（[CONST-CRT-6]）
- [ ] 4 键 JSON（[CONST-CRT-7]）
- [ ] 不调 LLM（[CONST-CRT-8]）

---

**作者注**：create 看起来简单，但 [BAN-CRT-1]（不覆盖已有）和 [CONST-CRT-2]（失败回滚）是 LLM 容易忽略的两条。务必用「临时目录 → 全部成功 → rename」的二阶段模式，不要原地建目录。原地建的写法会让失败留下半成品的 `raws/` `nodes/` `partial.db`，难以清理。

[PRIN-CRT-4]（三层节点预留）和 [PRIN-CRT-5]（弹性 Rebuild）是关键约束——create 必须为后续的 L1/L2/L3 节点和档位重建铺路，不能只建「Page + List」两类的简化版。