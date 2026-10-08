# 研究工作区入口

本目录说明 `.travel-research/<trip-id>/` 的生命周期与命令。创建、分配、提交、合并或装配时按当前动作读取一个文件，不需要整目录加载。任务域和波次由 [Agent 编排入口](../orchestration/index.md)定义。

## 文件路由

| 文件 | 何时读取 | 解决的问题 |
| --- | --- | --- |
| [lifecycle.md](lifecycle.md) | 初始化旅行、确认路线、生成 profile | 工作区目录、路线门槛与状态文件 |
| [assignments.md](assignments.md) | 创建或刷新研究任务 | assignment 字段、依赖、guide 与 revision |
| [submission-and-evidence.md](submission-and-evidence.md) | 归档来源、提交结果或快照 | 结果包、来源、证据、动态数据与敏感信息边界 |
| [merge-and-assembly.md](merge-and-assembly.md) | 所有任务结束后 | merge、候选 plan、decisions、assemble、audit 与 render |

## 唯一状态原则

每次旅行只有一个 workspace。Agent 结果、来源、标准快照、证据、合并状态、计划和成品都放在该目录内，不依赖聊天上下文，也不跨旅行复用动态事实。

## 读取顺序

- 新旅行：`lifecycle.md`。
- 路线已确认并拆任务：`assignments.md`。
- 某任务准备提交：`submission-and-evidence.md`。
- 全部任务完成：`merge-and-assembly.md`。
