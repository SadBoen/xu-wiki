# 02 — `create` 设计原则

## 定位

在指定目录从零初始化 wiki 实例：建三件套目录、初始化索引层、写库内配置、在系统注册表登记。**不写**任何节点内容。

## 原则

### [PRIN-CRT-1] create 是 install 之后的第二步

install = 雇图书馆管理员；create = 建一座新图书馆；register = 登记已有的图书馆。

### [PRIN-CRT-2] create 建的是空骨架

三件套目录 + `.xu/config.yaml` + 注册表项。空就是空。

### [PRIN-CRT-3] 两层边界清晰

✅ 动：raws/ nodes/ .xu/ 目录、库内 config、注册表项
❌ 不动：CLI/venv/SKILL（install 领域）
❌ 不动：已存在的 wiki 实例（delete-node 领域）

### [PRIN-CRT-4] 为两层节点预留位置

目录结构和 DB schema 必须为 Page/Entity/List/Report 预留位置。

### [PRIN-CRT-5] 为弹性 Rebuild 预留粒度开关

### [PRIN-CRT-6] 为 Page 不可变建 patches 字段空间

patches 是 frontmatter 内嵌字段，不是独立表。

## 禁令

### [BAN-CRT-1] 绝不覆盖已有内容

目标目录非空 → 拒绝。同路径已是 xu-wiki → warning 告知。

### [BAN-CRT-2] create 不碰 install 管辖的东西

### [BAN-CRT-3] 不自动决定 wiki 名字

`--name` 必须显式给。

### [BAN-CRT-4] 不预填示例数据

## 约束

### [CONST-CRT-1] 必须能被识别为 xu-wiki 项目

### [CONST-CRT-2] 失败原子回滚

临时目录建完整结构，全成功再原子换名。

### [CONST-CRT-3] 幂等性

同名+同路径重复 create → warning 复用。

### [CONST-CRT-4] 名字合法性

字母数字+连字符+下划线；全局唯一。

### [CONST-CRT-5] 路径越界防护

symlink 逃逸 → error。

### [CONST-CRT-6] 库内 config 必含 version + query/relation/rebuild 预留字段

### [CONST-CRT-7] 4 键 JSON

### [CONST-CRT-8] 不调 LLM

## 节点 CRUD 矩阵

| 节点类型 | 文件位置 | 创建命令 |
|---|---|---|
| Page | `nodes/pages/<node_path>/<slug>.md` | `ingest-commit` |
| List | `nodes/lists/<node_path>.md` | `list create` |
| Report | `nodes/reports/<node_path>.md` | `report create` |

## 相关命令边界

| 命令 | 动什么 |
|---|---|
| `install` | 软件本体 |
| `create` | 新 wiki 实例（空骨架+注册表） |
| `register` | 已有目录登记（不创建文件） |
| `wikis` | 列出注册表（只读） |
| `unregister` | 从注册表移除（不动本体） |
