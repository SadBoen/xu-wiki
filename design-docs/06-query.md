# 06 — `query` 模块设计原则

> **目的**：本文是面向开发者的设计原则文档，用于实现 wiki 风格的检索命令。
> **范围**：`query` 主流程及子查询命令。
> **风格**：每条原则标 [PRIN-N] / [BAN-N] / [CONST-N] / [DESIGN-N]。

---

## 一、一句话定位

`query` 是「找知识」的入口。它执行**三层介入的检索工作流**——物理定位（L1）→ 结构对齐（L2）→ 逻辑提炼（L3）。CLI 跑机械搜索与评分；语义过滤、关键词分级、Report 引用由 Agent 自己做。

## 二、原则

### [PRIN-QRY-1] 多轮 LLM 决策环——CLI 执行工具，LLM 决定下一步

```
用户发起查询
   ↓
1. LLM 生成中英文关键词（不分 core/expansion）
   ↓
2. CLI 搜 → 打分排序 → 取前 50 个切片块 → 合并为完整文本
   （每个块带 UID / 标题 / Layer / 位置索引）
   ↓
3. LLM 读 50 块合并文本，能结 → 停；不能结 →
   LLM 从 50 块中挑 30 个最相关的 UID
   ↓
4. CLI 取这 30 个 UID 的 body + relations 全文（合并）→ LLM
   ↓
5. LLM 读 30 个 body+relations，能结 → 停
   不能结 → LLM 决策：换词重搜（Path A）或沿 relations 扩散（Path B）
   ↓
   每轮 LLM 都决策，最多 max_rounds 轮（默认 5）
```

CLI 职责：搜、取、拼文本。LLM 职责：生成关键词、决策下一步、读正文给结论。
禁止 CLI 生成任何形式的摘要。

### [PRIN-QRY-2] 关键词由 LLM 生成，含中英文——不分 core/expansion

CLI 不做语义判断，不做关键词分级。关键词 100% 由 LLM 从原始查询直接生成，中英文都要：

```
用户发起查询 "A60 隔离区"
   ↓ LLM 直接读取原始查询
   ↓ LLM 生成中英文关键词：
     - "A60"
     - "隔离区" / "fire zone" / "fire compartment" / "fire barrier"
     - "阻燃区" / "防火分区"
   ↓ LLM 把这批词发给 CLI
```

扩展词必须含英文，这是硬性要求。

**Jieba 职责范围**：
- ✅ **ingest 阶段**：构建 词频表时做名词提取
- ❌ **query 阶段**：不参与关键词生成，Agent 从原始查询直接推理 core + expansion

CLI 接收**已分级的关键词列表**，按权重比处理。CLI 内部不再调 LLM。

### [PRIN-QRY-3] CLI 不调 LLM——速度原则

`query` 是高频操作。CLI 必须**零 LLM 调用**——只跑 ripgrep 二进制扫描 + 评分公式 + 词频表读取 + 50 条关系遍历。

理由：
- 用户/Agent 可能每秒调多次 query
- LLM 调用 100ms+ 起步，零 LLM = 毫秒级响应
- 语义相似度需要 LLM，但那是另一个命令（如 `query-semantic`），不是 `query`

### [PRIN-QRY-4] 检索的是内容，不是结构——范围原则

搜索范围 = 全库 `.md` 文件的 body + frontmatter 的关键字段。

不查：
- Phase 1 临时文件（系统 temp 目录，尚未 commit 的节点）
- 〈状态字段〉标记为 inactive 的节点（除非显式 `--include-inactive`）
- DB 的内容字段（DB 只有元数据，没存正文）

理由：Phase 1 临时文件尚未 commit，不是正式节点；inactive 节点已被删除；DB 不存正文（single source of truth 是 .md）。

### [PRIN-QRY-5] 评分公式硬编码——确定性原则

评分公式必须**硬编码**——不允许「运行时调 LLM 调权重」、「运行时让用户选公式」。

理由：
- 确定性 = 可复现 = 可调试
- 用户调参应通过库内 config，不是改公式本身
- LLM 调权重会让「同一个 query 不同次结果不同」——不可接受

### [PRIN-QRY-6] 子命令各司其职——不串味原则

