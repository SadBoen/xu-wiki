# 05 — `ingest` 模块设计原则

> **目的**：本文是面向开发者的设计原则文档，用于实现 wiki 风格的知识入库流程。
> **范围**：所有 `ingest*` 命令及 ingest-commit。
> **风格**：每条原则标 [PRIN-N] / [BAN-N] / [CONST-N] / [DESIGN-N]。

---

## 一、一句话定位

Ingest 把外部信息（文件/URL/文本）变成 wiki 里的 **Node_Page**。它是**两阶段流程**：
- **Phase 1（解析 + 暂存）**：原始内容 → 解析为 markdown → 写到暂存区
- **Phase 2（提交落库）**：CLI 校验 + 原子写入 Page + 写修订表初值 + 入 IDF 词频

**Agent 是语义判断者，CLI 是执行者**——这条边界绝不混淆。

## 二、原则

### [PRIN-ING-1] commit 是唯一的写盘入口——单入口原则

所有 ingest 命令（`ingest-file` / `ingest-url` / `ingest-text` / `ingest-commit`）：
- ingest-file / ingest-url / ingest-text → **只写暂存**，不创建节点
- ingest-commit → **唯一**会创建节点的入口

理由：
- 单一入口 = 单一校验点（frontmatter、SHA256、一致性、修订表、IDF 全在这查）
- 多入口 = 校验逻辑分散 = 必然漏检
- 暂存可丢弃，正式节点不可——分开两阶段让失败可恢复

### [PRIN-ING-2] 两阶段流程——分离关注点

```
Phase 1: 原始内容 → 解析为 markdown → 写暂存
   ↓
Agent 读暂存、提取元数据（title / digest / relations / node_path / 层级字段 / 形态字段 等）
   ↓
Phase 2: 元数据 + 暂存内容 → 校验 → 原子写 Page + 写 patches 表初值 + 入 IDF
```

Agent 在两阶段之间**做语义判断**（这是 Agent 唯一介入的地方）。Phase 1 内部纯解析，Phase 2 内部纯校验+写盘。

### [PRIN-ING-3] 幂等性——重复 ingest 不创建重复 Page

同一源文件（按 SHA256 识别）重复 ingest：
- ✅ 第一次：创建 Node_Page
- ❌ 第二次：返回 warning，告知已有 Page 信息，**不创建**

理由：用户可能误点「重新 ingest」——系统应识别并提示，而不是默默复制一份。

### [PRIN-ING-4] Page 切分粒度 = 300 行（正文,按余数)——可定位原则

如果 RAW 文件很大(PDF 转出几千行),Phase 1 应**按 300 行(正文内容,不含 frontmatter)切分**为多个 Node_Page。

切分粒度的**完整决策树**(自上而下,任一命中即停):

1. **大节优先**——按层级标题切:章 / 节 / 小节(`#` / `##` / `###` 及更深)都视作候选切点
2. **小节过细则合并**——若单个小节行数远低于 300,**按物理邻近度向上吞并相邻小节**,直到凑到接近 300 行为止
3. **物理行数兜底**——若无清晰章节边界,按 300 行硬切

**按余数算的规则**(切分算法的硬规则,非软上限):
- 累计行数每到 300 → 切一页
- 不足 300 的余数**仍算一页**——向下取整,不做向上吞并
- 例:850 行正文 → 300+300+250(3 页,最后一页 250 行)
- 例:1200 行正文 → 300+300+300+300(4 页,整除)

**300 是默认阈值**,库内 config 可调（键名由实现决定）——保持切分行为在所有 wiki 实例上一致,便于跨实例引用与审计。

理由:
- Page 太小则证据碎片化、查询组合成本高
- Page 太大则定位精度低(Agent 拿到整页却只要其中一段)
- 小节不合并会产生"幽灵 Page"——几行内容独立成页,引用链冗余、查询结果噪音化
- 300 行是经验值,既能容纳典型 1-3 个小节,又不会让单页过载

**这一条与 [DESIGN-ARCH-2] / [DESIGN-ARCH-6] / [DESIGN-ARCH-7] 互补**:后者管"切片内部怎么找边界"和"切完后怎么合并",本条管"切之前粒度怎么定"。

