# 06 — `query` 设计原则

## 定位

「找知识」的入口。三层介入检索：Page 物理定位 → List 结构对齐 → Report 逻辑提炼。CLI 跑机械搜索；Agent 做关键词分级和决策。

## 原则

### [PRIN-QRY-1] 多轮 LLM 决策环

```
用户发起查询
  → LLM 生成中英文关键词
  → CLI 搜→打分→取前50块→合并
  → LLM 读50块，能结→停；不能结→挑30个UID
  → CLI 取30个body+relations→LLM
  → LLM 决策：换词(Path A)或沿关系扩散(Path B)
  → 每轮最多 max_rounds 轮(默认5)
```

### [PRIN-QRY-2] 关键词由 LLM 生成，含中英文，不分 core/expansion

### [PRIN-QRY-3] CLI 不调 LLM

速度原则：零 LLM = 毫秒级响应。

### [PRIN-QRY-4] 检索的是内容，不是结构

不搜 Phase 1 临时文件，不搜 inactive 节点，不查 DB 内容字段。

### [PRIN-QRY-5] 评分公式硬编码——确定性原则

### [PRIN-QRY-6] 子命令各司其职

| 命令 | 用途 |
|---|---|
| `query` | 三层介入检索 |
| `query-relation` | 直接管关系表 |
| `list` | 读/建 List |
| `report` | 读/建 Report |
| `nodes` | DB 元数据查询 |
| `read` | 单节点全 body |

### [PRIN-QRY-7] ripgrep 是检索底层引擎

### [PRIN-QRY-8] 弹性切片：前后第一个标点，或 50 字符上限

优先句号/问号/叹号；次选逗号；上限强制截断。

### [PRIN-QRY-9] 邻域合并半径

物理距离 < 阈值则合并为上下文块。

### [PRIN-QRY-10] 打分 = 标题×5 + body命中 + 层权重

Entity=2, Report=3, List=1, Page=0。

### [PRIN-QRY-13] 50 条关系上限约束

LRU 链表：建立进队首 / 命中前挪 / 满50弹队尾。

### [PRIN-QRY-14] Path A 换词优先，Path B 关系扩散兜底

### [PRIN-QRY-15] 每轮独立计分，禁止摘要

## 禁令

### [BAN-QRY-1] CLI 不调 LLM 做语义匹配

### [BAN-QRY-2] 不跨 wiki

### [BAN-QRY-3] 默认不返 raw body

### [BAN-QRY-4] 不索引 inactive 和 temp-file nodes

### [BAN-QRY-5] 不人工指定权重

## 约束

### [CONST-QRY-1] 评分公式硬编码

### [CONST-QRY-2] 切片窗口从库级 config 读

### [CONST-QRY-3] 邻域合并从库级 config 读

### [CONST-QRY-8] ripgrep 优先 + Python re fallback

### [CONST-QRY-9] 超时返回部分结果

### [CONST-QRY-10] 4 键 JSON 返回

`data.uid_batch`(默认30) + `data.max_rounds`(默认5) + `data.reflection` + hints。

### [CONST-QRY-11] 不调 LLM

## 性能

目标子秒级。超预算返回 warning + partial result。