| 命令 | 用途 |
|---|---|
| `query` | 三层介入检索（L1 物理定位 + L2/L3 提示） |
| `query-relation` | 直接管关系表（不走搜索，含 50 条上限校验） |
| `list` | 读 / 建 Node_List（L2 对比表节点） |
| `report` | 读 / 建 Node_Report（L3） |
| `table` | 读 table 内容形态的行（不走搜索） |
| `gallery` | 读 gallery 内容形态的项（不走搜索） |
| `nodes` | DB 节点元数据查询（不走 ripgrep，区别于建 L2 的 `list`） |
| `read` | 单节点全 body（叠加 patches 还原当前视图） |

LLM 重写时**不要**让 `query` 替代以上任何一个——那是串味。每个命令的边界清晰，Agent 才能正确组合。

**`read` 是三层通用的单节点读取入口**：传 UID 即可读 L1 Page / L2 List / L3 Report 任意一层的完整 body（L1 会叠加 patches 还原当前视图）。`read` 关注「按 UID 取单个节点全文」，`list show` / `report show` 关注「按 L2/L3 的呈现语义展开」——前者是通用取文，后者是结构化视图，职责不重叠。

## 三、检索算法（核心机制）

### [PRIN-QRY-7] 物理定位 = ripgrep + 标点延伸切片

CLI 调用 ripgrep 二进制，对全库 `.md` 文件正文进行多关键词并行扫描。

输出：所有命中点的物理坐标（路径、行、列、匹配内容）。

性能：1-2 秒横扫百万文件——利用 `rg` 的二进制 SIMD 加速。

### [PRIN-QRY-8] 弹性切片 = 软上限 + 硬上限（具体数值由实现决定）

针对每个命中点，向前后寻找「语义边界」：

| 优先级 | 标点 |
|---|---|
| 高 | 句号 `。` / 问号 `？` / 叹号 `！` |
| 低 | 逗号 `，` |

规则：
- 向前后探测，软上限内寻找高优先级标点
- 软上限内出现高优先级标点 → 立即截断
- 硬上限内仍无标点 → 强制截断
- 若软上限内无高优先级但有低优先级（逗号）→ 也可截断

理由：解决「断章取义」问题——确保工程逻辑的完整性。

### [PRIN-QRY-9] 邻域合并半径 = 合并距离阈值（紧凑关联物理证据）

同一文档内切片若物理距离 < 紧凑阈值字符数（具体数值由实现决定）（或边界重叠），合并为上下文块。

理由：紧凑关联物理证据——避免相邻证据被切碎。

### [PRIN-QRY-10] 打分公式 = (覆盖分 + 稀有分) × 密度奖励——重平衡算法

| 项 | 计算 | 含义 |
|---|---|---|
| **A 覆盖分** | `核心词权重 × 命中数 + 扩展词权重 × 命中数` | 核心词权重远大于扩展词 |
| **B 稀有分** | `命中关键词的稀有权重之和` |  加成（稀有词远超通用词） |
| **C 密度奖励** | `同一切片块内多词共现 → × 密度奖励系数（> 1）` | 放大「高密度证据区」 |

**核心权重远大于扩展**——确保核心实体（船名、项目号）不被同义词淹没。

### [PRIN-QRY-11]  稀有度查询 = 常量除以（库内频次 + 1）

query 时从 `词频表` 实时调取每个命中关键词的频次，计算权重：

| 词 | 库内频次 | 权重 |
|---|---|---|
| 船名 `LITA` | 1 | 高（频次低 → 权重大） |
| `A60` | 50 | 高（频次低 → 权重大） |
| `项目` | 中频 | 中低（通用词被压低） |
| `系统` | 高频 | 极低（通用词被压低） |

稀有词贡献远超通用词——这让精确查询命中证据链时，分数不被通用词淹没。


### [PRIN-QRY-13] 50 条关系上限约束——不要越界

query 涉及图扩展时，每个节点的出边最多 50 条（无分类的 LRU 链表，见 [PRIN-ARCH-8]）。查询命中一条关系时，把它在链表里**前挪一位**（触碰即升温）。

LLM 重写时**不要扩展这个上限**——50 条是约束关系爆炸的核心手段。如果发现「50 不够」，应该把真正需要长期保留的关联升级为 L2 List，而不是放大上限或加分类。

## 四、禁令

### [BAN-QRY-1] CLI 不调 LLM 做语义匹配

query 路径上**任何** LLM 调用都是禁止的：
- ❌ 用 LLM 做 query 扩展（同义词、概念联想）
- ❌ 用 LLM 做 snippet 重排序
- ❌ 用 LLM 做语义相似度匹配
- ❌ 用 LLM 做关键词分级