### [PRIN-ING-5] 解析器是插件式，回退链按格式分组——可插拔原则

  解析器走**双发现机制**：内置一组 + 用户级扩展目录(由实现决定,典型位置如 `~/.xu-wiki/parsers/`)。每个解析器是一个含 `name` 属性、`can_parse(path)` 判定、`parse(path, **kw)` 入口的对象——只要满足这个签名就能被发现,主流程不需任何修改。

回退链按文件格式分组(同一格式内按优先级串联,失败自动回退,末尾兜底为「不解析直接存」)。当前默认回退链:

- PDF / DOCX / PPTX → minerU(主) → markitdown(次) → 兜底
- XLSX → markitdown(主) → excel(次) → 兜底
- 图片 → vision(主) → ocr(次) → 兜底
- 文本/Markdown/CSV → 单一解析器即可

**事实锚点**:主矿换引擎(比如未来加 PaddleOCR、Unstructured、docling)不需要重写设计,只更新 [CONST-ING-1] 的「当前默认」表即可——架构本身不绑死任何具体引擎。

**但**「必须先有解析结果才能进入 Phase 2」这条规则不可破。失败兜底 = 解析器返回空 + Phase 1 拒绝进入 Phase 2,而不是「随便放点什么」。

### [PRIN-ING-6] 原始文件必须可追溯——取证原则

任何被 ingest 的源文件必须在 `raws/` 留一份副本,保证「这页从哪来」可溯源、可校验。

**图片例外**:需要压缩的图片,其「原样可追溯」由 [PRIN-ING-12] 的双 SHA256 保证,不强求物理保留未压缩字节（压缩后的文件仍须进 raws/）。

### [PRIN-ING-7] 暂存是中间产物——生命周期原则

暂存文件（Phase 1 的输出，存于系统临时目录）：
- Phase 1 创建 → 原子写
- Phase 2 成功 → **立即删除**
- Phase 2 失败 → 保留供 debug / 重试

**暂存文件位置是实现细节**，`nodes/pending/` 不是设计要求。实现使用系统临时目录（`tempfile.gettempdir()`），由 CLI 内部管理路径，Agent 通过返回的路径使用，不涉及路径构造逻辑。

规则：commit 成功的 wiki **不应有 Phase 1 临时文件残留**。任何残留 = 必有 ingest 半途崩了 → 用户可用 doctor 检测。

### [PRIN-ING-8] 不并发 ingest——并发安全原则

ingest 的暂存文件名 + DB locks 都是**单进程安全**的。并发 ingest 会让暂存文件冲突。

Agent 多文件批量 ingest 应该**串行**调用多条 ingest 命令，由 Agent 自己排队。

### [PRIN-ING-9] 入 IDF 词频表是 commit 的副产物

`ingest-commit` 成功后，必须**用 jieba 提取 Page body 里的名词 + 计算库内频次**，写入 `IDF 词频表`。

理由：检索时 `query` 会实时调取这些频次计算稀有度权重（[PRIN-ARCH-20] 的工程落地）。

```
稀有度权重 = 常量 / (库内频次 + 1)
```

稀有词（船名 LITA，库内频次低）→ 权重高（稀有 → 权重大）；通用词（项目，库内频次高）→ 权重低（常见 → 权重小）。

### [PRIN-ING-10] patches 表初值是 commit 的副产物

`ingest-commit` 成功后，必须在 `patches 表`（L1 修订表）写一条**初值记录**——代表「当前 Markdown 内容是 v1」。

后续修订通过**增量 patch**叠加——绝不直接覆盖 Markdown（[PRIN-ARCH-3] L1 不可变原则）。

### [PRIN-ING-11] 摄取意图不明就问，绝不猜（[PRIN-SAFETY] 在 ingest 的落地）

摄取常有意图歧义(一批图片是按相册还是逐张?目标库不存在是写错了还是要新建?),Agent 必须先问用户、绝不替用户猜默认值。脏数据一旦摄入会污染后续所有查询和推理,多问一句远比事后清理便宜。CLI 仍保持确定性。

### [PRIN-ING-12] 图片压缩——双 SHA256

对于需要压缩的图片,使用双 SHA256 设计:压缩前的 SHA256 用于查重(保证压缩不影响幂等去重),压缩后的 SHA256 用于完整性校验。EXIF 必须保留。阈值与压缩参数由库级 config 决定。

