# 03 — `install` 设计原则

## 定位

把工具装到用户机器上：CLI 可用、SKILL 已注册、配置可读写。**不动**用户已有知识。

## 原则

### [PRIN-INST-1] install 装的是「能力」，不是「数据」

配装备，不搬藏书。

### [PRIN-INST-2] 隔离是 install 的存在理由

与系统保持清晰边界，不污染系统。

### [PRIN-INST-3] Agent 管的资源，让 Agent 自己装

必须走 Agent 的 SKILL 安装 API，不直 cp 到 Agent 私有目录。

### [PRIN-INST-4] 幂等性

重复 install 不破坏已有东西。

### [PRIN-INST-5] 失败不留半成品

临时位置建完整结构，全成功再落位；已存在用户数据绝不动。

### [PRIN-INST-6] 步骤顺序由因果决定

后一步依赖前一步，不打乱因果链。

## 禁令

### [BAN-INST-1] 绝不碰用户数据

### [BAN-INST-2] 绝不装到系统级 Python

### [BAN-INST-3] 绝不直写 Agent 资源目录

### [BAN-INST-4] 绝不假设 Python 路径

### [BAN-INST-5] 不自动做超出「安装」的事

## 约束

### [CONST-INST-1] 隔离策略

pipx（推荐，全局隔离 venv）或项目本地 venv（备选）。

### [CONST-INST-2] CLI 是软链不是真文件

### [CONST-INST-3] 项目标识校验

### [CONST-INST-3a] install 不创建 wiki 内部结构

raws/ nodes/ patches 等由 create 负责。

### [CONST-INST-4] 4 键 JSON

### [CONST-INST-5] 不调 LLM

### [CONST-INST-6] 安装文档唯一权威源是 README

SKILL.md 等提到安装只写一句指向 README。