这些都是 [PRIN-QRY-2]（关键词分级是 Agent 责任）+ [PRIN-QRY-3]（CLI 不调 LLM）的硬编码。

### [BAN-QRY-2] 不跨 wiki

`query` 命令单 wiki——不允许一条命令搜多个 wiki。

理由：
- 跨 wiki 编排 = Agent 责任
- 单 wiki 内 ripgrep 性能可控；跨 wiki 无法预测
- 跨 wiki 会让 hint 复杂化

### [BAN-QRY-3] 默认不返 raw body

Round 1 只返回 snippet map（path/line/col/match/context），**不**返回完整 body——Agent 通过 `expand` 主动获取 body 是设计意图，不是性能缺陷。

理由：
- 默认返 body 会让响应体膨胀
- snippet 已经足够 Agent 决定是否要读 body
- Agent 二次请求的「round-trip」是设计意图

### [BAN-QRY-4] 不索引 inactive 和 pending

不写索引层、不在搜索时跳过——直接**根本不搜**这些文件。

理由：Phase 1 临时文件尚未 commit（不是正式节点）、inactive 已被删除——它们出现在结果里 = bug。

### [BAN-QRY-5] 不绕过词频表用通用权重

B 稀有分**必须**从 `词频表` 查——不允许「CLI 内部硬编码常见词白名单」、「用 LLM 估算稀有度」等替代方案。

理由：词频表是 ingest 阶段建立的客观频次，任何「主观估算」都会让评分变成非确定性。

## 五、约束

### [CONST-QRY-1] 评分公式（硬编码）

```
score = (覆盖分 + 稀有分) × 密度奖励
A = 核心权重 × 核心命中数 + 扩展权重 × 扩展命中数
B = Σ _weight(keyword) for each hit
C = 密度奖励系数（> 1，多词共现时；否则 = 1）
sort_key = (score desc)
```

LLM 重写时改这个公式必须明确文档化——它是 query 行为的核心契约。

### [CONST-QRY-2] 切片窗口 = 软上限 + 硬上限（软优先寻标点，硬上限兜底）

不可改成「统一 33」或「不切片」等。软/硬双限是设计取舍的产物——保证长难句语义完整。

### [CONST-QRY-3] 邻域合并 = 紧凑阈值字符数（具体数值由实现决定）

不可改成「不合并」或「按段落合并」。

### [CONST-QRY-4] 核心/扩展权重比 = 显著比例（核心远大于扩展）

`核心权重 : 扩展权重 = 显著比例`。可调，但**核心必须远大于扩展**——防同义词噪音污染。

### [CONST-QRY-5] 密度奖励 = 显著大于 1 的系数

可调（如 1.3 或 2.0），但**必须 > 1.0**——奖励多词共现是机制的核心，不能去掉。


### [CONST-QRY-7] top_k 默认小整数（具体由实现决定）

Round 1 返回片段数有上限（小整数量级，默认值由实现在库内 config 给定），避免响应体膨胀。

### [CONST-QRY-8] ripgrep 优先 + Python re fallback

ripgrep 不可用时自动 fallback 到 Python re（慢但能用）。必须 fallback，不能报错说「请装 rg」。

### [CONST-QRY-9] 超时返回部分结果

单次扫描有超时上限(默认值由实现定)。超时返回 partial result + warning，不阻塞 Agent。

### [CONST-QRY-10] 4 键 JSON 返回

返回 `status/data/message/hints`：
- `data.blocks` = snippet 列表（必有）
- `data.uid_batch` = 本轮建议选取的最大 UID 数（默认 30）
- `data.max_rounds` = 剩余轮数（默认 5）
- `data.reflection` = 现有 Entity/List/Report 命中提示
- `hints` 含 Path A / Path B 多轮建议

### [CONST-QRY-11] 不调 LLM

全 CLI 路径无 LLM 调用。

## 六、性能预算

目标是**全程子秒级、最差不过数秒**：全库扫描、切片、关系遍历都应远快于人的感知阈值。具体预算值由实现按硬件与库规模标定。超预算时返回 warning + partial result，绝不无限期阻塞 Agent。

## 七、多轮扩展查询（Agent 决策环）

每轮完成后由 LLM 自己决定下一步，CLI 只提供工具能力。最大轮数由库内配置 `query.max_rounds` 控制（默认 5）。

### [PRIN-QRY-14] 多轮扩展——LLM 决策，CLI 执行，Path A 优先，Path B 兜底

