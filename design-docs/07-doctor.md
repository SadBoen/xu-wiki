# 07 — `doctor` 设计原则

## 定位

Wiki 体检医生：扫描实例、发现一致性问题、可选修复。**默认只读**，绝不擅自改动数据。

## 原则

### [PRIN-DOC-1] 默认只读

`--fix` 启用安全自动修复，不设默认写操作。

### [PRIN-DOC-2] doctor 检查 = 两层节点架构不变量

Page 不可变 / Report 证据链 / 50 条关系上限 / 两层引用一致性。

### [PRIN-DOC-3] --fix 是 ingest 的逆操作

### [PRIN-DOC-4] 子命令专题化

| 子命令 | 检查 |
|---|---|
| `doctor-fields` | frontmatter 必填/类型/格式 |
| `doctor-files` | raws/ 与 nodes/ 文件系统一致性 |
| `doctor-relations` | 50 条上限 + 无重复边/悬挂边 |
| `doctor-l1-immutable` | Page Markdown 未被外部修改 |
| `doctor-report-evidence` | Report 证据链完整 |
| `doctor-node-path-organization` | 根级堆积 + 建议路径 |
| `doctor-all` | 串行上述所有 |

### [PRIN-DOC-5] --fix 必须显式 flag

### [PRIN-DOC-6] --fix 边界

- `doctor-l1-immutable`：检测到外部修改 → 报警，不修复（Page 不可变）
- `doctor-report-evidence`：悬挂引用可 auto-fix；Report 无任何引用 → 只读
- Report 不自动删

## 禁令

### [BAN-DOC-1] 默认不写数据

### [BAN-DOC-2] 不发明「智能修复」

--fix 必须是机械的、对称的、可预测的。

### [BAN-DOC-3] 不静默修改

### [BAN-DOC-4] 不调 LLM

### [BAN-DOC-5] Page 不可变性绝不让 --fix 覆盖

### [BAN-DOC-6] Report 本身不自动删

## 约束

### [CONST-DOC-1] 两层一致性检查

DB 记录 ↔ 文件存在 ↔ raw_path 存在。

### [CONST-DOC-2] Page 不变性检查

patches v1 存在 + SHA256 匹配。

### [CONST-DOC-3] Report 证据链检查

每个 reference UID 存在且 active。

### [CONST-DOC-4] 关系上限检查

每节点 ≤ 50 条 + 无重复/悬挂边。

### [CONST-DOC-5] --fix 必须先列「将做什么」

### [CONST-DOC-6] 4 键 JSON

按 Page/List/Report 分层汇总。

### [CONST-DOC-8] 修复后立即重新检查

### [CONST-DOC-9] 不修 content_type 与 body 不匹配

### [CONST-DOC-10] 不调 LLM
