# 05 — `ingest` 设计原则

## 定位

把外部信息变成 Node_Page（Page）。**两阶段流程**：Phase 1 解析暂存 → Phase 2 提交落库。

## 原则

### [PRIN-ING-1] commit 是唯一写盘入口

ingest-file / ingest-url / ingest-text → 只写暂存；ingest-commit → 唯一创建节点入口。

### [PRIN-ING-2] 两阶段分离

Phase 1 纯解析；Agent 在两阶段之间做语义判断；Phase 2 纯校验+写盘。

### [PRIN-ING-3] 幂等性——重复 ingest 不创建重复 Page

Level-2 dedup（SHA256）在 Phase 1 parser 调用之前检查，不浪费付费 parser 费用。

### [PRIN-ING-3a] SHA256 三路哈希

| 哈希 | 作用域 | 检查时机 |
|---|---|---|
| `source_hash` | 源文件级 | Phase 1，parser 调用前 |
| `content_hash` | 每页独立 | Phase 2 |
| 相册 `source_hashes[]` | 每张图片独立 | 写入前 |

### [PRIN-ING-4] Page 切分粒度 = 300 行正文（按余数）

层级标题优先切；小节过短则向上合并；无边界则硬切 300 行。余数不足 300 也算一页。

### [PRIN-ING-5] 解析器插件式，回退链按格式分组

| 格式 | 主引擎 | 回退 |
|---|---|---|
| PDF/DOCX/PPTX | minerU | markitdown |
| XLSX/XLS | excel | openpyxl→YAML |
| 图片 | vision | ocr |
| CSV | csv | csv.reader→YAML |
| 文本/Markdown | text | — |
| HTML | markitdown | text |

### [PRIN-ING-6] 原始文件必须可追溯

所有被 ingest 的源文件必须留副本到 `raws/`。

### [PRIN-ING-7] 暂存是中间产物

Phase 2 成功 → 立即删除；失败 → 保留供 debug。

### [PRIN-ING-8] 不并发

单文件串行 ingest。

### [PRIN-ING-10] patches 表初值是 commit 的副产物

ingest-commit 成功后写 version=1 的 create 记录。

### [PRIN-ING-11] 意图不明就问，绝不猜

### [PRIN-ING-12] 图片压缩：双 SHA256 + 保 EXIF

压缩前 SHA256 用于查重，压缩后 SHA256 用于完整性校验。

### [PRIN-ING-13] Page body 样式与内容类型匹配

| 内容类型 | body 样式 | CLI |
|---|---|---|
| 表格化（一图一行/一项一行） | markdown 表格 | `ingest-album` |
| 散文 | prose 段落/标题/列表 | `ingest-file` → `ingest-commit` |
| 代码/命令块 | fenced code block | `ingest-commit --native` |

Agent 第一步问用户内容形态。

### [PRIN-ING-14] ingest-album 是单次写入，不走两阶段

一次调用直接产出 1 个 Page + N 个源文件 copy + 1 条 patches v1。

### [PRIN-ING-15] 业务变更追溯走 frontmatter，不走过程层日志

`created_at` / `patches` / 业务字段 = 业务数据。`audit.jsonl` = 过程日志。

### [PRIN-ING-16] ingest 后必须运行 `xu ingest-verify`

6 项检查：nodes 文件存在 / frontmatter 完整（gallery 无 content_hash）/ content_hash 匹配（非 gallery）/ content_type↔body 匹配 / raw 文件存在 / raw_path 镜像。

## 禁令

### [BAN-ING-1] Agent 不直写 Page 文件

### [BAN-ING-2] Phase 2 不调 LLM

### [BAN-ING-3] 跳过 Phase 1 仍要走 commit 流程

`--native` 模式无源文件进 raws/。

### [BAN-ING-4] SHA256 重复不覆盖已有 Page

普通文件返回 `DuplicateSource`；相册重复图片逐张跳过，全部重复才拒绝。

### [BAN-ING-5] 暂存内容路径必须白名单校验

### [BAN-ING-6] 不修改已存在 Page Markdown

## 约束

### [CONST-ING-1] 解析器按内容类型分派

### [CONST-ING-2] SSRF 防护

### [CONST-ING-3] SHA256 两级去重

### [CONST-ING-4] frontmatter 校验

### [CONST-ING-5] 关系处理通过 `query-relation add`

50 条上限，LRU 置换。

### [CONST-ING-6] patches frontmatter 字段

`patches: [{op, delta, created_at}]`，YAML 列表，写入 nodes/pages/ .md 的 frontmatter。

### [CONST-ING-8] 4 键 JSON

### [CONST-ING-9] 不并发