### [PRIN-ING-13] L1 body 样式与内容类型匹配——内容形态原则

**不同的内容,要有不同的正文样式**。L1 body 不是"一段 markdown 字符串"——它必须与承载的内容形态对齐。

当前至少有三类内容形态,对应三种 body 样式:

| 内容类型 | 典型来源 | body 样式 | CLI |
|---|---|---|---|
| **表格化** (一图一行 / 一项一行) | 相册 (album)、参数对比表、清单 | **markdown 表格**——表头 + 一行一项;列 = 关键元数据 | `ingest-album` (album 场景) |
| **散文** (普通文档) | PDF / DOCX / Markdown / 文本 | **prose**——段落、标题、列表;解析器按文档结构产出 | `ingest-file` + `ingest-commit` (单源) |
| **代码 / 命令块** | 脚本片段、终端输出、API 响应 | **fenced code block**——语言标注 + 单块代码 | `ingest-commit --native` 直接 commit markdown 源码 |

理由:

- body 样式错配 = 后期 query 切片、read 还原、人工审阅全部成本上升
- 表格化内容塞进 prose = 无法按行做交叉查询;prose 内容塞进表格 = 浪费表头且断行
- **body 形态由内容类型决定,不由 content_type 名决定**——`content_type` 是 frontmatter 标签,可以由 L2/L3 工具识别;body 形态是文件实际写出去的 markdown 结构,二者正交
- Agent 编排 SOP 时,**第一步就是问用户"这些内容是表格化 / 散文 / 代码块"**,而不是默认走散文

#### 强制约束