**Round 1 标准流程**：
```
LLM → CLI：中英文关键词
CLI → LLM：前 50 个切片块合并文本
         （每个块带 UID / 标题 / Layer / 位置索引，全文非摘要）
LLM：能结 → 停；不能结 → 从 50 块中挑 30 个 UID 发给 CLI
CLI → LLM：30 个 UID 的 body + relations 全文
LLM：能结 → 停；不能结 → 选 Path A 或 Path B
```

**Path A（换词再搜）**：LLM 发新一批中英文关键词 → CLI 跑 Round N（回到上一步）→ LLM 决策

**Path B（沿关系扩散）**：LLM 从当前 body+relations 中选若干 UID，指定要跟进的下一跳方向 → CLI 取这些节点的 body + relations → LLM 决策

**LLM 每轮决策点**：
- 结 / 不结
- 不结：走 Path A 还是 Path B
- Path B 中：跟哪些 UID 的哪些 relations

**停机条件**：LLM 能给结论 / 达到 max_rounds / 关系链到头 / 50 条关系上限

### [PRIN-QRY-15] 每轮独立计分，禁止摘要

每轮 query 独立评分，不继承前轮分数。CLI 严禁生成任何形式的摘要，所有返回内容均为原文切片或原文全文。

## 八、自检清单（开发时勾选）

**原则**：
- [ ] 多轮 LLM 决策环：LLM 生成关键词、决策每轮下一步，CLI 执行搜索和取 body（[PRIN-QRY-1]）
  - [ ] 关键词由 LLM 生成，含中英文，不分 core/expansion（[PRIN-QRY-2]）
- [ ] CLI 不调 LLM（[PRIN-QRY-3]）
- [ ] 检索内容不检索结构（[PRIN-QRY-4]）
- [ ] 评分公式硬编码（[PRIN-QRY-5]）
- [ ] 子命令各司其职（[PRIN-QRY-6]）
- [ ] 物理定位用 ripgrep（[PRIN-QRY-7]）
- [ ] 弹性切片（软/硬双上限）（[PRIN-QRY-8]）
- [ ] 邻域合并按紧凑阈值（[PRIN-QRY-9]）
- [ ] 打分 (覆盖分 + 稀有分) × 密度奖励，核心权重远大于扩展（[PRIN-QRY-10]）
- [ ] 50 条关系上限不越界（LRU、命中前挪）（[PRIN-QRY-13]）
- [ ] 多轮扩展：Path A 换词优先，Path B 关系扩散兜底，每轮 LLM 决策（[PRIN-QRY-14]）
- [ ] 每轮独立计分，CLI 禁止生成摘要（[PRIN-QRY-15]）

**禁令**：
- [ ] CLI 不调 LLM 语义匹配（[BAN-QRY-1]）
- [ ] 不跨 wiki（[BAN-QRY-2]）
- [ ] 默认不返 raw body（[BAN-QRY-3]）
- [ ] 不索引 inactive/pending（[BAN-QRY-4]）

**约束**：
- [ ] 评分公式硬编码（[CONST-QRY-1]）
- [ ] 切片窗口软/硬双上限（[CONST-QRY-2]）
- [ ] 合并距离阈值（紧凑关联物理证据）（[CONST-QRY-3]）
- [ ] 核心/扩展权重比显著（核心远大于扩展）（[CONST-QRY-4]）
- [ ] 密度奖励显著大于 1（[CONST-QRY-5]）
- [ ] top_k 默认值由实现在库内 config 给定（[CONST-QRY-7]）
- [ ] rg + Python re fallback（[CONST-QRY-8]）
- [ ] 超时返回部分（[CONST-QRY-9]）
- [ ] 4 键 JSON + list/report hint（[CONST-QRY-10]）
- [ ] 不调 LLM（[CONST-QRY-11]）
- [ ] max_rounds 由库内 config `query.max_rounds` 给出，默认 5（[CONST-QRY-12]）

---

**作者注**：query 的灵魂是 [PRIN-QRY-1]（多轮 LLM 决策环）+ [PRIN-QRY-14]（Path A 换词优先，Path B 关系扩散兜底）+ [PRIN-QRY-15]（禁止摘要，全文返回）。新设计的关键改进是**「CLI 只管搜和取，LLM 每轮决策下一步」，Round 1 给 LLM 50 个索引块，LLM 挑 30 个 UID，CLI 取这 30 个 body+relations 全文，继续决策或扩展。最大 5 轮强制停机。

禁止 CLI 生成任何形式的摘要——这是系统级约束，任何摘要都必须由 LLM 自己从原文生成。