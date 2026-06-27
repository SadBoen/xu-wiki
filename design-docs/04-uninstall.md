# 04 — `uninstall` 设计原则

## 定位

把 install 装进系统的东西原样拆出来。**不动**用户的知识。

## 原则

### [PRIN-UNINST-1] 卸载的是软件，不是知识

管理员辞职不销毁图书馆。**最高原则**。

### [PRIN-UNINST-2] 清理必须彻底——零残留

install 写进系统的东西，uninstall 必须能反向拆除。

### [PRIN-UNINST-3] 安装的反函数——对称性原则

逐行对照 install 步骤，每个 install 动作对应一个 uninstall 动作。

### [PRIN-UNINST-4] Agent 管的资源，让 Agent 自己拆

走 Agent API，不直删 Agent 私有目录。

### [PRIN-UNINST-5] 卸完再查一次——验证原则

### [PRIN-UNINST-6] 默认是 dry-run

## 禁令

### [BAN-UNINST-1] 绝不删除知识库本体

任何情况下都不动知识库。

### [BAN-UNINST-2] 不直删 Agent 管的资源

### [BAN-UNINST-3] 不自动做超出「卸载」的事

### [BAN-UNINST-4] 不动 Page 修订历史

patches 是 frontmatter 内嵌字段，是 wiki 自己状态。

## 约束

### [CONST-UNINST-1] 必须有项目标识才能识别

### [CONST-UNINST-2] 幂等性

### [CONST-UNINST-3] 顺序敏感性

按 install 的反向顺序清理。

### [CONST-UNINST-4] 4 键 JSON

### [CONST-UNINST-5] 不调 LLM