- **表格化 body 的列必须稳定**——同一相册的 L1,列定义改了就等于创建新形态,跨实例引用会断(PRIN-ING-4 的精神)
- **散文 body 不允许内嵌大段代码**——超过 5 行的代码必须走 fenced code block(` ``` `),与正文分离
- **代码块 body 不允许混入散文**——一段代码就是一段代码,需要解释时另起一个 L1 page 写说明

### [PRIN-ING-14] 相册是单次写入,不走两阶段——单次原则

`ingest-album` 是 ingest SOP 的**子流(sub-flow)**,用于"多张图 → 1 个 L1 相册"场景。它**不**走 `ingest-file` → `ingest-commit` 两阶段:

- **单次写入**:一次调用直接产出 1 个 L1 Page + N 个源文件 copy + 1 条 patches v1 + N 条 source_hash dedup
- **不写 pending**:相册没有"先看再 commit"的需要——body 是程序生成的,Agent 看不到中间态有意义
- **不强求两阶段校验**:相册内容的元数据(分辨率、GPS、DateTime)是**程序可决定的**,不需要 Agent 审阅;Agent 唯一要决定的只有 title / node-path / layout / vision 意图——这些都在调用前问清

理由:

- 两阶段的设计初衷是**让 Agent 在两阶段之间做语义判断**([PRIN-ING-2])。相册的 body 是机器生成的,Agent 在两阶段之间没东西可判断
- 强塞两阶段 = 多一次 IO + 多一次 pending 文件清理,无收益
- 但**单次不意味着无校验**:dedup (CONST-ING-3)、frontmatter (CONST-ING-4)、patches v1 (PRIN-ING-10)、IDF 入库 (PRIN-ING-9) 全部照跑

#### 与 PRIN-ING-1 的关系

- [PRIN-ING-1] "commit 是唯一写盘入口"——**仍然成立**:相册只有 1 个写盘入口(`ingest-album` 自身,内部一次性完成所有写入),不存在"先写一个临时 entry 再 commit"
- [PRIN-ING-1] 管的是"写盘入口数量",[PRIN-ING-14] 管的是"入库流程形状"——两个维度正交

#### 子流识别与设计原则清单 (B/C/D)

**B 类 (跨 SOP 共享原子能力)**:`ingest-album` 虽然是 ingest SOP 的子流,但其内部逻辑用了"复制源文件 + 提取 EXIF + 写 1 个 L1 + dedup"四件套——前两件与 `ingest-commit` 的 raws/ 复制、PRIN-ING-6 完全同源;后两件与 PRIN-ING-10 / CONST-ING-3 完全同源。所以 `ingest-album` **不是发明新能力**,而是 ingest 已有原子能力的「单次组合」(PRIN-SOP-3: CLI 是原子,SOP 是其按需组合)

**C 类 (软件生命周期)**:`ingest-album` **不**属于——它动的是 wiki 数据,不是软件本体

**D 类 (可争议)**:`ingest-album` 是不是应该拆成"先创建 L1 → 再循环 ingest-file 引用"?答案:**不**。因为 L1 的 body 是程序生成的,无法用 `ingest-file` 链式表达(每个 `ingest-file` 产生的是单源的 pending,不是相册的多源表格)

**A 类 (明确归 SOP-ingest)**:`ingest-album` 是 ingest SOP 的子流,在 08-sop-architecture.md §5.2 SOP-ingest 的「典型用户意图 → CLI 编排」表里有专行

#### `ingest-album` 详细流程 (相册子流)

**调用形态**:

```bash
xu-wiki ingest-album \
  --wiki <name> \
  --title "SGW001 第一次岸上系统部署完工" \
  --files /abs/001.jpeg,/abs/002.jpeg,... \
  --node-path "船舶/SGW001/联想产岸系统/首次完工/照片" \
  --layout table|list \
  [--vision] \
  [--captions '{"001.jpeg":"船头整体完工",...}'] \
  --digest <D> --author <A>
```

**9 步内部流程**:

| # | 步骤 | 说明 |
|---|---|---|
| 1 | 解析 wiki | `resolve_wiki` (CONST-ING: wiki 必须先存在) |
| 2 | 校验必填 | `--title` 必须非空;`--files` 必须 ≥ 1;`--layout ∈ {table, list}` (CONST-ING-4) |
| 3 | 路径校验 | 所有源文件**绝对路径** + 文件存在 (hard rule 9 / BAN-CRT-1) |
| 4 | captions 解析 | `--captions` JSON → `{filename: description}`;缺省视为空串 |
| 5 | EXIF 提取 | `parsers/image_meta.read_image_meta` (Pillow 软依赖);resolution + GPS + DateTime 缺失字段一律 "—" (PRIN-ING-13 优雅降级) |
| 6 | 源文件 copy | 每张图 `shutil.copy2` 到 `raws/<node-path>/<原文件名>` (PRIN-ING-6) |
| 7 | Level-2 dedup | 对每张图 `SELECT ... WHERE source_hash=?`;任一命中 → warning + 整相册拒绝 (CONST-ING-3 / BAN-ING-4) |
| 8 | 渲染 body | `_render_body` 生成 markdown 表格或列表;每行包含 # / Filename / Path / Resolution / GPS / Captured / Description 七列 (PRIN-ING-13 表格化形态) |
| 9 | 一次性写盘 | 1 条 INSERT nodes (content_type=gallery) + 1 条 INSERT patches v1 + N 条 IDF 增量;**单事务,失败全回滚** (PRIN-ING-1 / PRIN-ING-10 / PRIN-ING-9) |

**与两阶段流的差异**:

| 维度 | `ingest-file` → `ingest-commit` | `ingest-album` |
|---|---|---|
| 源文件数 | 1 | N (≥1) |
| 写盘入口 | 2 个 (Phase 1 写临时文件 + Phase 2 写正式节点) | 1 个 (album 内部完成所有写入) |
| Phase 1 临时文件 | 有,Phase 2 成功后删 | 无 (PRIN-ING-14 单次原则) |
| body 来源 | 解析器产出 | 程序渲染 |
| Agent 介入点 | Phase 1 与 Phase 2 之间 | 调用前 (title / node-path / layout / vision 全部问清) |
| 关系建 | commit 时 `--relations` | 不在本次建;调用后由 SOP 调 `query-relation add` (PRIN-ING-14 子流识别 B 类) |
| 模板 | `article` / `table` / `gallery` | `gallery` (固定;相册语义本就如此) |

**Vision/OCR 子流程 (--vision 标志)**:

- Agent 在调用 `ingest-album` **之前**应主动问用户「要不要给每张图加视觉识别描述?」(PRIN-SOP-7 主动澄清)
- 用户答 yes → `--vision` 标志置位,body 末尾 marker 记录 `vision=yes`;**当前 build 无 vision 后端** → 提示「vision 意图已标记,等后端就位再补 caption」
- 用户答 no → `--vision` 缺省,marker 记录 `vision=no`;相册只有元数据
- 用户没被问 / 问完没答 → **禁止** Agent 自己决定 yes/no → CLI 用 `--vision` 缺省值(no),并在 `hints` 里说「vision intent was not set; per-photo captions are empty」

**典型 body 输出样例 (table layout)**:

```markdown
# SGW001 第一次岸上系统部署完工

> 相册主题:SGW001 第一次岸上系统部署完工;10 张图片;源文件存于 `raws/船舶/SGW001/.../照片/`。

| # | Filename | Path | Resolution | GPS | Captured | Description |
|---|----------|------|------------|-----|----------|-------------|
| 1 | 001.jpeg | `raws/船舶/SGW001/.../001.jpeg` | 6000×4000 | 31.23450°N, 121.45670°E | 2026-01-15 | 船头整体完工 |
| 2 | 002.jpeg | `raws/船舶/SGW001/.../002.jpeg` | 6000×4000 | — | 2026-01-15 | — |
| ... |
| 10 | 010.jpeg | `raws/船舶/SGW001/.../010.jpeg` | 6000×4000 | — | 2026-01-15 | — |

<!-- xu-album layout=table count=10 vision=no -->
```

**attrs.album.sources 存储形态 (供 L2/L3 工具查询)**:

```json
{
  "album": {
    "layout": "table",
    "count": 10,
    "vision": false,
    "sources": [
      {
        "filename": "001.jpeg",
        "source_hash": "sha256:...",
        "raw_rel_path": "raws/船舶/SGW001/.../001.jpeg",
        "width": 6000,
        "height": 4000,
        "gps": "31.23450°N, 121.45670°E",
        "captured": "2026-01-15 14:32:00"
      },
      ...
    ]
  }
}
```

**与 image-parser 解析器的关系**:`parsers/registry.py` 的 `ImageParser` 仍然负责**单图走散文**场景 (PRIN-ING-13 散文形态);`parsers/image_meta.read_image_meta` 专门服务**相册**场景。两者不重复——一个管 prose 形态,一个管 table 形态。

### [PRIN-ING-15] 业务变更追溯走 DB——不走过程层日志

业务侧的「这张照片是哪次加的」「这个 Page 是什么时候 commit 的」**不是**过程层的事——是**业务数据**。由 DB 自己的机制承担:

- `nodes.created_at` / `nodes.updated_at` —— 节点生命周期
- `patches 表` —— L1 修订历史（[PRIN-ING-10]）
- `nodes.attrs` 里的领域字段（如 `album.sources[i].captured`）—— 业务元数据

**审计 vs 业务变更的边界**：过程层 `audit.jsonl` 只记「谁跑了什么 CLI、跑没跑成」（[CONST-ARCH-6] / [PRIN-ARCH-26]）；业务变更历史由 DB 表与 frontmatter 字段承担。两者不重叠。

理由:
- 审计日志是「程序行为记录」,丢了可重建（process-layer 无原始数据依赖）
- 业务变更历史是「数据本身的一部分」,丢了**不可重建**——必须存在 DB 与 Markdown 里
- 把业务变更塞进过程层 = 模糊边界 + 制造耦合,违反 [PRIN-ARCH-26] 的「各层不互替」精神

## 三、禁令

### [BAN-ING-1] Agent 不直写 Page 文件

Agent 不能绕过 commit 直接把内容写进正式 Page 文件。**必须**走 `ingest-commit`。

理由：
- ingest-commit 会校验 frontmatter、写 DB、写 patches 表、入 IDF——Agent 直写会绕过这一切
- Agent 写错了 Page = L1 客观层腐化 = 整层知识失真

### [BAN-ING-2] Phase 2 不调 LLM

ingest-commit 是纯确定性逻辑：
- 校验 frontmatter（必填字段、类型、正则）
- 写 .md 文件（原子）
- 写 DB 行（事务）
- 建关系（如果 Agent 在 Phase 2 调用时给了 relations 参数）
- 写 patches 表初值
- 提取名词入 IDF 表
- 写审计日志

**绝不**调 LLM 做内容生成、标题建议、关系推断——这些都是 Phase 1 和 Phase 2 之间的 Agent 责任。

### [BAN-ING-3] 不解析就 commit——跳过 Phase 1

`ingest-commit --native`（直接传 markdown 字符串）允许「绕过解析」，但仍要走：
- 写暂存（即使是 markdown 原样）
- 走 commit 流程
- 写 DB / 关系 / patches / IDF

> **警告**：`--native` 模式**不满足 PRIN-ING-6**（无源文件可 copy 进 raws/）。
> 设计用途：Agent 合成的代码片段、终端输出等**无外部源**的纯文本。
> **禁止**用 `--native` 摄取外部 `.md / .pdf / .docx / .pptx` 文档——会静默绕过取证副本。
> 必须使用 Phase 1 + Phase 2 流程（`ingest-file` → `ingest-commit --pending`）。

**不允许**「Agent 在 Phase 2 之前直接拼好 frontmatter 然后调用 ingest-commit 跳校验」——校验是 commit 的**入口**。

### [BAN-ING-4] SHA256 重复不覆盖已有 Page

命中 SHA256 重复时：
- ❌ 不删旧 Page 重建
- ❌ 不覆盖旧 Page 的 frontmatter
- ✅ 返回 warning + 旧 Page 信息

用户用 `revise` 改旧 Page，不是用 ingest 覆盖。

### [BAN-ING-5] 暂存内容路径必须白名单校验

Agent 传入的暂存内容路径必须白名单校验：只允许 wiki root 内或系统临时目录,其他位置一律拒绝。

理由：Agent 可能传入敏感系统文件路径——CLI 不能信任任何外部传入的路径。

### [BAN-ING-6] 不修改已存在的 Page Markdown

Page 一旦写入，**commit 命令绝不修改 Markdown 内容**。发现错误 → 走 patches 表叠加修订，不直接覆盖。

## 四、约束

### [CONST-ING-1] 解析器按内容类型分派（可扩展）

按源文件类型分派到合适的解析器，至少覆盖以下几类输入；**具体用哪个第三方库由实现决定，集合可扩展**：

| 输入类型 | 期望输出 |
|---|---|
| 纯文本 / Markdown | 纯文本 |
| 富文档（PDF / Office / HTML 等） | markdown |
| 图片 | markdown（图像描述，作为 fallback） |
| 扫描件（图片型 PDF / 扫描图） | markdown（OCR 文本） |
| 高质量结构化提取（含表格/公式） | markdown |
| 表格文件（CSV / 电子表格） | markdown table |

原则：**解析路由可扩展，但「必须先有解析结果才能进 Phase 2」这条不可破**（[PRIN-ING-5]）。失败时按优先级 fallback 到下一候选解析器。

**当前默认引擎事实锚点**（与 [PRIN-ING-5] 的回退链对应）:

- **minerU**:主引擎,云 API 形态(需要联网 + API Key;Key 缺失则静默回退,这是设计行为不是 bug)。承担高质量结构化提取(表格/公式/扫描件 OCR)。
- **markitdown**:本地 fallback,不依赖网络、不烧 API、覆盖 PDF/DOCX/PPTX/XLSX/HTML。适合离线或 minerU 不可用场景。
- **vision / ocr**:图片类文件双引擎,vision 优先。
- **excel / csv / text**:专用解析器,单一即可,无回退。

**未来加引擎的路径**:把新解析器文件丢到用户级扩展目录(或注册为内置),满足 [PRIN-ING-5] 的签名即可。引擎名 / 优先级 / 适用扩展名 = 改 [PRIN-ING-5] 表格事实层的事实,不改设计。

#### 代码事实参考:MinerU 使用方式（特批录入,踩坑留痕)

> 以下为**当前实现**对 MinerU 的具体使用方式,作为事实证据,供审计与回溯。**不是设计规约**——任何一行都可能在实现层变动而不更新本文档。设计原则请见上方段落,不要从这里反推原则。

```python
# 摘自 xu-wiki/src/xu/parsers/mineru_parser.py(踩坑时的事实快照)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx"}
_API_BATCH_URLS  = "https://mineru.net/api/v4/file-urls/batch"
_API_RESULTS     = "https://mineru.net/api/v4/extract-results/batch"
_API_MAX_PAGES   = 200
_API_MAX_SIZE_MB = 200
_POLL_INTERVAL   = 3     # 秒
_POLL_TIMEOUT    = 600   # 秒

def _resolve_mineru_key(api_key: str) -> str:
    """API Key 解析优先级: 参数 > 环境变量 MINERU_API_KEY > config.mineru.api_key."""
    if api_key:
        return api_key
    env_key = os.getenv("MINERU_API_KEY", "")
    if env_key:
        return env_key
    try:
        from xu.utils.config import load_global_config
        cfg = load_global_config()
        return cfg.get("mineru", {}).get("api_key", "")
    except Exception:
        return ""
```

**踩坑点(亲历)**:
- Key 缺失**静默回退**到下一级解析器(是设计,见 [CONST-ING-1]),容易让人误以为「bug」;
- 端点为云 API,强依赖外网,Key 缺失 / 服务不可达 / 配额耗尽都会触发回退;
- 单文件 ≤ 200MB / ≤ 200 页,超出会被截断或失败(大 PDF/书稿需先切片);
- 轮询最坏等 10 分钟,ingest 命令会阻塞同样时长(并发摄取需考虑);
- 全部走 `urllib.request` 而非 `requests`,超时与重试由调用方控制。

### [CONST-ING-2] SSRF 防护(ingest_url)

URL 摄取必须：
- 黑名单 IP 段（loopback、私网、链路本地）
- 端口限标准 HTTP/HTTPS（具体由实现决定）
- DNS pinning（防 rebinding）

### [CONST-ING-3] SHA256 两级去重

- Level 1：active Page 的内容哈希（正文 SHA256）
- Level 2：所有 Page 的原始文件哈希（图片用压缩前的哈希，见 [PRIN-ING-12]）

任一命中 → warning + 返回已有 Page 信息。

### [CONST-ING-4] 校验（commit 入口必跑）

frontmatter 必填字段、类型、正则、必填 list 非空等——任何失败 → error 列出具体缺失项，**不**部分写入。

### [CONST-ING-5] 关系处理

- `--relations` 必为 JSON 数组（dict → error）
- 每条 relation = `{to: <uid>, relation_name: <str>, [comment]}`——**不带分类、不带权重**（关系是无分类的 LRU 链表，见 [PRIN-ARCH-8]）
- `to_uid` 不存在 → `relations_warning`（累积，不 fatal）
- `add` = 一次触碰 → 插入该节点出边链表的**队首**
- **50 条上限约束**——满了弹出队尾最久未触碰的关系（[PRIN-ARCH-9] / [PRIN-ARCH-10]）

### [CONST-ING-6] IDF 入库 schema

```
IDF 词频表:
  名词 主键（字符串类型）,    -- 名词
  频次 整数字段 非空,   -- 库内出现次数
  权重 浮点字段 非空      -- = 常量（具体数值由实现决定） / (频次 + 1)
  updated_at 整数字段
```

ingest-commit 时增量更新（不是重建）。用户可在 `doctor-idf` 检测异常。

### [CONST-ING-7] patches 表 schema

```
patches 表（字段命名由实现决定，这里描述角色）:
  〈所属 Page 的 UID〉    字符串 非空,   -- 这条 patch 属于哪个 Page
  〈版本号〉              整数   非空,   -- 从 1 开始递增
  〈操作类型〉            字符串 非空,   -- create / revise / correct
  〈增量内容〉            字符串 非空,   -- diff 或 patch 正文
  〈作者〉                字符串,        -- 谁提交的
  〈时间戳〉              整数,
  主键 (〈所属 Page 的 UID〉, 〈版本号〉)
```

ingest-commit 时写 version=1 的 create 记录。

### [CONST-ING-8] 4 键 JSON 返回

返回 `status/data/message/hints`：
- 成功 → success
- SHA256 重复 → warning（带旧 Page uid/title）
- 校验失败 → error（data 含具体缺失字段）
- 关系部分失败 → warning（data.invalid_relations）

### [CONST-ING-9] 不并发

每次 ingest 是原子操作。多文件批量由 Agent 串行调用。

## 五、Page 三层节点定位

ingest 只创建 **Node_Page（L1）**。Node_List（L2）/ Node_Report（L3）由其他命令创建：

| 节点类型 | 创建命令 | 内容形态 |
|---|---|---|
| **Node_Page** (L1) | `ingest-commit` | 与 RAW 高对齐的物理切片 |
| **Node_List** (L2) | `list create` | 横向对比表 |
| **Node_Report** (L3) | `report create` | 逻辑推演、必须引用 L1/L2 证据 |

LLM 重写 ingest 时务必只动 L1——不要让 ingest 顺便创建 L2/L3（违反职责分离）。

## 六、与相关模块的关系

- **query**：ingest 创建的 Page = query 检索的目标
- **doctor**：ingest 留下的不变量（patches 初值 / IDF 入库 / 三层一致性）= doctor 检查的内容
- **rebuild**：ingest 是 L1 的入口，rebuild 是重建索引层的入口——两者必须协同

## 七、自检清单（开发时勾选）

**原则**：
- [ ] commit 是唯一写盘入口（[PRIN-ING-1]）
- [ ] 两阶段分离（[PRIN-ING-2]）
- [ ] 幂等性（[PRIN-ING-3]）
- [ ] Page 切分 = 300 行（正文,按余数,见 [PRIN-ING-4]）
- [ ] 解析路由不可混乱（[PRIN-ING-5]）
- [ ] 原始文件可追溯（[PRIN-ING-6]）
- [ ] 暂存生命周期正确（[PRIN-ING-7]）
- [ ] 不并发（[PRIN-ING-8]）
- [ ] 入 IDF 词频表（[PRIN-ING-9]）
- [ ] 写 patches 表初值（[PRIN-ING-10]）
- [ ] 意图不明先问用户、绝不猜（[PRIN-ING-11]）
- [ ] 图片压缩：双 SHA256 + 保 EXIF（[PRIN-ING-12]）
- [ ] L1 body 样式与内容类型匹配（[PRIN-ING-13]——表格/散文/代码块三种形态，Agent 必须先问内容形态）
- [ ] 相册子流 `ingest-album` 单次写入（[PRIN-ING-14]——不走两阶段，但 dedup / patches v1 / IDF 全跑）
- [ ] 业务变更追溯走 DB（`nodes.created_at` / `patches 表` / 业务字段），不走过程层日志（[PRIN-ING-15]）

**禁令**：
- [ ] Agent 不直写 Page（[BAN-ING-1]）
- [ ] Phase 2 不调 LLM（[BAN-ING-2]）
- [ ] 跳过 Phase 1 仍要走 commit 流程（[BAN-ING-3]）
- [ ] SHA256 重复不覆盖（[BAN-ING-4]）
- [ ] 路径白名单（[BAN-ING-5]）
- [ ] 不修改已存在 Page（[BAN-ING-6]）

**约束**：
- [ ] 解析器按内容类型正确路由（[CONST-ING-1]）
- [ ] SSRF 防护（[CONST-ING-2]）
- [ ] SHA256 两级去重（[CONST-ING-3]）
- [ ] frontmatter 校验（[CONST-ING-4]）
- [ ] 关系处理 + 50 条上限（无分类、LRU）（[CONST-ING-5]）
- [ ] IDF 入库 schema（[CONST-ING-6]）
- [ ] patches 表 schema（[CONST-ING-7]）
- [ ] 4 键 JSON（[CONST-ING-8]）
- [ ] 不并发（[CONST-ING-9]）

---

**作者注**：ingest 是最容易出 bug 的模块。新设计引入的两个**副产物**——IDF 入库（[PRIN-ING-9]）和 patches 初值（[PRIN-ING-10]）——是 Page 客观性的工程保障。LLM 重写时务必先实现「commit 是唯一写盘入口」（[PRIN-ING-1]）这条铁律，再加这两个副产物——**顺序反了会写入脏数据**。

Page 切分 = 300 行正文、按余数算（[PRIN-ING-4]）是**默认行为**——库内 config 可调（键名由实现决定），但缺省值 300 保证跨实例切分行为一致,便于跨实例引用与审计;「按层级标题优先,过短则合并相邻小节,物理行数兜底」这条原则不可破。